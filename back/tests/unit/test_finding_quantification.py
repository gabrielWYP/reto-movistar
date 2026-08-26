"""Findings carry the magnitude the specialists already compute.

Payload shapes are copied from the deployed agents so the extraction is tested
against what the three specialists actually return, not an invented envelope.
"""

from datetime import date
from decimal import Decimal
from typing import Any

from sonia.application.specialist_adapters import build_specialist_adapters
from sonia.domain.orchestration import (
    ExecutionPlan,
    Finding,
    SpecialistPhase,
    quantified_exposure,
)

COLLECTIONS_FINDING = {
    "type": "UNMATCHED_PAYMENT_CUTOFF",
    "severity": "MEDIUM",
    "message": "Pagos que apuntan a documentos no presentes en el corte de facturas.",
    "count": 74,
    "amount": 106289.4,
}
BI_FINDING = {
    "type": "OVERDUE_EXPOSURE",
    "severity": "MEDIUM",
    "message": "There is documented overdue balance at the selected cut-off.",
    "amount": 147679.93,
}
BILLING_FINDINGS = [
    {
        "type": "BILLING_CYCLE_GAP",
        "severity": "MEDIUM",
        "message": "Se encontraron candidatos de ausencia documental mensual.",
        "observed_value": {"count": 22},
    },
    {
        "type": "DATA_QUALITY_JOIN_GAP",
        "severity": "MEDIUM",
        "message": "Parte de las cuentas facturadas no tiene planta enlazada.",
        "observed_value": {"invoiced_customer_accounts": 1672, "matched_share": 0.69},
    },
]


class BillingStub:
    def billing_health_snapshot(self, as_of_date: str) -> dict[str, Any]:
        return {"agent": "billing", "status": "READY", "findings": BILLING_FINDINGS}


class ToolStub:
    def __init__(self, phase: str, findings: list[dict[str, Any]]) -> None:
        self.phase, self.findings = phase, findings

    def execute_tool(
        self, operation: str, arguments: dict[str, Any], as_of_date: str
    ) -> dict[str, Any]:
        return {"agent": self.phase, "status": "READY", "findings": self.findings}


def _plan(phase: SpecialistPhase, upstream: tuple[Any, ...] = ()) -> ExecutionPlan:
    return ExecutionPlan(
        run_id="run-1",
        dataset_revision="ds-1",
        ruleset_revision="rs-1",
        as_of_date=date(2026, 8, 7),
        phase=phase,
        global_rules=(),
        upstream_evidence=upstream,
    )


def _run_all() -> dict[SpecialistPhase, tuple[Finding, ...]]:
    collections = ToolStub("collections", [COLLECTIONS_FINDING])
    bi = ToolStub("bi", [BI_FINDING])
    adapters = build_specialist_adapters(BillingStub(), collections, bi)
    billing = adapters[SpecialistPhase.BILLING].execute(_plan(SpecialistPhase.BILLING), attempt=1)
    cobranzas = adapters[SpecialistPhase.COLLECTIONS].execute(
        _plan(SpecialistPhase.COLLECTIONS, billing.evidence_refs), attempt=1
    )
    intelligence = adapters[SpecialistPhase.BI].execute(
        _plan(SpecialistPhase.BI, cobranzas.evidence_refs), attempt=1
    )
    return {
        SpecialistPhase.BILLING: billing.findings,
        SpecialistPhase.COLLECTIONS: cobranzas.findings,
        SpecialistPhase.BI: intelligence.findings,
    }


def test_collections_amount_and_count_reach_the_run_record() -> None:
    finding = _run_all()[SpecialistPhase.COLLECTIONS][0]

    assert finding.code == "UNMATCHED_PAYMENT_CUTOFF"
    assert finding.amount == Decimal("106289.4")
    assert finding.currency == "PEN"
    assert finding.entity_count == 74
    assert finding.severity == "MEDIUM"


def test_billing_reports_a_nested_count_and_no_amount() -> None:
    """Billing quantifies documents, not soles; the record must say so honestly."""
    cycle_gap, join_gap = _run_all()[SpecialistPhase.BILLING]

    assert cycle_gap.entity_count == 22
    assert cycle_gap.amount is None and cycle_gap.currency is None
    assert join_gap.entity_count is None


def test_bi_amount_without_a_count_is_still_quantified() -> None:
    finding = _run_all()[SpecialistPhase.BI][0]

    assert finding.amount == Decimal("147679.93")
    assert finding.entity_count is None


def test_exposure_never_counts_the_same_code_twice() -> None:
    """Two specialists observing one phenomenon must not double the soles."""
    findings = [
        Finding(
            code="OVERDUE_EXPOSURE",
            summary="collections view",
            evidence_refs=("a",),
            amount=Decimal("147679.93"),
            currency="PEN",
        ),
        Finding(
            code="OVERDUE_EXPOSURE",
            summary="bi view of the same balance",
            evidence_refs=("b",),
            amount=Decimal("147679.93"),
            currency="PEN",
        ),
        Finding(
            code="UNMATCHED_PAYMENT_CUTOFF",
            summary="unmatched payments",
            evidence_refs=("c",),
            amount=Decimal("106289.4"),
            currency="PEN",
        ),
    ]

    assert quantified_exposure(findings) == {"PEN": Decimal("253969.33")}


def test_unusable_amounts_are_dropped_rather_than_guessed() -> None:
    adapters = build_specialist_adapters(
        BillingStub(),
        ToolStub(
            "collections",
            [
                {"type": "A", "message": "texto", "amount": "no es un número"},
                {"type": "B", "message": "texto", "amount": -5},
                {"type": "C", "message": "texto", "amount": True},
            ],
        ),
        ToolStub("bi", []),
    )
    billing = adapters[SpecialistPhase.BILLING].execute(_plan(SpecialistPhase.BILLING), attempt=1)

    result = adapters[SpecialistPhase.COLLECTIONS].execute(
        _plan(SpecialistPhase.COLLECTIONS, billing.evidence_refs), attempt=1
    )

    assert [item.amount for item in result.findings] == [None, None, None]
    assert quantified_exposure(result.findings) == {}
