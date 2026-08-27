"""Integration coverage for Camila's Billing agent in the shared backend."""

from pathlib import Path

from fastapi.testclient import TestClient

from billing_agent.data import load_dataset_bytes
from billing_agent.service import BillingService
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


def _billing_sources() -> dict[str, str]:
    return {
        "001_TBL_CLIENTES_B2B.csv": ("NUMERO_IDENTIFICACION_FISCAL|RAZON_SOCIAL\n201|CLIENT_001\n"),
        "002_TBL_PLANTA_FIJA_B2B.csv": (
            "RAZON_SOCIAL|COD_CUENTA|STATUS_DESC\nCLIENT_001|ACC_001|Active\n"
        ),
        "003_TBL_PLANTA_MOVIL_B2B.csv": (
            "RAZON_SOCIAL|COD_CUENTA|ESTADO_LINEA\nCLIENT_001|ACC_001|Activo\n"
        ),
        "005_TBL_FACTURAS_B2B.csv": (
            "NUMERO_IDENTIFICACION_FISCAL|RAZON_SOCIAL|COD_CLIENTE|COD_CUENTA|"
            "NRO_DOC_FISCAL|FUENTE|SISTEMA|FECHA_EMISION|FECHA_VTO|MONEDA|"
            "CHARGE_NET_AMOUNT|CHARGE_IGV_INVOICE|CHARGE_TOTAL_AMOUNT\n"
            "201|CLIENT_001|C1|ACC_001|F001|FACTURACION CICLICA|S1|2026-08-01|"
            "2026-08-31|PEN|100|18|118\n"
        ),
        "006_TBL_NOTAS_CREDITO_B2B.csv": (
            "NUMERO_IDENTIFICACION_FISCAL|RAZON_SOCIAL|COD_CUENTA|NRO_DOC_FISCAL|"
            "FACTURA_AFECTADA|FECHAEMISION|MONEDA|MONTO_SIN_IGV|SUBTOTAL|MONTO\n"
            "201|CLIENT_001|ACC_001|NC001|F001|2026-08-02|PEN|10|10|11.8\n"
        ),
    }


def _billing_files() -> list[tuple[str, tuple[str, bytes, str]]]:
    return [
        ("files", (name, content.encode("utf-8"), "text/csv"))
        for name, content in _billing_sources().items()
    ]


def test_shared_backend_mounts_billing_and_rejects_direct_manual_upload() -> None:
    """Shared Billing must consume only the Supervisor-owned default dataset."""
    with TestClient(create_app(_settings())) as client:
        initial = client.get("/api/billing/status")
        uploaded = client.post("/api/billing/datasets", files=_billing_files())

    assert initial.status_code == 200
    assert initial.json()["status"] == "dataset_not_configured"
    assert uploaded.status_code == 403
    assert "Supervisor" in uploaded.json()["detail"]


def test_shared_backend_exposes_billing_work_queue() -> None:
    """The additive queue is reachable through Billing's integrated namespace."""
    application = create_app(_settings())
    billing_mount = next(
        route
        for route in application.routes
        if getattr(route, "name", None) == "billing-agent"
    )
    service = BillingService.from_dataset(
        load_dataset_bytes(
            {name: content.encode("utf-8") for name, content in _billing_sources().items()}
        )
    )
    billing_mount.app.state.dataset_registry.publish_default(service, origin="integration-test")

    with TestClient(application) as client:
        response = client.get("/api/billing/work-queue")

    assert response.status_code == 200
    assert response.json()["summary"]["invoice_documents"] == 1
    assert response.json()["cases"] == []
