"""Deterministic analyst work queue built from existing Billing rules."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from .contracts import json_value
from .model import ZERO, CreditNote, Invoice
from .rules import HEURISTIC, invoice_findings

if TYPE_CHECKING:
    from .service import BillingService


ACTIONABLE_INVOICE_CODES = frozenset(
    {
        "MATERIAL_CREDIT_NOTE",
        "ARITHMETIC_MISMATCH",
        "ZERO_VALUE_INVOICE",
        "MISSING_CURRENCY",
    }
)
DOCUMENTARY_CODES = frozenset(
    {"ARITHMETIC_MISMATCH", "ZERO_VALUE_INVOICE", "MISSING_CURRENCY"}
)
PRIORITY_RANK = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
RISK_REVENUE = "Riesgo de ingreso"
RISK_ADJUSTMENTS = "Ajustes post-emisión"
RISK_DOCUMENT = "Calidad documental"

MONTHS = (
    "",
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


def _period_label(period: str) -> str:
    year, month = period.split("-")
    return f"{MONTHS[int(month)]} de {year}"


def _money_text(amount: Decimal, currency: str | None) -> str:
    prefix = f"{currency} " if currency else ""
    return f"{prefix}{amount:.2f}"


def _priority(findings: list[dict[str, Any]]) -> tuple[str, str]:
    codes = {item["type"] for item in findings}
    if len(codes) >= 2:
        return "HIGH", "Dos o más señales accionables coinciden en el mismo documento."
    finding = findings[0]
    if finding["type"] == "MATERIAL_CREDIT_NOTE":
        severity = "HIGH" if finding["severity"] == "HIGH" else "MEDIUM"
        return severity, "Prioridad derivada de la materialidad calculada por la regla existente."
    if finding["type"] == "MISSING_CURRENCY":
        return "LOW", "Moneda no informada; requiere completar el dato antes de interpretar el monto."
    return "MEDIUM", "Señal accionable que requiere validación documental."


def _credit_amounts(
    invoice: Invoice, notes: list[CreditNote]
) -> tuple[Decimal | None, str | None, list[dict[str, Any]], str]:
    totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    unknown = ZERO
    for note in notes:
        currency = (note.currency or invoice.currency).strip().upper()
        if currency:
            totals[currency] += note.total
        else:
            unknown += note.total
    amounts = [
        {"currency": currency, "amount": amount}
        for currency, amount in sorted(totals.items())
    ]
    if unknown:
        amounts.append({"currency": None, "amount": unknown})
    if len(amounts) == 1 and amounts[0]["currency"]:
        return (
            amounts[0]["amount"],
            amounts[0]["currency"],
            amounts,
            "Monto documentado de la nota de crédito",
        )
    return (
        None,
        None,
        amounts,
        "Ajustes documentados por moneda; no se agregan monedas distintas",
    )


def _finding_summary(
    finding: dict[str, Any], invoice: Invoice, notes: list[CreditNote]
) -> str:
    observed = finding.get("observed_value") or {}
    code = finding["type"]
    if code == "ARITHMETIC_MISMATCH":
        currency = invoice.currency or None
        return (
            f"Neto + IGV = {_money_text(invoice.net + invoice.tax, currency)}; "
            f"total registrado = {_money_text(invoice.total, currency)}; "
            f"diferencia observada = {_money_text(abs(invoice.net + invoice.tax - invoice.total), currency)}."
        )
    if code == "ZERO_VALUE_INVOICE":
        return "El total registrado de la factura es 0.00 y requiere validar su propósito operativo."
    if code == "MISSING_CURRENCY":
        return "La factura no informa moneda en el extracto conectado."
    if code == "MATERIAL_CREDIT_NOTE":
        ratio = observed.get("ratio")
        totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
        for note in notes:
            totals[(note.currency or invoice.currency or "SIN MONEDA").upper()] += note.total
        note_text = " + ".join(
            _money_text(amount, currency) for currency, amount in sorted(totals.items())
        )
        ratio_text = f"{Decimal(str(ratio)) * 100:.1f}%" if ratio is not None else "—"
        return (
            f"La nota de crédito representa {ratio_text} de la factura. "
            f"Monto factura: {_money_text(invoice.total, invoice.currency or None)}; "
            f"monto NC: {note_text}."
        )
    return finding["message"]


def _invoice_case(
    invoice: Invoice, notes: list[CreditNote], findings: list[dict[str, Any]]
) -> dict[str, Any]:
    priority, priority_basis = _priority(findings)
    codes = list(dict.fromkeys(item["type"] for item in findings))
    material = next(
        (item for item in findings if item["type"] == "MATERIAL_CREDIT_NOTE"), None
    )
    arithmetic = next(
        (item for item in findings if item["type"] == "ARITHMETIC_MISMATCH"), None
    )
    if material:
        amount, currency, amounts, amount_basis = _credit_amounts(invoice, notes)
        risk_category = RISK_ADJUSTMENTS
        title = "Ajuste post-emisión material"
        drilldown = {"view": "notes", "invoice_id": invoice.document}
    elif arithmetic:
        amount = abs(invoice.net + invoice.tax - invoice.total)
        currency = invoice.currency or None
        amounts = [{"currency": currency, "amount": amount}]
        amount_basis = "Diferencia aritmética observada"
        risk_category = RISK_DOCUMENT
        title = "Factura con diferencia aritmética"
        drilldown = {"view": "invoice", "invoice_id": invoice.document}
    elif "ZERO_VALUE_INVOICE" in codes:
        amount = invoice.total
        currency = invoice.currency or None
        amounts = [{"currency": currency, "amount": amount}]
        amount_basis = "Total registrado en la factura"
        risk_category = RISK_DOCUMENT
        title = "Factura con importe cero"
        drilldown = {"view": "invoice", "invoice_id": invoice.document}
    else:
        amount = invoice.total
        currency = None
        amounts = [{"currency": None, "amount": amount}]
        amount_basis = "Total registrado sin moneda informada"
        risk_category = RISK_DOCUMENT
        title = "Factura sin moneda informada"
        drilldown = {"view": "invoice", "invoice_id": invoice.document}
    if len(codes) >= 2:
        title = "Factura con múltiples señales"
    categories = sorted({item["rule_category"] for item in findings})
    return {
        "case_id": f"invoice:{invoice.document}",
        "priority": priority,
        "priority_basis": priority_basis,
        "risk_category": risk_category,
        "customer": invoice.customer,
        "account": invoice.account,
        "invoice_id": invoice.document,
        "period": invoice.issued_at.strftime("%Y-%m") if invoice.issued_at else None,
        "title": title,
        "finding_codes": codes,
        "rule_category": categories[0] if len(categories) == 1 else "MIXED",
        "amount": amount,
        "currency": currency,
        "amounts_by_currency": amounts,
        "amount_basis": amount_basis,
        "evidence_summary": " ".join(
            _finding_summary(item, invoice, notes) for item in findings
        ),
        "recommended_action": " ".join(
            dict.fromkeys(item["recommended_validation"] for item in findings)
        ),
        "drilldown": drilldown,
        "technical_trace": {
            "invoice": invoice.evidence,
            "credit_notes": [note.evidence for note in notes],
            "findings": findings,
        },
    }


def _gap_cases(service: BillingService, as_of: date) -> list[dict[str, Any]]:
    response = service.billing_cycle_gaps(as_of.isoformat())
    evidence = {item["id"]: item for item in response["evidence"]}
    cases: list[dict[str, Any]] = []
    for item in response["evidence"]:
        if item["type"] != "cycle_gap":
            continue
        gap = item["value"]
        finding = next(
            result for result in response["findings"] if item["id"] in result["evidence_refs"]
        )
        plant_ref = f"plant:{gap['customer']}:{gap['account']}"
        plant_linked = bool(evidence.get(plant_ref, {}).get("value"))
        summary = (
            f"Se encontró factura cíclica en {_period_label(gap['before_period'])} "
            f"({gap['before_document']}) y {_period_label(gap['after_period'])} "
            f"({gap['after_document']}), pero no documento para "
            f"{_period_label(gap['missing_period'])} en la misma cuenta. "
            f"Planta enlazada: {'sí' if plant_linked else 'no'}."
        )
        refs = {
            ref: evidence[ref] for ref in finding["evidence_refs"] if ref in evidence
        }
        cases.append(
            {
                "case_id": (
                    f"cycle-gap:{gap['customer']}:{gap['account']}:"
                    f"{gap['missing_period']}"
                ),
                "priority": "MEDIUM",
                "priority_basis": "Posible quiebre documental definido por la regla M, M+2.",
                "risk_category": RISK_REVENUE,
                "customer": gap["customer"],
                "account": gap["account"],
                "invoice_id": None,
                "period": gap["missing_period"],
                "title": "Posible quiebre de ciclo",
                "finding_codes": ["BILLING_CYCLE_GAP"],
                "rule_category": HEURISTIC,
                "amount": None,
                "currency": None,
                "amounts_by_currency": [],
                "amount_basis": "No cuantificable sin PxQ contractual",
                "evidence_summary": summary,
                "recommended_action": finding["recommended_validation"],
                "drilldown": {
                    "view": "gaps",
                    "customer_id": gap["customer"],
                    "account_id": gap["account"],
                },
                "technical_trace": {"finding": finding, "evidence": refs},
            }
        )
    return cases


def _plant_cases(service: BillingService, as_of: date) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for customer, account, rows in service._active_plant_without_invoice(as_of):
        plant_evidence = service._plant_evidence(rows)
        cases.append(
            {
                "case_id": f"plant:{customer}:{account}",
                "priority": "MEDIUM",
                "priority_basis": "Planta activa sin evidencia de factura en el extracto.",
                "risk_category": RISK_REVENUE,
                "customer": customer,
                "account": account,
                "invoice_id": None,
                "period": as_of.strftime("%Y-%m"),
                "title": "Planta sin evidencia de factura",
                "finding_codes": ["PLANT_WITHOUT_BILLING_EVIDENCE"],
                "rule_category": HEURISTIC,
                "amount": None,
                "currency": None,
                "amounts_by_currency": [],
                "amount_basis": "No cuantificable sin PxQ contractual",
                "evidence_summary": (
                    "La cuenta tiene planta activa en el extracto y no presenta evidencia "
                    f"de factura hasta el corte {as_of.isoformat()}. Esto no prueba un "
                    "servicio no facturado ni una fuga de ingresos."
                ),
                "recommended_action": (
                    "Validar cobertura temporal, vigencia contractual y sistema de origen "
                    "antes de escalar el caso."
                ),
                "drilldown": {
                    "view": "customer",
                    "customer_id": customer,
                    "account_id": account,
                },
                "technical_trace": {
                    "technical_code": "PLANT_WITHOUT_BILLING_EVIDENCE",
                    "validation_rule": (
                        "Planta Active/Activo y sin factura del cliente-cuenta hasta el corte."
                    ),
                    "plant": plant_evidence,
                },
            }
        )
    return cases


def _case_sort(case: dict[str, Any]) -> tuple[Any, ...]:
    amount = case["amount"] if isinstance(case["amount"], Decimal) else ZERO
    return (
        PRIORITY_RANK[case["priority"]],
        case["currency"] is None,
        case["currency"] or "",
        -amount,
        case["case_id"],
    )


def build_work_queue(
    service: BillingService, as_of_date: str | None = None
) -> dict[str, Any]:
    """Return actionable cases without changing any existing tool response."""
    as_of = service._as_of(as_of_date)
    invoices = service._invoices_as_of(as_of)
    cases: list[dict[str, Any]] = []
    documentary_documents: set[str] = set()
    for invoice in invoices:
        notes = service._notes_for_invoice(invoice.document, as_of)
        relevant = [
            item
            for item in invoice_findings(invoice, notes, f"invoice:{invoice.document}")
            if item["type"] in ACTIONABLE_INVOICE_CODES
        ]
        if {item["type"] for item in relevant} & DOCUMENTARY_CODES:
            documentary_documents.add(invoice.document)
        if relevant:
            cases.append(_invoice_case(invoice, notes, relevant))
    cases.extend(_gap_cases(service, as_of))
    cases.extend(_plant_cases(service, as_of))
    cases.sort(key=_case_sort)

    totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    breakdown: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: defaultdict(lambda: ZERO)
    )
    quantified_cases = 0
    for case in cases:
        known_amounts = [
            item
            for item in case["amounts_by_currency"]
            if item["currency"] and isinstance(item["amount"], Decimal)
        ]
        if known_amounts:
            quantified_cases += 1
        for item in known_amounts:
            totals[item["currency"]] += item["amount"]
            breakdown[item["currency"]][case["amount_basis"]] += item["amount"]

    risk_counts = {category: 0 for category in (RISK_REVENUE, RISK_ADJUSTMENTS, RISK_DOCUMENT)}
    priority_counts = {priority: 0 for priority in ("HIGH", "MEDIUM", "LOW")}
    for case in cases:
        risk_counts[case["risk_category"]] += 1
        priority_counts[case["priority"]] += 1

    return json_value(
        {
            "as_of_date": as_of,
            "summary": {
                "invoice_documents": len(invoices),
                "invoices_without_documentary_findings": (
                    len(invoices) - len(documentary_documents)
                ),
                "invoices_with_documentary_findings": len(documentary_documents),
                "cases_requiring_attention": len(cases),
                "invoice_cases": sum(case["invoice_id"] is not None for case in cases),
                "account_period_cases": sum(case["invoice_id"] is None for case in cases),
                "risk_category_counts": risk_counts,
                "priority_counts": priority_counts,
                "quantified_case_count": quantified_cases,
                "quantifiable_amounts_by_currency": [
                    {"currency": currency, "amount": amount}
                    for currency, amount in sorted(totals.items())
                ],
                "amount_breakdown_by_currency": {
                    currency: dict(values) for currency, values in sorted(breakdown.items())
                },
                "definitions": {
                    "invoice_denominator": (
                        "Facturas emitidas hasta el corte y evaluadas con las validaciones "
                        "documentales disponibles."
                    ),
                    "without_findings": (
                        "No presenta ARITHMETIC_MISMATCH, ZERO_VALUE_INVOICE ni "
                        "MISSING_CURRENCY; no valida PxQ contractual."
                    ),
                    "attention_cases": (
                        "Unidades agrupadas por factura, cuenta sin evidencia o periodo de "
                        "quiebre; no se usa como denominador financiero."
                    ),
                    "quantifiable_amounts": (
                        "Suma un monto principal documentado por caso y moneda; no representa "
                        "pérdida y nunca mezcla monedas."
                    ),
                },
            },
            "cases": cases,
        }
    )
