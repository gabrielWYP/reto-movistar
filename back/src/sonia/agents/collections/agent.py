"""A thin, token-efficient interface to connect a future GPT-5.6 client to deterministic tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .service import CollectionsService

SYSTEM_PROMPT = """Eres SON-IA Cobranzas/Recaudación. Nunca calcules importes, saldos, ageing,
scores ni conciliaciones: usa una tool. No afirmes una conciliación bancaria, porque sólo hay
aplicaciones documentales. Explica únicamente información presente en el resultado de la tool.
Responde de forma breve: situación, hallazgos, acción recomendada y evidencia relevante."""


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]


def tool_definitions() -> list[ToolDefinition]:
    return [
        ToolDefinition("portfolio_snapshot", "KPIs y ageing de cartera.", {"as_of_date": "YYYY-MM-DD opcional"}),
        ToolDefinition("customer_snapshot", "Situación de cobranza de un cliente.", {"customer_id": "CLIENT_XXXXX", "as_of_date": "opcional"}),
        ToolDefinition("invoice_trace", "Trazabilidad de una factura.", {"document": "NRO_DOC_FISCAL", "as_of_date": "opcional"}),
        ToolDefinition("collection_priorities", "Ranking determinístico de cobranza.", {"limit": "entero opcional", "as_of_date": "opcional"}),
        ToolDefinition("reconciliation_exceptions", "Excepciones de aplicación documental.", {"limit": "entero opcional", "as_of_date": "opcional"}),
    ]


def dispatch(service: CollectionsService, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    tools: dict[str, Callable[..., dict[str, Any]]] = {
        "portfolio_snapshot": service.portfolio_snapshot,
        "customer_snapshot": service.customer_snapshot,
        "invoice_trace": service.invoice_trace,
        "collection_priorities": service.collection_priorities,
        "reconciliation_exceptions": service.reconciliation_exceptions,
    }
    if tool_name not in tools:
        raise ValueError(f"Tool no permitida: {tool_name}")
    return tools[tool_name](**arguments)

