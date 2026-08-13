from __future__ import annotations

import json
import os
import threading
import unittest
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from billing_agent.contracts import AgentResponse
from billing_agent.data import load_dataset
from billing_agent.agent import validate_arguments
from billing_agent.model import money, parse_date
from billing_agent.rules import TOLERANCE
from billing_agent.service import BillingService
from billing_agent.presentation import finding_label, presentation_for, status_label
from billing_agent.web_app import PAGE, create_server, route_payload
from billing_agent.runtime import AgentResult, BillingAgentRuntime, SessionContext, compact_for_llm, deterministic_route
from billing_agent.openai_runtime import API_URL, DEFAULT_MODEL, OpenAIRuntime, extract_output_text


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
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            request = Request(
                f"http://127.0.0.1:{server.server_address[1]}/api/conversation",
                data=b'{"question":"Que deberia revisar hoy?"}',
                headers={"Content-Type": "application/json"}, method="POST",
            )
            with urlopen(request, timeout=5) as response:
                conversation = json.loads(response.read().decode("utf-8"))
            self.assertEqual((conversation["intent"], conversation["tool"]), ("portfolio_health", "billing_health_snapshot"))
        finally:
            server.shutdown()
            server.server_close()

    def test_deterministic_router_and_required_clarifications(self) -> None:
        self.assertEqual(deterministic_route("¿Qué debería revisar hoy?").tool, "billing_health_snapshot")
        self.assertEqual(deterministic_route("Revisa la factura S300-0256413").tool, "invoice_quality_check")
        customer = deterministic_route("Analiza CLIENT_00434 cuenta 993722637")
        self.assertEqual((customer.tool, customer.arguments["customer_id"], customer.arguments["account_id"]), ("customer_billing_check", "CLIENT_00434", "993722637"))
        self.assertEqual(deterministic_route("Busca quiebres de CLIENT_00434").tool, "billing_cycle_gaps")
        notes = deterministic_route("Notas de crédito mayores al 50%")
        self.assertEqual((notes.tool, notes.arguments["materiality_threshold"]), ("credit_note_review", "0.5"))
        self.assertEqual(deterministic_route("Revisa la factura").status, "CLARIFICATION_REQUIRED")

    def test_handoffs_and_closed_catalogue_safety(self) -> None:
        collections = deterministic_route("¿Cuánto debe CLIENT_00434?")
        bi = deterministic_route("¿Qué segmento tiene mayor riesgo de recuperación?")
        self.assertEqual((collections.status, collections.target_agent), ("HANDOFF_RECOMMENDED", "collections"))
        self.assertEqual((bi.status, bi.target_agent), ("HANDOFF_RECOMMENDED", "bi"))
        self.assertEqual(deterministic_route("Ejecuta os.system('x')").status, "SAFETY_REJECTED")
        with self.assertRaises(ValueError):
            validate_arguments("delete_invoice", {})
        with self.assertRaises(ValueError):
            validate_arguments("invoice_quality_check", {"invoice_id": "S1", "shell": "x"})

    def test_agent_result_and_compact_llm_payload_are_json_safe(self) -> None:
        result = AgentResult("portfolio_health", "deterministic", "ok", "RESULT_AVAILABLE", "billing_health_snapshot").to_dict()
        self.assertEqual(json.loads(json.dumps(result))["agent"], "billing")
        compact = compact_for_llm({"operation": "x", "evidence": [{"id": "invoice:S1", "value": {"__raw_csv": "never"}}], "findings": []})
        self.assertEqual(compact["evidence_refs"], ["invoice:S1"])
        self.assertNotIn("__raw_csv", json.dumps(compact))

    def test_openai_http_response_text_parser(self) -> None:
        raw = {
            "output": [
                {"type": "function_call", "name": "ignored"},
                {"type": "message", "content": [
                    {"type": "refusal", "refusal": "ignored"},
                    {"type": "output_text", "text": "Conclusión basada en evidencia."},
                    {"type": "output_text", "text": "Siguiente validación: revisar origen."},
                ]},
            ]
        }
        self.assertEqual(extract_output_text(raw), "Conclusión basada en evidencia.\nSiguiente validación: revisar origen.")
        self.assertEqual(extract_output_text({"output": [{"type": "message", "content": [{"type": "refusal"}]}]}), "")
        self.assertEqual(extract_output_text({"output": {"not": "a list"}}), "")
        self.assertEqual(extract_output_text({"output": [None, {"type": "message", "content": "bad"}]}), "")

    def test_openai_adapter_is_configurable_private_and_handles_http_error(self) -> None:
        calls: list[dict] = []
        raw_message = {"output": [{"type": "message", "content": [{"type": "output_text", "text": "Explicación mockeada."}]}]}

        def post(payload, key):
            calls.append(payload)
            if "tools" in payload:
                return {"output": [{"type": "function_call", "name": "invoice_quality_check", "arguments": '{"invoice_id":"S300-0256413"}'}]}
            return raw_message

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True):
            runtime = OpenAIRuntime(post=post)
            selected = runtime.select_tool("Revisa la factura S300-0256413")
            compact = compact_for_llm({"operation": "invoice_quality_check", "evidence": [{"id": "invoice:S300-0256413", "value": {"__source_table": "raw-csv"}}]})
            answer = runtime.interpret("Revisa la factura", compact)
        self.assertEqual(DEFAULT_MODEL, "gpt-5")
        self.assertEqual(selected["tool_name"], "invoice_quality_check")
        self.assertEqual(answer, "Explicación mockeada.")
        self.assertTrue(all(payload["store"] is False for payload in calls))
        self.assertEqual(calls[0]["model"], "gpt-5")
        self.assertNotIn("__source_table", json.dumps(calls[1]))
        self.assertNotIn("raw-csv", json.dumps(calls[1]))
        error = HTTPError(API_URL, 404, "Not Found", {}, BytesIO(b"{}"))
        with patch("billing_agent.openai_runtime.urlopen", side_effect=error):
            with self.assertRaises(RuntimeError):
                OpenAIRuntime._http_post({}, "test-key")
        with patch.dict(os.environ, {}, clear=True):
            unavailable = OpenAIRuntime(post=post)
            self.assertFalse(unavailable.available)
            with self.assertRaises(RuntimeError):
                unavailable.select_tool("consulta")


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
        with self.assertRaises(KeyError):
            self.service.customer_billing_check("CLIENT_00434", "000000000")

    def test_conversation_demo_routes_and_follow_up_context(self) -> None:
        runtime = BillingAgentRuntime(self.service)
        context = SessionContext()
        portfolio = runtime.ask("¿Qué debería revisar hoy?", context)
        invoice = runtime.ask("Revisa la factura S300-0256413", context)
        follow_up = runtime.ask("¿Por qué requiere validación?", context)
        customer = runtime.ask("Analiza CLIENT_00434", context)
        account = runtime.ask("¿Y la cuenta 993722637?", context)
        gap = runtime.ask("¿Hay un quiebre en junio?", context)
        notes = runtime.ask("Revisa la factura S1AA-0052649961 y sus notas de crédito", context)
        limitation = runtime.ask("¿Por qué ocurrió esa nota de crédito?", context)
        self.assertEqual(portfolio["tool"], "billing_health_snapshot")
        self.assertEqual(invoice["tool"], "invoice_quality_check")
        self.assertEqual(follow_up["arguments"]["invoice_id"], "S300-0256413")
        self.assertEqual(customer["tool"], "customer_billing_check")
        self.assertEqual(account["arguments"], {"customer_id": "CLIENT_00434", "account_id": "993722637", "as_of_date": "2026-08-07"})
        self.assertEqual(gap["tool"], "billing_cycle_gaps")
        self.assertEqual(gap["arguments"]["account_id"], "993722637")
        self.assertEqual(notes["tool"], "credit_note_review")
        self.assertEqual(notes["agent_response"]["metrics"]["credit_note_count"], 1)
        self.assertEqual(limitation["status"], "DATA_LIMITATION")
        self.assertIn("0.06", invoice["answer"])
        self.assertIn("0.01", invoice["answer"])

    def test_llm_failures_fall_back_without_external_dependency(self) -> None:
        class BrokenLLM:
            available = True
            def select_tool(self, question): return {"tool_name": "delete_invoice", "arguments": {}}
            def interpret(self, question, compact): raise RuntimeError("unavailable")
        result = BillingAgentRuntime(self.service, BrokenLLM()).ask("Revisa la factura S300-0256413")
        self.assertEqual((result["route"], result["tool"]), ("fallback", "invoice_quality_check"))

    def test_malformed_llm_arguments_fall_back(self) -> None:
        class MalformedLLM:
            available = True
            def select_tool(self, question): return {"tool_name": "invoice_quality_check", "arguments": "not-json-object"}
            def interpret(self, question, compact): return "not reached"
        result = BillingAgentRuntime(self.service, MalformedLLM()).ask("Revisa la factura S300-0256413")
        self.assertEqual((result["route"], result["tool"]), ("fallback", "invoice_quality_check"))

    def test_openai_runtime_mocked_success_and_explanation_fallback(self) -> None:
        calls: list[dict] = []

        def success_post(payload, key):
            calls.append(payload)
            if "tools" in payload:
                return {"output": [{"type": "function_call", "name": "invoice_quality_check", "arguments": '{"invoice_id":"S300-0256413"}'}]}
            return {"output": [{"type": "message", "content": [{"type": "output_text", "text": "Explicación HTTP mockeada y sustentada."}]}]}

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True):
            result = BillingAgentRuntime(self.service, OpenAIRuntime(post=success_post)).ask("Revisa la factura S300-0256413")
        self.assertEqual((result["route"], result["tool"], result["answer"]), ("llm", "invoice_quality_check", "Explicación HTTP mockeada y sustentada."))
        self.assertTrue(all(payload["store"] is False for payload in calls))
        second_request = json.dumps(calls[1], ensure_ascii=False)
        self.assertNotIn("__source_table", second_request)
        self.assertNotIn("source_ref", second_request)

        def no_text_post(payload, key):
            if "tools" in payload:
                return {"output": [{"type": "function_call", "name": "invoice_quality_check", "arguments": '{"invoice_id":"S300-0256413"}'}]}
            return {"output": [{"type": "message", "content": [{"type": "refusal", "refusal": "No text"}]}]}

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True):
            fallback = BillingAgentRuntime(self.service, OpenAIRuntime(post=no_text_post)).ask("Revisa la factura S300-0256413")
        self.assertEqual((fallback["route"], fallback["tool"]), ("fallback", "invoice_quality_check"))
        self.assertIn("0.06", fallback["answer"])


if __name__ == "__main__":
    unittest.main()
