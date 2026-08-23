"""Unit tests for immutable orchestration contracts and state invariants."""

from datetime import date

import pytest
from pydantic import ValidationError

from sonia.domain.orchestration import (
    BusinessRule,
    ExecutionMetadata,
    ExecutionPlan,
    JudgeDecision,
    JudgeMode,
    JudgeVerdict,
    RevenueAnalysisRun,
    RunState,
    SpecialistPhase,
    SpecialistResult,
    ValidationCheck,
)
from sonia.persistence.repository import OrchestrationRepository


def _pass_decision(phase: SpecialistPhase) -> JudgeDecision:
    return JudgeDecision(
        phase=phase,
        attempt=1,
        verdict=JudgeVerdict.PASS,
        hard_checks=(ValidationCheck(name="lineage", passed=True, detail="bound"),),
        rubric=(ValidationCheck(name="quality", passed=True, detail="accepted"),),
        mode=JudgeMode.DETERMINISTIC,
        evidence_refs=(f"evidence:{phase}:1",),
    )


def test_execution_plan_is_immutable_and_revision_bound() -> None:
    plan = ExecutionPlan(
        run_id="run-001",
        dataset_revision="dataset-001",
        ruleset_revision="ruleset-001",
        as_of_date=date(2026, 8, 23),
        phase=SpecialistPhase.BILLING,
        global_rules=(BusinessRule(rule_id="objective", answer="Find leakage"),),
    )

    assert plan.dataset_revision == "dataset-001"
    assert plan.global_rules[0].answer == "Find leakage"
    with pytest.raises(ValidationError, match="frozen"):
        plan.dataset_revision = "dataset-002"


def test_run_follows_the_fixed_specialist_and_judge_sequence() -> None:
    run = RevenueAnalysisRun(
        run_id="run-001",
        dataset_revision="dataset-001",
        ruleset_revision="ruleset-001",
    )

    run = run.transition_to(RunState.BILLING_RUNNING)
    run = run.transition_to(RunState.BILLING_JUDGING)
    run = run.transition_to(RunState.COLLECTIONS_RUNNING, _pass_decision(SpecialistPhase.BILLING))
    run = run.transition_to(RunState.COLLECTIONS_JUDGING)
    run = run.transition_to(RunState.BI_RUNNING, _pass_decision(SpecialistPhase.COLLECTIONS))
    run = run.transition_to(RunState.BI_JUDGING)
    run = run.transition_to(RunState.COMPLETED, _pass_decision(SpecialistPhase.BI))

    assert run.state is RunState.COMPLETED
    assert run.version == 7


def test_run_rejects_collections_before_billing_pass() -> None:
    run = RevenueAnalysisRun(
        run_id="run-002",
        dataset_revision="dataset-001",
        ruleset_revision="ruleset-001",
    )

    with pytest.raises(ValueError, match="Illegal orchestration transition"):
        run.transition_to(RunState.COLLECTIONS_RUNNING)

    judging = run.transition_to(RunState.BILLING_RUNNING).transition_to(RunState.BILLING_JUDGING)
    retry = _pass_decision(SpecialistPhase.BILLING).model_copy(
        update={"verdict": JudgeVerdict.RETRY}
    )
    with pytest.raises(ValueError, match="PASS verdict"):
        judging.transition_to(RunState.COLLECTIONS_RUNNING, retry)


def test_judge_decision_rejects_attempt_outside_bounded_range() -> None:
    with pytest.raises(ValidationError, match="less than or equal to 2"):
        JudgeDecision(
            phase=SpecialistPhase.BILLING,
            attempt=3,
            verdict=JudgeVerdict.PASS,
            hard_checks=(),
            rubric=(),
            mode=JudgeMode.DETERMINISTIC,
            evidence_refs=("evidence:billing:3",),
        )


def test_repository_port_is_structurally_implementable() -> None:
    class MemoryRepository:
        def get_run(self, run_id: str) -> RevenueAnalysisRun | None:
            return None

        def create_run(self, run: RevenueAnalysisRun) -> RevenueAnalysisRun:
            return run

        def save_run(self, run: RevenueAnalysisRun, *, expected_version: int) -> RevenueAnalysisRun:
            return run

        def append_specialist_result(self, run_id: str, result: SpecialistResult) -> None:
            return None

        def append_judge_decision(self, run_id: str, decision: JudgeDecision) -> None:
            return None

    repository: OrchestrationRepository = MemoryRepository()

    assert (
        repository.create_run(
            RevenueAnalysisRun(
                run_id="run-003",
                dataset_revision="dataset-001",
                ruleset_revision="ruleset-001",
            )
        ).state
        is RunState.CREATED
    )
    assert isinstance(repository, OrchestrationRepository)


def test_execution_metadata_rejects_negative_telemetry() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        ExecutionMetadata(latency_ms=-1, token_count=0)
