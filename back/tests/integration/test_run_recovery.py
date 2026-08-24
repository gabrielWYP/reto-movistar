"""Durable runner recovery, idempotency, sequencing, and ownership scenarios."""

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
from sonia.persistence.sqlite import SQLiteIntakeRepository

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/supervisor"


class Probe:
    def __init__(self, phase: SpecialistPhase) -> None:
        self.phase, self.calls = phase, 0

    def __call__(self, at: str) -> dict[str, Any]:
        self.calls += 1
        return {"agent": self.phase, "status": "RESULT_AVAILABLE", "data_quality": {"date": at}}


def _intake(root: Path) -> tuple[SQLiteIntakeRepository, str, str, str]:
    repository = SQLiteIntakeRepository(root)
    files = {path.name: path.read_bytes() for path in FIXTURES.glob("*.csv")}
    dataset = repository.publish_dataset(files, "upload-1")
    answers = {question.question_id: "10" for question in repository.questions(dataset.revision_id)}
    answers |= {"as_of_date": "2026-08-31", "objective": "Find leakage", "scope": "B2B"}
    first = repository.create_ruleset(dataset.revision_id, answers)
    second = repository.create_ruleset(dataset.revision_id, answers | {"scope": "Enterprise"})
    return repository, dataset.revision_id, first.revision_id, second.revision_id


def _runner(
    root: Path, owner: str = "worker-a", judge: Judge | None = None
) -> tuple[RunOrchestrator, dict[SpecialistPhase, Probe]]:
    intake, _, _, _ = _intake(root)
    probes = {phase: Probe(phase) for phase in SpecialistPhase}
    adapters = {phase: SpecialistAdapter(phase, probes[phase]) for phase in SpecialistPhase}
    return RunOrchestrator(
        root / "db/sonia.sqlite3", intake, adapters, judge or Judge(), owner=owner
    ), probes


def test_creation_and_commands_are_revision_bound_and_digest_idempotent(tmp_path: Path) -> None:
    intake, dataset, ruleset, revised = _intake(tmp_path)
    runner, _ = _runner(tmp_path)
    created = runner.create_run(dataset, ruleset, "create-1")
    assert runner.create_run(dataset, ruleset, "create-1") == created
    with pytest.raises(ValueError, match="Conflicting idempotency"):
        runner.create_run(dataset, revised, "create-1")
    foreign = SQLiteIntakeRepository(tmp_path / "foreign")
    files = {path.name: path.read_bytes() for path in FIXTURES.glob("*.csv")}
    files["004_TBL_PAGOS_B2B.csv"] += b"\n"
    other_dataset = foreign.publish_dataset(files, "other").revision_id
    with pytest.raises(ValueError, match="compatible"):
        runner.create_run(other_dataset, ruleset, "create-bad")
    assert runner.create_run(dataset, ruleset, "create-2") == created


def test_fixed_sequence_replays_commits_without_rerunning_specialists(tmp_path: Path) -> None:
    _, dataset, ruleset, _ = _intake(tmp_path)
    runner, probes = _runner(tmp_path)
    run = runner.create_run(dataset, ruleset, "create")
    started = runner.start(run.run_id, "start")
    assert runner.start(run.run_id, "start") == started
    with pytest.raises(ValueError, match="Expected state"):
        runner.advance(run.run_id, RunState.COLLECTIONS_RUNNING, "wrong-order")
    first = runner.advance(run.run_id, RunState.BILLING_RUNNING, "billing-1")
    assert runner.advance(run.run_id, RunState.BILLING_RUNNING, "billing-1") == first
    assert probes[SpecialistPhase.BILLING].calls == 1
    with pytest.raises(ValueError, match="Conflicting idempotency"):
        runner.advance(run.run_id, RunState.BILLING_JUDGING, "billing-1")
    completed = runner.run(run.run_id, "nominal")
    assert completed.state is RunState.COMPLETED
    expected = "billing billing:judge collections collections:judge bi bi:judge".split()
    assert runner.history(run.run_id) == tuple(expected)
    assert [probes[phase].calls for phase in SpecialistPhase] == [1, 1, 1]


def test_restart_resumes_committed_state_and_competing_owner_is_read_only(tmp_path: Path) -> None:
    _, dataset, ruleset, _ = _intake(tmp_path)
    first, probes = _runner(tmp_path)
    run = first.create_run(dataset, ruleset, "create")
    first.start(run.run_id, "start")
    first.advance(run.run_id, RunState.BILLING_RUNNING, "billing")
    args = (first.database, first.intake, first.adapters, Judge())
    second = RunOrchestrator(*args, owner="worker-b")

    with pytest.raises(RuntimeError, match="leased by worker-a"):
        second.advance(run.run_id, RunState.BILLING_JUDGING, "judge")
    first.lease_seconds = -1
    first.advance(run.run_id, RunState.BILLING_JUDGING, "expire")
    reopened = RunOrchestrator(*args, owner="worker-b")
    completed = reopened.run(run.run_id, "recovered")
    assert completed.state is RunState.COMPLETED
    assert probes[SpecialistPhase.BILLING].calls == 1
    assert len(reopened.history(run.run_id)) == 6


def test_retry_is_bounded_and_storage_loss_freezes_recovery(tmp_path: Path) -> None:
    recover = False

    def reject(result: SpecialistResult) -> tuple[tuple[ValidationCheck, ...], ExecutionMetadata]:
        passed = result.phase is not SpecialistPhase.BILLING or recover and result.attempt == 2
        check = ValidationCheck(name="quality", passed=passed, detail="retryable")
        return (check,), ExecutionMetadata(latency_ms=1, token_count=0)

    _, dataset, ruleset, _ = _intake(tmp_path)
    runner, probes = _runner(tmp_path, judge=Judge(reject))
    run = runner.create_run(dataset, ruleset, "create")
    stopped = runner.run(run.run_id, "retry")
    assert stopped.state is RunState.MANUAL_REVIEW
    assert probes[SpecialistPhase.BILLING].calls == 2
    assert probes[SpecialistPhase.COLLECTIONS].calls == 0
    recover, ready = True, tmp_path / "pass"
    _, dataset, ruleset, _ = _intake(ready)
    passing, _ = _runner(ready, judge=Judge(reject))
    run = passing.create_run(dataset, ruleset, "create")
    assert passing.run(run.run_id, "retry-pass").state is RunState.COMPLETED
    runner.database.rename(runner.database.with_suffix(".unavailable"))
    with pytest.raises(RuntimeError, match="storage unavailable"):
        runner.get_run(run.run_id)


@pytest.mark.parametrize(
    ("changed", "expected_state", "expected_steps"),
    [(False, RunState.COMPLETED, 8), (True, RunState.MANUAL_REVIEW, 4)],
)
def test_validation_required_confirms_stable_digest_without_third_attempt(
    tmp_path: Path, changed: bool, expected_state: RunState, expected_steps: int
) -> None:
    intake, dataset, ruleset, _ = _intake(tmp_path)
    probes = {phase: Probe(phase) for phase in SpecialistPhase}

    def billing(at: str) -> dict[str, Any]:
        probe = probes[SpecialistPhase.BILLING]
        probe.calls += 1
        revision = probe.calls if changed else 1
        return {
            "agent": "billing",
            "status": "REQUIERE_VALIDACION",
            "data_quality": {"date": at},
            "revision": revision,
        }

    adapters = {
        SpecialistPhase.BILLING: SpecialistAdapter(SpecialistPhase.BILLING, billing),
        **{
            phase: SpecialistAdapter(phase, probes[phase])
            for phase in (SpecialistPhase.COLLECTIONS, SpecialistPhase.BI)
        },
    }
    runner = RunOrchestrator(
        tmp_path / "db/sonia.sqlite3", intake, adapters, Judge(), owner="confirm"
    )
    run = runner.create_run(dataset, ruleset, "create-confirmation")
    completed = runner.run(run.run_id, "confirmation")

    assert completed.state is expected_state
    assert len(runner.history(run.run_id)) == expected_steps
    assert probes[SpecialistPhase.BILLING].calls == 2
