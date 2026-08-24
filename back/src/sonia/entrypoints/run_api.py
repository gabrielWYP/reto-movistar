"""Runs/review API; ingress must replace ``X-Forwarded-User`` with the SSO claim."""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, File, Header, HTTPException, UploadFile
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from sonia.application.dataset_supervisor import (
    MAX_DATASET_BYTES,
    MAX_DATASET_FILES,
    SupervisorDatasetCoordinator,
)
from sonia.application.orchestrator import RunOrchestrator
from sonia.persistence.backup import StorageHardener

_LOG = logging.getLogger(__name__)
_IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._@+-]{0,127}")
_REVIEW_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS review_decisions("
    "idempotency_key TEXT PRIMARY KEY,request_digest TEXT NOT NULL,"
    "package_revision TEXT UNIQUE NOT NULL,payload TEXT NOT NULL)"
)


def _non_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("Value cannot be whitespace-only")
    return value.strip()


IdempotencyKey = Annotated[
    str, Header(alias="Idempotency-Key", min_length=1, max_length=128), AfterValidator(_non_blank)
]


class _Immutable(BaseModel):
    """Strict immutable API model."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class RunCreate(_Immutable):
    """Immutable revisions selected for one run."""

    dataset_revision: str = Field(min_length=1)
    ruleset_revision: str = Field(min_length=1)


class RulesetCreate(_Immutable):
    """Answers bound to one immutable Supervisor dataset."""

    dataset_revision: str = Field(min_length=1)
    answers: dict[str, str]


class ReviewRequest(_Immutable):
    """One decision against an exact immutable package revision."""

    package_revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    outcome: Literal["accept", "reject"]
    reason: str | None = Field(default=None, min_length=1, max_length=500)
    annotation: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def require_rejection_reason(self) -> ReviewRequest:
        """Reject packages only with an auditable bounded reason."""
        if self.reason is not None and not self.reason.strip():
            raise ValueError("Reason cannot be whitespace-only")
        if self.annotation is not None and not self.annotation.strip():
            raise ValueError("Annotation cannot be whitespace-only")
        if self.outcome == "reject" and self.reason is None:
            raise ValueError("A reason is required when rejecting a package")
        return self


class ReviewDecision(_Immutable):
    """Append-only analyst decision persisted independently of run evidence."""

    decision_id: str
    analyst_id: str
    identity_source: Literal["trusted_proxy_sso"] = "trusted_proxy_sso"
    identity_header: Literal["X-Forwarded-User"] = "X-Forwarded-User"
    package_revision: str
    package_digest: str
    outcome: Literal["accept", "reject"]
    reason: str | None
    annotation: str | None
    decided_at: datetime
    idempotency_key: str
    request_digest: str


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


class _ReviewStore:
    """Transactionally append decisions to the runner's SQLite database."""

    def __init__(self, runner: RunOrchestrator) -> None:
        self.database = runner.database
        with sqlite3.connect(self.database) as connection:
            connection.execute(_REVIEW_SCHEMA)

    def record(
        self, request: ReviewRequest, analyst_id: str, key: str, package_digest: str
    ) -> ReviewDecision:
        content = {
            "analyst_id": analyst_id,
            "package_revision": request.package_revision,
            "outcome": request.outcome,
            "reason": request.reason,
            "annotation": request.annotation,
        }
        digest = sha256(_canonical(content)).hexdigest()
        with sqlite3.connect(self.database) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT request_digest,payload FROM review_decisions WHERE idempotency_key=?",
                (key,),
            ).fetchone()
            if row:
                if row[0] != digest:
                    raise ValueError("Conflicting review idempotency key content")
                return ReviewDecision.model_validate_json(row[1])
            if connection.execute(
                "SELECT 1 FROM review_decisions WHERE package_revision=?",
                (request.package_revision,),
            ).fetchone():
                raise ValueError("Package already has an analyst decision")
            decision = ReviewDecision(
                decision_id=f"review_{digest[:20]}",
                analyst_id=analyst_id,
                package_revision=request.package_revision,
                package_digest=package_digest,
                outcome=request.outcome,
                reason=request.reason,
                annotation=request.annotation,
                decided_at=datetime.now(UTC),
                idempotency_key=key,
                request_digest=digest,
            )
            connection.execute(
                "INSERT INTO review_decisions VALUES(?,?,?,?)",
                (key, digest, request.package_revision, decision.model_dump_json()),
            )
        _LOG.info(
            "analyst_review_committed",
            extra={
                "run_package": request.package_revision,
                "analyst_id": analyst_id,
                "outcome": request.outcome,
            },
        )
        return decision

    def get(self, package_revision: str) -> ReviewDecision:
        """Read the sole committed decision for an immutable package."""
        with sqlite3.connect(self.database) as connection:
            row = connection.execute(
                "SELECT payload FROM review_decisions WHERE package_revision=?",
                (package_revision,),
            ).fetchone()
        if row is None:
            raise KeyError(package_revision)
        return ReviewDecision.model_validate_json(row[0])


def _analyst(value: str | None) -> str:
    if value is None or not _IDENTITY.fullmatch(value.strip()):
        raise HTTPException(status_code=401, detail="Trusted analyst identity is required")
    return value.strip()


def _package(storage: StorageHardener, run_id: str) -> dict[str, object]:
    try:
        artifact = storage.assemble_package(run_id)
        return {
            "package_revision": artifact.sha256,
            "envelope": json.loads(artifact.path.read_bytes()),
        }
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Run not found") from error
    except RuntimeError as error:
        status = 409 if "not package-ready" in str(error) else 503
        raise HTTPException(status_code=status, detail=str(error)) from error


async def read_dataset_uploads(
    files: Annotated[list[UploadFile], File(...)],
) -> dict[str, bytes]:
    """Read one bounded data-only Supervisor publication."""
    if not files or len(files) > MAX_DATASET_FILES:
        raise HTTPException(
            status_code=422, detail="Carga un ZIP o las seis fuentes CSV oficiales."
        )
    payload: dict[str, bytes] = {}
    request_bytes = 0
    for upload in files:
        raw_name = upload.filename or ""
        candidate = Path(raw_name.replace("\\", "/"))
        if candidate.is_absolute() or ".." in candidate.parts or len(candidate.parts) != 1:
            raise HTTPException(status_code=422, detail="La ruta del archivo no está permitida.")
        filename = candidate.name
        if not filename or Path(filename).suffix.lower() not in {".csv", ".zip"}:
            raise HTTPException(status_code=422, detail="Solo se aceptan archivos CSV o ZIP.")
        if filename in payload:
            raise HTTPException(status_code=422, detail=f"Archivo duplicado: {filename}.")
        chunks: list[bytes] = []
        while chunk := await upload.read(1024 * 1024):
            request_bytes += len(chunk)
            if request_bytes > MAX_DATASET_BYTES:
                raise HTTPException(status_code=413, detail="La carga excede 25 MiB.")
            chunks.append(chunk)
        payload[filename] = b"".join(chunks)
    return payload


def create_run_router(
    runner: RunOrchestrator,
    storage: StorageHardener,
    datasets: SupervisorDatasetCoordinator,
) -> APIRouter:
    """Create revision-bound run and immutable final-review routes."""
    router = APIRouter(prefix="/api/supervisor", tags=["revenue-runs"])
    reviews = _ReviewStore(runner)

    @router.post("/datasets", status_code=201, tags=["supervisor-intake"])
    async def publish_dataset(
        files: Annotated[list[UploadFile], File(...)], key: IdempotencyKey
    ) -> object:
        try:
            return datasets.publish(await read_dataset_uploads(files), idempotency_key=key)
        except ValueError as error:
            status = 409 if "Conflicting idempotency" in str(error) else 422
            raise HTTPException(status_code=status, detail=str(error)) from error

    @router.get("/datasets/{revision}/questions", tags=["supervisor-intake"])
    def questions(revision: str) -> object:
        try:
            return runner.intake.questions(revision)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Dataset revision not found") from error

    @router.post("/rulesets", status_code=201, tags=["supervisor-intake"])
    def create_ruleset(request: RulesetCreate) -> object:
        try:
            return runner.intake.create_ruleset(request.dataset_revision, request.answers)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Dataset revision not found") from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/runs", status_code=201)
    def create(request: RunCreate, key: IdempotencyKey) -> object:
        try:
            return runner.create_run(request.dataset_revision, request.ruleset_revision, key)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.post("/runs/{run_id}/start", status_code=202)
    def start(run_id: str, background: BackgroundTasks, key: IdempotencyKey) -> object:
        try:
            started = runner.start(run_id, key)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Run not found") from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        background.add_task(runner.run, run_id, f"background:{key}")
        return started

    @router.get("/runs/{run_id}")
    def poll(run_id: str) -> object:
        try:
            return runner.get_run(run_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Run not found") from error

    @router.get("/runs/{run_id}/history")
    def history(run_id: str) -> dict[str, object]:
        try:
            runner.get_run(run_id)
            return {"run_id": run_id, "history": runner.history(run_id)}
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Run not found") from error

    @router.get("/runs/{run_id}/evidence")
    def evidence(run_id: str) -> dict[str, object]:
        try:
            return {"run_id": run_id, "evidence": runner.evidence(run_id)}
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Run not found") from error

    @router.get("/runs/{run_id}/package")
    def package(run_id: str) -> dict[str, object]:
        return _package(storage, run_id)

    @router.get("/runs/{run_id}/review")
    def review_decision(run_id: str) -> ReviewDecision:
        package_revision = _package(storage, run_id)["package_revision"]
        try:
            return reviews.get(str(package_revision))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Review decision not found") from error

    @router.post("/runs/{run_id}/review")
    def review(
        run_id: str,
        request: ReviewRequest,
        key: IdempotencyKey,
        forwarded_user: Annotated[str | None, Header(alias="X-Forwarded-User")] = None,
    ) -> ReviewDecision:
        analyst_id = _analyst(forwarded_user)
        current = _package(storage, run_id)
        if current["package_revision"] != request.package_revision:
            raise HTTPException(status_code=409, detail="Package revision does not match")
        envelope = current["envelope"]
        if not isinstance(envelope, dict) or not isinstance(envelope.get("sha256"), str):
            raise HTTPException(status_code=503, detail="Invalid package envelope")
        try:
            return reviews.record(request, analyst_id, key, envelope["sha256"])
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    return router
