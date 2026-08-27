"""Public JSON-only boundary for read-only Collections evidence.

This module intentionally does not import ``collections_agent`` or its ledger.
It accepts an AgentResponse-shaped mapping, validates its provenance and scope,
and copies only the explicitly approved KPI values. BI never derives or
recalculates those values.
"""

from __future__ import annotations

from copy import deepcopy
from math import isfinite
from typing import Any

APPROVED_COLLECTIONS_KPIS = (
    "collection_ratio_30_days",
    "average_collection_period_days",
    "overdue_balance",
    "partial_payment_invoice_count",
)
COLLECTIONS_PORTFOLIO_OPERATION = "portfolio_snapshot"


def collections_response_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate minimal public contract fields and return traceable provenance."""
    if payload.get("agent") != "collections":
        raise ValueError("collections_response debe tener agent='collections'")
    if not payload.get("contract_version") or not payload.get("operation"):
        raise ValueError("collections_response debe incluir contract_version y operation")
    return {
        "type": "collections_agent_response",
        "agent": "collections",
        "status": "reference_only",
        "access": "read_only_json",
        "calculation_owner": "collections",
        "contract_version": payload["contract_version"],
        "operation": payload["operation"],
        "as_of_date": payload.get("as_of_date"),
        "priority_evidence_available": payload.get("operation") == "collection_priorities",
    }


def _unavailable_context(
    expected_as_of_date: str,
    reason: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    upstream = {
        "type": "collections_agent_response",
        "agent": "collections",
        "status": "unavailable",
        "access": "read_only_json",
        "calculation_owner": "collections",
        "as_of_date": expected_as_of_date,
        "approved_metrics": [],
        "reason": reason,
    }
    if metadata:
        upstream.update(metadata)
        upstream["status"] = "unavailable"
        upstream["reason"] = reason
    return {
        "available": False,
        "metrics": {},
        "reason": reason,
        "upstream_input": upstream,
    }


def unavailable_collections_kpi_context(
    expected_as_of_date: str,
    reason: str,
) -> dict[str, Any]:
    """Describe an upstream transport/provider failure without breaking BI."""
    return _unavailable_context(expected_as_of_date, reason)


def _response_payload(payload: object) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    nested = payload.get("agent_response")
    if isinstance(nested, dict):
        return nested
    return payload


def _valid_number(value: object, *, ratio: bool = False) -> bool:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    numeric = float(value)
    if not isfinite(numeric) or numeric < 0:
        return False
    return not ratio or numeric <= 1


def _approved_metrics(metrics: object) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(metrics, dict):
        return {}, list(APPROVED_COLLECTIONS_KPIS)
    accepted: dict[str, Any] = {}
    rejected: list[str] = []
    for field in APPROVED_COLLECTIONS_KPIS:
        value = metrics.get(field)
        if field == "partial_payment_invoice_count":
            valid = isinstance(value, int) and not isinstance(value, bool) and value >= 0
        else:
            valid = _valid_number(value, ratio=field == "collection_ratio_30_days")
        if valid:
            # Preserve the exact JSON value emitted by Collections: no conversion,
            # rounding or financial formula is permitted at this boundary.
            accepted[field] = deepcopy(value)
        elif field in metrics:
            rejected.append(field)
    return accepted, rejected


def collections_kpi_context(
    payload: object,
    expected_as_of_date: str,
    expected_currency: str = "PEN",
) -> dict[str, Any]:
    """Return approved Collections KPIs only when contract, cut-off and currency match."""
    response = _response_payload(payload)
    if response is None:
        return _unavailable_context(expected_as_of_date, "collections_response_not_provided")
    try:
        metadata = collections_response_metadata(response)
    except ValueError:
        return _unavailable_context(expected_as_of_date, "invalid_collections_contract")

    if response.get("operation") != COLLECTIONS_PORTFOLIO_OPERATION:
        metadata["reason"] = "operation_does_not_expose_portfolio_kpis"
        return {
            "available": False,
            "metrics": {},
            "reason": metadata["reason"],
            "upstream_input": metadata,
        }
    if response.get("as_of_date") != expected_as_of_date:
        return _unavailable_context(
            expected_as_of_date,
            "collections_as_of_date_mismatch",
            metadata=metadata,
        )

    raw_status = response.get("status")
    status = raw_status if isinstance(raw_status, dict) else {}
    currency = status.get("currency")
    if currency != expected_currency:
        return _unavailable_context(
            expected_as_of_date,
            "collections_currency_scope_mismatch",
            metadata={**metadata, "currency": currency or "UNSPECIFIED"},
        )

    accepted, rejected = _approved_metrics(response.get("metrics"))
    if not accepted:
        return _unavailable_context(
            expected_as_of_date,
            "approved_collections_kpis_missing_or_invalid",
            metadata={**metadata, "currency": currency},
        )

    upstream = {
        **metadata,
        "status": "evidence_available",
        "currency": currency,
        "currency_scope": status.get("currency_scope"),
        "approved_metrics": list(accepted),
        "rejected_metrics": rejected,
    }
    return {
        "available": True,
        "metrics": accepted,
        "reason": None,
        "upstream_input": upstream,
    }
