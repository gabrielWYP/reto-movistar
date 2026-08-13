"""Typed contracts for the deterministic SON-IA visual demo."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class DemoState(StrEnum):
    """States exposed by the first visual MVP."""

    VALIDATING = "VALIDATING"
    NEEDS_APPROVAL = "NEEDS_APPROVAL"
    ISSUED = "ISSUED"
    PAYMENT_DETECTED = "PAYMENT_DETECTED"
    RECONCILING = "RECONCILING"
    ANALYZING = "ANALYZING"
    CLOSED = "CLOSED"


class DemoAction(StrEnum):
    """Allowed actions for the visual journey."""

    VALIDATE_PXQ = "VALIDATE_PXQ"
    APPROVE_INVOICE = "APPROVE_INVOICE"
    ANALYZE_PAYMENT = "ANALYZE_PAYMENT"
    PREPARE_RECONCILIATION = "PREPARE_RECONCILIATION"
    CONFIRM_PAYMENT = "CONFIRM_PAYMENT"
    GENERATE_INSIGHTS = "GENERATE_INSIGHTS"


class AgentStatus(StrEnum):
    """Presentation status for each specialist agent."""

    PENDING = "pending"
    ACTIVE = "active"
    REVIEW = "review"
    COMPLETED = "completed"


class AgentSnapshot(BaseModel):
    """Current presentation data for one specialist agent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_id: str
    name: str
    specialty: str
    summary: str
    status: AgentStatus
    confidence: int
    processed_items: int
    evidence_count: int


class MetricSnapshot(BaseModel):
    """Business metric displayed in the visual MVP."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str
    value: str
    trend: str


class TimelineEvent(BaseModel):
    """Auditable event shown in the supervisor timeline."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    actor: str
    title: str
    detail: str
    time: str
    tone: str


class DemoScenarioResponse(BaseModel):
    """Complete initial state for the deterministic demo."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    customer_name: str
    service_name: str
    invoice_reference: str
    invoice_amount: str
    currency: str
    current_state: DemoState
    progress: int
    agents: tuple[AgentSnapshot, ...]
    metrics: tuple[MetricSnapshot, ...]
    timeline: tuple[TimelineEvent, ...]


class DemoTransitionRequest(BaseModel):
    """State and action supplied by the browser demo."""

    model_config = ConfigDict(extra="forbid")

    current_state: DemoState
    action: DemoAction


class DemoTransitionResponse(BaseModel):
    """Validated next state and auditable event."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    previous_state: DemoState
    current_state: DemoState
    progress: int
    requires_human: bool
    event: TimelineEvent
