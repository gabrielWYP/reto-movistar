import os
from pathlib import Path
import unittest
from unittest.mock import patch

from sonia.agents.collections.application import CollectionsBackend
from sonia.agents.collections.openai_runtime import _schemas
from sonia.agents.collections.service import CollectionsService
from sonia.agents.collections.uploads import load_uploaded_csvs
from sonia.agents.collections.web_app import route_payload

DATASET_VALUE = os.environ.get("SONIA_DATASET")
DATASET = Path(DATASET_VALUE) if DATASET_VALUE else None


class CollectionsContractTests(unittest.TestCase):
    def test_gpt_runtime_exposes_only_the_five_deterministic_tools(self):
        schemas = _schemas()
        self.assertEqual(len(schemas), 5)
        self.assertEqual(
            {schema["name"] for schema in schemas},
            {
                "portfolio_snapshot",
                "customer_snapshot",
                "invoice_trace",
                "collection_priorities",
                "reconciliation_exceptions",
            },
        )

    def test_validated_csv_package_builds_an_isolated_service(self):
        invoices = (
            "RAZON_SOCIAL|COD_CLIENTE|COD_CUENTA|NRO_DOC_FISCAL|"
            "FECHA_EMISION|FECHA_VTO|CHARGE_TOTAL_AMOUNT\n"
            "CLIENT_TEST|001|ACC-1|FAC-001|2026-07-01|2026-07-20|100.50\n"
        ).encode()
        payments = (
            "RAZON_SOCIAL|COD_CUENTA|FACTURA_AFECTADA|FECHA_PAGO|MONTO_PAGADO\n"
            "CLIENT_TEST|ACC-1|FAC-001|2026-07-15|40.50\n"
        ).encode()
        dataset, report = load_uploaded_csvs(
            [("facturas.csv", invoices), ("pagos.csv", payments)],
            max_files=6,
            max_bytes=1_000_000,
        )
        self.assertTrue(report.ready_for_analysis)
        self.assertIsNotNone(dataset)
        assert dataset is not None
        result = CollectionsService.from_dataset(dataset).invoice_trace(
            "FAC-001", "2026-08-07"
        )
        self.assertEqual(result["metrics"]["outstanding_balance"], 60.0)

    def test_incompatible_csv_does_not_replace_the_backend_dataset(self):
        backend = CollectionsBackend()
        report = backend.upload_dataset([("desconocido.csv", b"NOMBRE|MONTO\nEjemplo|10\n")])
        self.assertFalse(report["ready_for_analysis"])
        self.assertFalse(backend.configured)

    def test_openai_mode_requires_a_runtime_secret(self):
        backend = CollectionsBackend()
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            self.assertFalse(backend.llm_available)


@unittest.skipUnless(DATASET and DATASET.exists(), "Set SONIA_DATASET to run dataset tests.")
class CollectionsAgentTests(unittest.TestCase):
    def service(self) -> CollectionsService:
        assert DATASET is not None
        return CollectionsService(DATASET)

    def test_portfolio_has_stable_contract_and_known_counts(self):
        response = self.service().portfolio_snapshot("2026-08-07")
        self.assertEqual(response["contract_version"], "1.0")
        self.assertEqual(response["agent"], "collections")
        self.assertEqual(response["metrics"]["invoice_count"], 3364)
        self.assertEqual(response["metrics"]["unmatched_payment_count"], 74)
        self.assertGreater(response["metrics"]["outstanding_balance"], 0)

    def test_invoice_trace_reconstructs_document_state(self):
        response = self.service().invoice_trace("S1AA-0052403449", "2026-08-07")
        evidence = response["evidence"][0]
        self.assertEqual(evidence["customer"], "CLIENT_00063")
        self.assertGreater(evidence["outstanding_balance"], 0)
        self.assertEqual(response["status"]["settlement"], "PAGO_PARCIAL")

    def test_customer_and_priorities_are_explainable(self):
        customer = self.service().customer_snapshot("CLIENT_00385", "2026-08-07")
        priorities = self.service().collection_priorities(5, "2026-08-07")
        self.assertEqual(customer["entity"]["id"], "CLIENT_00385")
        self.assertGreater(customer["metrics"]["priority_score"], 0)
        self.assertGreaterEqual(
            priorities["evidence"][0]["priority_score"],
            priorities["evidence"][1]["priority_score"],
        )
        self.assertEqual(
            set(priorities["evidence"][0]["score_components"]),
            {
                "overdue_amount",
                "days_past_due",
                "overdue_share",
                "portfolio_concentration",
            },
        )

    def test_legacy_routes_still_delegate_to_deterministic_tools(self):
        service = self.service()
        status, portfolio = route_payload(
            service, "/api/portfolio?as_of_date=2026-08-07"
        )
        missing_status, error = route_payload(service, "/api/customer?id=UNKNOWN")
        self.assertEqual(status, 200)
        self.assertEqual(portfolio["operation"], "portfolio_snapshot")
        self.assertEqual(missing_status, 404)
        self.assertIn("error", error)
