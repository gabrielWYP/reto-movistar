"""Integration tests for Cobranzas inside the shared FastAPI process."""

from pathlib import Path
from unittest.mock import Mock, patch

from bi_agent.application import BIBackend
from collections_agent.application import CollectionsBackend
from collections_agent.data import SoniaDataset
from collections_agent.llm_runtime import OpenAIRuntime
from collections_agent.service import CollectionsService
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


def _collections_backend() -> CollectionsBackend:
    dataset = SoniaDataset(
        customers=[{"RAZON_SOCIAL": "CLIENT_TEST"}],
        fixed_plant=[],
        mobile_plant=[],
        payments=[
            {
                "RAZON_SOCIAL": "CLIENT_TEST",
                "COD_CUENTA": "ACC-1",
                "FACTURA_AFECTADA": "FAC-001",
                "FECHA_PAGO": "2026-07-15",
                "MONTO_PAGADO": "40.50",
            }
        ],
        invoices=[
            {
                "RAZON_SOCIAL": "CLIENT_TEST",
                "COD_CLIENTE": "001",
                "COD_CUENTA": "ACC-1",
                "NRO_DOC_FISCAL": "FAC-001",
                "FECHA_EMISION": "2026-07-01",
                "FECHA_VTO": "2026-07-20",
                "CHARGE_TOTAL_AMOUNT": "100.50",
            }
        ],
        credit_notes=[],
    )
    return CollectionsBackend(service=CollectionsService.from_dataset(dataset))


def test_shared_backend_mounts_collections_router() -> None:
    app = create_app(
        _settings(),
        bi_backend=BIBackend(),
        collections_backend=_collections_backend(),
    )
    with TestClient(app) as client:
        status = client.get("/api/collections/status")
        portfolio = client.get("/api/collections/portfolio", params={"as_of_date": "2026-08-07"})

    assert status.status_code == 200
    assert status.json()["dataset_configured"] is True
    assert portfolio.status_code == 200
    assert portfolio.json()["agent"] == "collections"
    assert portfolio.json()["metrics"]["outstanding_balance"] == 60.0


def test_collections_dataset_upload_is_validated_and_used() -> None:
    app = create_app(
        _settings(),
        bi_backend=BIBackend(),
        collections_backend=CollectionsBackend(),
    )
    invoices = (
        b"RAZON_SOCIAL|COD_CLIENTE|COD_CUENTA|NRO_DOC_FISCAL|"
        b"FECHA_EMISION|FECHA_VTO|CHARGE_TOTAL_AMOUNT\n"
        b"CLIENT_UPLOAD|002|ACC-2|FAC-002|2026-07-01|2026-07-20|75.00\n"
    )

    with TestClient(app) as client:
        before = client.get("/api/collections/portfolio")
        uploaded = client.post(
            "/api/collections/dataset",
            files={"files": ("facturas.csv", invoices, "text/csv")},
        )
        after = client.get(
            "/api/collections/invoice",
            params={"id": "FAC-002", "as_of_date": "2026-08-07"},
        )

    assert before.status_code == 503
    assert uploaded.status_code == 200
    assert uploaded.json()["ready_for_analysis"] is True
    assert after.status_code == 200
    assert after.json()["metrics"]["outstanding_balance"] == 75.0


def test_collections_rejects_an_incompatible_csv_without_mixing_data() -> None:
    backend = _collections_backend()
    app = create_app(
        _settings(),
        bi_backend=BIBackend(),
        collections_backend=backend,
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/collections/dataset",
            files={"files": ("otro.csv", b"NOMBRE|MONTO\nCaso|10\n", "text/csv")},
        )
        existing = client.get(
            "/api/collections/invoice",
            params={"id": "FAC-001", "as_of_date": "2026-08-07"},
        )

    assert response.status_code == 422
    assert existing.status_code == 200


def test_collections_query_uses_openai_tools_and_reports_ai_mode() -> None:
    responses = [
        {
            "output": [
                {
                    "type": "function_call",
                    "call_id": "call-1",
                    "name": "collection_priorities",
                    "arguments": '{"limit":5}',
                }
            ],
            "usage": {"input_tokens": 20, "output_tokens": 5, "total_tokens": 25},
        },
        {
            "output": [{"type": "message", "content": []}],
            "output_text": "Prioriza el saldo vencido documentado.",
            "usage": {"input_tokens": 30, "output_tokens": 8, "total_tokens": 38},
        },
    ]
    runtime = OpenAIRuntime(create_response=Mock(side_effect=responses))
    backend = CollectionsBackend(service=_collections_backend().service(), runtime=runtime)
    app = create_app(_settings(), bi_backend=BIBackend(), collections_backend=backend)

    with patch.dict("os.environ", {"OPENAI_API_KEY": "test-only"}, clear=True):
        with TestClient(app) as client:
            response = client.post(
                "/api/collections/query",
                json={"question": "¿A quién priorizo?", "as_of_date": "2026-08-07"},
            )

    assert response.status_code == 200
    assert response.json()["mode"] == "llm"
    assert response.json()["tool_used"] == "collection_priorities"
    assert response.json()["llm"]["provider"] == "openai"
    assert response.json()["usage"]["total_tokens"] == 63


def test_collections_query_reports_provider_failure_without_keyword_fallback() -> None:
    runtime = OpenAIRuntime(create_response=Mock(side_effect=RuntimeError("provider unavailable")))
    backend = CollectionsBackend(service=_collections_backend().service(), runtime=runtime)
    app = create_app(_settings(), bi_backend=BIBackend(), collections_backend=backend)

    with patch.dict("os.environ", {"OPENAI_API_KEY": "test-only"}, clear=True):
        with TestClient(app) as client:
            response = client.post(
                "/api/collections/query",
                json={"question": "Resume la cartera", "as_of_date": "2026-08-07"},
            )

    assert response.status_code == 503
    assert "provider unavailable" in response.json()["detail"]
