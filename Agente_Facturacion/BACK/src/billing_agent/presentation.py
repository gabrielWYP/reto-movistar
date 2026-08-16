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
    "PLANT_WITHOUT_BILLING_EVIDENCE": "Cuentas de planta sin evidencia documental de factura en el extracto",
    "DATA_QUALITY_JOIN_GAP": "Cobertura incompleta entre fuentes",
    "DATA_QUALITY_NIF_INCONSISTENT": "Identificador fiscal inconsistente entre fuentes",
}

SEVERITY_LABELS = {"HIGH": "Alta", "MEDIUM": "Media", "LOW": "Baja", "INFO": "Informativo"}
RULE_CATEGORY_LABELS = {
    "DETERMINISTIC": "Validación determinística",
    "HEURISTIC": "Señal heurística",
    "DATA_QUALITY": "Calidad de datos",
}
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
        "rule_category_label": RULE_CATEGORY_LABELS.get(item.get("rule_category", ""), item.get("rule_category", "")),
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


def _money(value: Any) -> str:
    return f"S/ {float(value or 0):,.2f}"


def _invoice_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    return next((item.get("value", {}) for item in payload.get("evidence", []) if item.get("type") == "invoice"), {})


def conversational_narrative(payload: dict[str, Any]) -> str:
    """Grounded no-key explanation. It only formats values the deterministic tool returned."""
    operation = payload.get("operation")
    metrics = payload.get("metrics", {})
    findings = payload.get("findings", [])
    action = next((item.get("reason") for item in payload.get("recommended_actions", []) if item.get("reason")), "Revisar la evidencia disponible antes de escalar el caso.")
    if operation == "billing_health_snapshot":
        return (
            f"Conclusión: el corte revisó {metrics.get('invoice_documents', 0):,} facturas y prioriza excepciones para validación.\n\n"
            f"Por qué: hay {metrics.get('material_credit_note_count', 0):,} ajustes post-emisión materiales, "
            f"{metrics.get('cycle_gap_candidates', 0):,} posibles quiebres documentales y "
            f"{metrics.get('exception_counts', {}).get('ARITHMETIC_MISMATCH', 0):,} diferencias aritméticas.\n\n"
            f"Siguiente acción: {action}\n\nCaveat: los hallazgos son candidatos de revisión; no representan errores financieros confirmados."
        )
    if operation == "invoice_quality_check":
        invoice = _invoice_evidence(payload)
        mismatch = next((item for item in findings if item.get("type") == "ARITHMETIC_MISMATCH"), None)
        material = next((item for item in findings if item.get("type") == "MATERIAL_CREDIT_NOTE"), None)
        conclusion = "Esta factura requiere validación documental." if findings else "No se detectaron excepciones documentales en esta factura."
        lines = [f"Conclusión: {conclusion}"]
        if mismatch:
            observed = mismatch.get("observed_value", {})
            lines.extend([
                "",
                f"Por qué: el total derivado difiere del total registrado por {_money(abs(float(observed.get('difference', 0))))}, superando la tolerancia de S/ 0.01.",
                "",
                f"Evidencia: Neto {_money(metrics.get('net'))}; IGV {_money(metrics.get('tax'))}; total derivado {_money(metrics.get('derived_total'))}; total registrado {_money(metrics.get('reported_total'))}; sistema {invoice.get('system') or 'no informado'}.",
            ])
        if material:
            observed = material.get("observed_value", {})
            lines.extend(["", f"Ajuste post-emisión: la nota de crédito vinculada representa {float(observed.get('ratio', 0)):.1%} del importe original."])
        lines.extend(["", f"Siguiente acción: {action}", "", "Caveat: la validación documental no confirma un error financiero ni su causa."])
        return "\n".join(lines)
    if operation == "customer_billing_check":
        gap = next((item for item in findings if item.get("type") == "BILLING_CYCLE_GAP"), None)
        plant = next((item for item in findings if item.get("type") == "PLANT_WITHOUT_BILLING_EVIDENCE"), None)
        lines = [
            f"Conclusión: se reconstruyó el alcance del cliente con {metrics.get('account_count', 0)} cuentas, {metrics.get('invoice_count', 0)} facturas y {metrics.get('credit_note_count', 0)} notas de crédito.",
        ]
        if gap:
            observed = gap.get("observed_value", {})
            lines.extend(["", f"Se detectó un candidato de quiebre documental: {observed.get('before_period')} con evidencia, {observed.get('missing_period')} sin documento cíclico y {observed.get('after_period')} con evidencia."])
        if plant:
            lines.extend(["", "También existe planta sin evidencia de factura en el extracto; es una señal exploratoria, no una prueba de servicio no facturado."])
        lines.extend(["", f"Siguiente acción: {action}", "", "Caveat: validar cobertura temporal, vigencia contractual y sistema de origen antes de concluir una incidencia."])
        return "\n".join(lines)
    if operation == "billing_cycle_gaps":
        gap = next((item.get("value", {}) for item in payload.get("evidence", []) if item.get("type") == "cycle_gap"), {})
        return (
            f"Conclusión: se identificó un posible quiebre documental para {gap.get('customer', 'el alcance consultado')} / cuenta {gap.get('account', 'no informada')}.\n\n"
            f"Evidencia: {gap.get('before_period')} · factura {gap.get('before_document')}; {gap.get('missing_period')} · sin evidencia de factura cíclica; "
            f"{gap.get('after_period')} · factura {gap.get('after_document')}.\n\n"
            f"Siguiente acción: {action}\n\nCaveat: es un candidato HEURISTIC; no prueba que el periodo debió facturarse ni una fuga de ingresos."
        )
    if operation == "credit_note_review":
        material = next((item for item in findings if item.get("type") == "MATERIAL_CREDIT_NOTE"), None)
        if material:
            observed = material.get("observed_value", {})
            detail = f"La nota de crédito representa {float(observed.get('ratio', 0)):.1%} del importe de la factura y supera el umbral de materialidad aplicado."
        else:
            detail = "Las notas de crédito encontradas están enlazadas documentalmente a sus facturas afectadas."
        return f"Conclusión: se revisaron {metrics.get('credit_note_count', 0)} ajustes post-emisión.\n\nPor qué: {detail}\n\nSiguiente acción: {action}\n\nCaveat: una nota de crédito no confirma un error de facturación y el dataset no contiene su motivo."
    return deterministic_narrative(payload)


def presentation_for(payload: dict[str, Any]) -> dict[str, Any]:
    """Add display-only fields without changing or replacing the public AgentResponse."""
    status = payload.get("status", {})
    evidence = {item.get("id"): item.get("value", {}) for item in payload.get("evidence", [])}
    adjustments = []
    for item in payload.get("findings", []):
        if item.get("type") != "CREDIT_NOTE_PRESENT":
            continue
        refs = item.get("evidence_refs", [])
        invoice_ref = next((ref for ref in refs if str(ref).startswith("invoice:")), None)
        credit_ref = next((ref for ref in refs if str(ref).startswith("credit_note:")), None)
        material = next((candidate for candidate in payload.get("findings", []) if candidate.get("type") == "MATERIAL_CREDIT_NOTE" and credit_ref in candidate.get("evidence_refs", [])), None)
        adjustments.append({
            "invoice": evidence.get(invoice_ref, {}),
            "credit_note": evidence.get(credit_ref, {}),
            "ratio": (material or item).get("observed_value", {}).get("ratio"),
            "severity": (material or item).get("severity", "INFO"),
            "severity_label": severity_label((material or item).get("severity", "INFO")),
            "material": material is not None,
        })
    return {
        "narrative": deterministic_narrative(payload),
        "status_labels": {key: status_label(value) for key, value in status.items()},
        "findings": [present_finding(item) for item in payload.get("findings", [])],
        "alerts": [present_finding(item) for item in payload.get("alerts", [])],
        "adjustments": adjustments,
        "data_quality_message": "El agente distingue entre evidencia disponible e información que requiere validación externa.",
    }
