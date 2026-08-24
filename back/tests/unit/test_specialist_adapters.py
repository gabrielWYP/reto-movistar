"""Specialist adapter binding, lineage, and read-only tests."""

from datetime import date
from typing import Any

import pytest

from sonia.application.judge import Judge
from sonia.application.specialist_adapters import build_specialist_adapters
from sonia.domain.orchestration import (
    BusinessRule,
    EvidenceReference,
    ExecutionPlan,
    JudgeVerdict,
    SpecialistPhase,
)


def _payload(agent: str) -> dict[str, Any]:
    return {
        "agent": agent,
        "status": {"state": "READY"},
        "findings": [{"type": "F1", "message": "finding", "evidence_refs": ["source"]}],
        "evidence": [{"id": "source", "value": {"count": 2}}],
        "data_quality": {"known_limitations": ["bounded"]},
        "recommended_actions": [{"action": "review"}],
    }


class BillingStub:
    def billing_health_snapshot(self, as_of_date: str) -> dict[str, Any]:
        return _payload("billing")


class ToolStub:
    def __init__(self, phase: str) -> None:
        self.phase, self.calls = phase, []

    def execute_tool(
        self, operation: str, arguments: dict[str, Any], as_of_date: str
    ) -> dict[str, Any]:
        self.calls.append((operation, arguments, as_of_date))
        payload = _payload(self.phase)
        return {"agent_response": payload} if self.phase == "bi" else payload


def _plan(phase: SpecialistPhase, upstream: tuple[EvidenceReference, ...] = ()) -> ExecutionPlan:
    return ExecutionPlan(
        run_id="run-1",
        dataset_revision="ds-1",
        ruleset_revision="rs-1",
        as_of_date=date(2026, 8, 23),
        phase=phase,
        global_rules=(),
        upstream_evidence=upstream,
    )


def test_adapters_normalize_lineage_and_handoff_in_fixed_order() -> None:
    collections, bi = ToolStub("collections"), ToolStub("bi")
    adapters = build_specialist_adapters(BillingStub(), collections, bi)

    billing = adapters[SpecialistPhase.BILLING].execute(_plan(SpecialistPhase.BILLING), attempt=1)
    cobranzas = adapters[SpecialistPhase.COLLECTIONS].execute(
        _plan(SpecialistPhase.COLLECTIONS, billing.evidence_refs), attempt=1
    )
    intelligence = adapters[SpecialistPhase.BI].execute(
        _plan(SpecialistPhase.BI, cobranzas.evidence_refs), attempt=2
    )

    assert [billing.phase, cobranzas.phase, intelligence.phase] == list(SpecialistPhase)
    assert all(
        result.findings and result.evidence_refs and result.validation_checks
        for result in (billing, cobranzas, intelligence)
    )
    assert set(billing.evidence_refs).issubset(cobranzas.evidence_refs)
    assert set(cobranzas.evidence_refs).issubset(intelligence.evidence_refs)
    assert collections.calls[0][0] == "portfolio_snapshot"
    expected = "run-1:bi:attempt=2:executive_snapshot:result"
    assert intelligence.evidence_refs[-1].evidence_id == expected


def test_adapters_reject_phase_mismatch_and_missing_upstream() -> None:
    adapters = build_specialist_adapters(BillingStub(), ToolStub("collections"), ToolStub("bi"))

    with pytest.raises(ValueError, match="phase"):
        adapters[SpecialistPhase.BILLING].execute(_plan(SpecialistPhase.BI), attempt=1)
    with pytest.raises(ValueError, match="upstream"):
        adapters[SpecialistPhase.COLLECTIONS].execute(_plan(SpecialistPhase.COLLECTIONS), attempt=1)


@pytest.mark.parametrize("rule", ["Emitir factura al cliente", "Delete all invoice records"])
def test_adapter_refuses_bound_external_effect_before_invoking_tool(rule: str) -> None:
    calls = 0

    def forbidden(_: str) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return _payload("billing")

    plan = _plan(SpecialistPhase.BILLING).model_copy(
        update={"global_rules": (BusinessRule(rule_id="g1", answer=rule),)}
    )
    result = build_specialist_adapters(
        type("Billing", (), {"billing_health_snapshot": staticmethod(forbidden)})(),
        ToolStub("collections"),
        ToolStub("bi"),
    )[SpecialistPhase.BILLING].execute(plan, attempt=1)

    assert calls == 0 and result.status == "EXTERNAL_EFFECT_REFUSED"
    assert result.findings[0].code == "EXTERNAL_EFFECT_REFUSED"
    assert (
        next(check for check in result.validation_checks if check.name == "external_effect").passed
        is False
    )
    assert Judge().evaluate(result).verdict is JudgeVerdict.MANUAL_REVIEW
