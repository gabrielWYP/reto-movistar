"""Central registry for the three specialist agents."""

from sonia.domain.agents import AgentDescriptor

_AGENTS: tuple[AgentDescriptor, ...] = (
    AgentDescriptor(
        agent_id="billing",
        display_name="Facturación",
        source_branch="camila",
        package="sonia.agents.billing",
        capabilities=("invoice_validation", "billing_control", "evidence_trace"),
    ),
    AgentDescriptor(
        agent_id="collections",
        display_name="Cobranzas y conciliación",
        source_branch="Arian",
        package="sonia.agents.collections",
        capabilities=("portfolio_snapshot", "payment_matching", "collection_priority"),
    ),
    AgentDescriptor(
        agent_id="bi",
        display_name="Business Intelligence",
        source_branch="Mauricio",
        package="sonia.agents.bi",
        capabilities=("revenue_metrics", "aging_analysis", "executive_insights"),
    ),
)


def list_agents() -> tuple[AgentDescriptor, ...]:
    """Return the immutable registry in business-journey order."""
    return _AGENTS


def get_agent(agent_id: str) -> AgentDescriptor | None:
    """Return one registered agent by its stable identifier."""
    return next((agent for agent in _AGENTS if agent.agent_id == agent_id), None)
