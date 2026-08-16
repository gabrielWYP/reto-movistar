import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from collections_agent.agent import (
    TOOL_NAMES,
    ask,
    deterministic_route,
    tool_schemas,
    validate_arguments,
)
from collections_agent.application import CollectionsBackend
from collections_agent.config import CollectionsSettings
from collections_agent.llm_runtime import OpenCodeRuntime
from collections_agent.service import CollectionsService
from collections_agent.uploads import load_uploaded_csvs
from collections_agent.web_app import route_payload

DATASET_VALUE = os.environ.get("SONIA_DATASET")
DATASET = Path(DATASET_VALUE) if DATASET_VALUE else None


class CollectionsContractTests(unittest.TestCase):
    @staticmethod
    def service_from_csv() -> CollectionsService:
        invoices = (
            b"RAZON_SOCIAL|COD_CLIENTE|COD_CUENTA|NRO_DOC_FISCAL|"
            b"FECHA_EMISION|FECHA_VTO|CHARGE_TOTAL_AMOUNT\n"
            b"CLIENT_TEST|001|ACC-1|FAC-001|2026-07-01|2026-07-20|100.50\n"
        )
        payments = (
            b"RAZON_SOCIAL|COD_CUENTA|FACTURA_AFECTADA|FECHA_PAGO|MONTO_PAGADO\n"
            b"CLIENT_TEST|ACC-1|FAC-001|2026-07-15|40.50\n"
        )
        dataset, report = load_uploaded_csvs(
            [("facturas.csv", invoices), ("pagos.csv", payments)],
            max_files=6,
            max_bytes=1_000_000,
        )
        if dataset is None or not report.ready_for_analysis:
            raise AssertionError("No se pudo construir el dataset de prueba.")
        return CollectionsService.from_dataset(dataset)

    def test_opencode_runtime_exposes_only_the_five_deterministic_tools(self):
        schemas = tool_schemas()
        self.assertEqual(len(schemas), 5)
        self.assertEqual({schema["name"] for schema in schemas}, TOOL_NAMES)

    def test_validated_csv_package_builds_an_isolated_service(self):
        result = self.service_from_csv().invoice_trace("FAC-001", "2026-08-07")
        self.assertEqual(result["metrics"]["outstanding_balance"], 60.0)

    def test_opencode_selects_exactly_one_tool_and_interprets_compact_evidence(self):
        responses = [
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "portfolio_snapshot",
                                        "arguments": '{"as_of_date":"2026-08-01"}',
                                    },
                                }
                            ]
                        }
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            },
            {
                "choices": [
                    {
                        "message": {
                            "content": "La cartera mantiene saldo pendiente respaldado por el corte."
                        }
                    }
                ],
                "usage": {"prompt_tokens": 80, "completion_tokens": 18},
            },
        ]
        settings = CollectionsSettings.from_environment()
        post = Mock(side_effect=responses)
        runtime = OpenCodeRuntime(settings, post=post)
        with patch.dict(os.environ, {"OPENCODE_KEY": "test-only"}, clear=True):
            result = ask(self.service_from_csv(), "Resume la cartera", "2026-08-07", runtime)

        self.assertEqual(result["tool_used"], "portfolio_snapshot")
        self.assertEqual(result["tool_arguments"]["as_of_date"], "2026-08-07")
        self.assertEqual(result["mode"], "llm")
        self.assertEqual(result["usage"]["prompt_tokens"], 180)
        second_payload = post.call_args_list[1].args[0]
        self.assertIn("Resultado:", second_payload["messages"][1]["content"])
        self.assertNotIn("OPENAI_API_KEY", str(second_payload))

    def test_runtime_rejects_ungrounded_model_response(self):
        response = {"choices": [{"message": {"content": "Respuesta sin tool"}}]}
        runtime = OpenCodeRuntime(post=Mock(return_value=response))
        with (
            patch.dict(os.environ, {"OPENCODE_KEY": "test-only"}, clear=True),
            self.assertRaisesRegex(RuntimeError, "exactamente una tool"),
        ):
            runtime.select_tool("Resume la cartera", "2026-08-07")

    def test_runtime_retries_an_incomplete_selection_and_accounts_for_usage(self):
        responses = [
            {
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {"content": ""},
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 400,
                    "total_tokens": 500,
                },
            },
            {
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "call-retry",
                                    "type": "function",
                                    "function": {
                                        "name": "portfolio_snapshot",
                                        "arguments": "{}",
                                    },
                                }
                            ]
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 110,
                    "completion_tokens": 30,
                    "total_tokens": 140,
                },
            },
        ]
        post = Mock(side_effect=responses)
        runtime = OpenCodeRuntime(post=post)

        with patch.dict(os.environ, {"OPENCODE_KEY": "test-only"}, clear=True):
            selected = runtime.select_tool("Resume la cartera", "2026-08-07")

        self.assertEqual(selected["tool_name"], "portfolio_snapshot")
        self.assertEqual(selected["usage"]["total_tokens"], 640)
        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args_list[0].args[0]["max_tokens"], 400)
        self.assertEqual(post.call_args_list[1].args[0]["max_tokens"], 800)
        self.assertEqual(post.call_args_list[1].args[0]["tool_choice"], "auto")

    def test_argument_validation_rejects_unknown_fields_and_overrides_cutoff(self):
        with self.assertRaisesRegex(ValueError, "parámetros no autorizados"):
            validate_arguments("portfolio_snapshot", {"sql": "SELECT 1"})
        result = validate_arguments(
            "collection_priorities",
            {"limit": 5, "as_of_date": "2020-01-01"},
            "2026-08-07",
        )
        self.assertEqual(result, {"limit": 5, "as_of_date": "2026-08-07"})

    def test_fallback_does_not_invent_an_identifier_from_regular_words(self):
        tool, arguments = deterministic_route(
            "¿Qué cliente tiene mayor saldo vencido?", "2026-08-07"
        )
        self.assertEqual(tool, "portfolio_snapshot")
        self.assertNotIn("customer_id", arguments)

    def test_incompatible_csv_does_not_replace_the_backend_dataset(self):
        backend = CollectionsBackend()
        report = backend.upload_dataset([("desconocido.csv", b"NOMBRE|MONTO\nEjemplo|10\n")])
        self.assertFalse(report["ready_for_analysis"])
        self.assertFalse(backend.configured)

    def test_opencode_mode_requires_the_shared_runtime_secret(self):
        backend = CollectionsBackend()
        with patch.dict(os.environ, {"OPENCODE_KEY": ""}, clear=True):
            self.assertFalse(backend.llm_available)

    def test_six_csv_files_are_loaded_atomically_in_memory(self):
        files = [
            ("001_TBL_CLIENTES_B2B.csv", b"RAZON_SOCIAL\nCLIENT_TEST\n"),
            (
                "002_TBL_PLANTA_FIJA_B2B.csv",
                b"RAZON_SOCIAL|COD_CLIENTE|COD_CUENTA|CICLO\nCLIENT_TEST|001|ACC-1|1\n",
            ),
            (
                "003_TBL_PLANTA_MOVIL_B2B.csv",
                b"RAZON_SOCIAL|COD_CLIENTE|COD_CUENTA|PRODUCTO\nCLIENT_TEST|001|ACC-1|MOVIL\n",
            ),
            (
                "004_TBL_PAGOS_B2B.csv",
                b"RAZON_SOCIAL|COD_CUENTA|FACTURA_AFECTADA|FECHA_PAGO|MONTO_PAGADO\n"
                b"CLIENT_TEST|ACC-1|FAC-001|2026-07-15|40.50\n",
            ),
            (
                "005_TBL_FACTURAS_B2B.csv",
                b"RAZON_SOCIAL|COD_CLIENTE|COD_CUENTA|NRO_DOC_FISCAL|FECHA_EMISION|"
                b"FECHA_VTO|CHARGE_TOTAL_AMOUNT\n"
                b"CLIENT_TEST|001|ACC-1|FAC-001|2026-07-01|2026-07-20|100.50\n",
            ),
            (
                "006_TBL_NOTAS_CREDITO_B2B.csv",
                b"NRO_DOC_FISCAL|FACTURA_AFECTADA|FECHAEMISION|MONTO\n"
                b"NC-001|FAC-001|2026-07-10|10.00\n",
            ),
        ]
        backend = CollectionsBackend()
        report = backend.upload_dataset(files)
        self.assertTrue(report["ready_for_analysis"])
        self.assertEqual(len(report["accepted_tables"]), 6)
        self.assertEqual(backend.dataset_status()["dataset_source"], "memory")


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
        status, portfolio = route_payload(service, "/api/portfolio?as_of_date=2026-08-07")
        missing_status, error = route_payload(service, "/api/customer?id=UNKNOWN")
        self.assertEqual(status, 200)
        self.assertEqual(portfolio["operation"], "portfolio_snapshot")
        self.assertEqual(missing_status, 404)
        self.assertIn("error", error)
