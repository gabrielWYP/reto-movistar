"""In-process read-only adapters that let each specialist route its own tools."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from time import perf_counter
from typing import Any, Protocol

from sonia.application.specialist_prompts import build_question
from sonia.domain.orchestration import (
    DEFAULT_CURRENCY,
    EvidenceReference,
    ExecutionMetadata,
    ExecutionPlan,
    Finding,
    SpecialistPhase,
    SpecialistResult,
    ValidationCheck,
    external_effect_rule_ids,
)

_OPERATIONS = {
    SpecialistPhase.BILLING: "billing_health_snapshot",
    SpecialistPhase.COLLECTIONS: "portfolio_snapshot",
    SpecialistPhase.BI: "executive_snapshot",
}
DatasetScope = Callable[[str, Callable[[], dict[str, Any]]], dict[str, Any]]
logger = logging.getLogger(__name__)


class BillingService(Protocol):
    """Structural boundary for Billing's portfolio tool."""

    def billing_health_snapshot(self, as_of_date: str) -> dict[str, Any]: ...


class ToolBackend(Protocol):
    """Structural boundary shared by Collections and BI backends."""

    def execute_tool(self, op: str, args: dict[str, Any], at: str, /) -> dict[str, Any]: ...


class AgentBackend(Protocol):
    """Structural boundary for a specialist that selects its own tools."""

    @property
    def llm_available(self) -> bool: ...

    def query(self, question: str, as_of_date: str) -> dict[str, Any]: ...


def _routed_tools(raw: dict[str, Any]) -> tuple[str, ...]:
    """Read the executed tool names from any of the three agent envelopes."""
    listed = raw.get("tools_used")
    if isinstance(listed, list):
        return tuple(str(item) for item in listed if item)
    single = raw.get("tool_used") or raw.get("tool")
    return (str(single),) if single else ()


def _amount(value: object) -> Decimal | None:
    """Read a monetary magnitude without trusting the specialist's number type."""
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        amount = Decimal(str(value))
    except (ArithmeticError, InvalidOperation, ValueError):
        return None
    return amount if amount >= 0 else None


def _entity_count(item: dict[str, Any]) -> int | None:
    """Accept the flat count Collections reports or the nested one Billing reports."""
    for candidate in (item.get("count"), _observed(item).get("count")):
        if isinstance(candidate, int) and not isinstance(candidate, bool) and candidate >= 0:
            return candidate
    return None


def _observed(item: dict[str, Any]) -> dict[str, Any]:
    observed = item.get("observed_value")
    return observed if isinstance(observed, dict) else {}


def _finding(item: dict[str, Any], refs: tuple[str, ...]) -> Finding:
    """Carry the magnitude the specialist already computed into the run record."""
    amount = _amount(item.get("amount"))
    return Finding(
        code=str(item.get("type", "UNCLASSIFIED")),
        summary=str(item.get("message", "Specialist finding")),
        evidence_refs=refs,
        severity=str(item.get("severity") or "UNSPECIFIED"),
        amount=amount,
        currency=str(item.get("currency") or DEFAULT_CURRENCY) if amount is not None else None,
        entity_count=_entity_count(item),
    )


def _telemetry(raw: dict[str, Any], started: float) -> ExecutionMetadata:
    """Normalize provider telemetry, defaulting to the deterministic profile."""
    reported, described = raw.get("usage"), raw.get("llm")
    usage: dict[str, Any] = reported if isinstance(reported, dict) else {}
    llm: dict[str, Any] = described if isinstance(described, dict) else {}
    counted = [
        value
        for key, value in usage.items()
        if key in ("prompt_tokens", "completion_tokens")
        and isinstance(value, int)
        and not isinstance(value, bool)
    ]
    total = usage.get("total_tokens")
    tokens = total if isinstance(total, int) and not isinstance(total, bool) else sum(counted)
    model = llm.get("model")
    return ExecutionMetadata(
        provider=str(llm.get("provider") or "deterministic"),
        model=str(model) if model else None,
        latency_ms=round((perf_counter() - started) * 1000),
        token_count=max(tokens, 0),
    )


def _reference(identity: str, value: object) -> EvidenceReference:
    serialized = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return EvidenceReference(evidence_id=identity, sha256=sha256(serialized.encode()).hexdigest())


class SpecialistAdapter:
    """Let the specialist route its own tools, then normalize the evidence it returns."""

    def __init__(
        self,
        phase: SpecialistPhase,
        runner: Callable[[str], dict[str, Any]],
        dataset_scope: DatasetScope | None = None,
        agent: AgentBackend | None = None,
        replay: Callable[[str, str], dict[str, Any]] | None = None,
    ) -> None:
        self.phase, self.operation, self._runner = phase, _OPERATIONS[phase], runner
        self._dataset_scope = dataset_scope
        self._agent = agent
        self._replay = replay

    def _scoped(self, plan: ExecutionPlan, invoke: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        if self._dataset_scope is None:
            return invoke()
        return self._dataset_scope(plan.dataset_revision, invoke)

    def _route(self, plan: ExecutionPlan) -> tuple[dict[str, Any], ValidationCheck]:
        """Prefer the agent, replay a prior selection, and always keep a working floor."""
        at = plan.as_of_date.isoformat()
        if plan.replay_tools and self._replay is not None:
            tool, replay = plan.replay_tools[0], self._replay
            try:
                raw = self._scoped(plan, lambda: replay(tool, at))
                detail = f"deterministic replay of {tool}"
                return raw, ValidationCheck(name="routing", passed=True, detail=detail)
            except Exception as error:
                logger.exception(
                    "specialist_replay_failed",
                    extra={"phase": self.phase, "run_id": plan.run_id, "tool": tool},
                )
                reason = f"replay of {tool} failed: {type(error).__name__}"
                raw = self._scoped(plan, lambda: self._runner(at))
                return raw, ValidationCheck(name="routing", passed=False, detail=reason[:160])
        agent = self._agent
        if agent is not None and not agent.llm_available:
            raw = self._scoped(plan, lambda: self._runner(at))
            return raw, ValidationCheck(
                name="routing", passed=False, detail="no provider; fixed operation executed"
            )
        if agent is not None:
            question = build_question(plan)
            try:
                raw = self._scoped(plan, lambda: agent.query(question, at))
                tools = ", ".join(_routed_tools(raw)) or "none reported"
                detail = f"agent selected: {tools}"
                return raw, ValidationCheck(name="routing", passed=True, detail=detail)
            except Exception as error:
                logger.exception(
                    "specialist_agent_routing_failed",
                    extra={"phase": self.phase, "run_id": plan.run_id},
                )
                reason = f"agent unavailable: {type(error).__name__}: {error}"
                raw = self._scoped(plan, lambda: self._runner(at))
                return raw, ValidationCheck(name="routing", passed=False, detail=reason[:160])
        raw = self._scoped(plan, lambda: self._runner(at))
        return raw, ValidationCheck(
            name="routing", passed=True, detail=f"fixed operation {self.operation}"
        )

    def execute(self, plan: ExecutionPlan, *, attempt: int) -> SpecialistResult:
        """Route the specialist, then normalize its evidence with revision lineage."""
        if plan.phase is not self.phase:
            raise ValueError(f"Adapter phase {self.phase} cannot execute plan phase {plan.phase}")
        if self.phase is not SpecialistPhase.BILLING and not plan.upstream_evidence:
            raise ValueError(f"{self.phase} requires approved upstream evidence")
        started = perf_counter()
        unsafe = external_effect_rule_ids(plan.global_rules + plan.specialist_rules)
        prefix = f"{plan.run_id}:{self.phase}:attempt={attempt}:{self.operation}"
        dataset = _reference(f"dataset:{plan.dataset_revision}", plan.dataset_revision)
        ruleset = _reference(f"ruleset:{plan.ruleset_revision}", plan.ruleset_revision)
        if unsafe:
            refusal = _reference(f"{prefix}:external-effect-refusal", unsafe)
            refs = (dataset.evidence_id, ruleset.evidence_id, refusal.evidence_id)
            return SpecialistResult(
                phase=self.phase,
                attempt=attempt,
                status="EXTERNAL_EFFECT_REFUSED",
                validation_checks=(
                    ValidationCheck(
                        name="external_effect",
                        passed=False,
                        detail="unsupported bound rules refused: " + ", ".join(unsafe),
                    ),
                    ValidationCheck(name="read_only", passed=True, detail="tool not invoked"),
                ),
                findings=(
                    Finding(
                        code="EXTERNAL_EFFECT_REFUSED",
                        summary="Unsupported external effect was not executed",
                        evidence_refs=refs,
                    ),
                ),
                evidence_refs=plan.upstream_evidence + (dataset, ruleset, refusal),
                data_quality=(),
                recommended_actions=("Revise the bound rule for read-only analysis",),
                metadata=ExecutionMetadata(
                    latency_ms=round((perf_counter() - started) * 1000), token_count=0
                ),
            )

        raw, routing = self._route(plan)
        payload = raw.get("agent_response", raw)
        if not isinstance(payload, dict):
            raise ValueError("Specialist returned an invalid response envelope")
        output = _reference(f"{prefix}:result", payload)
        evidence = plan.upstream_evidence + (dataset, ruleset, output)
        finding_refs = (dataset.evidence_id, ruleset.evidence_id, output.evidence_id)
        findings = tuple(
            _finding(item, finding_refs)
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
            routing.model_copy(update={"required": False}),
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
            metadata=_telemetry(raw, started),
            routed_tools=_routed_tools(raw),
        )


def build_specialist_adapters(
    billing: BillingService,
    collections: ToolBackend,
    bi: ToolBackend,
    dataset_scope: DatasetScope | None = None,
    agents: Mapping[SpecialistPhase, AgentBackend] | None = None,
) -> dict[SpecialistPhase, SpecialistAdapter]:
    """Wire agent routing over the closed tool contract, keeping a deterministic floor."""
    routed = agents or {}
    runners = (
        billing.billing_health_snapshot,
        lambda at: collections.execute_tool("portfolio_snapshot", {}, at),
        lambda at: bi.execute_tool("executive_snapshot", {}, at),
    )
    replays: tuple[Callable[[str, str], dict[str, Any]] | None, ...] = (
        None,
        lambda tool, at: collections.execute_tool(tool, {}, at),
        lambda tool, at: bi.execute_tool(tool, {}, at),
    )
    return {
        phase: SpecialistAdapter(phase, runner, dataset_scope, routed.get(phase), replay)
        for phase, runner, replay in zip(SpecialistPhase, runners, replays, strict=True)
    }
