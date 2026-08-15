"""Integration tests for the shared specialist-agent registry."""

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
        frontend_dir=Path("front").resolve(),
    )


def test_registry_exposes_the_three_integrated_agents() -> None:
    """The API must expose one stable package per source branch."""
    with TestClient(create_app(_settings())) as client:
        response = client.get("/api/agents")

    assert response.status_code == 200
    assert [(item["agent_id"], item["source_branch"]) for item in response.json()] == [
        ("billing", "camila"),
        ("collections", "Arian"),
        ("bi", "Mauricio"),
    ]


def test_unknown_agent_returns_not_found() -> None:
    """Unknown agent identifiers must fail with an explicit HTTP contract."""
    with TestClient(create_app(_settings())) as client:
        response = client.get("/api/agents/unknown")

    assert response.status_code == 404
