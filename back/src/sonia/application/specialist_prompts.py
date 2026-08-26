"""Analyst answers projected into the question each specialist receives."""

from __future__ import annotations

from sonia.domain.orchestration import ExecutionPlan, SpecialistPhase

MAX_QUESTION_LENGTH = 1000
_MAX_ANSWER_LENGTH = 240

_PHASE_FOCUS = {
    SpecialistPhase.BILLING: (
        "facturación: documentos faltantes, ciclos incompletos y planta activa sin factura"
    ),
    SpecialistPhase.COLLECTIONS: (
        "cobranzas: mora, priorización de cartera y excepciones de conciliación"
    ),
    SpecialistPhase.BI: (
        "inteligencia de negocio: métricas de ingreso, aging y concentración de riesgo"
    ),
}
_PHASE_PARAMETERS = {
    SpecialistPhase.BILLING: ("billing_materiality",),
    SpecialistPhase.COLLECTIONS: ("overdue_days",),
    SpecialistPhase.BI: ("variance_threshold",),
}
_LABELS = {
    "objective": "Objetivo",
    "scope": "Alcance",
    "billing_materiality": "Materialidad de facturación",
    "overdue_days": "Días de mora",
    "variance_threshold": "Umbral de varianza",
}


def build_question(plan: ExecutionPlan) -> str:
    """Turn the analyst's bound answers into this phase's grounded question."""
    answers = {rule.rule_id: rule.answer for rule in plan.global_rules + plan.specialist_rules}
    lines = [f"Analiza {_PHASE_FOCUS[plan.phase]}."]
    for rule_id in ("objective", "scope", *_PHASE_PARAMETERS[plan.phase]):
        answer = answers.get(rule_id, "").strip()[:_MAX_ANSWER_LENGTH]
        if answer:
            lines.append(f"{_LABELS[rule_id]}: {answer}")
    lines.append(
        "Selecciona las herramientas necesarias y entrega hallazgos cuantificados "
        "con la evidencia que los respalda."
    )
    return "\n".join(lines)[:MAX_QUESTION_LENGTH]
