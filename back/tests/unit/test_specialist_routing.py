"""Agent-routed specialist execution, telemetry, fallback, and replay."""

from datetime import date
from typing import Any

from sonia.application.specialist_adapters import SpecialistAdapter, build_specialist_adapters
from sonia.application.specialist_prompts import MAX_QUESTION_LENGTH, build_question
from sonia.domain.orchestration import (
    BusinessRule,
    EvidenceReference,
    ExecutionPlan,
    SpecialistPhase,
)

_ANSWERS = (
    BusinessRule(rule_id="objective", answer="Detectar fuga de ingresos"),
    BusinessRule(rule_id="scope", answer="Cartera B2B"),
    BusinessRule(rule_id="overdue_days", answer="30"),
)


def _payload(agent: str) -> dict[str, Any]:
    return {
        "agent": agent,
        "status": "RESULT_AVAILABLE",
        "findings": [{"type": "F1", "message": "finding"}],
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
        self.calls.append(operation)
        return {"agent_response": _payload(self.phase), "tool_used": operation}


class AgentStub:
    """Stand in for a specialist that routes its own tools through a provider."""

    def __init__(self, phase: str, *, available: bool = True, fails: bool = False) -> None:
        self.phase, self._available, self._fails = phase, available, fails
        self.questions: list[str] = []

    @property
    def llm_available(self) -> bool:
        return self._available

    def query(self, question: str, as_of_date: str) -> dict[str, Any]:
        self.questions.append(question)
        if self._fails:
            raise RuntimeError("provider unavailable")
        return {
            "agent_response": _payload(self.phase),
            "mode": "llm",
            "tools_used": ["reconciliation_exceptions", "collection_priorities"],
            "usage": {"prompt_tokens": 1200, "completion_tokens": 300},
            "llm": {"provider": "opencode-go", "model": "deepseek-v4-flash"},
        }


def _plan(
    phase: SpecialistPhase,
    upstream: tuple[EvidenceReference, ...] = (),
    replay_tools: tuple[str, ...] = (),
) -> ExecutionPlan:
    return ExecutionPlan(
        run_id="run-1",
        dataset_revision="ds-1",
        ruleset_revision="rs-1",
        as_of_date=date(2026, 8, 23),
        phase=phase,
        global_rules=_ANSWERS,
        upstream_evidence=upstream,
        replay_tools=replay_tools,
    )


def _adapters(
    agent: AgentStub | None, collections: ToolStub, bi: ToolStub
) -> dict[SpecialistPhase, SpecialistAdapter]:
    agents = {SpecialistPhase.COLLECTIONS: agent} if agent is not None else None
    return build_specialist_adapters(BillingStub(), collections, bi, None, agents)


def _collections_plan() -> ExecutionPlan:
    billing = build_specialist_adapters(BillingStub(), ToolStub("c"), ToolStub("bi"))[
        SpecialistPhase.BILLING
    ].execute(_plan(SpecialistPhase.BILLING), attempt=1)
    return _plan(SpecialistPhase.COLLECTIONS, billing.evidence_refs)


def test_question_carries_the_analyst_answers_for_the_phase() -> None:
    """The ruleset the analyst filled in is what the specialist is asked."""
    question = build_question(_plan(SpecialistPhase.COLLECTIONS))

    assert "Detectar fuga de ingresos" in question
    assert "Cartera B2B" in question
    assert "Días de mora: 30" in question
    assert "Umbral de varianza" not in question
    assert len(question) <= MAX_QUESTION_LENGTH


def test_agent_routing_records_tools_and_provider_telemetry() -> None:
    agent = AgentStub("collections")
    collections, bi = ToolStub("collections"), ToolStub("bi")
    adapter = _adapters(agent, collections, bi)[SpecialistPhase.COLLECTIONS]

    result = adapter.execute(_collections_plan(), attempt=1)

    assert agent.questions and "Cartera B2B" in agent.questions[0]
    assert collections.calls == []
    assert result.routed_tools == ("reconciliation_exceptions", "collection_priorities")
    assert result.metadata.provider == "opencode-go"
    assert result.metadata.model == "deepseek-v4-flash"
    assert result.metadata.token_count == 1500
    routing = next(item for item in result.validation_checks if item.name == "routing")
    assert routing.passed and routing.required is False


def test_provider_failure_falls_back_to_the_fixed_operation() -> None:
    """A dead provider must never cost the run its evidence."""
    agent = AgentStub("collections", fails=True)
    collections, bi = ToolStub("collections"), ToolStub("bi")
    adapter = _adapters(agent, collections, bi)[SpecialistPhase.COLLECTIONS]

    result = adapter.execute(_collections_plan(), attempt=1)

    assert collections.calls == ["portfolio_snapshot"]
    assert result.metadata.provider == "deterministic"
    routing = next(item for item in result.validation_checks if item.name == "routing")
    assert routing.passed is False and "agent unavailable" in routing.detail


def test_missing_provider_keeps_the_deterministic_pipeline_untouched() -> None:
    agent = AgentStub("collections", available=False)
    collections, bi = ToolStub("collections"), ToolStub("bi")
    adapter = _adapters(agent, collections, bi)[SpecialistPhase.COLLECTIONS]

    result = adapter.execute(_collections_plan(), attempt=1)

    assert agent.questions == []
    assert collections.calls == ["portfolio_snapshot"]
    assert result.metadata.token_count == 0


def test_second_attempt_replays_the_first_selection_deterministically() -> None:
    """Confirmation must re-run what the model chose, not ask it again."""
    agent = AgentStub("collections")
    collections, bi = ToolStub("collections"), ToolStub("bi")
    adapter = _adapters(agent, collections, bi)[SpecialistPhase.COLLECTIONS]
    first = adapter.execute(_collections_plan(), attempt=1)

    replayed = adapter.execute(
        _plan(SpecialistPhase.COLLECTIONS, first.evidence_refs, first.routed_tools),
        attempt=2,
    )

    assert len(agent.questions) == 1
    assert collections.calls == ["reconciliation_exceptions"]
    routing = next(item for item in replayed.validation_checks if item.name == "routing")
    assert "deterministic replay" in routing.detail
