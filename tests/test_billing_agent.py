from __future__ import annotations

import json
import os
import unittest
from decimal import Decimal
from pathlib import Path

from billing_agent.contracts import AgentResponse
from billing_agent.data import load_dataset
from billing_agent.model import money, parse_date
from billing_agent.rules import TOLERANCE
from billing_agent.service import BillingService


def dataset_path() -> Path | None:
    candidates = [
        os.environ.get("SONIA_DATASET", ""),
        r"C:\Users\Acer\Downloads\SONIA_DESAFIO_03\SONIA_DESAFIO_03\DATASET\DATASET",
    ]
    return next((Path(value) for value in candidates if value and Path(value).is_dir()), None)


DATASET = dataset_path()


class UnitTests(unittest.TestCase):
    def test_parse_amdocs_date(self) -> None:
        self.assertEqual(parse_date("2026-07-21"), parse_date("20260721"))

    def test_parse_isis_compact_date(self) -> None:
        self.assertEqual(parse_date("20260811").isoformat(), "2026-08-11")

    def test_decimal_is_exact(self) -> None:
        self.assertEqual(money("0.60") + money("0.11"), Decimal("0.71"))

    def test_rounding_tolerance(self) -> None:
        self.assertEqual(TOLERANCE, Decimal("0.01"))
        self.assertFalse(abs(Decimal("0.01")) > TOLERANCE)
        self.assertTrue(abs(Decimal("0.02")) > TOLERANCE)

    def test_json_safe_contract(self) -> None:
        payload = AgentResponse(operation="test", as_of_date=parse_date("2026-08-07"), metrics={"amount": Decimal("1.20")}).to_dict()
        self.assertEqual(payload["agent"], "billing")
        self.assertEqual(payload["contract_version"], "1.0")
        self.assertEqual(json.loads(json.dumps(payload))["metrics"]["amount"], 1.2)


@unittest.skipUnless(DATASET, "Set SONIA_DATASET to run integration tests against the official CSV directory.")
class OfficialDatasetIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset = load_dataset(DATASET)
        cls.service = BillingService(DATASET)

    def test_mobile_rows_are_not_deduplicated(self) -> None:
        self.assertEqual(len(self.dataset.mobile_plant), 1798)

    def test_customer_join_uses_razon_social(self) -> None:
        result = self.service.customer_billing_check("CLIENT_00434", "993722637")
        self.assertEqual(result["entity"]["id"], "CLIENT_00434")
        self.assertGreater(result["metrics"]["invoice_count"], 0)
        self.assertIn("BILLING_CYCLE_GAP", {item["type"] for item in result["findings"]})

    def test_credit_note_links_to_invoice(self) -> None:
        result = self.service.credit_note_review(invoice_id="S1AA-0052649961")
        self.assertEqual(result["metrics"]["credit_note_count"], 1)
        material = next(item for item in result["findings"] if item["type"] == "MATERIAL_CREDIT_NOTE")
        self.assertAlmostEqual(material["observed_value"]["ratio"], 0.738, places=3)

    def test_arithmetic_mismatch_case(self) -> None:
        result = self.service.invoice_quality_check("S300-0256413")
        issue = next(item for item in result["findings"] if item["type"] == "ARITHMETIC_MISMATCH")
        self.assertGreater(abs(issue["observed_value"]["difference"]), 0.01)

    def test_missing_currency_case(self) -> None:
        result = self.service.invoice_quality_check("FOBF-00121753")
        self.assertIn("MISSING_CURRENCY", {item["type"] for item in result["findings"]})

    def test_zero_value_case(self) -> None:
        result = self.service.invoice_quality_check("S7AA-0067926518")
        self.assertIn("ZERO_VALUE_INVOICE", {item["type"] for item in result["findings"]})

    def test_cycle_gap_case(self) -> None:
        result = self.service.billing_cycle_gaps(customer_id="CLIENT_00434", account_id="993722637")
        self.assertEqual(result["metrics"]["candidate_count"], 1)
        gap = result["findings"][0]
        self.assertEqual(gap["type"], "BILLING_CYCLE_GAP")
        self.assertEqual(gap["observed_value"]["missing_period"], "2026-06")

    def test_unknown_customer_and_invoice(self) -> None:
        with self.assertRaises(KeyError):
            self.service.customer_billing_check("CLIENT_INEXISTENTE")
        with self.assertRaises(KeyError):
            self.service.invoice_quality_check("FACTURA_INEXISTENTE")


if __name__ == "__main__":
    unittest.main()
