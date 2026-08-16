"""Standalone HTTP contract tests for the Collections agent."""

from fastapi.testclient import TestClient

from collections_agent.api import create_app
from collections_agent.application import CollectionsBackend


def test_standalone_health_and_status_contracts() -> None:
    app = create_app(backend=CollectionsBackend())
    with TestClient(app) as client:
        health = client.get("/health")
        status = client.get("/api/collections/status")

    assert health.status_code == 200
    assert health.json() == {"status": "ok", "service": "sonia-collections-back"}
    assert status.status_code == 200
    assert status.json()["dataset_configured"] is False
    assert set(status.json()["tools"]) == {
        "portfolio_snapshot",
        "customer_snapshot",
        "invoice_trace",
        "collection_priorities",
        "reconciliation_exceptions",
    }


def test_standalone_rejects_an_incompatible_csv() -> None:
    app = create_app(backend=CollectionsBackend())
    with TestClient(app) as client:
        response = client.post(
            "/api/collections/dataset",
            files={"files": ("otro.csv", b"NOMBRE|MONTO\nCaso|10\n", "text/csv")},
        )

    assert response.status_code == 422
    assert response.json()["detail"]["ready_for_analysis"] is False
