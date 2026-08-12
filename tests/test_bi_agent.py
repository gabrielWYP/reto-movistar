from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from bi_agent.service import BIService


HEADERS = {
    "001_TBL_CLIENTES_B2B.csv": ["SEGMENTO_PAIS", "TIPO_DOCUMENTO", "NUMERO_IDENTIFICACION_FISCAL", "RAZON_SOCIAL", "SUNAT_ESTADO_RUC", "SUNAT_ESTADO_CONTRIBUYENTE", "SUNAT_DEPARTAMENTO", "SUNAT_PROVINCIA", "SUNAT_DISTRITO"],
    "002_TBL_PLANTA_FIJA_B2B.csv": ["SEGMENTO_PAIS", "NUMERO_IDENTIFICACION_FISCAL", "RAZON_SOCIAL", "COD_CLIENTE", "COD_CUENTA", "SUB_MAIN_OFFER_DESC"],
    "003_TBL_PLANTA_MOVIL_B2B.csv": ["SEGMENTO_PAIS", "NUMERO_IDENTIFICACION_FISCAL", "RAZON_SOCIAL", "COD_CLIENTE", "COD_CUENTA", "PRODUCT_DESC"],
    "004_TBL_PAGOS_B2B.csv": ["TIPO_DOCUMENTO", "NRO_IDENTIFICACION_FISCAL", "RAZON_SOCIAL", "COD_CLIENTE", "COD_CUENTA", "SISTEMA", "FACTURA_AFECTADA", "FECHA_PAGO", "MONEDA_FACTURA", "SUBTOTAL", "IGV", "MONTO_PAGADO"],
    "005_TBL_FACTURAS_B2B.csv": ["NUMERO_IDENTIFICACION_FISCAL", "RAZON_SOCIAL", "COD_CLIENTE", "COD_CUENTA", "NRO_DOC_FISCAL", "FUENTE", "SISTEMA", "FECHA_EMISION", "FECHA_VTO", "MONEDA", "CHARGE_NET_AMOUNT", "CHARGE_IGV_INVOICE", "CHARGE_TOTAL_AMOUNT"],
    "006_TBL_NOTAS_CREDITO_B2B.csv": ["NUMERO_IDENTIFICACION_FISCAL", "RAZON_SOCIAL", "COD_CLIENTE", "COD_CUENTA", "NRO_DOC_FISCAL", "FUENTE", "SISTEMA", "FACTURA_AFECTADA", "FECHAEMISION", "MONEDA", "MONTO_SIN_IGV", "SUBTOTAL", "MONTO"],
}


def write_dataset(folder: Path) -> None:
    rows = {
        "001_TBL_CLIENTES_B2B.csv": [
            {"SEGMENTO_PAIS": "SEG_A", "TIPO_DOCUMENTO": "RUC", "NUMERO_IDENTIFICACION_FISCAL": "RUC_1", "RAZON_SOCIAL": "CLIENT_A", "SUNAT_ESTADO_RUC": "HABIDO", "SUNAT_ESTADO_CONTRIBUYENTE": "ACTIVO", "SUNAT_DEPARTAMENTO": "LIMA", "SUNAT_PROVINCIA": "LIMA", "SUNAT_DISTRITO": "MIRAFLORES"},
            {"SEGMENTO_PAIS": "SEG_B", "TIPO_DOCUMENTO": "RUC", "NUMERO_IDENTIFICACION_FISCAL": "RUC_2", "RAZON_SOCIAL": "CLIENT_B", "SUNAT_ESTADO_RUC": "HABIDO", "SUNAT_ESTADO_CONTRIBUYENTE": "ACTIVO", "SUNAT_DEPARTAMENTO": "CUSCO", "SUNAT_PROVINCIA": "CUSCO", "SUNAT_DISTRITO": "CUSCO"},
        ],
        "002_TBL_PLANTA_FIJA_B2B.csv": [
            {"SEGMENTO_PAIS": "SEG_A", "NUMERO_IDENTIFICACION_FISCAL": "RUC_1", "RAZON_SOCIAL": "CLIENT_A", "COD_CLIENTE": "C1", "COD_CUENTA": "001", "SUB_MAIN_OFFER_DESC": "FIXED_A"},
            {"SEGMENTO_PAIS": "SEG_A", "NUMERO_IDENTIFICACION_FISCAL": "RUC_1", "RAZON_SOCIAL": "CLIENT_A", "COD_CLIENTE": "C1", "COD_CUENTA": "001", "SUB_MAIN_OFFER_DESC": "FIXED_B"},
        ],
        "003_TBL_PLANTA_MOVIL_B2B.csv": [
            {"SEGMENTO_PAIS": "SEG_A", "NUMERO_IDENTIFICACION_FISCAL": "RUC_1", "RAZON_SOCIAL": "CLIENT_A", "COD_CLIENTE": "C1", "COD_CUENTA": "001", "PRODUCT_DESC": "MOBILE_A"},
        ],
        "004_TBL_PAGOS_B2B.csv": [
            {"TIPO_DOCUMENTO": "Pago", "NRO_IDENTIFICACION_FISCAL": "DIFFERENT_RUC", "RAZON_SOCIAL": "CLIENT_A", "COD_CLIENTE": "C1", "COD_CUENTA": "001", "SISTEMA": "SYS", "FACTURA_AFECTADA": "INV_A", "FECHA_PAGO": "2026-07-15", "MONEDA_FACTURA": "PEN", "SUBTOTAL": "50", "IGV": "0", "MONTO_PAGADO": "50"},
            {"TIPO_DOCUMENTO": "Pago", "NRO_IDENTIFICACION_FISCAL": "DIFFERENT_RUC", "RAZON_SOCIAL": "CLIENT_A", "COD_CLIENTE": "C1", "COD_CUENTA": "001", "SISTEMA": "SYS", "FACTURA_AFECTADA": "INV_A", "FECHA_PAGO": "2026-08-05", "MONEDA_FACTURA": "PEN", "SUBTOTAL": "20", "IGV": "0", "MONTO_PAGADO": "20"},
            {"TIPO_DOCUMENTO": "Pago", "NRO_IDENTIFICACION_FISCAL": "USD_RUC", "RAZON_SOCIAL": "CLIENT_B", "COD_CLIENTE": "C2", "COD_CUENTA": "002", "SISTEMA": "SYS", "FACTURA_AFECTADA": "MISSING_USD", "FECHA_PAGO": "2026-07-20", "MONEDA_FACTURA": "USD", "SUBTOTAL": "999", "IGV": "0", "MONTO_PAGADO": "999"},
        ],
        "005_TBL_FACTURAS_B2B.csv": [
            {"NUMERO_IDENTIFICACION_FISCAL": "BAD_RUC", "RAZON_SOCIAL": "CLIENT_A", "COD_CLIENTE": "C1", "COD_CUENTA": "001", "NRO_DOC_FISCAL": "INV_A", "FUENTE": "CICLICA", "SISTEMA": "SYS", "FECHA_EMISION": "20260701", "FECHA_VTO": "2026-07-10", "MONEDA": "PEN", "CHARGE_NET_AMOUNT": "100", "CHARGE_IGV_INVOICE": "0", "CHARGE_TOTAL_AMOUNT": "100"},
            {"NUMERO_IDENTIFICACION_FISCAL": "RUC_2", "RAZON_SOCIAL": "CLIENT_B", "COD_CLIENTE": "C2", "COD_CUENTA": "002", "NRO_DOC_FISCAL": "INV_B", "FUENTE": "CICLICA", "SISTEMA": "SYS", "FECHA_EMISION": "20260701", "FECHA_VTO": "2026-08-10", "MONEDA": "PEN", "CHARGE_NET_AMOUNT": "200", "CHARGE_IGV_INVOICE": "0", "CHARGE_TOTAL_AMOUNT": "200"},
        ],
        "006_TBL_NOTAS_CREDITO_B2B.csv": [
            {"NUMERO_IDENTIFICACION_FISCAL": "BAD_RUC", "RAZON_SOCIAL": "CLIENT_A", "COD_CLIENTE": "C1", "COD_CUENTA": "001", "NRO_DOC_FISCAL": "NC_A", "FUENTE": "NOTA", "SISTEMA": "SYS", "FACTURA_AFECTADA": "INV_A", "FECHAEMISION": "20260720", "MONEDA": "PEN", "MONTO_SIN_IGV": "10", "SUBTOTAL": "0", "MONTO": "10"},
        ],
    }
    for name, header in HEADERS.items():
        with (folder / name).open("w", encoding="latin1", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=header, delimiter="|")
            writer.writeheader()
            writer.writerows(rows[name])


class BICoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.dataset = Path(self.temp.name)
        write_dataset(self.dataset)
        self.service = BIService(self.dataset)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_executive_is_as_of_and_pen_only(self):
        response = self.service.executive_snapshot("2026-07-31")
        metrics = response["metrics"]
        self.assertEqual(response["contract_version"], "1.0")
        self.assertEqual(response["agent"], "bi")
        self.assertEqual(metrics["currency"], "PEN")
        self.assertEqual(metrics["total_billed"], 300.0)
        self.assertEqual(metrics["total_paid_linked"], 50.0)
        self.assertEqual(metrics["credit_notes_linked"], 10.0)
        self.assertEqual(metrics["outstanding_balance"], 240.0)
        self.assertEqual(metrics["overdue_balance"], 40.0)
        self.assertEqual(response["data_quality"]["as_of_exclusions"]["payments_after_as_of_count"], 1)
        self.assertEqual(response["data_quality"]["as_of_exclusions"]["unmatched_payment_amount_pen"], 0.0)

    def test_plant_is_summarized_before_enrichment_and_does_not_duplicate_money(self):
        response = self.service.risk_concentration("SERVICE_PROFILE", "outstanding_balance", 10, "2026-07-31")
        self.assertEqual(response["metrics"]["metric_total"], 240.0)
        groups = response["evidence"][0]["value"]
        fixed_mobile = next(group for group in groups if group["value"] == "FIXED_AND_MOBILE")
        self.assertEqual(fixed_mobile["outstanding_balance"], 40.0)

    def test_pareto_is_reproducible_and_fully_evidenced(self):
        first = self.service.risk_concentration("SEGMENTO_PAIS", "overdue_balance", 10, "2026-07-31")
        second = self.service.risk_concentration("SEGMENTO_PAIS", "overdue_balance", 10, "2026-07-31")
        executive = self.service.executive_snapshot("2026-07-31")
        self.assertEqual(first["evidence"], second["evidence"])
        self.assertEqual(first["evidence"][0]["value"][0]["value"], "SEG_A")
        self.assertEqual(first["findings"][0]["evidence_refs"], ["concentration_by_dimension"])
        self.assertEqual(first["metrics"]["metric_total"], executive["metrics"]["overdue_balance"])

    def test_quality_report_documents_canonical_keys(self):
        response = self.service.data_quality_report("2026-07-31")
        self.assertEqual(response["data_quality"]["join_rules"]["customer"], "RAZON_SOCIAL")
        self.assertEqual(response["data_quality"]["join_rules"]["document"], "NRO_DOC_FISCAL -> FACTURA_AFECTADA")
        self.assertTrue(response["data_quality"]["quality_checks"]["ruc_join_disabled"])

    def assert_evidence_traceable(self, response):
        evidence_ids = {item["id"] for item in response["evidence"]}
        for item in response["findings"] + response["alerts"] + response["recommended_actions"]:
            self.assertIn("evidence_refs", item)
            self.assertTrue(item["evidence_refs"])
            self.assertTrue(set(item["evidence_refs"]).issubset(evidence_ids))

    def test_recovery_is_reproducible_pen_only_and_does_not_duplicate_plant_amounts(self):
        first = self.service.recovery_intelligence("2026-07-31", "PORTFOLIO", "SEGMENTO_PAIS", 10)
        second = self.service.recovery_intelligence("2026-07-31", "PORTFOLIO", "SEGMENTO_PAIS", 10)
        self.assertEqual(first, second)
        self.assertEqual(first["agent"], "bi")
        self.assertEqual(first["metrics"]["currency"], "PEN")
        self.assertEqual(first["metrics"]["exposure_total"], 240.0)
        self.assertEqual(first["metrics"]["overdue_balance"], 40.0)
        self.assertEqual(first["metrics"]["addressable_exposure"], 40.0)
        self.assert_evidence_traceable(first)

    def test_recovery_pareto_and_dimension_percentages_are_consistent(self):
        response = self.service.recovery_intelligence("2026-07-31")
        customers = response["evidence"][0]["value"]
        groups = response["evidence"][1]["value"]
        self.assertEqual(customers[-1]["cumulative_share"], 1.0)
        self.assertEqual(groups[-1]["cumulative_share"], 1.0)
        self.assertEqual(sum(item["share"] for item in groups), 1.0)
        self.assertEqual(response["metrics"]["top_n_customer_coverage"], customers[-1]["cumulative_share"])

    def test_recovery_respects_cutoff_and_changes_its_opportunities(self):
        before_due = self.service.recovery_intelligence("2026-07-09")
        after_due = self.service.recovery_intelligence("2026-07-31")
        before_types = {item["type"] for item in before_due["findings"]}
        after_types = {item["type"] for item in after_due["findings"]}
        self.assertEqual(before_due["metrics"]["overdue_balance"], 0.0)
        self.assertNotIn("IMMEDIATE_RECOVERY_OPPORTUNITY", before_types)
        self.assertIn("IMMEDIATE_RECOVERY_OPPORTUNITY", after_types)
        self.assertEqual(before_due["metrics"]["preventive_open_balance"], 300.0)

    def test_credit_note_creates_document_review_not_billing_error(self):
        response = self.service.recovery_intelligence("2026-07-31")
        document_finding = next(item for item in response["findings"] if item["type"] == "DOCUMENT_REVIEW_OPPORTUNITY")
        self.assertIn("does not establish a billing error", document_finding["impact"])
        self.assertFalse(any("ERROR" in item["type"] for item in response["findings"]))
        self.assertTrue(any(item["action"] == "review_document_adjustments_before_contact" for item in response["recommended_actions"]))

    def test_management_insights_are_priority_ordered_and_quality_is_separate(self):
        response = self.service.management_insights("2026-07-31")
        priority = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "INFO": 3}
        finding_priorities = [priority[item["severity"]] for item in response["findings"]]
        self.assertEqual(finding_priorities, sorted(finding_priorities))
        self.assertTrue(all(not item["type"].startswith("DATA_QUALITY") for item in response["findings"]))
        self.assertTrue(any(item["type"].startswith("DATA_QUALITY") for item in response["alerts"]))
        self.assert_evidence_traceable(response)

    def test_management_insights_change_with_cutoff_and_dataset(self):
        before_due = self.service.management_insights("2026-07-09")
        after_due = self.service.management_insights("2026-07-31")
        self.assertNotEqual(before_due["metrics"]["overdue_balance"], after_due["metrics"]["overdue_balance"])
        with tempfile.TemporaryDirectory() as folder:
            changed = Path(folder)
            write_dataset(changed)
            invoice_path = changed / "005_TBL_FACTURAS_B2B.csv"
            with invoice_path.open(encoding="latin1", newline="") as source:
                rows = list(csv.DictReader(source, delimiter="|"))
            for row in rows:
                if row["NRO_DOC_FISCAL"] == "INV_A":
                    row["CHARGE_NET_AMOUNT"] = "500"
                    row["CHARGE_TOTAL_AMOUNT"] = "500"
            with invoice_path.open("w", encoding="latin1", newline="") as target:
                writer = csv.DictWriter(target, fieldnames=HEADERS["005_TBL_FACTURAS_B2B.csv"], delimiter="|")
                writer.writeheader()
                writer.writerows(rows)
            changed_response = BIService(changed).management_insights("2026-07-31")
        self.assertNotEqual(after_due["metrics"]["overdue_balance"], changed_response["metrics"]["overdue_balance"])

    def test_collections_response_boundary_is_json_only_and_does_not_recalculate_priority(self):
        collections_response = {
            "contract_version": "1.0",
            "agent": "collections",
            "operation": "collection_priorities",
            "as_of_date": "2026-07-31",
            "evidence": [{"customer": "CLIENT_A", "priority_score": 99}],
        }
        response = BIService(self.dataset, collections_response).recovery_intelligence("2026-07-31")
        upstream = next(item for item in response["upstream_inputs"] if item["type"] == "collections_agent_response")
        self.assertEqual(upstream["status"], "reference_only")
        self.assertTrue(upstream["priority_evidence_available"])
        self.assertNotIn("priority_score", response["metrics"])
