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
