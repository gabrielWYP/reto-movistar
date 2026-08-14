"""Transparent billing-assurance rules; they never assert a financial error."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from .model import CreditNote, Invoice, ZERO

TOLERANCE = Decimal("0.01")
MATERIAL_MEDIUM = Decimal("0.25")
MATERIAL_HIGH = Decimal("0.50")

DETERMINISTIC = "DETERMINISTIC"
HEURISTIC = "HEURISTIC"
DATA_QUALITY = "DATA_QUALITY"


def finding(
    type_: str,
    severity: str,
    category: str,
    message: str,
    evidence_refs: list[str],
    validation_rule: str,
    recommended_validation: str,
    observed_value: Any | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": type_,
        "severity": severity,
        "rule_category": category,
        "message": message,
        "evidence_refs": evidence_refs,
        "validation_rule": validation_rule,
        "recommended_validation": recommended_validation,
    }
    if observed_value is not None:
        payload["observed_value"] = observed_value
    return payload


def invoice_findings(invoice: Invoice, notes: list[CreditNote], evidence_ref: str) -> list[dict[str, Any]]:
    """Return document-level facts and explicitly-labelled materiality heuristics."""
    findings: list[dict[str, Any]] = []
    if not invoice.currency:
        findings.append(
            finding(
                "MISSING_CURRENCY", "MEDIUM", DETERMINISTIC,
                "La factura no contiene moneda en el extracto.", [evidence_ref],
                "MONEDA debe estar informada para interpretar el importe.",
                "Confirmar moneda y documento fuente antes de usar el importe.", None,
            )
        )
    if invoice.total == ZERO:
        findings.append(
            finding(
                "ZERO_VALUE_INVOICE", "MEDIUM", DETERMINISTIC,
                "La factura tiene importe total igual a cero; el dataset no permite determinar su causa.", [evidence_ref],
                "CHARGE_TOTAL_AMOUNT = 0.",
                "Validar si corresponde a una emisión informativa, ajuste o anulación operativa.", invoice.total,
            )
        )
    difference = invoice.net + invoice.tax - invoice.total
    if abs(difference) > TOLERANCE:
        findings.append(
            finding(
                "ARITHMETIC_MISMATCH", "MEDIUM", DETERMINISTIC,
                "Neto más IGV difiere del total por encima de la tolerancia de redondeo.", [evidence_ref],
                "abs(CHARGE_NET_AMOUNT + CHARGE_IGV_INVOICE - CHARGE_TOTAL_AMOUNT) > 0.01.",
                "Contrastar los componentes y el redondeo con el sistema de origen; no se confirma error financiero.",
                {"derived_total": invoice.net + invoice.tax, "reported_total": invoice.total, "difference": difference, "tolerance": TOLERANCE},
            )
        )
    if notes:
        findings.append(
            finding(
                "CREDIT_NOTE_PRESENT", "INFO", DETERMINISTIC,
                "La factura tiene una o más notas de crédito relacionadas; ello representa un ajuste post-emisión, no un error confirmado.",
                [evidence_ref, *[f"credit_note:{note.document}" for note in notes]],
                "FACTURA_AFECTADA coincide con NRO_DOC_FISCAL.",
                "Revisar el ajuste y su soporte operativo.",
                {"credit_note_count": len(notes), "credit_note_total": sum((note.total for note in notes), ZERO)},
            )
        )
        if invoice.total > ZERO:
            ratio = sum((note.total for note in notes), ZERO) / invoice.total
            if ratio >= MATERIAL_MEDIUM:
                severity = "HIGH" if ratio >= MATERIAL_HIGH else "MEDIUM"
                findings.append(
                    finding(
                        "MATERIAL_CREDIT_NOTE", severity, HEURISTIC,
                        "El ajuste por nota de crédito alcanza un umbral de materialidad y merece revisión post-emisión.",
                        [evidence_ref, *[f"credit_note:{note.document}" for note in notes]],
                        "importe NC / importe de factura >= 25%; HIGH desde 50%.",
                        "Validar motivo, aprobación y posible necesidad de refacturación; el ratio no prueba una facturación errónea.",
                        {"credit_note_total": sum((note.total for note in notes), ZERO), "invoice_total": invoice.total, "ratio": ratio},
                    )
                )
    return findings


def materiality(note_total: Decimal, invoice_total: Decimal, threshold: Decimal) -> tuple[Decimal | None, str | None]:
    if invoice_total <= ZERO:
        return None, None
    ratio = note_total / invoice_total
    if ratio < threshold:
        return ratio, None
    return ratio, "HIGH" if ratio >= MATERIAL_HIGH else "MEDIUM"
