"""Model-graded Judge rubric and its fail-safe behaviour."""

import json
from hashlib import sha256
from typing import Any

import pytest

from sonia.application.judge import Judge
from sonia.application.judge_evaluator import RUBRIC, OpenCodeJudgeEvaluator
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

_EVIDENCE = EvidenceReference(
    evidence_id="run-1:collections:attempt=1:portfolio_snapshot:result",
    sha256=sha256(b"evidence").hexdigest(),
)


def _result() -> SpecialistResult:
    return SpecialistResult(
        phase=SpecialistPhase.COLLECTIONS,
        attempt=1,
        status="RESULT_AVAILABLE",
        validation_checks=(ValidationCheck(name="read_only", passed=True, detail="snapshot"),),
        findings=(
            Finding(
                code="OVERDUE_CONCENTRATION",
                summary="La mora se concentra en 12 cuentas",
                evidence_refs=(_EVIDENCE.evidence_id,),
            ),
        ),
        evidence_refs=(_EVIDENCE,),
        data_quality=(),
        recommended_actions=("priorizar cobranza",),
        metadata=ExecutionMetadata(latency_ms=5, token_count=0),
        routed_tools=("portfolio_snapshot",),
    )


def _evaluator(text: str, usage: dict[str, int] | None = None) -> OpenCodeJudgeEvaluator:
    captured: list[list[dict[str, Any]]] = []

    def create(messages: list[dict[str, Any]]) -> dict[str, Any]:
        captured.append(messages)
        return {"text": text}

    evaluator = OpenCodeJudgeEvaluator(
        create,
        lambda response: str(response["text"]),
        lambda _: usage or {"total_tokens": 420},
        "deepseek-v4-flash",
    )
    evaluator.captured = captured  # type: ignore[attr-defined]
    return evaluator


def _verdict(passed: bool) -> str:
    return json.dumps(
        {"checks": [{"name": name, "passed": passed, "detail": text} for name, text, _ in RUBRIC]}
    )


def test_model_graded_pass_is_recorded_with_its_telemetry() -> None:
    judge = Judge(_evaluator(_verdict(True)), qualitative_required=True)

    decision = judge.evaluate(_result())

    assert decision.verdict is JudgeVerdict.PASS
    assert decision.mode is JudgeMode.MODEL
    assert decision.metadata.model == "deepseek-v4-flash"
    assert decision.metadata.token_count == 420
    assert {item.name for item in decision.rubric} == {name for name, _, _ in RUBRIC}


def test_rubric_failure_retries_once_then_escalates() -> None:
    judge = Judge(_evaluator(_verdict(False)), qualitative_required=True)

    first = judge.evaluate(_result())
    second = judge.evaluate(_result().model_copy(update={"attempt": 2}))

    assert first.verdict is JudgeVerdict.RETRY
    assert second.verdict is JudgeVerdict.MANUAL_REVIEW


def test_unusable_verdict_escalates_instead_of_passing() -> None:
    """An unparseable or incomplete grade is never a silent approval."""
    judge = Judge(_evaluator("no soy JSON"), qualitative_required=True)

    decision = judge.evaluate(_result().model_copy(update={"attempt": 2}))

    assert decision.verdict is JudgeVerdict.MANUAL_REVIEW
    assert decision.mode is JudgeMode.FALLBACK
    assert "qualitative: unavailable" in decision.corrective_constraints


def test_partial_rubric_is_rejected() -> None:
    evaluator = _evaluator(json.dumps({"checks": [{"name": RUBRIC[0][0], "passed": True}]}))

    with pytest.raises(ValueError, match="omitió"):
        evaluator(_result())


def test_the_grader_receives_the_evidence_identifiers() -> None:
    evaluator = _evaluator(_verdict(True))

    evaluator(_result())

    payload = evaluator.captured[0][1]["content"]  # type: ignore[attr-defined]
    assert _EVIDENCE.evidence_id in payload
    assert "OVERDUE_CONCENTRATION" in payload


def _mixed_verdict(failing: str) -> str:
    return json.dumps(
        {
            "checks": [
                {"name": name, "passed": name != failing, "detail": text}
                for name, text, _ in RUBRIC
            ]
        }
    )


def test_unquantified_findings_are_reported_without_stopping_the_analysis() -> None:
    """Billing observes data quality, which carries no soles; blocking there would
    keep the analyst from ever reaching the phases that do quantify."""
    judge = Judge(_evaluator(_mixed_verdict("quantified")), qualitative_required=True)

    decision = judge.evaluate(_result())

    assert decision.verdict is JudgeVerdict.PASS
    quantified = next(item for item in decision.rubric if item.name == "quantified")
    assert quantified.passed is False and quantified.required is False


def test_an_unsupported_finding_still_blocks() -> None:
    """Evidence integrity is not advisory."""
    judge = Judge(
        _evaluator(_mixed_verdict("evidence_supports_findings")), qualitative_required=True
    )

    assert judge.evaluate(_result()).verdict is JudgeVerdict.RETRY
