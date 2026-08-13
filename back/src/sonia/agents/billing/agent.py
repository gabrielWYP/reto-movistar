"""Safe public dispatcher; intentionally no LLM or external-agent integration in v0.1."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable

from .service import BillingService

TOOL_NAMES = {
    "billing_health_snapshot",
    "customer_billing_check",
    "invoice_quality_check",
    "billing_cycle_gaps",
    "credit_note_review",
}


def dispatch(service: BillingService, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if tool_name not in TOOL_NAMES:
        raise ValueError(f"Tool no autorizada: {tool_name}")
    if not isinstance(arguments, dict):
        raise ValueError("arguments debe ser un objeto JSON")
    routes: dict[str, Callable[[], dict[str, Any]]] = {
        "billing_health_snapshot": lambda: service.billing_health_snapshot(arguments.get("as_of_date")),
        "customer_billing_check": lambda: service.customer_billing_check(arguments["customer_id"], arguments.get("account_id"), arguments.get("as_of_date")),
        "invoice_quality_check": lambda: service.invoice_quality_check(arguments["invoice_id"], arguments.get("as_of_date")),
        "billing_cycle_gaps": lambda: service.billing_cycle_gaps(arguments.get("as_of_date"), arguments.get("customer_id"), arguments.get("account_id")),
        "credit_note_review": lambda: service.credit_note_review(arguments.get("as_of_date"), arguments.get("customer_id"), arguments.get("account_id"), arguments.get("invoice_id"), Decimal(str(arguments.get("materiality_threshold", "0.25")))),
    }
    required = {"customer_billing_check": "customer_id", "invoice_quality_check": "invoice_id"}
    if tool_name in required and not arguments.get(required[tool_name]):
        raise ValueError(f"{required[tool_name]} es obligatorio")
    return routes[tool_name]()
