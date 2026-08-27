from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from billing_agent.app import create_app
from billing_agent.config import Settings
from billing_agent.service import BillingService
from billing_agent.work_queue import build_work_queue
from dataset_fixtures import write_sources


CUSTOMERS = """NUMERO_IDENTIFICACION_FISCAL|RAZON_SOCIAL
201|CLIENT_QUEUE
"""
FIXED_PLANT = """RAZON_SOCIAL|COD_CUENTA|STATUS_DESC
CLIENT_QUEUE|100001|Active
CLIENT_QUEUE|200002|Active
"""
MOBILE_PLANT = """RAZON_SOCIAL|COD_CUENTA|ESTADO_LINEA
"""
INVOICE_HEADER = (
    "NUMERO_IDENTIFICACION_FISCAL|RAZON_SOCIAL|COD_CLIENTE|COD_CUENTA|"
    "NRO_DOC_FISCAL|FUENTE|SISTEMA|FECHA_EMISION|FECHA_VTO|MONEDA|"
    "CHARGE_NET_AMOUNT|CHARGE_IGV_INVOICE|CHARGE_TOTAL_AMOUNT\n"
)
INVOICES = INVOICE_HEADER + """201|CLIENT_QUEUE|C1|100001|F-GAP-MAY|FACTURACION CICLICA|ISIS|2026-05-01|2026-05-31|PEN|100|18|118
201|CLIENT_QUEUE|C1|100001|F-GAP-JUL|FACTURACION CICLICA|ISIS|2026-07-01|2026-07-31|PEN|100|18|118
201|CLIENT_QUEUE|C1|100001|F-MULTI|SRC|ISIS|2026-06-01|2026-06-30||100|18|100
201|CLIENT_QUEUE|C1|100001|F-MATERIAL-PEN|SRC|ISIS|2026-06-02|2026-06-30|PEN|84.75|15.25|100
201|CLIENT_QUEUE|C1|100001|F-MATERIAL-USD|SRC|ISIS|2026-06-03|2026-06-30|USD|169.49|30.51|200
201|CLIENT_QUEUE|C1|100001|F-CLEAN|SRC|ISIS|2026-06-04|2026-06-30|PEN|100|18|118
201|CLIENT_QUEUE|C1|100001|F-MISSING|SRC|ISIS|2026-06-05|2026-06-30||100|18|118
201|CLIENT_QUEUE|C1|100001|F-ZERO|SRC|ISIS|2026-06-06|2026-06-30|PEN|0|0|0
"""
NOTES = """NUMERO_IDENTIFICACION_FISCAL|RAZON_SOCIAL|COD_CUENTA|NRO_DOC_FISCAL|FACTURA_AFECTADA|FECHAEMISION|MONEDA|MONTO_SIN_IGV|SUBTOTAL|MONTO
201|CLIENT_QUEUE|100001|NC-PEN|F-MATERIAL-PEN|2026-06-10|PEN|50.85|50.85|60
201|CLIENT_QUEUE|100001|NC-USD|F-MATERIAL-USD|2026-06-11|USD|93.22|93.22|110
"""


def write_queue_dataset(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    files = {
        "001_TBL_CLIENTES_B2B.csv": CUSTOMERS,
        "002_TBL_PLANTA_FIJA_B2B.csv": FIXED_PLANT,
        "003_TBL_PLANTA_MOVIL_B2B.csv": MOBILE_PLANT,
        "005_TBL_FACTURAS_B2B.csv": INVOICES,
        "006_TBL_NOTAS_CREDITO_B2B.csv": NOTES,
    }
    for name, content in files.items():
        (root / name).write_text(content, encoding="utf-8")
    return root


class WorkQueueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.dataset = write_queue_dataset(self.root / "queue")
        self.service = BillingService(self.dataset)
        self.queue = build_work_queue(self.service)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_endpoint_returns_summary_and_cases(self) -> None:
        client = TestClient(create_app(Settings(dataset_path=self.dataset)))

        response = client.get("/api/work-queue")

        self.assertEqual(response.status_code, 200)
        self.assertIn("summary", response.json())
        self.assertIn("cases", response.json())

    def test_actionable_invoice_is_one_grouped_case(self) -> None:
        matches = [
            item for item in self.queue["cases"] if item["invoice_id"] == "F-MULTI"
        ]

        self.assertEqual(len(matches), 1)
        self.assertEqual(
            set(matches[0]["finding_codes"]),
            {"MISSING_CURRENCY", "ARITHMETIC_MISMATCH"},
        )
        self.assertEqual(matches[0]["priority"], "HIGH")

    def test_cycle_gap_contains_customer_account_and_period(self) -> None:
        gap = next(
            item
            for item in self.queue["cases"]
            if "BILLING_CYCLE_GAP" in item["finding_codes"]
        )

        self.assertEqual(gap["customer"], "CLIENT_QUEUE")
        self.assertEqual(gap["account"], "100001")
        self.assertEqual(gap["period"], "2026-06")
        self.assertIn("mayo", gap["evidence_summary"])
        self.assertIn("julio", gap["evidence_summary"])

    def test_active_plant_without_invoice_is_revenue_risk(self) -> None:
        plant = next(
            item
            for item in self.queue["cases"]
            if "PLANT_WITHOUT_BILLING_EVIDENCE" in item["finding_codes"]
        )

        self.assertEqual(plant["account"], "200002")
        self.assertEqual(plant["risk_category"], "Riesgo de ingreso")
        self.assertIsNone(plant["amount"])
        self.assertIn("no prueba", plant["evidence_summary"].lower())

    def test_cases_are_ordered_by_explicit_priority(self) -> None:
        rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        priorities = [rank[item["priority"]] for item in self.queue["cases"]]

        self.assertEqual(priorities, sorted(priorities))
        missing = next(
            item for item in self.queue["cases"] if item["invoice_id"] == "F-MISSING"
        )
        self.assertEqual(missing["priority"], "LOW")

    def test_amounts_never_claim_loss_and_currencies_are_separate(self) -> None:
        serialized = str(self.queue).lower()
        totals = {
            item["currency"]: item["amount"]
            for item in self.queue["summary"]["quantifiable_amounts_by_currency"]
        }

        self.assertNotIn("pérdida confirmada", serialized)
        self.assertEqual(totals["PEN"], 60.0)
        self.assertEqual(totals["USD"], 110.0)
        self.assertEqual(set(totals), {"PEN", "USD"})

    def test_clean_dataset_has_empty_queue(self) -> None:
        clean = write_sources(self.root / "clean", invoice_count=2)

        queue = build_work_queue(BillingService(clean))

        self.assertEqual(queue["cases"], [])
        self.assertEqual(queue["summary"]["cases_requiring_attention"], 0)
        self.assertEqual(queue["summary"]["invoices_without_documentary_findings"], 2)

    def test_frontend_exports_excel_compatible_csv_and_drilldowns(self) -> None:
        app_js = (
            Path(__file__).resolve().parents[2] / "FRONT" / "assets" / "app.js"
        ).read_text(encoding="utf-8")

        self.assertIn('const csv = "\\uFEFF"', app_js)
        self.assertIn('row.map(csvCell).join(";")', app_js)
        self.assertIn("Acción recomendada", app_js)
        self.assertIn("function openCase", app_js)
        self.assertIn('apiUrl("/api/work-queue"', app_js)


if __name__ == "__main__":
    unittest.main()
