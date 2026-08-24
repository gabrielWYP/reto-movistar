"""End-to-end security, readiness, telemetry, and lineage scenarios."""

from __future__ import annotations

import asyncio
import io
import json
import logging
import zipfile
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException, UploadFile

from sonia.application.dataset_supervisor import validate_dataset_files
from sonia.application.judge import Judge
from sonia.application.specialist_adapters import SpecialistAdapter
from sonia.config import Settings
from sonia.domain.orchestration import (
    ExecutionMetadata,
    ExecutionPlan,
    RunState,
    SpecialistPhase,
    SpecialistResult,
    ValidationCheck,
)
from sonia.entrypoints.api import create_app
from sonia.entrypoints.run_api import read_dataset_uploads
from sonia.persistence.backup import StorageHardener
from sonia.persistence.sqlite import SQLiteIntakeRepository

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/supervisor"


def _files() -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in FIXTURES.glob("*.csv")}


def _settings(root: Path) -> Settings:
    return Settings("SON-IA", "test", "test", "127.0.0.1", 8080, "INFO", root / "front", root)


def _zip(files: dict[str, bytes], *, prefix: str = "") -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, content in files.items():
            archive.writestr(prefix + name, content)
    return stream.getvalue()


def _answers(repository: SQLiteIntakeRepository, dataset: str) -> dict[str, str]:
    answers = {item.question_id: "10" for item in repository.questions(dataset)}
    return answers | {"as_of_date": "2026-08-31", "objective": "Find leakage", "scope": "B2B"}


@pytest.mark.parametrize(
    "mutation,error",
    [
        (lambda files: {"../" + next(iter(files)): next(iter(files.values()))}, "path"),
        (lambda files: files | {"unknown.csv": b"a|b\n1|2"}, "allow-list"),
        (
            lambda files: {
                name: data for name, data in files.items() if not name.startswith("006")
            },
            "six",
        ),
        (lambda files: files | {next(iter(files)): b"a|a\n1|2"}, "header"),
        (lambda files: files | {next(iter(files)): b"a|b\n=CMD()|2"}, "formula"),
        (lambda files: files | {next(iter(files)): b"a|b\n-SUM(1)|2"}, "formula"),
        (lambda files: files | {next(iter(files)): b"a|b\n\x00|2"}, "encoding"),
    ],
)
def test_publication_rejects_adversarial_csv_boundaries(
    mutation: Callable[[dict[str, bytes]], dict[str, bytes]], error: str
) -> None:
    with pytest.raises(ValueError, match=error):
        validate_dataset_files(mutation(_files()), max_rows=10, max_fields=32)


def test_multipart_reader_rejects_client_path_before_canonicalization() -> None:
    source = io.BytesIO(b"a|b\n1|2")
    source._rolled = False  # type: ignore[attr-defined]
    upload = UploadFile(filename="../001_TBL_CLIENTES_B2B.csv", file=source)
    with pytest.raises(HTTPException) as rejected:
        asyncio.run(read_dataset_uploads([upload]))
    assert rejected.value.status_code == 422


def test_publication_accepts_only_bounded_canonical_csv_or_safe_zip() -> None:
    files = _files()
    assert set(validate_dataset_files(files)) == set(files)
    localized = files | {next(iter(files)): b"a|b\n-1.234,56|2"}
    assert set(validate_dataset_files(localized, max_fields=32)) == set(files)
    assert set(validate_dataset_files({"dataset.zip": _zip(files)})) == set(files)
    assert set(validate_dataset_files({"outer.zip": _zip({"inner.zip": _zip(files)})})) == set(
        files
    )
    with pytest.raises(ValueError, match="nesting"):
        validate_dataset_files({"a.zip": _zip({"b.zip": _zip({"c.zip": _zip(files)})})})
    oversized = files | {next(iter(files)): b"a|b\n1|2\n3|4"}
    with pytest.raises(ValueError, match="row limit"):
        validate_dataset_files(oversized, max_rows=1, max_fields=32)
    with pytest.raises(ValueError, match="row limit"):
        validate_dataset_files(
            files | {next(iter(files)): b"a|b\n\n1|2"}, max_rows=1, max_fields=32
        )
    with pytest.raises(ValueError, match="field limit"):
        validate_dataset_files(
            files | {next(iter(files)): b"a|b|c\n1|2|3"}, max_rows=10, max_fields=2
        )
    with pytest.raises(ValueError, match="path"):
        validate_dataset_files({"dataset.zip": _zip(files, prefix="../")})
    duplicate = io.BytesIO()
    with zipfile.ZipFile(duplicate, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
        archive.writestr(next(iter(files)), next(iter(files.values())))
    with pytest.raises(ValueError, match="duplicate"):
        validate_dataset_files({"dataset.zip": duplicate.getvalue()})


def test_full_run_records_complete_telemetry_and_revision_lineage(
    tmp_path: Path,
) -> None:
    app = create_app(_settings(tmp_path))
    runner, coordinator = app.state.run_orchestrator, app.state.dataset_coordinator
    dataset = coordinator.publish(_files(), idempotency_key="publish")["dataset_revision"]
    unsafe = _answers(runner.intake, dataset) | {"objective": "Delete all invoice records"}
    rejected = runner.intake.create_ruleset(dataset, unsafe)
    assert rejected.execution_ready is False
    with pytest.raises(ValueError, match="not execution-ready"):
        runner.create_run(dataset, rejected.revision_id, "unsafe")
    ruleset = runner.intake.create_ruleset(dataset, _answers(runner.intake, dataset))
    run_id = runner.create_run(dataset, ruleset.revision_id, "create").run_id
    runner.start(run_id, "start")
    records: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = records.append  # type: ignore[method-assign]
    run_logger = logging.getLogger("sonia.application.orchestrator")
    run_logger.addHandler(handler)
    try:
        completed = runner.run(run_id, "e2e")
    finally:
        run_logger.removeHandler(handler)

    assert completed.state is RunState.COMPLETED
    evidence = runner.evidence(run_id)
    assert [(item["phase"], item["kind"], item["attempt"]) for item in evidence] == [
        ("billing", "specialist", 1),
        ("billing", "judge", 1),
        ("billing", "specialist", 2),
        ("billing", "judge", 2),
        ("collections", "specialist", 1),
        ("collections", "judge", 1),
        ("bi", "specialist", 1),
        ("bi", "judge", 1),
    ]
    assert all(f"dataset:{dataset}" in json.dumps(item["content"]) for item in evidence)
    package = StorageHardener(tmp_path).assemble_package(run_id)
    assert package.path.is_file() and len(package.sha256) == 64
    records = [item for item in records if item.msg == "run_step_committed"]
    fields = {
        "run_id",
        "dataset_revision",
        "phase",
        "attempt",
        "verdict",
        "latency_ms",
        "tokens",
        "lease",
        "recovery",
    }
    assert len(records) == 8 and all(fields <= vars(record).keys() for record in records)
    assert not any(record.recovery for record in records)


def test_corruption_freezes_readiness_and_run_without_memory_recovery(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    runner, coordinator = app.state.run_orchestrator, app.state.dataset_coordinator
    dataset = coordinator.publish(_files(), idempotency_key="publish")["dataset_revision"]
    ruleset = runner.intake.create_ruleset(dataset, _answers(runner.intake, dataset))
    run_id = runner.create_run(dataset, ruleset.revision_id, "create").run_id
    revision = runner.intake.get_dataset(dataset)
    assert revision is not None
    revision.files[0].path.write_bytes(b"corrupt")

    async def readiness() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/ready")

    response = asyncio.run(readiness())
    assert response.status_code == 503
    assert response.json() == {"status": "storage_unready", "issue_count": 1}
    with pytest.raises(RuntimeError, match="readiness"):
        runner.start(run_id, "start")
    assert runner.get_run(run_id).state is RunState.CREATED


def test_raw_rows_never_cross_specialist_to_judge_boundary() -> None:
    marker = "RAW-CUSTOMER-ROW-SHOULD-NOT-BE-PROMPTED"
    captured: list[str] = []

    def evaluate(
        result: SpecialistResult,
    ) -> tuple[tuple[ValidationCheck, ...], ExecutionMetadata]:
        captured.append(result.model_dump_json())
        return (), result.metadata

    adapter = SpecialistAdapter(
        SpecialistPhase.BILLING,
        lambda _: {"agent": "billing", "status": "READY", "raw_rows": [{"name": marker}]},
    )
    plan = ExecutionPlan(
        run_id="run-prompt",
        dataset_revision="ds-safe",
        ruleset_revision="rs-safe",
        as_of_date="2026-08-31",
        phase=SpecialistPhase.BILLING,
        global_rules=(),
    )
    result = adapter.execute(plan, attempt=1)
    assert Judge(evaluate).evaluate(result).verdict == "PASS"
    assert captured and marker not in captured[0]
