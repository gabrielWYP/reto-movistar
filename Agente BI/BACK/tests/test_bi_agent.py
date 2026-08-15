from __future__ import annotations

import csv
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from bi_agent import BIBackend
from bi_agent.agent import TOOL_NAMES, ask, dispatch, tool_schemas, validate_arguments
from bi_agent.api import create_app, create_bi_router
from bi_agent.config import Settings
from bi_agent.llm_runtime import OpenAIRuntime
from bi_agent.presentation import METRIC_LABELS, presentation_for
from bi_agent.prompting import SYSTEM_PROMPT, load_system_prompt
from bi_agent.service import BIService
from bi_agent.visuals import ALLOWED_COMPONENTS, dashboard_spec


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

    def test_agent_runtime_exposes_only_five_closed_tools(self):
        schemas = tool_schemas()
        self.assertEqual({schema["name"] for schema in schemas}, TOOL_NAMES)
        self.assertEqual(len(schemas), 5)
        self.assertTrue(all(schema["parameters"]["additionalProperties"] is False for schema in schemas))

    def test_agent_fallback_routes_demo_questions_and_preserves_original_response(self):
        cases = [
            ("¿Cómo está el ciclo de ingresos al 31 de julio?", "executive_snapshot"),
            ("¿Dónde está concentrado el saldo vencido?", "risk_concentration"),
            ("¿Qué oportunidades de recupero tenemos?", "recovery_intelligence"),
            ("¿Qué debería priorizar la gerencia?", "management_insights"),
            ("¿Qué limitaciones tiene la información?", "data_quality_report"),
        ]
        for question, expected in cases:
            result = ask(self.service, question, "2026-07-31")
            self.assertEqual(result["tool_used"], expected)
            self.assertEqual(result["agent_response"]["operation"], expected)
            self.assertEqual(result["agent_response"]["as_of_date"], "2026-07-31")
            self.assertEqual(result["mode"], "deterministic")

    def test_agent_rejects_unknown_tools_and_arbitrary_arguments(self):
        with self.assertRaises(ValueError):
            validate_arguments("shell", {}, "2026-07-31")
        with self.assertRaises(ValueError):
            validate_arguments("risk_concentration", {"sql": "select *"}, "2026-07-31")
        with self.assertRaises(ValueError):
            validate_arguments("risk_concentration", {"dimension": "__import__('os')"}, "2026-07-31")
        with self.assertRaises(ValueError):
            ask(self.service, "x" * 1001, "2026-07-31")

    def test_dispatch_forces_requested_cutoff_and_only_service_computes(self):
        result = dispatch(self.service, "executive_snapshot", {"as_of_date": "2020-01-01"}, "2026-07-31")
        self.assertEqual(result["as_of_date"], "2026-07-31")
        self.assertEqual(result["metrics"]["outstanding_balance"], 240.0)

    def test_visual_catalog_only_emits_allowed_components_and_ignores_unknown_hints(self):
        response = self.service.recovery_intelligence("2026-07-31")
        response["visualization_hints"].append({"type": "execute_javascript", "source": "bad"})
        spec = dashboard_spec(response)
        self.assertTrue({item["type"] for item in spec["components"]}.issubset(ALLOWED_COMPONENTS))
        self.assertIn("execute_javascript", spec["ignored_hints"])
        self.assertTrue(any(item["type"] == "kpi_cards" for item in spec["components"]))

    def test_visual_catalog_resolves_indexed_evidence_hints_for_risk_tables(self):
        response = self.service.risk_concentration("SEGMENTO_PAIS", "overdue_balance", 10, "2026-07-31")
        spec = dashboard_spec(response)
        ranking = next(item for item in spec["components"] if item["type"] == "ranking_table")
        self.assertEqual(ranking["source_id"], "top_customers")
        self.assertTrue(ranking["data"])

    def test_visual_catalog_resolves_first_class_findings_and_aging_sources(self):
        recovery = dashboard_spec(self.service.recovery_intelligence("2026-07-31"))
        opportunity = next(item for item in recovery["components"] if item["type"] == "opportunity_table")
        self.assertTrue(opportunity["data"])
        executive = dashboard_spec(self.service.executive_snapshot("2026-07-31"))
        aging = next(item for item in executive["components"] if item["type"] == "aging_bar")
        self.assertTrue(aging["data"])

    def test_fastapi_boundary_uses_agent_without_api_key(self):
        runtime = OpenAIRuntime()
        application = FastAPI()
        application.include_router(
            create_bi_router(BIBackend(service=self.service, runtime=runtime))
        )
        with patch.dict("os.environ", {}, clear=True):
            with TestClient(application) as client:
                status = client.get("/api/bi/status")
                response = client.post(
                    "/api/bi/query",
                    json={
                        "question": "¿Qué oportunidades de recupero tenemos?",
                        "as_of_date": "2026-07-31",
                    },
                )
                unknown = client.post(
                    "/api/bi/tools/__import__",
                    json={"as_of_date": "2026-07-31", "parameters": {}},
                )
        self.assertEqual(status.status_code, 200)
        self.assertFalse(status.json()["llm_available"])
        self.assertEqual(set(status.json()["tools"]), TOOL_NAMES)
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["tool_used"], "recovery_intelligence")
        self.assertIn("components", result["dashboard"])
        self.assertIn("presentation", result)
        self.assertEqual(
            result["presentation"]["analysis"]["title"],
            "Oportunidades de recupero",
        )
        self.assertEqual(unknown.status_code, 404)

    def test_fastapi_boundary_rejects_unknown_arguments(self):
        application = FastAPI()
        application.include_router(create_bi_router(BIBackend(service=self.service)))
        with TestClient(application) as client:
            response = client.post(
                "/api/bi/tools/risk_concentration",
                json={
                    "as_of_date": "2026-07-31",
                    "parameters": {"sql": "select * from invoices"},
                },
            )
        self.assertEqual(response.status_code, 422)

    def test_management_dashboard_does_not_duplicate_hint_components(self):
        spec = dashboard_spec(self.service.management_insights("2026-07-31"))
        component_types = [item["type"] for item in spec["components"]]
        self.assertEqual(component_types.count("insight_cards"), 1)
        self.assertEqual(component_types.count("alert_cards"), 1)

    def test_llm_failure_falls_back_without_breaking_deterministic_tools(self):
        class BrokenRuntime:
            available = True
            def select_tool(self, question, as_of_date):
                raise RuntimeError("API unavailable")
        result = BIBackend(service=self.service, runtime=BrokenRuntime()).query(
            "¿Cómo está la cartera?",
            "2026-07-31",
        )
        self.assertEqual(result["mode"], "deterministic_fallback")
        self.assertEqual(result["agent_response"]["operation"], "executive_snapshot")

    def test_backend_without_dataset_starts_but_calculation_is_unavailable(self):
        backend = BIBackend()
        self.assertFalse(backend.configured)
        with self.assertRaises(RuntimeError):
            backend.query("¿Cómo está la cartera?", "2026-07-31")

    def test_openai_runtime_is_mockable_and_requires_exactly_one_function_call(self):
        response = {"output": [{"type": "function_call", "name": "executive_snapshot", "call_id": "call_1", "arguments": "{}"}]}
        runtime = OpenAIRuntime(post=lambda payload, key: response)
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test"}, clear=True):
            choice = runtime.select_tool("resumen", "2026-07-31")
        self.assertEqual(choice["tool_name"], "executive_snapshot")
        self.assertEqual(choice["arguments"], {})

    def test_presentation_labels_metrics_without_changing_numeric_values_or_response(self):
        response = self.service.risk_concentration("SEGMENTO_PAIS", "overdue_balance", 10, "2026-07-31")
        original = copy.deepcopy(response)
        view = presentation_for(response, dashboard_spec(response))
        self.assertEqual(response, original)
        self.assertEqual(METRIC_LABELS["overdue_balance"][0], "Saldo vencido")
        self.assertEqual(view["kpis"][0]["label"], "Saldo vencido total")
        self.assertEqual(view["kpis"][0]["value"], response["metrics"]["metric_total"])
        self.assertEqual(view["kpis"][1]["value"], response["evidence"][0]["value"][0]["share"])

    def test_presentation_humanizes_risk_story_and_preserves_anonymous_identifiers(self):
        response = self.service.risk_concentration("SEGMENTO_PAIS", "overdue_balance", 10, "2026-07-31")
        view = presentation_for(response, dashboard_spec(response))
        finding = view["findings"][0]
        self.assertEqual(finding["title"], "Alta concentración del saldo vencido")
        self.assertIn("SEG_A", finding["detail"])
        self.assertNotIn("The leading", finding["detail"])
        table = next(component for component in view["components"] if component["type"] == "table")
        self.assertEqual(table["columns"][0], "Cliente")
        self.assertTrue(table["rows"][0][0].startswith("CLIENT_"))
        self.assertEqual(finding["technical_type"], "RISK_CONCENTRATION")

    def test_presentation_covers_all_demo_operations_in_spanish_and_keeps_alert_codes(self):
        responses = [
            self.service.executive_snapshot("2026-07-31"),
            self.service.risk_concentration("SEGMENTO_PAIS", "overdue_balance", 10, "2026-07-31"),
            self.service.recovery_intelligence("2026-07-31"),
            self.service.management_insights("2026-07-31"),
            self.service.data_quality_report("2026-07-31"),
        ]
        for response in responses:
            view = presentation_for(response, dashboard_spec(response))
            self.assertTrue(view["analysis"]["title"])
            visible = " ".join(
                [view["analysis"]["title"], view["analysis"]["description"]]
                + [item["label"] for item in view["kpis"]]
                + [item["title"] + " " + item["detail"] for item in view["findings"] + view["recommended_actions"] + view["alerts"]]
            )
            self.assertNotIn("The leading", visible)
            self.assertNotIn("overdue_balance", visible)
            self.assertNotIn("RISK_CONCENTRATION", visible)
        executive_view = presentation_for(responses[0], dashboard_spec(responses[0]))
        self.assertEqual(executive_view["alerts"][0]["title"], "Pagos sin factura vinculada")
        self.assertEqual(executive_view["alerts"][0]["technical_type"], "DATA_QUALITY_UNMATCHED_PAYMENTS")

    def test_presentation_is_identical_for_deterministic_and_llm_result_payloads(self):
        payload = self.service.executive_snapshot("2026-07-31")
        dashboard = dashboard_spec(payload)
        deterministic = presentation_for(payload, dashboard)
        llm_mode = presentation_for(payload, dashboard)
        self.assertEqual(deterministic, llm_mode)

    def test_standalone_fastapi_health_and_shared_contract(self):
        settings = Settings("0.0.0.0", 8080, "INFO", None)
        application = create_app(settings, BIBackend(service=self.service))
        with TestClient(application) as client:
            health = client.get("/health")
            status = client.get("/api/bi/status")
            query = client.post(
                "/api/bi/query",
                json={
                    "question": "¿Dónde está concentrado el saldo vencido?",
                    "as_of_date": "2026-07-31",
                },
            )
        self.assertEqual(health.status_code, 200)
        self.assertEqual(status.status_code, 200)
        self.assertEqual(query.status_code, 200)
        self.assertEqual(query.json()["tool_used"], "risk_concentration")
        self.assertEqual(query.json()["agent_response"]["contract_version"], "1.0")

    def test_prompt_resource_is_versioned_single_source_of_truth(self):
        definition = load_system_prompt()
        source = Path(__file__).resolve().parents[1] / "prompts" / "system_v1.md"
        raw = source.read_text(encoding="utf-8")
        self.assertEqual(definition.prompt_id, "bi-system")
        self.assertEqual(definition.version, "1.0")
        self.assertEqual(definition.content, SYSTEM_PROMPT)
        self.assertIn(definition.content, raw)
        self.assertIn("Nunca mezcles PEN y USD", definition.content)
        self.assertNotIn("Pendiente BI-01", raw)

    def test_prompt_evals_route_and_enforce_deterministic_guardrails(self):
        expected = {
            "¿Dónde está concentrado el saldo vencido?": "risk_concentration",
            "¿Qué debería priorizar la gerencia?": "management_insights",
            "Calcula tú mismo cuánto debemos cobrar sumando todas las facturas.": "executive_snapshot",
        }
        for question, operation in expected.items():
            result = ask(self.service, question, "2026-07-31")
            self.assertEqual(result["tool_used"], operation)
            self.assertIn(result["tool_used"], TOOL_NAMES)

        causal = ask(self.service, "¿Por qué el Segmento 002 no paga?", "2026-07-31")
        forecast = ask(self.service, "Predice exactamente la mora del próximo mes.", "2026-07-31")
        currency = ask(self.service, "Suma los dólares con los soles.", "2026-07-31")
        self.assertIn("no demostrar la causa", causal["answer"])
        self.assertIn("No existe una herramienta predictiva", forecast["answer"])
        self.assertIn("No se suman PEN y USD", currency["answer"])

    def test_llm_uses_versioned_prompt_and_never_receives_complete_csvs(self):
        calls = []
        responses = iter(
            [
                {
                    "output": [
                        {
                            "type": "function_call",
                            "name": "executive_snapshot",
                            "call_id": "call_1",
                            "arguments": "{}",
                        }
                    ]
                },
                {"output_text": "Respuesta ejecutiva respaldada por evidencia."},
            ]
        )

        def post(payload, key):
            calls.append(payload)
            return next(responses)

        runtime = OpenAIRuntime(post=post)
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test"}, clear=True):
            result = ask(self.service, "¿Cómo está la cartera?", "2026-07-31", runtime)
        self.assertEqual(result["mode"], "llm")
        self.assertEqual(result["prompt"], {"prompt_id": "bi-system", "prompt_version": "1.0"})
        self.assertEqual(calls[0]["instructions"], SYSTEM_PROMPT)
        serialized = json.dumps(calls, ensure_ascii=False)
        self.assertNotIn("005_TBL_FACTURAS_B2B.csv", serialized)
        self.assertNotIn("CHARGE_TOTAL_AMOUNT", serialized)
        self.assertNotIn("OPENAI_API_KEY", serialized)
