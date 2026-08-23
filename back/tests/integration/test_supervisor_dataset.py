"""Integration contract for Supervisor-owned dataset publication."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sonia.config import Settings
from sonia.entrypoints.api import create_app

ROOT = Path(__file__).resolve().parents[3]


def _settings() -> Settings:
    return Settings(
        app_name="SON-IA",
        app_version="test",
        environment="test",
        host="127.0.0.1",
        port=8080,
        log_level="INFO",
        frontend_dir=(ROOT / "front").resolve(),
    )


def _dataset_files(
    *,
    billing_compatible: bool = True,
    invoice_total: str = "118",
) -> list[tuple[str, tuple[str, bytes, str]]]:
    invoice_columns = [
        "NUMERO_IDENTIFICACION_FISCAL",
        "RAZON_SOCIAL",
        "COD_CLIENTE",
        "COD_CUENTA",
        "NRO_DOC_FISCAL",
        "FUENTE",
        "SISTEMA",
        "FECHA_EMISION",
        "FECHA_VTO",
    ]
    invoice_values = [
        "201",
        "CLIENT_001",
        "C1",
        "ACC_001",
        "F001",
        "FACTURACION CICLICA",
        "S1",
        "2026-08-01",
        "2026-08-31",
    ]
    if billing_compatible:
        invoice_columns.append("MONEDA")
        invoice_values.append("PEN")
    invoice_columns.extend(["CHARGE_NET_AMOUNT", "CHARGE_IGV_INVOICE", "CHARGE_TOTAL_AMOUNT"])
    invoice_values.extend(["100", "18", invoice_total])

    sources = {
        "001_TBL_CLIENTES_B2B.csv": ("NUMERO_IDENTIFICACION_FISCAL|RAZON_SOCIAL\n201|CLIENT_001\n"),
        "002_TBL_PLANTA_FIJA_B2B.csv": (
            "RAZON_SOCIAL|COD_CLIENTE|COD_CUENTA|CICLO|STATUS_DESC\n"
            "CLIENT_001|C1|ACC_001|1|Active\n"
        ),
        "003_TBL_PLANTA_MOVIL_B2B.csv": (
            "RAZON_SOCIAL|COD_CLIENTE|COD_CUENTA|PRODUCTO|ESTADO_LINEA\n"
            "CLIENT_001|C1|ACC_001|MOVIL|Activo\n"
        ),
        "004_TBL_PAGOS_B2B.csv": (
            "RAZON_SOCIAL|COD_CUENTA|FACTURA_AFECTADA|FECHA_PAGO|MONTO_PAGADO\n"
            "CLIENT_001|ACC_001|F001|2026-08-15|40\n"
        ),
        "005_TBL_FACTURAS_B2B.csv": (
            "|".join(invoice_columns) + "\n" + "|".join(invoice_values) + "\n"
        ),
        "006_TBL_NOTAS_CREDITO_B2B.csv": (
            "NUMERO_IDENTIFICACION_FISCAL|RAZON_SOCIAL|COD_CUENTA|NRO_DOC_FISCAL|"
            "FACTURA_AFECTADA|FECHAEMISION|MONEDA|MONTO_SIN_IGV|SUBTOTAL|MONTO\n"
            "201|CLIENT_001|ACC_001|NC001|F001|2026-08-02|PEN|10|10|11.8\n"
        ),
    }
    return [
        ("files", (name, content.encode("utf-8"), "text/csv")) for name, content in sources.items()
    ]


def test_supervisor_atomically_publishes_one_dataset_to_all_agents() -> None:
    with TestClient(create_app(_settings())) as client:
        published = client.post("/api/supervisor/dataset", files=_dataset_files())
        supervisor = client.get("/api/supervisor/dataset")
        billing = client.get("/api/billing/status")
        collections = client.get("/api/collections/status")
        bi = client.get("/api/bi/status")

        billing_view = client.get("/api/billing/health")
        collections_view = client.get(
            "/api/collections/portfolio",
            params={"as_of_date": "2026-08-31"},
        )
        bi_view = client.post(
            "/api/bi/tools/executive_snapshot",
            json={"as_of_date": "2026-08-31", "parameters": {}},
        )

    assert published.status_code == 200
    assert supervisor.json()["dataset_source"] == "supervisor"
    assert supervisor.json()["dataset_file_count"] == 6
    assert all(state["dataset_configured"] for state in supervisor.json()["agents"].values())
    assert billing.json()["origin"] == "Supervisor SON-IA"
    assert billing.json()["dataset_id"] == "default"
    assert collections.json()["dataset_source"] == "supervisor"
    assert bi.json()["dataset_source"] == "supervisor"
    assert billing_view.status_code == 200
    assert collections_view.status_code == 200
    assert bi_view.status_code == 200


def test_agent_upload_routes_cannot_bypass_supervisor() -> None:
    files = {"files": ("sample.csv", b"A|B\n1|2\n", "text/csv")}
    with TestClient(create_app(_settings())) as client:
        assert client.post("/api/billing/datasets", files=files).status_code == 403
        assert client.post("/api/collections/dataset", files=files).status_code == 403
        assert client.post("/api/bi/dataset", files=files).status_code == 403


def test_failed_cross_agent_validation_does_not_publish_partial_state() -> None:
    with TestClient(create_app(_settings())) as client:
        accepted = client.post("/api/supervisor/dataset", files=_dataset_files())
        before = client.get(
            "/api/collections/portfolio",
            params={"as_of_date": "2026-08-31"},
        )
        rejected = client.post(
            "/api/supervisor/dataset",
            files=_dataset_files(billing_compatible=False, invoice_total="236"),
        )
        status = client.get("/api/supervisor/dataset")
        after = client.get(
            "/api/collections/portfolio",
            params={"as_of_date": "2026-08-31"},
        )

    assert accepted.status_code == 200
    assert rejected.status_code == 422
    assert "MONEDA" in rejected.json()["detail"]
    assert status.json()["dataset_configured"] is True
    assert before.json()["metrics"] == after.json()["metrics"]


def test_only_supervisor_frontend_exposes_manual_file_selection() -> None:
    supervisor = (ROOT / "front" / "index.html").read_text(encoding="utf-8")
    supervisor_js = (ROOT / "front" / "assets" / "app.js").read_text(encoding="utf-8")
    assert 'id="supervisor-dataset-files"' in supervisor
    assert 'type="file"' in supervisor
    assert "/api/supervisor/dataset" in supervisor_js

    specialists = (
        ROOT / "Agente BI" / "FRONT",
        ROOT / "Agente Cobranzas" / "FRONT",
        ROOT / "Agente_Facturacion" / "FRONT",
    )
    for frontend in specialists:
        html = (frontend / "index.html").read_text(encoding="utf-8")
        javascript = (frontend / "assets" / "app.js").read_text(encoding="utf-8")
        assert 'type="file"' not in html
        assert "new FormData()" not in javascript
