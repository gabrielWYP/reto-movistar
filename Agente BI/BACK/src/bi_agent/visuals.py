"""Declarative visualization catalog: known hints only, no generated code."""

from __future__ import annotations

import re
from typing import Any

ALLOWED_COMPONENTS = {
    "kpi_cards",
    "bar_chart",
    "pareto_chart",
    "aging_bar",
    "ranking_table",
    "opportunity_table",
    "insight_cards",
    "alert_cards",
    "evidence_table",
}


def dashboard_spec(agent_response: dict[str, Any]) -> dict[str, Any]:
    evidence = {item.get("id"): item for item in agent_response.get("evidence", [])}
    components: list[dict[str, Any]] = []
    ignored: list[str] = []
    raw_evidence = agent_response.get("evidence", [])
    for hint in agent_response.get("visualization_hints", []):
        kind = hint.get("type")
        if kind not in ALLOWED_COMPONENTS:
            ignored.append(str(kind))
            continue
        source = hint.get("source", "metrics")
        source_id = source if source in evidence else None
        indexed = re.fullmatch(r"evidence\[(\d+)]\.value", str(source))
        if indexed and int(indexed.group(1)) < len(raw_evidence):
            source_id = raw_evidence[int(indexed.group(1))].get("id")
        if source == "findings":
            data = agent_response.get("findings", [])
        elif source == "alerts":
            data = agent_response.get("alerts", [])
        elif source == "aging":
            data = agent_response.get("aging", [])
        else:
            data = (
                evidence.get(source_id, {}).get("value")
                if source_id
                else agent_response.get("metrics", {})
            )
        components.append(
            {
                "type": kind,
                "source": source,
                "source_id": source_id,
                "fields": hint.get("fields", []),
                "data": data,
            }
        )
    if not any(item["type"] == "kpi_cards" for item in components):
        components.insert(
            0,
            {
                "type": "kpi_cards",
                "source": "metrics",
                "source_id": None,
                "fields": [],
                "data": agent_response.get("metrics", {}),
            },
        )
    if agent_response.get("findings") and not any(
        item["type"] == "insight_cards" for item in components
    ):
        components.append(
            {
                "type": "insight_cards",
                "source": "findings",
                "source_id": None,
                "fields": [],
                "data": agent_response["findings"],
            }
        )
    if agent_response.get("alerts") and not any(
        item["type"] == "alert_cards" for item in components
    ):
        components.append(
            {
                "type": "alert_cards",
                "source": "alerts",
                "source_id": None,
                "fields": [],
                "data": agent_response["alerts"],
            }
        )
    return {
        "components": components,
        "ignored_hints": ignored,
        "allowed_components": sorted(ALLOWED_COMPONENTS),
    }
