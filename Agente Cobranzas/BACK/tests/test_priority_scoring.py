"""Priority scoring must survive a portfolio with nothing overdue."""

from __future__ import annotations

from collections_agent.data import SoniaDataset
from collections_agent.service import CollectionsService

_CUSTOMER = {"NUMERO_IDENTIFICACION_FISCAL": "201", "RAZON_SOCIAL": "CLIENT_001"}
_INVOICE = {
    "NUMERO_IDENTIFICACION_FISCAL": "201",
    "RAZON_SOCIAL": "CLIENT_001",
    "COD_CLIENTE": "C1",
    "COD_CUENTA": "ACC_001",
    "NRO_DOC_FISCAL": "F001",
    "FUENTE": "FACTURACION CICLICA",
    "SISTEMA": "S1",
    "FECHA_EMISION": "2026-08-01",
    "FECHA_VTO": "2026-12-31",
    "MONEDA": "PEN",
    "CHARGE_NET_AMOUNT": "100",
    "CHARGE_IGV_INVOICE": "18",
    "CHARGE_TOTAL_AMOUNT": "118",
}


def _healthy_portfolio() -> CollectionsService:
    """Every invoice is open but none is past due at the cut-off."""
    return CollectionsService.from_dataset(
        SoniaDataset(
            customers=[_CUSTOMER],
            fixed_plant=[],
            mobile_plant=[],
            payments=[],
            invoices=[_INVOICE],
            credit_notes=[],
        )
    )


def test_collection_priorities_without_any_overdue_balance() -> None:
    """The score divisor is zero here; it used to raise decimal.InvalidOperation."""
    result = _healthy_portfolio().collection_priorities(limit=10, as_of_date="2026-08-15")

    assert result["operation"] == "collection_priorities"
    assert all(
        item["score_components"]["overdue_amount"] == 0 for item in result.get("priorities", [])
    )
