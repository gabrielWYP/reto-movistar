"""Business-facing work queue built from existing deterministic Billing rules.

This module is intentionally additive: it does not change the five agent tools or
any shared Supervisor contract. It only groups already-computed Billing signals
into cases an analyst can prioritize and drill into.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal
from typing import Any

from .model import ZERO
from .rules import invoice_findings
from .service import BillingService


_ACTIONABLE_INVOICE_TYPES = {
    "MISSING_CURRENCY",
    "ZERO_VALUE_INVOICE",
    "ARITHMETIC_MISMATCH",
    "MATERIAL_CREDIT_NOTE",
}

_PRIORITY_RANK = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
_RISK_RANK = {"INGRESO": 0, "AJUSTE_POST_EMISION": 1, "CALIDAD_DOCUMENTAL": 2}


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _priority(findings: list[dict[str, Any]]) -> str:
    severities = {item.get("severity") for item in findings}
    if "HIGH" in severities:
        return "HIGH"
    if "MEDIUM" in severities:
        return "MEDIUM"
    return "LOW"


def _invoice_case(invoice: Any, findings: list[dict[str, Any]]) -> dict[str, Any]:
    codes = [item["type"] for item in findings]
    material = next((item for item in findings if item["type"] == "MATERIAL_CREDIT_NOTE"), None)
    arithmetic = next((item for item in findings if item["type"] == "ARITHMETIC_MISMATCH"), None)

    if material:
        risk_category = "AJUSTE_POST_EMISION"
        title = "Nota de crédito material"
        observed = material.get("observed_value") or {}
        ratio = _float(observed.get("ratio"))
        note_total = _float(observed.get("credit_note_total"))
        invoice_total = _float(observed.get("invoice_total"))
        evidence_summary = (
            f"Ajuste por nota de crédito de {ratio:.1%} sobre la factura. "
            f"Monto NC: {note_total:.2f}; factura: {invoice_total:.2f}."
            if ratio is not None and note_total is not None and invoice_total is not None
            else "La nota de crédito supera el umbral de materialidad definido por Billing."
        )
        amount = note_total
        amount_basis = "Monto documentado de nota de crédito material"
        recommended_action = "Validar motivo, autorización y necesidad de refacturación o compensación."
    elif arithmetic:
        risk_category = "CALIDAD_DOCUMENTAL"
        title = "Diferencia aritmética en factura"
        observed = arithmetic.get("observed_value") or {}
        derived = _float(observed.get("derived_total"))
        reported = _float(observed.get("reported_total"))
        difference = _float(observed.get("difference"))
        evidence_summary = (
            f"Neto + IGV = {derived:.2f}; total registrado = {reported:.2f}; "
            f"diferencia = {difference:.2f}."
            if derived is not None and reported is not None and difference is not None
            else "Los componentes de la factura no cuadran con el total registrado."
        )
        amount = abs(difference) if difference is not None else None
        amount_basis = "Diferencia aritmética observada"
        recommended_action = "Contrastar el cálculo con el sistema de origen antes de corregir o refacturar."
    elif "ZERO_VALUE_INVOICE" in codes:
        risk_category = "CALIDAD_DOCUMENTAL"
        title = "Factura con importe cero"
        evidence_summary = "El total registrado de la factura es 0; el dataset no contiene la causa."
        amount = None
        amount_basis = None
        recommended_action = "Validar si corresponde a una emisión informativa, ajuste o anulación operativa."
    else:
        risk_category = "CALIDAD_DOCUMENTAL"
        title = "Factura sin moneda informada"
        evidence_summary = "El campo MONEDA está vacío y el importe no puede interpretarse de forma segura."
        amount = None
        amount_basis = None
        recommended_action = "Confirmar la moneda en el documento o sistema de origen."

    if len(codes) > 1 and not (set(codes) <= {"MATERIAL_CREDIT_NOTE", "CREDIT_NOTE_PRESENT"}):
        title = f"{title} + {len(codes) - 1} observación adicional"

    return {
        "case_id": f"invoice:{invoice.document}",
        "case_type": "INVOICE",
        "priority": _priority(findings),
        "risk_category": risk_category,
        "customer": invoice.customer,
        "account": invoice.account,
        "invoice_id": invoice.document,
        "period": invoice.issued_at.strftime("%Y-%m") if invoice.issued_at else None,
        "title": title,
        "finding_codes": codes,
        "confidence": "HEURISTIC" if material else "DETERMINISTIC",
        "amount": amount,
        "currency": invoice.currency or None,
        "amount_basis": amount_basis,
        "evidence_summary": evidence_summary,
        "recommended_action": recommended_action,
        "drilldown": "invoice",
    }


def build_work_queue(service: BillingService, as_of_date: str | None = None) -> dict[str, Any]:
    """Return a prioritized, human-readable queue without changing tool outputs.

    A case is either an emitted invoice, a detected missing billing period, or an
    active plant account with no invoice evidence in the selected cut. Invoice
    cases are grouped so one invoice appears once even when several rules fire.
    """
    as_of = service._as_of(as_of_date)
    invoices = service._invoices_as_of(as_of)
    gaps = service._cycle_gaps(as_of)
    plant_without_invoice = service._active_plant_without_invoice(as_of)

    cases: list[dict[str, Any]] = []
    for invoice in invoices:
        notes = service._notes_for_invoice(invoice.document, as_of)
        actionable = [
            item for item in invoice_findings(invoice, notes, f"invoice:{invoice.document}")
            if item["type"] in _ACTIONABLE_INVOICE_TYPES
        ]
        if actionable:
            cases.append(_invoice_case(invoice, actionable))

    for gap in gaps:
        plant_rows = gap["plant_rows"]
        cases.append({
            "case_id": f"gap:{gap['customer']}:{gap['account']}:{gap['missing_period']}",
            "case_type": "CYCLE_GAP",
            "priority": "MEDIUM",
            "risk_category": "INGRESO",
            "customer": gap["customer"],
            "account": gap["account"],
            "invoice_id": None,
            "period": gap["missing_period"],
            "title": "Posible periodo sin facturar",
            "finding_codes": ["BILLING_CYCLE_GAP"],
            "confidence": "HEURISTIC",
            "amount": None,
            "currency": None,
            "amount_basis": None,
            "evidence_summary": (
                f"Hay factura cíclica en {gap['before_period']} ({gap['before_invoice'].document}) y "
                f"{gap['after_period']} ({gap['after_invoice'].document}), pero no se encontró documento "
                f"en {gap['missing_period']}. Planta enlazada: {'sí' if plant_rows else 'no'}."
            ),
            "recommended_action": "Validar vigencia, suspensión, cobertura del extracto y sistema de emisión del periodo faltante.",
            "drilldown": "gaps",
        })

    for customer, account, rows in plant_without_invoice:
        active_types = sorted({"fija" if row.get("__source_table") == "fixed_plant" else "móvil" for row in rows})
        cases.append({
            "case_id": f"plant:{customer}:{account}",
            "case_type": "PLANT_WITHOUT_INVOICE",
            "priority": "MEDIUM",
            "risk_category": "INGRESO",
            "customer": customer,
            "account": account,
            "invoice_id": None,
            "period": None,
            "title": "Planta activa sin evidencia de factura",
            "finding_codes": ["PLANT_WITHOUT_BILLING_EVIDENCE"],
            "confidence": "HEURISTIC",
            "amount": None,
            "currency": None,
            "amount_basis": None,
            "evidence_summary": (
                f"La cuenta tiene {len(rows)} registro(s) de planta activa ({', '.join(active_types)}) "
                "y no se encontró factura asociada hasta el corte."
            ),
            "recommended_action": "Confirmar vigencia contractual y cobertura del dataset antes de escalar como no facturación.",
            "drilldown": "customer",
        })

    cases.sort(key=lambda item: (
        _PRIORITY_RANK[item["priority"]],
        _RISK_RANK[item["risk_category"]],
        -(item["amount"] or 0),
        item["customer"],
        item["account"],
        item["invoice_id"] or "",
    ))

    by_risk = Counter(item["risk_category"] for item in cases)
    by_priority = Counter(item["priority"] for item in cases)
    quantified_by_currency: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for item in cases:
        amount = item.get("amount")
        currency = item.get("currency")
        if amount is not None and amount > 0 and currency:
            quantified_by_currency[currency] += Decimal(str(amount))

    cases_analyzed = len(invoices) + len(gaps) + len(plant_without_invoice)
    requires_attention = len(cases)
    without_observations = max(cases_analyzed - requires_attention, 0)

    return {
        "as_of_date": as_of.isoformat(),
        "summary": {
            "cases_analyzed": cases_analyzed,
            "without_actionable_observations": without_observations,
            "requires_attention": requires_attention,
            "by_risk": dict(by_risk),
            "by_priority": dict(by_priority),
            "quantified_by_currency": {key: float(value) for key, value in quantified_by_currency.items()},
            "quantification_note": (
                "Suma únicamente montos observables de casos cuantificables (por ejemplo NC materiales o diferencias aritméticas); "
                "no equivale a pérdida confirmada ni estima quiebres sin PxQ contractual."
            ),
        },
        "cases": cases,
        "scope_note": (
            "Sin observaciones significa que no se activaron las reglas disponibles con las fuentes conectadas. "
            "No valida precio x cantidad contractual ni confirma que el importe esperado sea correcto."
        ),
    }
