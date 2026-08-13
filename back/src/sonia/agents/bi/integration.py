"""Public, JSON-only boundary for future Collections Agent integration.

This module intentionally does not import ``collections_agent`` or its ledger. It
accepts an AgentResponse-shaped payload and records only provenance metadata. A
later version can map approved collection evidence into the canonical BI input.
"""

from __future__ import annotations

from typing import Any


def collections_response_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate minimal public contract fields and return traceable provenance."""
    if payload.get("agent") != "collections":
        raise ValueError("collections_response debe tener agent='collections'")
    if not payload.get("contract_version") or not payload.get("operation"):
        raise ValueError("collections_response debe incluir contract_version y operation")
    return {
        "type": "collections_agent_response",
        "status": "reference_only",
        "contract_version": payload["contract_version"],
        "operation": payload["operation"],
        "as_of_date": payload.get("as_of_date"),
        "priority_evidence_available": payload.get("operation") == "collection_priorities",
    }
