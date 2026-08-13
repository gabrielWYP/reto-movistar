"""Deterministic orchestration for the first SON-IA visual MVP."""

from dataclasses import dataclass

from sonia.domain.demo import (
    AgentSnapshot,
    AgentStatus,
    DemoAction,
    DemoScenarioResponse,
    DemoState,
    DemoTransitionRequest,
    DemoTransitionResponse,
    MetricSnapshot,
    TimelineEvent,
)


@dataclass(frozen=True, slots=True)
class _Transition:
    """Internal transition definition for the visual journey."""

    next_state: DemoState
    progress: int
    actor: str
    title: str
    detail: str
    tone: str
    requires_human: bool = False


_TRANSITIONS: dict[tuple[DemoState, DemoAction], _Transition] = {
    (DemoState.VALIDATING, DemoAction.VALIDATE_PXQ): _Transition(
        next_state=DemoState.NEEDS_APPROVAL,
        progress=28,
        actor="Agente Facturación",
        title="PxQ validado con evidencia",
        detail="5 campos críticos y 3 reglas deterministas superadas.",
        tone="blue",
        requires_human=True,
    ),
    (DemoState.NEEDS_APPROVAL, DemoAction.APPROVE_INVOICE): _Transition(
        next_state=DemoState.ISSUED,
        progress=48,
        actor="Aprobación humana",
        title="Emisión simulada autorizada",
        detail="La factura FAC-DEMO-001 quedó emitida y trazada.",
        tone="green",
    ),
    (DemoState.ISSUED, DemoAction.ANALYZE_PAYMENT): _Transition(
        next_state=DemoState.PAYMENT_DETECTED,
        progress=68,
        actor="Agente Cobranzas",
        title="Pago informado detectado",
        detail="Mensaje clasificado y asociado a FAC-DEMO-001 con 96% de confianza.",
        tone="violet",
    ),
    (DemoState.PAYMENT_DETECTED, DemoAction.PREPARE_RECONCILIATION): _Transition(
        next_state=DemoState.RECONCILING,
        progress=86,
        actor="Agente Recaudo",
        title="Conciliación preparada",
        detail="Monto, moneda, cliente y referencia coinciden; falta confirmación humana.",
        tone="amber",
        requires_human=True,
    ),
    (DemoState.RECONCILING, DemoAction.CONFIRM_PAYMENT): _Transition(
        next_state=DemoState.CLOSED,
        progress=100,
        actor="Aprobación humana",
        title="Pago aplicado y caso cerrado",
        detail="El ciclo E2E terminó sin diferencias y conserva toda la auditoría.",
        tone="green",
    ),
}


def build_demo_scenario() -> DemoScenarioResponse:
    """Return the stable synthetic scenario used by the visual MVP."""
    return DemoScenarioResponse(
        case_id="SON-2026-0031",
        customer_name="Andes Logística Demo",
        service_name="Conectividad empresarial",
        invoice_reference="FAC-DEMO-001",
        invoice_amount="18,450.00",
        currency="PEN",
        current_state=DemoState.VALIDATING,
        progress=12,
        agents=(
            AgentSnapshot(
                agent_id="billing",
                name="Facturación",
                specialty="Control PxQ",
                summary="Valida cantidad, tarifa, periodo y total antes de emitir.",
                status=AgentStatus.ACTIVE,
                confidence=98,
                processed_items=5,
                evidence_count=5,
            ),
            AgentSnapshot(
                agent_id="collections",
                name="Cobranzas",
                specialty="Intención de pago",
                summary="Clasifica comunicaciones y extrae referencias con evidencia.",
                status=AgentStatus.PENDING,
                confidence=96,
                processed_items=1,
                evidence_count=3,
            ),
            AgentSnapshot(
                agent_id="reconciliation",
                name="Recaudo",
                specialty="Conciliación",
                summary="Compara factura, pago, moneda, cliente y ventana temporal.",
                status=AgentStatus.PENDING,
                confidence=100,
                processed_items=1,
                evidence_count=4,
            ),
        ),
        metrics=(
            MetricSnapshot(label="Tiempo estimado", value="4 min", trend="-83%"),
            MetricSnapshot(label="Campos con evidencia", value="100%", trend="5 de 5"),
            MetricSnapshot(label="Acciones automáticas", value="0", trend="control humano"),
        ),
        timeline=(
            TimelineEvent(
                actor="Supervisor SON-IA",
                title="Caso creado",
                detail="PxQ_DEMO_031.csv registrado y asignado a Facturación.",
                time="10:42",
                tone="navy",
            ),
            TimelineEvent(
                actor="Sistema",
                title="Evidencia preservada",
                detail="Hash y ubicación de origen registrados para auditoría.",
                time="10:42",
                tone="gray",
            ),
        ),
    )


def transition_demo(request: DemoTransitionRequest) -> DemoTransitionResponse:
    """Validate and execute one explicit transition without persistent side effects."""
    transition = _TRANSITIONS.get((request.current_state, request.action))
    if transition is None:
        raise ValueError(
            f"Action {request.action.value} is not allowed from {request.current_state.value}"
        )

    return DemoTransitionResponse(
        previous_state=request.current_state,
        current_state=transition.next_state,
        progress=transition.progress,
        requires_human=transition.requires_human,
        event=TimelineEvent(
            actor=transition.actor,
            title=transition.title,
            detail=transition.detail,
            time="ahora",
            tone=transition.tone,
        ),
    )
