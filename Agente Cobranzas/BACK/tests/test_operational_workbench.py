"""Operational workbench contracts remain deterministic and dataset-independent."""

from collections_agent.data import SoniaDataset
from collections_agent.service import CollectionsService


def _service() -> CollectionsService:
    invoices = [
        {
            "RAZON_SOCIAL": "CUSTOMER_ALPHA",
            "COD_CLIENTE": "A",
            "COD_CUENTA": "ACCOUNT_A",
            "NRO_DOC_FISCAL": "INVOICE_PARTIAL",
            "FECHA_EMISION": "2026-01-01",
            "FECHA_VTO": "2026-01-31",
            "CHARGE_TOTAL_AMOUNT": "100",
        },
        {
            "RAZON_SOCIAL": "CUSTOMER_BETA",
            "COD_CLIENTE": "B",
            "COD_CUENTA": "ACCOUNT_B",
            "NRO_DOC_FISCAL": "INVOICE_BETA",
            "FECHA_EMISION": "2026-07-01",
            "FECHA_VTO": "2026-12-31",
            "CHARGE_TOTAL_AMOUNT": "80",
        },
    ]
    payments = [
        {
            "RAZON_SOCIAL": "CUSTOMER_ALPHA",
            "COD_CUENTA": "ACCOUNT_A",
            "FACTURA_AFECTADA": "INVOICE_PARTIAL",
            "FECHA_PAGO": "2026-02-01",
            "MONTO_PAGADO": "25",
        },
        {
            "RAZON_SOCIAL": "CUSTOMER_ALPHA",
            "COD_CUENTA": "ACCOUNT_A",
            "FACTURA_AFECTADA": "INVOICE_MISSING",
            "FECHA_PAGO": "2026-02-02",
            "MONTO_PAGADO": "15",
        },
    ]
    return CollectionsService.from_dataset(
        SoniaDataset(
            customers=[],
            fixed_plant=[],
            mobile_plant=[],
            payments=payments,
            invoices=invoices,
            credit_notes=[],
        )
    )


def test_priority_rows_expose_partial_payment_filter_without_changing_score() -> None:
    result = _service().collection_priorities(limit=20, as_of_date="2026-08-01")
    alpha = next(row for row in result["evidence"] if row["customer"] == "CUSTOMER_ALPHA")

    assert alpha["partial_payment_invoice_count"] == 1
    assert alpha["priority"] in {"HIGH", "MEDIUM", "LOW"}
    assert alpha["priority_score"] == round(sum(alpha["score_components"].values()), 1)


def test_documentary_exception_has_stable_trace_and_default_operational_state() -> None:
    service = _service()
    first = service.reconciliation_exceptions(20, "2026-08-01")
    second = service.reconciliation_exceptions(20, "2026-08-01")
    case = next(
        row for row in first["evidence"] if row["type"] == "PAYMENT_OUTSIDE_INVOICE_CUTOFF"
    )

    assert case["case_id"].startswith("COL-")
    assert case["case_id"] == second["evidence"][0]["case_id"]
    assert case["operational_state"] == "PENDIENTE_VALIDACION"
    assert case["payment"]["account_code"] == "ACCOUNT_A"
    assert case["reason"]
    assert case["evidence"]


def test_revenue_summary_counts_real_high_cases_only() -> None:
    result = _service().reconciliation_exceptions(20, "2026-08-01")
    expected = sum(row["severity"] == "HIGH" for row in result["evidence"])
    assert result["metrics"]["high_priority_exception_count"] == expected


def test_invoice_trace_reports_related_documentary_case_ids() -> None:
    dataset = SoniaDataset(
        customers=[],
        fixed_plant=[],
        mobile_plant=[],
        payments=[
            {
                "RAZON_SOCIAL": "CUSTOMER_ALPHA",
                "COD_CUENTA": "ACCOUNT_A",
                "FACTURA_AFECTADA": "INVOICE_OVER",
                "FECHA_PAGO": "2026-02-01",
                "MONTO_PAGADO": "120",
            }
        ],
        invoices=[
            {
                "RAZON_SOCIAL": "CUSTOMER_ALPHA",
                "COD_CLIENTE": "A",
                "COD_CUENTA": "ACCOUNT_A",
                "NRO_DOC_FISCAL": "INVOICE_OVER",
                "FECHA_EMISION": "2026-01-01",
                "FECHA_VTO": "2026-01-31",
                "CHARGE_TOTAL_AMOUNT": "100",
            }
        ],
        credit_notes=[],
    )
    result = CollectionsService.from_dataset(dataset).invoice_trace(
        "INVOICE_OVER", "2026-08-01"
    )

    assert result["reconciliation"]["case_ids"]
    assert result["evidence"][0]["reconciliation_case_count"] == 1
