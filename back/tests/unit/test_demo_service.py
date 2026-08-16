"""Unit tests for the controlled visual demo transitions."""

import pytest

from sonia.application.demo_service import build_demo_scenario, transition_demo
from sonia.domain.demo import DemoAction, DemoState, DemoTransitionRequest


def test_demo_scenario_contains_three_agents() -> None:
    """The first visual MVP must expose exactly three specialist agents."""
    scenario = build_demo_scenario()

    assert [agent.agent_id for agent in scenario.agents] == [
        "billing",
        "collections",
        "bi",
    ]
    assert scenario.current_state is DemoState.VALIDATING


def test_demo_happy_path_requires_human_gates() -> None:
    """The deterministic journey must preserve both human approvals."""
    steps = (
        (DemoAction.VALIDATE_PXQ, DemoState.NEEDS_APPROVAL, True),
        (DemoAction.APPROVE_INVOICE, DemoState.ISSUED, False),
        (DemoAction.ANALYZE_PAYMENT, DemoState.PAYMENT_DETECTED, False),
        (DemoAction.PREPARE_RECONCILIATION, DemoState.RECONCILING, True),
        (DemoAction.CONFIRM_PAYMENT, DemoState.ANALYZING, False),
        (DemoAction.GENERATE_INSIGHTS, DemoState.CLOSED, False),
    )
    current_state = DemoState.VALIDATING

    for action, expected_state, requires_human in steps:
        response = transition_demo(
            DemoTransitionRequest(current_state=current_state, action=action)
        )
        assert response.current_state is expected_state
        assert response.requires_human is requires_human
        current_state = response.current_state


def test_demo_rejects_invalid_transition() -> None:
    """The supervisor must reject attempts to skip the human approval gate."""
    with pytest.raises(ValueError, match="not allowed"):
        transition_demo(
            DemoTransitionRequest(
                current_state=DemoState.NEEDS_APPROVAL,
                action=DemoAction.ANALYZE_PAYMENT,
            )
        )
