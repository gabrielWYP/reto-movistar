"""In-process read-only adapters for the three deterministic specialists."""

from __future__ import annotations

import json
from collections.abc import Callable
from hashlib import sha256
from time import perf_counter
from typing import Any, Protocol

from sonia.domain.orchestration import (
    EvidenceReference,
    ExecutionMetadata,
    ExecutionPlan,
    Finding,
    SpecialistPhase,
    SpecialistResult,
    ValidationCheck,
)

_OPERATIONS = {
    SpecialistPhase.BILLING: "billing_health_snapshot",
    SpecialistPhase.COLLECTIONS: "portfolio_snapshot",
    SpecialistPhase.BI: "executive_snapshot",
}
DatasetScope = Callable[[str, Callable[[], dict[str, Any]]], dict[str, Any]]


class BillingService(Protocol):
    """Structural boundary for Billing's portfolio tool."""

    def billing_health_snapshot(self, as_of_date: str) -> dict[str, Any]: ...


class ToolBackend(Protocol):
    """Structural boundary shared by Collections and BI backends."""

    def execute_tool(self, op: str, args: dict[str, Any], at: str, /) -> dict[str, Any]: ...


def _reference(identity: str, value: object) -> EvidenceReference:
    serialized = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return EvidenceReference(evidence_id=identity, sha256=sha256(serialized.encode()).hexdigest())


class SpecialistAdapter:
    """Bind one fixed read-only operation to the normalized result contract."""

    def __init__(
        self,
        phase: SpecialistPhase,
        runner: Callable[[str], dict[str, Any]],
        dataset_scope: DatasetScope | None = None,
    ) -> None:
        self.phase, self.operation, self._runner = phase, _OPERATIONS[phase], runner
        self._dataset_scope = dataset_scope

    def execute(self, plan: ExecutionPlan, *, attempt: int) -> SpecialistResult:
        """Execute the fixed tool and normalize its evidence with revision lineage."""
        if plan.phase is not self.phase:
            raise ValueError(f"Adapter phase {self.phase} cannot execute plan phase {plan.phase}")
        if self.phase is not SpecialistPhase.BILLING and not plan.upstream_evidence:
            raise ValueError(f"{self.phase} requires approved upstream evidence")
        started = perf_counter()

        def invoke() -> dict[str, Any]:
            return self._runner(plan.as_of_date.isoformat())

        raw = (
            self._dataset_scope(plan.dataset_revision, invoke) if self._dataset_scope else invoke()
        )
        payload = raw.get("agent_response", raw)
        if not isinstance(payload, dict):
            raise ValueError("Specialist returned an invalid response envelope")
        prefix = f"{plan.run_id}:{self.phase}:attempt={attempt}:{self.operation}"
        output = _reference(f"{prefix}:result", payload)
        dataset = _reference(f"dataset:{plan.dataset_revision}", plan.dataset_revision)
        ruleset = _reference(f"ruleset:{plan.ruleset_revision}", plan.ruleset_revision)
        evidence = plan.upstream_evidence + (dataset, ruleset, output)
        findings = tuple(
            Finding(
                code=str(item.get("type", "UNCLASSIFIED")),
                summary=str(item.get("message", "Specialist finding")),
                evidence_refs=(dataset.evidence_id, ruleset.evidence_id, output.evidence_id),
            )
            for item in payload.get("findings", ())
            if isinstance(item, dict)
        )
        agent_ok = payload.get("agent", self.phase) == self.phase
        binding = f"{plan.dataset_revision}/{plan.ruleset_revision}"
        checks = (
            ValidationCheck(name="input_binding", passed=True, detail=binding),
            ValidationCheck(
                name="schema", passed=agent_ok, detail="specialist envelope matches phase"
            ),
            ValidationCheck(name="read_only", passed=True, detail=self.operation),
        )
        quality = payload.get("data_quality", {})
        quality_check = ValidationCheck(
            name="data_quality", passed=bool(quality), detail="profile recorded", required=False
        )
        status = payload.get("status", "RESULT_AVAILABLE")
        if isinstance(status, dict):
            status = next(iter(status.values()), "RESULT_AVAILABLE")
        actions = tuple(
            str(item.get("action", item.get("reason", "review")))
            if isinstance(item, dict)
            else str(item)
            for item in payload.get("recommended_actions", ())
        )
        return SpecialistResult(
            phase=self.phase,
            attempt=attempt,
            status=str(status),
            validation_checks=checks,
            findings=findings,
            evidence_refs=evidence,
            data_quality=(quality_check,),
            recommended_actions=actions,
            metadata=ExecutionMetadata(
                latency_ms=round((perf_counter() - started) * 1000), token_count=0
            ),
        )


def build_specialist_adapters(
    billing: BillingService,
    collections: ToolBackend,
    bi: ToolBackend,
    dataset_scope: DatasetScope | None = None,
) -> dict[SpecialistPhase, SpecialistAdapter]:
    """Wire fixed deterministic operations without HTTP or prompt execution."""
    runners = (
        billing.billing_health_snapshot,
        lambda at: collections.execute_tool("portfolio_snapshot", {}, at),
        lambda at: bi.execute_tool("executive_snapshot", {}, at),
    )
    return {
        phase: SpecialistAdapter(phase, runner, dataset_scope)
        for phase, runner in zip(SpecialistPhase, runners, strict=True)
    }
