"""Qualitative Judge gate backed by the same provider the specialists use."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from time import perf_counter
from typing import Any

from sonia.domain.orchestration import ExecutionMetadata, SpecialistResult, ValidationCheck

logger = logging.getLogger(__name__)

# The third element is whether a failure blocks the run. Integrity gates block;
# quantification is reported to the analyst but cannot stop the analysis, because
# a specialist may legitimately observe something that carries no magnitude.
RUBRIC = (
    ("evidence_supports_findings", "Cada hallazgo se apoya en la evidencia citada.", True),
    ("quantified", "Los hallazgos materiales indican magnitud o alcance medible.", False),
    ("within_scope", "La respuesta se mantiene dentro del alcance y la fecha de corte.", True),
)
_MAX_EVIDENCE = 12
_MAX_ANSWER = 4000

_INSTRUCTION = (
    "Eres el juez de calidad de un análisis de ingresos. Evalúa la salida del especialista "
    "contra la rúbrica. No recalcules cifras: juzga si la evidencia sostiene lo afirmado. "
    'Responde solo JSON: {"checks":[{"name":"<rúbrica>","passed":true|false,'
    '"detail":"<motivo breve>"}]}.'
)


class OpenCodeJudgeEvaluator:
    """Score one specialist attempt against a fixed rubric bound to its evidence."""

    def __init__(
        self,
        create: Callable[[list[dict[str, Any]]], dict[str, Any]],
        output_text: Callable[[dict[str, Any]], str],
        usage: Callable[[dict[str, Any]], dict[str, int]],
        model: str,
        provider: str = "opencode-go",
    ) -> None:
        self._create, self._output_text, self._usage = create, output_text, usage
        self._model, self._provider = model, provider

    def _payload(self, result: SpecialistResult) -> str:
        return json.dumps(
            {
                "phase": result.phase,
                "status": result.status,
                "routed_tools": list(result.routed_tools),
                "findings": [
                    {
                        "code": item.code,
                        "summary": item.summary[:400],
                        "severity": item.severity,
                        "amount": str(item.amount) if item.amount is not None else None,
                        "currency": item.currency,
                        "entity_count": item.entity_count,
                    }
                    for item in result.findings
                ],
                "recommended_actions": [item[:200] for item in result.recommended_actions],
                "evidence_ids": [item.evidence_id for item in result.evidence_refs[:_MAX_EVIDENCE]],
                "rubric": [{"name": name, "criterion": text} for name, text, _ in RUBRIC],
            },
            ensure_ascii=False,
            default=str,
        )[:_MAX_ANSWER]

    def __call__(
        self, result: SpecialistResult
    ) -> tuple[tuple[ValidationCheck, ...], ExecutionMetadata]:
        """Return rubric checks and telemetry, raising so the Judge can fail safe."""
        started = perf_counter()
        conversation = [
            {"role": "system", "content": _INSTRUCTION},
            {"role": "user", "content": self._payload(result)},
        ]
        response = self._create(conversation)
        checks = _parse_checks(self._output_text(response))
        usage = self._usage(response)
        metadata = ExecutionMetadata(
            provider=self._provider,
            model=self._model,
            latency_ms=round((perf_counter() - started) * 1000),
            token_count=max(usage.get("total_tokens", 0), 0),
        )
        logger.info(
            "judge_rubric_evaluated",
            extra={
                "phase": result.phase,
                "attempt": result.attempt,
                "provider": self._provider,
                "model": self._model,
                "failed": sum(1 for item in checks if not item.passed),
                "latency_ms": metadata.latency_ms,
                "tokens": metadata.token_count,
            },
        )
        return checks, metadata


def _parse_checks(text: str) -> tuple[ValidationCheck, ...]:
    """Accept only the closed rubric; anything else is an unusable verdict."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("El juez no devolvió un veredicto JSON.")
    document = json.loads(text[start : end + 1])
    reported = document.get("checks") if isinstance(document, dict) else None
    if not isinstance(reported, list):
        raise ValueError("El veredicto del juez no contiene 'checks'.")
    scored = {
        str(item.get("name")): item
        for item in reported
        if isinstance(item, dict) and item.get("name")
    }
    checks = []
    for name, criterion, required in RUBRIC:
        item = scored.get(name)
        if item is None:
            raise ValueError(f"El juez omitió la rúbrica '{name}'.")
        detail = str(item.get("detail") or criterion)[:200]
        checks.append(
            ValidationCheck(
                name=name,
                passed=bool(item.get("passed")),
                detail=detail,
                required=required,
            )
        )
    return tuple(checks)
