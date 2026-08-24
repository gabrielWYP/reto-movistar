"""Judge precedence, retry, fallback, and history tests."""

from sonia.application.judge import Judge
from sonia.domain.orchestration import (
    EvidenceReference,
    ExecutionMetadata,
    Finding,
    JudgeMode,
    JudgeVerdict,
    SpecialistPhase,
    SpecialistResult,
    ValidationCheck,
)


def _result(*, attempt: int = 1, passed: bool = True, linked: bool = True) -> SpecialistResult:
    return SpecialistResult(
        phase=SpecialistPhase.BILLING,
        attempt=attempt,
        status="READY",
        validation_checks=(ValidationCheck(name="quality", passed=passed, detail="checked"),),
        findings=(
            Finding(code="F1", summary="finding", evidence_refs=("ev-1" if linked else "missing",)),
        ),
        evidence_refs=(EvidenceReference(evidence_id="ev-1", sha256="a" * 64),),
        data_quality=(),
        recommended_actions=(),
        metadata=ExecutionMetadata(latency_ms=2, token_count=0),
    )


def test_hard_gates_precede_model_and_complete_lineage_passes() -> None:
    rubric = (ValidationCheck(name="usefulness", passed=True, detail="accepted"),)
    metadata = ExecutionMetadata(
        provider="opencode", model="deepseek-v4-flash", latency_ms=3, token_count=7
    )
    judge = Judge(lambda _: (rubric, metadata))

    passed = judge.evaluate(_result(linked=True))
    broken = Judge(lambda _: (_ for _ in ()).throw(AssertionError("model called"))).evaluate(
        _result(linked=False)
    )

    assert (passed.verdict, passed.mode) == (JudgeVerdict.PASS, JudgeMode.MODEL)
    assert passed.metadata == metadata
    assert broken.verdict is JudgeVerdict.MANUAL_REVIEW
    assert next(check for check in broken.hard_checks if check.name == "lineage").passed is False


def test_retry_is_bounded_and_history_is_append_only() -> None:
    judge = Judge()

    first = judge.evaluate(_result(attempt=1, passed=False))
    second = judge.evaluate(_result(attempt=2, passed=False))

    assert first.verdict is JudgeVerdict.RETRY
    assert first.corrective_constraints == ("quality: checked",)
    assert second.verdict is JudgeVerdict.MANUAL_REVIEW
    assert judge.history == (first, second)


def test_provider_failure_uses_fail_safe_deterministic_fallback() -> None:
    def unavailable(_: SpecialistResult) -> tuple[tuple[ValidationCheck, ...], ExecutionMetadata]:
        raise RuntimeError("provider unavailable")

    complete = Judge(unavailable).evaluate(_result())
    undecidable = Judge(unavailable, qualitative_required=True).evaluate(_result())

    assert (complete.verdict, complete.mode) == (JudgeVerdict.PASS, JudgeMode.FALLBACK)
    assert "provider:unavailable" in complete.evidence_refs
    assert undecidable.verdict is JudgeVerdict.RETRY
