"""Integration tests for the shared specialist-agent registry."""

from pathlib import Path

from bi_agent.application import BIBackend
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


def test_shared_backend_mounts_bi_router() -> None:
    """BI must remain reachable through the shared backend process."""
    with TestClient(create_app(_settings(), bi_backend=BIBackend())) as client:
        response = client.get("/api/bi/status")

    assert response.status_code == 200
    assert response.json() == {
        "status": "dataset_not_configured",
        "dataset_configured": False,
        "dataset_source": None,
        "dataset_file_count": 0,
        "dataset_bytes": 0,
        "missing_files": [
            "001_TBL_CLIENTES_B2B.csv",
            "002_TBL_PLANTA_FIJA_B2B.csv",
            "003_TBL_PLANTA_MOVIL_B2B.csv",
            "004_TBL_PAGOS_B2B.csv",
            "005_TBL_FACTURAS_B2B.csv",
            "006_TBL_NOTAS_CREDITO_B2B.csv",
        ],
        "llm_available": False,
        "llm": {"provider": "opencode-go", "model": "deepseek-v4-flash"},
        "tools": [
            "data_quality_report",
            "executive_snapshot",
            "management_insights",
            "recovery_intelligence",
            "risk_concentration",
        ],
    }
