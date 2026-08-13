"""Integration tests for the visual demo API."""

from pathlib import Path

from fastapi.testclient import TestClient

from sonia.config import Settings
from sonia.entrypoints.api import create_app


def _settings() -> Settings:
    return Settings(
        app_name="SON-IA",
        app_version="test",
        environment="test",
        host="127.0.0.1",
        port=8080,
        log_level="INFO",
        frontend_dir=Path(__file__).resolve().parents[3] / "front",
    )


def test_visual_mvp_and_scenario_are_served() -> None:
    """The single entry point must serve both UI and its initial scenario."""
    with TestClient(create_app(_settings())) as client:
        page_response = client.get("/")
        bi_module_response = client.get("/agents/bi/config.js")
        scenario_response = client.get("/api/demo/scenario")

    assert page_response.status_code == 200
    assert "Centro de operaciones" in page_response.text
    assert bi_module_response.status_code == 200
    assert "SONIA_AGENT_UI.bi" in bi_module_response.text
    assert scenario_response.status_code == 200
    assert len(scenario_response.json()["agents"]) == 3


def test_demo_api_rejects_skipped_state() -> None:
    """HTTP callers cannot skip the invoice approval state."""
    with TestClient(create_app(_settings())) as client:
        response = client.post(
            "/api/demo/transition",
            json={
                "current_state": "NEEDS_APPROVAL",
                "action": "ANALYZE_PAYMENT",
            },
        )

    assert response.status_code == 409
    assert "not allowed" in response.json()["detail"]
