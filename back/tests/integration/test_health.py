"""Integration tests for the public application boundary."""

from pathlib import Path

from fastapi.testclient import TestClient

from sonia.config import Settings
from sonia.entrypoints.api import create_app


def test_health_contract() -> None:
    """The K3S health endpoint must remain stable and non-sensitive."""
    settings = Settings(
        app_name="SON-IA",
        app_version="test",
        environment="test",
        host="127.0.0.1",
        port=8080,
        log_level="INFO",
        frontend_dir=Path("frontend").resolve(),
    )

    with TestClient(create_app(settings)) as client:
        response = client.get("/health", headers={"x-request-id": "test-request"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "test-request"
    assert response.json() == {
        "status": "ok",
        "service": "SON-IA",
        "version": "test",
        "environment": "test",
    }
