"""Public contracts for the specialist-agent registry."""

from pydantic import BaseModel, ConfigDict


class AgentDescriptor(BaseModel):
    """Stable metadata exposed for one integrated specialist agent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_id: str
    display_name: str
    source_branch: str
    package: str
    capabilities: tuple[str, ...]
