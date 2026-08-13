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
from billing_agent.presentation import finding_label, presentation_for, status_label
from billing_agent.web_app import PAGE, create_server, route_payload


def dataset_path() -> Path | None:
    value = os.environ.get("SONIA_DATASET", "")
    return Path(value) if value and Path(value).is_dir() else None


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

    def test_presentation_translates_codes_without_mutating_response(self) -> None:
        payload = AgentResponse(
            operation="test", as_of_date=parse_date("2026-08-07"),
            status={"billing_assurance": "REQUIERE_VALIDACION"},
            findings=[{"type": "ARITHMETIC_MISMATCH", "severity": "MEDIUM", "message": "x"}],
        ).to_dict()
        view = presentation_for(payload)
        self.assertEqual(finding_label("ARITHMETIC_MISMATCH"), "Diferencia en validación aritmética")
        self.assertEqual(status_label("REQUIERE_VALIDACION"), "Requiere validación")
        self.assertEqual(view["findings"][0]["business_label"], "Diferencia en validación aritmética")
        self.assertNotIn("business_label", payload["findings"][0])

    def test_web_routes_and_localhost_binding(self) -> None:
        class StubService:
            def default_as_of_date(self): return parse_date("2026-08-07")
            def billing_health_snapshot(self, as_of): return {"operation": "billing_health_snapshot", "as_of_date": "2026-08-07", "status": {}, "metrics": {}, "findings": []}
            def customer_billing_check(self, customer, account, as_of):
                if customer == "UNKNOWN": raise KeyError("Cliente no encontrado")
                return {"operation": "customer_billing_check", "as_of_date": "2026-08-07", "status": {}, "metrics": {}, "findings": []}
            def invoice_quality_check(self, invoice, as_of):
                if invoice == "UNKNOWN": raise KeyError("Factura no encontrada")
                return {"operation": "invoice_quality_check", "as_of_date": "2026-08-07", "status": {}, "metrics": {}, "findings": []}
            def billing_cycle_gaps(self, as_of, customer, account): return {"operation": "billing_cycle_gaps", "as_of_date": "2026-08-07", "status": {}, "metrics": {}, "findings": []}
            def credit_note_review(self, as_of, customer, account, invoice, threshold): return {"operation": "credit_note_review", "as_of_date": "2026-08-07", "status": {}, "metrics": {}, "findings": []}
        service = StubService()
        status, payload = route_payload(service, "/api/status")
        self.assertEqual(status, 200)
        self.assertEqual(payload["default_as_of_date"], "2026-08-07")
        self.assertIn("default_as_of_date", PAGE)
        self.assertNotIn("asOf:'2026-08-07'", PAGE)
        for path in ("/api/health", "/api/customer?customer_id=CLIENT_00001", "/api/invoice?invoice_id=S1", "/api/gaps", "/api/credit-notes"):
            status, payload = route_payload(service, path)
            self.assertEqual(status, 200, path)
            self.assertIn("agent_response", payload)
        self.assertEqual(route_payload(service, "/api/customer?customer_id=UNKNOWN")[0], 400)
        self.assertEqual(route_payload(service, "/api/invoice?invoice_id=UNKNOWN")[0], 400)
        self.assertEqual(route_payload(service, "/api/missing")[0], 404)
        server = create_server(service, 0)
        try:
            self.assertEqual(server.server_address[0], "127.0.0.1")
        finally:
            server.server_close()


@unittest.skipUnless(DATASET, "Set SONIA_DATASET to run integration tests against the official CSV directory.")
class OfficialDatasetIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset = load_dataset(DATASET)
        cls.service = BillingService(DATASET)

    def test_mobile_rows_are_not_deduplicated(self) -> None:
        self.assertEqual(len(self.dataset.mobile_plant), 1798)

    def test_default_cutoff_uses_the_service_default(self) -> None:
        self.assertEqual(
            self.service.default_as_of_date().isoformat(),
            self.service.billing_health_snapshot()["as_of_date"],
        )

    def test_customer_join_uses_razon_social(self) -> None:
        result = self.service.customer_billing_check("CLIENT_00434", "993722637")
        self.assertEqual(result["entity"]["id"], "CLIENT_00434")
        self.assertGreater(result["metrics"]["invoice_count"], 0)
        self.assertIn("BILLING_CYCLE_GAP", {item["type"] for item in result["findings"]})

    def test_customer_without_account_includes_billed_and_plant_accounts(self) -> None:
        result = self.service.customer_billing_check("CLIENT_00434")
        plant_ids = [item["id"] for item in result["evidence"] if item["type"] == "plant"]
        self.assertIn("plant:993722637", plant_ids)  # Plant account with invoices.
        self.assertIn("plant:439397737", plant_ids)  # Plant account without invoice evidence.
        self.assertEqual(len(plant_ids), len(set(plant_ids)))  # Accounts, not raw mobile/fixed row duplicates.
        self.assertGreater(result["metrics"]["account_count"], result["metrics"]["invoice_account_count"])

    def test_plant_only_account_is_heuristic_not_no_exception(self) -> None:
        result = self.service.customer_billing_check("CLIENT_00434")
        finding = next(
            item for item in result["findings"]
            if item["type"] == "PLANT_WITHOUT_BILLING_EVIDENCE" and item["observed_value"]["account"] == "439397737"
        )
        self.assertEqual(finding["rule_category"], "HEURISTIC")
        self.assertEqual(finding["observed_value"]["invoice_evidence_count"], 0)
        self.assertIn("no prueba servicio no facturado", finding["message"])
        self.assertIn("cobertura temporal", finding["recommended_validation"])

    def test_explicit_plant_only_account_is_in_scope(self) -> None:
        result = self.service.customer_billing_check("CLIENT_00434", "439397737")
        self.assertEqual(result["metrics"]["account_count"], 1)
        self.assertEqual(result["metrics"]["invoice_count"], 0)
        self.assertIn("PLANT_WITHOUT_BILLING_EVIDENCE", {item["type"] for item in result["findings"]})

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
        evidence = next(item for item in result["evidence"] if item["type"] == "cycle_gap")
        self.assertEqual(evidence["value"]["before_document"], "S9AA-0081436803")
        self.assertEqual(evidence["value"]["after_document"], "S9AA-0083154556")

    def test_unknown_customer_and_invoice(self) -> None:
        with self.assertRaises(KeyError):
            self.service.customer_billing_check("CLIENT_INEXISTENTE")
        with self.assertRaises(KeyError):
            self.service.invoice_quality_check("FACTURA_INEXISTENTE")


if __name__ == "__main__":
    unittest.main()
