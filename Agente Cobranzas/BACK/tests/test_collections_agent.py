import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from collections_agent.agent import TOOL_NAMES, ask, tool_schemas, validate_arguments
from collections_agent.application import CollectionsBackend
from collections_agent.llm_runtime import OpenCodeRuntime
from collections_agent.service import CollectionsService
from collections_agent.uploads import load_uploaded_csvs
from collections_agent.web_app import route_payload

DATASET_VALUE = os.environ.get("SONIA_DATASET")
DATASET = Path(DATASET_VALUE) if DATASET_VALUE else None


def _invoice_csv(*rows: bytes) -> bytes:
    return (
        b"RAZON_SOCIAL|COD_CLIENTE|COD_CUENTA|NRO_DOC_FISCAL|"
        b"FECHA_EMISION|FECHA_VTO|CHARGE_TOTAL_AMOUNT\n" + b"".join(rows)
    )


def _payment_csv(*rows: bytes) -> bytes:
    return b"RAZON_SOCIAL|COD_CUENTA|FACTURA_AFECTADA|FECHA_PAGO|MONTO_PAGADO\n" + b"".join(rows)


class CollectionsContractTests(unittest.TestCase):
    @staticmethod
    def service_from_csv() -> CollectionsService:
        dataset, report = load_uploaded_csvs(
            [
                (
                    "facturas.csv",
                    _invoice_csv(b"CLIENT_TEST|001|ACC-1|FAC-001|2026-07-01|2026-07-20|100.50\n"),
                ),
                (
                    "pagos.csv",
                    _payment_csv(b"CLIENT_TEST|ACC-1|FAC-001|2026-07-15|40.50\n"),
                ),
            ],
            max_files=6,
            max_bytes=1_000_000,
        )
        if dataset is None or not report.ready_for_analysis:
            raise AssertionError("No se pudo construir el dataset de prueba.")
        return CollectionsService.from_dataset(dataset)

    def test_opencode_runtime_exposes_only_closed_deterministic_tools(self):
        schemas = tool_schemas()
        self.assertEqual(len(schemas), 5)
        self.assertEqual({schema["name"] for schema in schemas}, TOOL_NAMES)
        self.assertTrue(all(schema["strict"] for schema in schemas))

    def test_runtime_uses_opencode_chat_completions_and_environment_secret(self):
        post = Mock(
            return_value={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "portfolio_snapshot",
                                        "arguments": "{}",
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        )
        runtime = OpenCodeRuntime(post=post)
        with patch.dict(os.environ, {"OPENCODE_KEY": "test-only"}, clear=True):
            response = runtime.create(
                [{"role": "user", "content": "Resume la cartera"}],
                require_tool=True,
                stage="test",
            )

        payload, api_key = post.call_args.args
        self.assertEqual(api_key, "test-only")
        self.assertEqual(payload["model"], "deepseek-v4-flash")
        self.assertEqual(payload["tool_choice"], "auto")
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertEqual(payload["tools"][0]["type"], "function")
        self.assertEqual(runtime.function_calls(response)[0]["name"], "portfolio_snapshot")

    def test_validated_csv_builds_service_and_challenge_kpis(self):
        service = self.service_from_csv()
        result = service.portfolio_snapshot("2026-08-07")
        self.assertEqual(result["metrics"]["outstanding_balance"], 60.0)
        self.assertEqual(result["metrics"]["collection_ratio_30_days"], 0.403)
        self.assertEqual(result["metrics"]["average_collection_period_days"], 14.0)
        self.assertEqual(result["kpis"]["collection_ratio_30_days"]["eligible_invoice_count"], 1)

    def test_historical_cutoff_excludes_future_payments(self):
        dataset, report = load_uploaded_csvs(
            [
                (
                    "facturas.csv",
                    _invoice_csv(b"CLIENT_TEST|001|ACC-1|FAC-001|2026-07-01|2026-07-20|100.00\n"),
                ),
                (
                    "pagos.csv",
                    _payment_csv(
                        b"CLIENT_TEST|ACC-1|FAC-001|2026-07-15|40.00\n",
                        b"CLIENT_TEST|ACC-1|FAC-001|2026-08-15|60.00\n",
                    ),
                ),
            ],
            6,
            1_000_000,
        )
        self.assertTrue(report.ready_for_analysis)
        assert dataset is not None
        service = CollectionsService.from_dataset(dataset)
        july = service.invoice_trace("FAC-001", "2026-07-31")
        august = service.invoice_trace("FAC-001", "2026-08-31")
        self.assertEqual(july["metrics"]["paid"], 40.0)
        self.assertEqual(july["metrics"]["outstanding_balance"], 60.0)
        self.assertEqual(august["metrics"]["outstanding_balance"], 0.0)

    def test_opencode_selects_tools_and_explains_compact_evidence(self):
        responses = [
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "customer_snapshot",
                                        "arguments": '{"customer_id":"CLIENT_TEST"}',
                                    },
                                },
                                {
                                    "id": "call-2",
                                    "type": "function",
                                    "function": {
                                        "name": "collection_priorities",
                                        "arguments": '{"limit":5}',
                                    },
                                },
                            ],
                        }
                    },
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "total_tokens": 120,
                },
            },
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": (
                                "El cliente mantiene saldo vencido y debe priorizarse con evidencia."
                            ),
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": 80,
                    "completion_tokens": 18,
                    "total_tokens": 98,
                },
            },
        ]
        post = Mock(side_effect=responses)
        runtime = OpenCodeRuntime(post=post)
        with patch.dict(os.environ, {"OPENCODE_KEY": "test-only"}, clear=True):
            result = ask(
                self.service_from_csv(),
                "Analiza CLIENT_TEST y dime si debería priorizarlo.",
                "2026-08-07",
                runtime,
            )

        self.assertEqual(result["tools_used"], ["customer_snapshot", "collection_priorities"])
        self.assertEqual(result["agent_response"]["operation"], "multi_tool_analysis")
        self.assertEqual(result["mode"], "llm")
        self.assertEqual(result["usage"]["total_tokens"], 218)
        self.assertEqual(post.call_args_list[0].args[0]["tool_choice"], "auto")
        self.assertEqual(post.call_args_list[1].args[0]["tool_choice"], "auto")
        follow_up = post.call_args_list[1].args[0]["messages"]
        self.assertEqual(
            [message["role"] for message in follow_up[-3:]], ["assistant", "tool", "tool"]
        )
        self.assertNotIn("test-only", str([call.args[0] for call in post.call_args_list]))

    def test_natural_language_requires_opencode_instead_of_keyword_routing(self):
        runtime = OpenCodeRuntime(post=Mock())
        with (
            patch.dict(os.environ, {"OPENCODE_KEY": ""}, clear=True),
            self.assertRaisesRegex(RuntimeError, "OPENCODE_KEY"),
        ):
            ask(self.service_from_csv(), "Resume la cartera", "2026-08-07", runtime)

    def test_opencode_response_without_tool_is_rejected(self):
        post = Mock(
            return_value={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Respuesta sin evidencia",
                        }
                    }
                ]
            }
        )
        runtime = OpenCodeRuntime(post=post)
        with (
            patch.dict(os.environ, {"OPENCODE_KEY": "test-only"}, clear=True),
            self.assertRaisesRegex(RuntimeError, "no seleccionó"),
        ):
            ask(self.service_from_csv(), "Resume la cartera", "2026-08-07", runtime)
        self.assertEqual(post.call_count, 2)
        self.assertEqual(
            [call.args[0]["max_tokens"] for call in post.call_args_list],
            [700, 1400],
        )
        self.assertIn("REINTENTO", post.call_args_list[1].args[0]["messages"][-1]["content"])

    def test_argument_validation_rejects_unknown_fields_and_overrides_cutoff(self):
        with self.assertRaisesRegex(ValueError, "parámetros no autorizados"):
            validate_arguments("portfolio_snapshot", {"sql": "SELECT 1"})
        result = validate_arguments(
            "collection_priorities",
            {"limit": 5, "as_of_date": "2020-01-01"},
            "2026-08-07",
        )
        self.assertEqual(result, {"limit": 5, "as_of_date": "2026-08-07"})

    def test_incompatible_csv_does_not_replace_backend_dataset(self):
        backend = CollectionsBackend()
        report = backend.upload_dataset([("desconocido.csv", b"NOMBRE|MONTO\nEjemplo|10\n")])
        self.assertFalse(report["ready_for_analysis"])
        self.assertFalse(backend.configured)

    def test_csv_rejects_conflicting_payment_relationship(self):
        dataset, report = load_uploaded_csvs(
            [
                (
                    "facturas.csv",
                    _invoice_csv(b"CLIENT_TEST|001|ACC-1|FAC-001|2026-07-01|2026-07-20|100.00\n"),
                ),
                (
                    "pagos.csv",
                    _payment_csv(b"OTHER_CLIENT|ACC-9|FAC-001|2026-07-15|40.00\n"),
                ),
            ],
            6,
            1_000_000,
        )
        self.assertIsNone(dataset)
        self.assertFalse(report.ready_for_analysis)
        self.assertIn("no coincide", report.errors[0])

    def test_csv_reports_unmatched_payment_without_silent_mixing(self):
        dataset, report = load_uploaded_csvs(
            [
                (
                    "facturas.csv",
                    _invoice_csv(b"CLIENT_TEST|001|ACC-1|FAC-001|2026-07-01|2026-07-20|100.00\n"),
                ),
                (
                    "pagos.csv",
                    _payment_csv(b"CLIENT_TEST|ACC-1|FAC-999|2026-07-15|40.00\n"),
                ),
            ],
            6,
            1_000_000,
        )
        self.assertIsNotNone(dataset)
        self.assertTrue(report.ready_for_analysis)
        self.assertIn("facturas no incluidas", report.warnings[0])

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
                _payment_csv(b"CLIENT_TEST|ACC-1|FAC-001|2026-07-15|40.50\n"),
            ),
            (
                "005_TBL_FACTURAS_B2B.csv",
                _invoice_csv(b"CLIENT_TEST|001|ACC-1|FAC-001|2026-07-01|2026-07-20|100.50\n"),
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

    def test_portfolio_has_stable_contract_and_known_challenge_kpis(self):
        response = self.service().portfolio_snapshot("2026-08-07")
        self.assertEqual(response["contract_version"], "1.1")
        self.assertEqual(response["agent"], "collections")
        self.assertEqual(response["metrics"]["invoice_count"], 3364)
        self.assertEqual(response["metrics"]["unmatched_payment_count"], 74)
        self.assertEqual(response["metrics"]["collection_ratio_30_days"], 0.5728)
        self.assertEqual(response["metrics"]["average_collection_period_days"], 19.9)
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
            {"overdue_amount", "days_past_due", "overdue_share", "portfolio_concentration"},
        )

    def test_legacy_routes_delegate_to_deterministic_tools(self):
        service = self.service()
        status, portfolio = route_payload(service, "/api/portfolio?as_of_date=2026-08-07")
        missing_status, error = route_payload(service, "/api/customer?id=UNKNOWN")
        self.assertEqual(status, 200)
        self.assertEqual(portfolio["operation"], "portfolio_snapshot")
        self.assertEqual(missing_status, 404)
        self.assertIn("error", error)
