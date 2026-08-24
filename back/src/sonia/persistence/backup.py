"""Checksummed storage readiness, backup/restore, and quarantine."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import tempfile
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from sonia.domain.orchestration import (
    JudgeDecision,
    JudgeVerdict,
    RevenueAnalysisRun,
    RunState,
    SpecialistPhase,
    SpecialistResult,
)
from sonia.persistence.sqlite import DatasetRevision

_LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class Artifact:
    """Path and digest for one immutable manifest or package."""

    path: Path
    sha256: str


@dataclass(frozen=True)
class Readiness:
    """Fail-closed storage verification outcome."""

    ready: bool
    issues: tuple[str, ...]
    quarantined: tuple[Path, ...]


class PackageLineageError(RuntimeError):
    """Identify the required lineage that prevents a review-ready package."""

    def __init__(self, missing: str) -> None:
        self.missing = missing
        super().__init__(f"Missing package lineage: {missing}")


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        digest = sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}-")
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _envelope(payload: object) -> bytes:
    return _canonical({"payload": payload, "sha256": sha256(_canonical(payload)).hexdigest()})


def _read_envelope(path: Path, label: str) -> dict[str, Any]:
    try:
        document = json.loads(path.read_bytes())
        payload = document["payload"]
        if not isinstance(payload, dict):
            raise ValueError
        if document["sha256"] != sha256(_canonical(payload)).hexdigest():
            raise ValueError
        return payload
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Invalid or corrupt {label}") from error


def _package_history(
    rows: list[tuple[str, str, int, str]], run: RevenueAnalysisRun
) -> tuple[list[dict[str, Any]], JudgeDecision]:
    phases, phase_index, expected_attempt = tuple(SpecialistPhase), 0, 1
    pending: SpecialistResult | None = None
    approved: set[str] = set()
    history: list[dict[str, Any]] = []
    terminal: JudgeDecision | None = None
    for index, (kind, phase_text, attempt, raw) in enumerate(rows):
        phase = phases[min(phase_index, len(phases) - 1)]
        if kind == "specialist":
            if pending is not None:
                raise PackageLineageError(f"{phase} verdict")
            try:
                result = SpecialistResult.model_validate_json(raw)
            except ValueError as error:
                raise PackageLineageError(f"{phase} output") from error
            if result.phase is not phase or phase_text != phase or result.attempt != attempt:
                raise PackageLineageError(f"{phase} output")
            evidence = {item.evidence_id for item in result.evidence_refs}
            required = {f"dataset:{run.dataset_revision}", f"ruleset:{run.ruleset_revision}"}
            output = f"{run.run_id}:{phase}:attempt={attempt}:"
            findings = all(set(item.evidence_refs) <= evidence for item in result.findings)
            if not required <= evidence or not any(item.startswith(output) for item in evidence):
                raise PackageLineageError(f"{phase} evidence")
            if not approved <= evidence or not findings:
                raise PackageLineageError(f"{phase} cross-phase evidence")
            if attempt != expected_attempt:
                raise PackageLineageError(f"{phase} attempt")
            pending = result
        elif kind == "judge":
            if pending is None:
                raise PackageLineageError(f"{phase_text} output")
            try:
                decision = JudgeDecision.model_validate_json(raw)
            except ValueError as error:
                raise PackageLineageError(f"{phase} verdict") from error
            evidence = {item.evidence_id for item in pending.evidence_refs}
            if decision.phase is not phase or phase_text != phase or decision.attempt != attempt:
                raise PackageLineageError(f"{phase} verdict")
            if not evidence <= set(decision.evidence_refs):
                raise PackageLineageError(f"{phase} judge evidence")
            if decision.verdict is JudgeVerdict.RETRY and attempt == 1:
                expected_attempt = 2
            elif decision.verdict is JudgeVerdict.PASS:
                approved, expected_attempt, phase_index = evidence, 1, phase_index + 1
            elif decision.verdict is JudgeVerdict.MANUAL_REVIEW and index == len(rows) - 1:
                terminal = decision
            else:
                raise PackageLineageError(f"{phase} verdict sequence")
            pending = None
            terminal = decision
        else:
            raise PackageLineageError(f"{phase_text} output kind")
        history.append(
            {
                "kind": kind,
                "phase": phase_text,
                "attempt": attempt,
                "sha256": sha256(raw.encode()).hexdigest(),
                "content": json.loads(raw),
            }
        )
    if pending is not None:
        raise PackageLineageError(f"{pending.phase} verdict")
    if terminal is None:
        raise PackageLineageError("terminal verdict")
    if run.state is RunState.COMPLETED and (
        phase_index != len(phases) or terminal.verdict is not JudgeVerdict.PASS
    ):
        raise PackageLineageError("completed phase verdicts")
    if run.state is RunState.MANUAL_REVIEW and terminal.verdict is not JudgeVerdict.MANUAL_REVIEW:
        raise PackageLineageError("manual-review blocking verdict")
    return history, terminal


class StorageHardener:
    """Harden one single-process SQLite and immutable-file storage root."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.database = self.root / "db/sonia.sqlite3"

    @staticmethod
    def _safe(root: Path, value: str | Path) -> Path:
        candidate = Path(value)
        candidate = candidate if candidate.is_absolute() else root / candidate
        resolved = candidate.resolve()
        if not resolved.is_relative_to(root) or candidate.is_symlink():
            raise ValueError(f"Path escapes storage root: {value}")
        return resolved

    def _datasets(self) -> tuple[DatasetRevision, ...]:
        if not self.database.is_file() or self.database.is_symlink():
            raise RuntimeError("Durable storage unavailable")
        try:
            with sqlite3.connect(self.database) as connection:
                rows = connection.execute("SELECT payload FROM datasets").fetchall()
            return tuple(DatasetRevision.model_validate_json(row[0]) for row in rows)
        except (sqlite3.DatabaseError, ValueError) as error:
            raise RuntimeError("Dataset catalogue is corrupt") from error

    def _destination(self, value: Path) -> Path:
        candidate = value.resolve()
        if value.absolute().is_relative_to(self.root) or candidate.is_relative_to(self.root):
            raise ValueError("Destination cannot be inside live storage")
        return candidate

    def verify(self) -> Readiness:
        """Verify referenced files and quarantine only proven dataset orphans."""
        issues: list[str] = []
        quarantined: list[Path] = []
        try:
            datasets = self._datasets()
        except RuntimeError as error:
            datasets = ()
            issues.append(str(error))
        referenced: set[Path] = set()
        for dataset in datasets:
            for item in dataset.files:
                try:
                    path = self._safe(self.root, item.path)
                    referenced.add(path)
                    if not path.is_file() or _digest(path) != item.sha256:
                        issues.append(f"Invalid dataset reference: {item.source}")
                except (OSError, ValueError) as error:
                    issues.append(str(error))
        dataset_root = self.root / "datasets"
        if datasets and dataset_root.exists():
            for path in (
                item for item in dataset_root.rglob("*") if item.is_file() or item.is_symlink()
            ):
                if path.is_symlink() or path.resolve() not in referenced:
                    target = self.root / "quarantine" / f"{time.time_ns()}-{path.name}"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(path, target)
                    audit = {
                        "original": str(path.relative_to(self.root)),
                        "quarantined": target.name,
                    }
                    _atomic(target.with_suffix(".audit.json"), _canonical(audit))
                    quarantined.append(target)
        package_root = self.root / "packages"
        if package_root.exists():
            for package in package_root.glob("*.json"):
                try:
                    if package.is_symlink():
                        raise RuntimeError
                    _read_envelope(package, "package")
                except RuntimeError:
                    issues.append(f"Invalid package envelope: {package.name}")
        outcome = Readiness(not issues, tuple(issues), tuple(quarantined))
        _LOG.info(
            "storage_readiness",
            extra={"ready": outcome.ready, "issues": len(issues), "quarantined": len(quarantined)},
        )
        return outcome

    def require_ready(self) -> None:
        """Freeze advancement whenever durable lineage is not verifiable."""
        outcome = self.verify()
        if not outcome.ready:
            raise RuntimeError("Storage readiness frozen: " + "; ".join(outcome.issues))

    def backup(self, destination: Path) -> Artifact:
        """Create a SQLite-consistent backup plus verified immutable files and manifest."""
        self.require_ready()
        destination = self._destination(destination)
        if destination.exists():
            raise FileExistsError(destination)
        destination.mkdir(parents=True)
        target_database = destination / "db/sonia.sqlite3"
        target_database.parent.mkdir(parents=True)
        with (
            sqlite3.connect(self.database) as source_db,
            sqlite3.connect(target_database) as target_db,
        ):
            source_db.backup(target_db)
        with target_database.open("rb") as stream:
            os.fsync(stream.fileno())
        files: list[dict[str, str]] = []
        for dataset in self._datasets():
            for item in dataset.files:
                source = self._safe(self.root, item.path)
                relative = source.relative_to(self.root)
                target = self._safe(destination, relative)
                _atomic(target, source.read_bytes())
                if _digest(target) != item.sha256:
                    raise RuntimeError("Backup dataset verification failed")
                files.append({"path": str(relative), "sha256": item.sha256})
        package_root = self.root / "packages"
        for source in package_root.glob("*.json") if package_root.exists() else ():
            relative = source.relative_to(self.root)
            target = self._safe(destination, relative)
            checksum = _digest(source)
            _atomic(target, source.read_bytes())
            if _digest(target) != checksum:
                raise RuntimeError("Backup package verification failed")
            files.append({"path": str(relative), "sha256": checksum})
        payload = {
            "version": 1,
            "database": {"path": "db/sonia.sqlite3", "sha256": _digest(target_database)},
            "files": files,
        }
        manifest = destination / "manifest.json"
        _atomic(manifest, _envelope(payload))
        _LOG.info("storage_backup", extra={"files": len(files), "outcome": "verified"})
        return Artifact(manifest, _digest(manifest))

    def restore(self, backup: Path, destination: Path) -> StorageHardener:
        """Validate and restore a backup into a fresh root without overwriting live storage."""
        backup, destination = backup.resolve(), self._destination(destination)
        if destination == self.root or destination.exists():
            raise FileExistsError(destination)
        payload = _read_envelope(self._safe(backup, "manifest.json"), "manifest")
        entries = [payload["database"], *payload["files"]]
        for entry in entries:
            source = self._safe(backup, entry["path"])
            if not source.is_file() or _digest(source) != entry["sha256"]:
                raise RuntimeError("Backup lineage verification failed")
            _atomic(self._safe(destination, entry["path"]), source.read_bytes())
        database = destination / "db/sonia.sqlite3"
        with sqlite3.connect(database) as connection:
            for (raw,) in connection.execute("SELECT payload FROM datasets").fetchall():
                dataset = DatasetRevision.model_validate_json(raw)
                files = tuple(
                    item.model_copy(
                        update={"path": destination / Path(item.path).relative_to(self.root)}
                    )
                    for item in dataset.files
                )
                restored = dataset.model_copy(update={"files": files})
                connection.execute(
                    "UPDATE datasets SET payload = ? WHERE revision_id = ?",
                    (restored.model_dump_json(), restored.revision_id),
                )
        hardener = StorageHardener(destination)
        hardener.require_ready()
        _LOG.info("storage_restore", extra={"files": len(entries), "outcome": "verified"})
        return hardener

    def assemble_package(self, run_id: str) -> Artifact:
        """Write one immutable checksummed completed or manual-review package."""
        self.require_ready()
        with sqlite3.connect(self.database) as connection:
            run_row = connection.execute(
                "SELECT payload FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            rows = connection.execute(
                "SELECT kind, phase, attempt, payload FROM run_steps WHERE run_id = ? ORDER BY seq",
                (run_id,),
            ).fetchall()
        if run_row is None:
            raise KeyError(run_id)
        run = RevenueAnalysisRun.model_validate_json(run_row[0])
        if run.state not in (RunState.COMPLETED, RunState.MANUAL_REVIEW):
            raise RuntimeError("Run is not package-ready")
        history, terminal = _package_history(rows, run)
        payload: dict[str, Any] = {
            "run_id": run.run_id,
            "state": run.state,
            "review_ready": True,
            "dataset_revision": run.dataset_revision,
            "ruleset_revision": run.ruleset_revision,
            "history": history,
        }
        if run.state is RunState.MANUAL_REVIEW:
            next_phase = {"billing": "collections", "collections": "bi", "bi": "completion"}
            failed = terminal.hard_checks + terminal.rubric
            payload |= {
                "blocking_verdict": terminal.verdict,
                "blocked_phase": terminal.phase,
                "prevented_phase": next_phase[terminal.phase],
                "unresolved_checks": [item.name for item in failed if not item.passed],
            }
        target = self._safe(self.root, Path("packages") / f"{run_id}.json")
        content = _envelope(payload)
        if target.exists():
            if _read_envelope(target, "package") != payload:
                raise RuntimeError("Immutable package content changed")
        else:
            _atomic(target, content)
        _LOG.info(
            "storage_package",
            extra={"run_id": run_id, "state": run.state, "steps": len(history)},
        )
        return Artifact(target, _digest(target))
