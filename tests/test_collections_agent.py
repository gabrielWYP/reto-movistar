from pathlib import Path
import unittest

from collections_agent.service import CollectionsService
from collections_agent.openai_runtime import _schemas


DATASET = Path(__file__).resolve().parents[1] / "data" / "source" / "SONIA_DESAFIO_03.zip"


class CollectionsAgentTests(unittest.TestCase):
    def service(self) -> CollectionsService:
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
        self.assertGreaterEqual(priorities["evidence"][0]["priority_score"], priorities["evidence"][1]["priority_score"])
        self.assertEqual(set(priorities["evidence"][0]["score_components"]), {"overdue_amount", "days_past_due", "overdue_share", "portfolio_concentration"})

    def test_gpt_runtime_exposes_only_the_five_deterministic_tools(self):
        schemas = _schemas()
        self.assertEqual(len(schemas), 5)
        self.assertEqual({schema["name"] for schema in schemas}, {"portfolio_snapshot", "customer_snapshot", "invoice_trace", "collection_priorities", "reconciliation_exceptions"})
