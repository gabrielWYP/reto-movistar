"""Business-facing labels and view models; this module never recalculates rules."""

from __future__ import annotations

from typing import Any

FINDING_LABELS = {
    "MISSING_CURRENCY": "Moneda no informada",
    "ZERO_VALUE_INVOICE": "Factura con importe cero",
    "ARITHMETIC_MISMATCH": "Diferencia en validación aritmética",
    "CREDIT_NOTE_PRESENT": "Ajuste post-emisión registrado",
    "MATERIAL_CREDIT_NOTE": "Ajuste post-emisión material",
    "BILLING_CYCLE_GAP": "Posible quiebre de ciclo",
    "PLANT_WITHOUT_BILLING_EVIDENCE": "Planta sin evidencia de factura en el extracto",
    "DATA_QUALITY_JOIN_GAP": "Cobertura incompleta entre fuentes",
    "DATA_QUALITY_NIF_INCONSISTENT": "Identificador fiscal inconsistente entre fuentes",
}

SEVERITY_LABELS = {"HIGH": "Alta", "MEDIUM": "Media", "LOW": "Baja", "INFO": "Informativo"}
STATUS_LABELS = {
    "REQUIERE_VALIDACION": "Requiere validación",
    "SIN_EXCEPCIONES_DOCUMENTALES": "Sin excepciones documentales detectadas",
    "SIN_CANDIDATOS": "Sin candidatos en el alcance",
    "SIN_NOTAS_DE_CREDITO_EN_EL_ALCANCE": "Sin notas de crédito en el alcance",
    "SIN_EXCEPCIONES_RELEVANTES": "Sin excepciones relevantes",
}


def finding_label(code: str) -> str:
    return FINDING_LABELS.get(code, code.replace("_", " ").title())


def severity_label(code: str) -> str:
    return SEVERITY_LABELS.get(code, code.title())


def status_label(code: str) -> str:
    return STATUS_LABELS.get(code, code.replace("_", " ").title())


def present_finding(item: dict[str, Any]) -> dict[str, Any]:
    return {
        **item,
        "business_label": finding_label(item.get("type", "")),
        "severity_label": severity_label(item.get("severity", "INFO")),
        "technical_code": item.get("type", ""),
    }


def deterministic_narrative(payload: dict[str, Any]) -> str:
    metrics = payload.get("metrics", {})
    operation = payload.get("operation")
    if operation == "billing_health_snapshot":
        invoices = metrics.get("invoice_documents", 0)
        exceptions = metrics.get("exception_counts", {})
        material = metrics.get("material_credit_note_count", 0)
        gaps = metrics.get("cycle_gap_candidates", 0)
        return (
            f"Se analizaron {invoices:,} facturas. Se identificaron candidatos de revisión, principalmente "
            f"{material:,} ajustes post-emisión materiales y {gaps:,} posibles quiebres de facturación cíclica. "
            "Los hallazgos no representan errores financieros confirmados."
            if exceptions or gaps else f"Se analizaron {invoices:,} facturas sin excepciones relevantes en el corte."
        )
    if operation == "invoice_quality_check":
        return "La validación muestra los campos documentales y el cálculo derivado. Contrasta el sistema de origen antes de concluir una incidencia."
    if operation == "billing_cycle_gaps":
        return "Cada caso muestra evidencia antes y después del periodo sin documento. Es una ausencia documental para validar, no una fuga confirmada."
    if operation == "credit_note_review":
        return "Las notas de crédito son ajustes post-emisión. La materialidad prioriza revisión, pero no confirma un error de facturación."
    return "La vista reúne evidencia de cliente, cuentas, planta, documentos y ajustes para orientar la siguiente validación."


def presentation_for(payload: dict[str, Any]) -> dict[str, Any]:
    """Add display-only fields without changing or replacing the public AgentResponse."""
    status = payload.get("status", {})
    return {
        "narrative": deterministic_narrative(payload),
        "status_labels": {key: status_label(value) for key, value in status.items()},
        "findings": [present_finding(item) for item in payload.get("findings", [])],
        "alerts": [present_finding(item) for item in payload.get("alerts", [])],
        "data_quality_message": "El agente distingue entre evidencia disponible e información que requiere validación externa.",
    }
