"""Deterministic-first Judge with bounded retry and fail-safe fallback."""

from __future__ import annotations

from collections.abc import Callable

from sonia.domain.orchestration import (
    ExecutionMetadata,
    JudgeDecision,
    JudgeMode,
    JudgeVerdict,
    SpecialistResult,
    ValidationCheck,
)

QualitativeEvaluator = Callable[
    [SpecialistResult], tuple[tuple[ValidationCheck, ...], ExecutionMetadata]
]
_NON_RETRYABLE = {"lineage", "schema", "input_binding"}
_CONFIRMATION_STATUSES = {"REQUIERE_VALIDACION"}


def _output_digest(result: SpecialistResult | None) -> str | None:
    if result is None:
        return None
    marker = f":{result.phase}:attempt={result.attempt}:"
    return next(
        (
            item.sha256
            for item in result.evidence_refs
            if marker in item.evidence_id and item.evidence_id.endswith(":result")
        ),
        None,
    )


class Judge:
    """Resolve authoritative verdicts and retain append-only in-process history."""

    def __init__(
        self,
        evaluator: QualitativeEvaluator | None = None,
        *,
        qualitative_required: bool = False,
    ) -> None:
        self._evaluator = evaluator
        self._qualitative_required = qualitative_required
        self._history: list[JudgeDecision] = []

    @property
    def history(self) -> tuple[JudgeDecision, ...]:
        """Return decisions in evaluation order without exposing mutation."""
        return tuple(self._history)

    def evaluate(
        self, result: SpecialistResult, *, previous: SpecialistResult | None = None
    ) -> JudgeDecision:
        """Evaluate hard gates before any optional qualitative provider."""
        evidence_ids = {item.evidence_id for item in result.evidence_refs}
        linked = all(
            finding.evidence_refs and set(finding.evidence_refs) <= evidence_ids
            for finding in result.findings
        )
        lineage = ValidationCheck(
            name="lineage",
            passed=linked,
            detail="all findings linked" if linked else "missing evidence",
        )
        confirmation: tuple[ValidationCheck, ...] = ()
        if result.status in _CONFIRMATION_STATUSES:
            stable = (
                result.attempt == 2
                and previous is not None
                and previous.phase is result.phase
                and previous.attempt == 1
                and previous.status == result.status
                and _output_digest(previous) is not None
                and _output_digest(previous) == _output_digest(result)
            )
            confirmation = (
                ValidationCheck(
                    name="status_confirmation",
                    passed=stable,
                    detail=(
                        "stable normalized result digest"
                        if stable
                        else "deterministic result confirmation required"
                    ),
                ),
            )
        hard_checks = result.validation_checks + confirmation + (lineage,)
        failed = tuple(check for check in hard_checks if check.required and not check.passed)
        rubric: tuple[ValidationCheck, ...] = ()
        mode = JudgeMode.DETERMINISTIC
        metadata = ExecutionMetadata(latency_ms=0, token_count=0)
        unavailable = False
        if not failed and self._evaluator:
            try:
                rubric, metadata = self._evaluator(result)
                mode = JudgeMode.MODEL
            except Exception:
                mode, unavailable = JudgeMode.FALLBACK, True
        elif not failed and self._qualitative_required:
            mode, unavailable = JudgeMode.FALLBACK, True

        rubric_failed = tuple(check for check in rubric if check.required and not check.passed)
        undecidable = unavailable and self._qualitative_required
        if failed:
            retryable = not any(check.name in _NON_RETRYABLE for check in failed)
            verdict = (
                JudgeVerdict.RETRY
                if retryable and result.attempt == 1
                else JudgeVerdict.MANUAL_REVIEW
            )
        elif rubric_failed or undecidable:
            verdict = JudgeVerdict.RETRY if result.attempt == 1 else JudgeVerdict.MANUAL_REVIEW
        else:
            verdict = JudgeVerdict.PASS
        constraints = tuple(f"{check.name}: {check.detail}" for check in failed + rubric_failed)
        if undecidable:
            constraints += ("qualitative: unavailable",)
        references = tuple(item.evidence_id for item in result.evidence_refs)
        if unavailable:
            references += ("provider:unavailable",)
        decision = JudgeDecision(
            phase=result.phase,
            attempt=result.attempt,
            verdict=verdict,
            hard_checks=hard_checks,
            rubric=rubric,
            corrective_constraints=constraints,
            mode=mode,
            evidence_refs=references,
            metadata=metadata,
        )
        self._history.append(decision)
        return decision
