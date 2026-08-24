"""Immutable completed and manual-review package scenarios."""

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from sonia.application.judge import Judge
from sonia.application.orchestrator import RunOrchestrator
from sonia.application.specialist_adapters import SpecialistAdapter
from sonia.domain.orchestration import (
    ExecutionMetadata,
    RunState,
    SpecialistPhase,
    SpecialistResult,
    ValidationCheck,
)
from sonia.persistence.backup import PackageLineageError, StorageHardener
from sonia.persistence.sqlite import SQLiteIntakeRepository

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/supervisor"


class Probe:
    """Return non-trivial normalized content for one specialist."""

    def __init__(self, phase: SpecialistPhase) -> None:
        self.phase = phase

    def __call__(self, at: str) -> dict[str, Any]:
        return {
            "agent": self.phase,
            "status": "RESULT_AVAILABLE",
            "findings": [{"type": "LIMIT", "message": f"{self.phase} finding"}],
            "data_quality": {"limitations": [f"bounded at {at}"]},
            "recommended_actions": [{"action": f"review {self.phase}"}],
        }


def _runner(
    root: Path, judge: Judge | None = None, *, auto_package: bool = True
) -> tuple[RunOrchestrator, str]:
    intake = SQLiteIntakeRepository(root)
    files = {path.name: path.read_bytes() for path in FIXTURES.glob("*.csv")}
    dataset = intake.publish_dataset(files, "upload")
    answers = {item.question_id: "10" for item in intake.questions(dataset.revision_id)}
    answers |= {"as_of_date": "2026-08-31", "objective": "Find leakage", "scope": "B2B"}
    ruleset = intake.create_ruleset(dataset.revision_id, answers)
    adapters = {phase: SpecialistAdapter(phase, Probe(phase)) for phase in SpecialistPhase}
    runner = RunOrchestrator(
        root / "db/sonia.sqlite3",
        intake,
        adapters,
        judge or Judge(),
        owner="worker",
        auto_package=auto_package,
    )
    run = runner.create_run(dataset.revision_id, ruleset.revision_id, "create")
    return runner, run.run_id


def test_completed_package_is_immutable_and_cross_phase_traceable(tmp_path: Path) -> None:
    runner, run_id = _runner(tmp_path)
    assert runner.run(run_id, "run").state is RunState.COMPLETED
    hardener = StorageHardener(tmp_path)
    assert (tmp_path / "packages" / f"{run_id}.json").is_file()
    assert hardener.verify().ready is True

    package = hardener.assemble_package(run_id)
    document = json.loads(package.path.read_text())
    payload, history = document["payload"], document["payload"]["history"]
    specialists = [step["content"] for step in history if step["kind"] == "specialist"]

    assert package.path.parent.name == "packages" and len(package.sha256) == 64
    assert payload["review_ready"] is True and payload["state"] == "COMPLETED"
    assert payload["dataset_revision"] and payload["ruleset_revision"]
    assert [step["phase"] for step in history] == ["billing"] * 2 + ["collections"] * 2 + ["bi"] * 2
    assert all(
        item["data_quality"] and item["recommended_actions"] and item["metadata"]
        for item in specialists
    )
    billing_refs = {item["evidence_id"] for item in specialists[0]["evidence_refs"]}
    bi_refs = {item["evidence_id"] for item in specialists[-1]["evidence_refs"]}
    assert billing_refs < bi_refs
    assert runner.assemble_review_package(run_id, hardener) == package
    raw = package.path.read_bytes()
    backup = tmp_path.parent / f"{tmp_path.name}-backup"
    restored_root = tmp_path.parent / f"{tmp_path.name}-restore"
    restored = hardener.restore(hardener.backup(backup).path.parent, restored_root)
    assert (restored.root / "packages" / package.path.name).read_bytes() == raw
    recovered = restored.assemble_package(run_id)
    assert recovered.sha256 == package.sha256 and recovered.path.read_bytes() == raw
    package.path.write_bytes(b"{}")
    readiness = hardener.verify()
    assert readiness.ready is False and "package" in " ".join(readiness.issues)
    with pytest.raises(RuntimeError, match="package"):
        runner.assemble_review_package(run_id, hardener)
    assert runner.get_run(run_id).state is RunState.COMPLETED


@pytest.mark.parametrize("defect", ["output", "verdict", "evidence"])
def test_incomplete_completed_lineage_forces_manual_review(tmp_path: Path, defect: str) -> None:
    runner, run_id = _runner(tmp_path, auto_package=False)
    assert runner.run(run_id, "run").state is RunState.COMPLETED
    with sqlite3.connect(runner.database) as connection:
        if defect in {"output", "verdict"}:
            kind = "specialist" if defect == "output" else "judge"
            connection.execute(
                "DELETE FROM run_steps WHERE run_id = ? AND phase = 'bi' AND kind = ?",
                (run_id, kind),
            )
        else:
            row = connection.execute(
                "SELECT seq, payload FROM run_steps WHERE run_id = ? "
                "AND phase = 'bi' AND kind = 'specialist'",
                (run_id,),
            ).fetchone()
            content = json.loads(row[1])
            content["evidence_refs"] = []
            connection.execute(
                "UPDATE run_steps SET payload = ? WHERE seq = ?", (json.dumps(content), row[0])
            )

    with pytest.raises(PackageLineageError, match="bi") as error:
        runner.assemble_review_package(run_id, StorageHardener(tmp_path))
    assert defect in str(error.value)
    escalated = runner.get_run(run_id)
    assert escalated.state is RunState.MANUAL_REVIEW
    with pytest.raises(PackageLineageError, match="bi"):
        runner.assemble_review_package(run_id, StorageHardener(tmp_path))
    assert runner.get_run(run_id) == escalated
    reopened = RunOrchestrator(
        runner.database, runner.intake, runner.adapters, Judge(), owner="reopened"
    )
    reason = reopened.get_run(run_id).manual_reason
    assert reason == error.value.missing
    assert reopened.run(run_id, "reopen").state is RunState.MANUAL_REVIEW
    assert reopened.get_run(run_id).manual_reason == reason
    assert not tuple((tmp_path / "packages").glob("*.json"))


def test_manual_review_package_retains_retry_and_blocker(tmp_path: Path) -> None:
    def reject(result: SpecialistResult) -> tuple[tuple[ValidationCheck, ...], ExecutionMetadata]:
        check = ValidationCheck(name="quality", passed=False, detail="unresolved balance")
        return (check,), ExecutionMetadata(latency_ms=result.attempt, token_count=0)

    runner, run_id = _runner(tmp_path, Judge(reject))
    assert runner.run(run_id, "run").state is RunState.MANUAL_REVIEW
    hardener = StorageHardener(tmp_path)
    assert (tmp_path / "packages" / f"{run_id}.json").is_file()
    assert hardener.verify().ready is True

    package = hardener.assemble_package(run_id)
    payload = json.loads(package.path.read_text())["payload"]

    assert payload["review_ready"] is True and payload["state"] == "MANUAL_REVIEW"
    assert payload["blocking_verdict"] == "MANUAL_REVIEW"
    assert payload["blocked_phase"] == "billing" and payload["prevented_phase"] == "collections"
    assert [step["attempt"] for step in payload["history"]] == [1, 1, 2, 2]
    assert "quality" in payload["unresolved_checks"]
