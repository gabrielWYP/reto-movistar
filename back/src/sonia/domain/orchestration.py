"""Immutable contracts and state invariants for autonomous revenue analysis."""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SpecialistPhase(StrEnum):
    """Specialists in their only legal execution order."""

    BILLING = "billing"
    COLLECTIONS = "collections"
    BI = "bi"


class RunState(StrEnum):
    """Durable orchestration states owned by the central runner."""

    CREATED = "CREATED"
    BILLING_RUNNING = "BILLING_RUNNING"
    BILLING_JUDGING = "BILLING_JUDGING"
    COLLECTIONS_RUNNING = "COLLECTIONS_RUNNING"
    COLLECTIONS_JUDGING = "COLLECTIONS_JUDGING"
    BI_RUNNING = "BI_RUNNING"
    BI_JUDGING = "BI_JUDGING"
    COMPLETED = "COMPLETED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class JudgeVerdict(StrEnum):
    """Bounded outcomes available to a Judge gate."""

    PASS = "PASS"
    RETRY = "RETRY"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class JudgeMode(StrEnum):
    """Evidence source used to resolve a Judge decision."""

    MODEL = "model"
    DETERMINISTIC = "deterministic"
    FALLBACK = "fallback"


class ImmutableModel(BaseModel):
    """Shared strict and immutable Pydantic configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class BusinessRule(ImmutableModel):
    """Normalized answer retained in an execution plan."""

    rule_id: str = Field(min_length=1)
    answer: str = Field(min_length=1)


_EXTERNAL_EFFECT_TERMS = tuple(
    "issue invoice|apply payment|contact customer|delete|emitir factura|aplicar pago|"
    "contactar cliente|eliminar".split("|")
)


def external_effect_rule_ids(rules: tuple[BusinessRule, ...]) -> tuple[str, ...]:
    """Return bound rules requesting unsupported external business effects."""
    return tuple(
        rule.rule_id
        for rule in rules
        if any(term in rule.answer.lower() for term in _EXTERNAL_EFFECT_TERMS)
    )


class EvidenceReference(ImmutableModel):
    """Pointer to immutable evidence with its integrity digest."""

    evidence_id: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ValidationCheck(ImmutableModel):
    """Deterministic or qualitative check attached to evidence."""

    name: str = Field(min_length=1)
    passed: bool
    detail: str = Field(min_length=1)
    required: bool = True


class Finding(ImmutableModel):
    """Material specialist conclusion and its evidence lineage."""

    code: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    evidence_refs: tuple[str, ...]


class ExecutionMetadata(ImmutableModel):
    """Provider-neutral telemetry recorded for one attempt."""

    provider: str = "deterministic"
    model: str | None = None
    latency_ms: int = Field(ge=0)
    token_count: int = Field(ge=0)


class ExecutionPlan(ImmutableModel):
    """Revision-bound, read-only instructions for one specialist."""

    run_id: str = Field(min_length=1)
    dataset_revision: str = Field(min_length=1)
    ruleset_revision: str = Field(min_length=1)
    as_of_date: date
    phase: SpecialistPhase
    global_rules: tuple[BusinessRule, ...]
    specialist_rules: tuple[BusinessRule, ...] = ()
    upstream_evidence: tuple[EvidenceReference, ...] = ()


class SpecialistResult(ImmutableModel):
    """Normalized evidence envelope returned by every specialist."""

    phase: SpecialistPhase
    attempt: int = Field(ge=1, le=2)
    status: str = Field(min_length=1)
    validation_checks: tuple[ValidationCheck, ...]
    findings: tuple[Finding, ...]
    evidence_refs: tuple[EvidenceReference, ...]
    data_quality: tuple[ValidationCheck, ...]
    recommended_actions: tuple[str, ...]
    metadata: ExecutionMetadata


class JudgeDecision(ImmutableModel):
    """Append-only verdict emitted for one specialist attempt."""

    phase: SpecialistPhase
    attempt: int = Field(ge=1, le=2)
    verdict: JudgeVerdict
    hard_checks: tuple[ValidationCheck, ...]
    rubric: tuple[ValidationCheck, ...]
    corrective_constraints: tuple[str, ...] = ()
    mode: JudgeMode
    evidence_refs: tuple[str, ...]
    metadata: ExecutionMetadata = Field(
        default_factory=lambda: ExecutionMetadata(latency_ms=0, token_count=0)
    )
    decided_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


_NEXT_STATE = {
    RunState.CREATED: RunState.BILLING_RUNNING,
    RunState.BILLING_RUNNING: RunState.BILLING_JUDGING,
    RunState.BILLING_JUDGING: RunState.COLLECTIONS_RUNNING,
    RunState.COLLECTIONS_RUNNING: RunState.COLLECTIONS_JUDGING,
    RunState.COLLECTIONS_JUDGING: RunState.BI_RUNNING,
    RunState.BI_RUNNING: RunState.BI_JUDGING,
    RunState.BI_JUDGING: RunState.COMPLETED,
}

_JUDGE_PHASE = {
    RunState.BILLING_JUDGING: SpecialistPhase.BILLING,
    RunState.COLLECTIONS_JUDGING: SpecialistPhase.COLLECTIONS,
    RunState.BI_JUDGING: SpecialistPhase.BI,
}


class RunSummary(ImmutableModel):
    """Read-only projection listing past runs for analyst selection."""

    run_id: str
    dataset_revision: str
    ruleset_revision: str
    state: RunState
    created_at: str | None = None


class RevenueAnalysisRun(ImmutableModel):
    """Revision-bound run advanced only through the fixed legal sequence."""

    run_id: str = Field(min_length=1)
    dataset_revision: str = Field(min_length=1)
    ruleset_revision: str = Field(min_length=1)
    state: RunState = RunState.CREATED
    version: int = Field(default=0, ge=0)
    manual_reason: str | None = None

    def transition_to(
        self,
        next_state: RunState,
        decision: JudgeDecision | None = None,
    ) -> RevenueAnalysisRun:
        """Return the next immutable snapshot or reject an illegal transition."""
        if _NEXT_STATE.get(self.state) is not next_state:
            raise ValueError(f"Illegal orchestration transition: {self.state} -> {next_state}")
        required_phase = _JUDGE_PHASE.get(self.state)
        if required_phase is not None and (
            decision is None
            or decision.phase is not required_phase
            or decision.verdict is not JudgeVerdict.PASS
        ):
            raise ValueError(f"A matching PASS verdict is required after {required_phase}")
        if required_phase is None and decision is not None:
            raise ValueError("Judge decision is not accepted for this transition")
        return self.model_copy(update={"state": next_state, "version": self.version + 1})
