"""Closed Collections agent boundary for routing, validation and narration."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from .prompting import prompt_metadata
from .service import CollectionsService

TOOL_NAMES = {
    "portfolio_snapshot",
    "customer_snapshot",
    "invoice_trace",
    "collection_priorities",
    "reconciliation_exceptions",
}


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """Human-readable tool metadata exposed through the status endpoint."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AgentResult:
    """Stable response envelope shared by the frontend and future supervisor."""

    answer: str
    tool_name: str
    tool_arguments: dict[str, Any]
    agent_response: dict[str, Any]
    mode: str
    usage: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        """Serialize the public agent response."""
        return {
            "answer": self.answer,
            "tool_used": self.tool_name,
            "tool_arguments": self.tool_arguments,
            "agent_response": self.agent_response,
            "mode": self.mode,
            "usage": self.usage,
        }


def tool_schemas() -> list[dict[str, Any]]:
    """Expose only the five deterministic Collections calculations."""
    date_property = {"type": "string", "description": "Fecha ISO YYYY-MM-DD opcional."}
    limit_property = {"type": "integer", "minimum": 1, "maximum": 50}
    identifier = {"type": "string", "minLength": 1, "maxLength": 128}
    return [
        {
            "type": "function",
            "name": "portfolio_snapshot",
            "description": "Obtiene KPIs, saldo vencido y antigüedad de la cartera.",
            "parameters": {
                "type": "object",
                "properties": {"as_of_date": date_property},
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "customer_snapshot",
            "description": "Analiza la situación de cobranza de un cliente identificado.",
            "parameters": {
                "type": "object",
                "properties": {"customer_id": identifier, "as_of_date": date_property},
                "required": ["customer_id"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "invoice_trace",
            "description": "Reconstruye pagos, créditos, saldo y estados de una factura.",
            "parameters": {
                "type": "object",
                "properties": {"document": identifier, "as_of_date": date_property},
                "required": ["document"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "collection_priorities",
            "description": "Obtiene un ranking explicable para la gestión de cobranza.",
            "parameters": {
                "type": "object",
                "properties": {"limit": limit_property, "as_of_date": date_property},
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "reconciliation_exceptions",
            "description": "Lista documentos que requieren validar su aplicación.",
            "parameters": {
                "type": "object",
                "properties": {"limit": limit_property, "as_of_date": date_property},
                "additionalProperties": False,
            },
        },
    ]


def tool_definitions() -> list[ToolDefinition]:
    """Return compact metadata without duplicating schema policy."""
    return [
        ToolDefinition(schema["name"], schema["description"], schema["parameters"])
        for schema in tool_schemas()
    ]


def validate_arguments(
    tool_name: str, arguments: dict[str, Any], as_of_date: str | None = None
) -> dict[str, Any]:
    """Reject model-proposed tools and arguments outside the closed contract."""
    if tool_name not in TOOL_NAMES:
        raise ValueError("La tool solicitada no está autorizada para Cobranzas.")
    if not isinstance(arguments, dict):
        raise ValueError("Los argumentos de la tool deben ser un objeto JSON.")
    allowed = {
        "portfolio_snapshot": {"as_of_date"},
        "customer_snapshot": {"customer_id", "as_of_date"},
        "invoice_trace": {"document", "as_of_date"},
        "collection_priorities": {"limit", "as_of_date"},
        "reconciliation_exceptions": {"limit", "as_of_date"},
    }[tool_name]
    if set(arguments) - allowed:
        raise ValueError("La tool recibió parámetros no autorizados.")

    values = dict(arguments)
    if as_of_date is not None:
        values["as_of_date"] = as_of_date
    if values.get("as_of_date"):
        values["as_of_date"] = str(values["as_of_date"])
        date.fromisoformat(values["as_of_date"])
    else:
        values.pop("as_of_date", None)

    required_identifier = {
        "customer_snapshot": "customer_id",
        "invoice_trace": "document",
    }.get(tool_name)
    if required_identifier:
        identifier = values.get(required_identifier)
        if not isinstance(identifier, str) or not identifier.strip():
            raise ValueError(f"{required_identifier} es obligatorio para esta consulta.")
        if len(identifier.strip()) > 128:
            raise ValueError(f"{required_identifier} excede el máximo de 128 caracteres.")
        values[required_identifier] = identifier.strip()

    if "limit" in values:
        limit = values["limit"]
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
            raise ValueError("limit debe ser un entero entre 1 y 50.")
    elif tool_name in {"collection_priorities", "reconciliation_exceptions"}:
        values["limit"] = 10
    return values


def dispatch(
    service: CollectionsService,
    tool_name: str,
    arguments: dict[str, Any],
    as_of_date: str | None = None,
) -> dict[str, Any]:
    """Execute exactly one validated deterministic calculation."""
    values = validate_arguments(tool_name, arguments, as_of_date)
    routes: dict[str, Callable[[], dict[str, Any]]] = {
        "portfolio_snapshot": lambda: service.portfolio_snapshot(values.get("as_of_date")),
        "customer_snapshot": lambda: service.customer_snapshot(
            values["customer_id"], values.get("as_of_date")
        ),
        "invoice_trace": lambda: service.invoice_trace(
            values["document"], values.get("as_of_date")
        ),
        "collection_priorities": lambda: service.collection_priorities(
            values["limit"], values.get("as_of_date")
        ),
        "reconciliation_exceptions": lambda: service.reconciliation_exceptions(
            values["limit"], values.get("as_of_date")
        ),
    }
    return routes[tool_name]()


def _extract_identifier(question: str, noun: str) -> str | None:
    direct_pattern = (
        r"\bCLIENT_[A-Z0-9_-]{1,120}\b"
        if noun == "cliente"
        else r"\b(?:FAC|S[0-9A-Z]{2,8})-[A-Z0-9-]{2,120}\b"
    )
    direct = re.search(direct_pattern, question, flags=re.IGNORECASE)
    if direct:
        return direct.group(0)
    pattern = (
        rf"(?:{noun})\s*(?:n[.°ºo]*|id|código|codigo|[:#])\s*[:#-]?\s*"
        r"([A-Z0-9][A-Z0-9_-]{2,127})"
    )
    match = re.search(pattern, question, flags=re.IGNORECASE)
    return match.group(1) if match else None


def deterministic_route(question: str, as_of_date: str | None) -> tuple[str, dict[str, Any]]:
    """Route a safe deterministic fallback without performing calculations."""
    normalized = question.casefold()
    invoice_id = _extract_identifier(question, "factura") or _extract_identifier(
        question, "documento"
    )
    customer_id = _extract_identifier(question, "cliente")
    common = {"as_of_date": as_of_date} if as_of_date else {}
    if invoice_id:
        return "invoice_trace", {**common, "document": invoice_id}
    if customer_id:
        return "customer_snapshot", {**common, "customer_id": customer_id}
    if any(term in normalized for term in ("concili", "excep", "pago sin", "aplicación")):
        return "reconciliation_exceptions", {**common, "limit": 10}
    if any(
        term in normalized
        for term in ("prior", "urgente", "atender primero", "gestionar primero", "ranking")
    ):
        return "collection_priorities", {**common, "limit": 10}
    return "portfolio_snapshot", common


def _money(value: Any) -> str:
    return f"S/ {float(value or 0):,.2f}"


def deterministic_narrative(payload: dict[str, Any]) -> str:
    """Narrate only fields already calculated by the selected tool."""
    operation = payload.get("operation")
    metrics = payload.get("metrics", {})
    cutoff = payload.get("as_of_date", "el corte disponible")
    if operation == "portfolio_snapshot":
        answer = (
            f"Al {cutoff}, la cartera registra {_money(metrics.get('outstanding_balance'))} "
            f"pendiente y {_money(metrics.get('overdue_balance'))} vencido."
        )
    elif operation == "customer_snapshot":
        answer = (
            f"Al {cutoff}, el cliente analizado mantiene "
            f"{_money(metrics.get('overdue_balance'))} vencido."
        )
    elif operation == "invoice_trace":
        answer = (
            f"Al {cutoff}, la factura conserva "
            f"{_money(metrics.get('outstanding_balance'))} pendiente."
        )
    elif operation == "collection_priorities":
        answer = (
            f"El ranking determinístico evaluó {int(metrics.get('customers_ranked', 0))} "
            "clientes y ordena la gestión por saldo vencido, atraso y concentración."
        )
    else:
        answer = (
            f"Se identificaron {int(metrics.get('exception_count', 0))} casos de aplicación "
            "documental que requieren validación; no son errores confirmados."
        )
    return answer


def _apply_question_guardrails(question: str, answer: str) -> str:
    normalized = question.casefold()
    if any(term in normalized for term in ("predice", "pronóstico", "forecast", "próximo mes")):
        return (
            "No existe una herramienta predictiva en este MVP; no puedo afirmar pagos o mora "
            "futuros. " + answer
        )
    if "por qué" in normalized and any(term in normalized for term in ("no paga", "mora")):
        return (
            "El dataset describe asociaciones y saldos, pero no demuestra las causas del "
            "comportamiento de pago. " + answer
        )
    if any(term in normalized for term in ("dólar", "dolar", "usd")) and any(
        term in normalized for term in ("soles", "pen", "sol ")
    ):
        return "No se suman PEN y USD; el alcance monetario del MVP es PEN. " + answer
    return answer


def _merge_usage(*items: dict[str, int]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for item in items:
        for key, value in item.items():
            totals[key] = totals.get(key, 0) + value
    return totals


def ask(
    service: CollectionsService,
    question: str,
    as_of_date: str | None = None,
    runtime: Any | None = None,
) -> dict[str, Any]:
    """Answer through one grounded tool or a deterministic fallback."""
    if not isinstance(question, str) or not question.strip() or len(question) > 1000:
        raise ValueError("La pregunta debe ser texto no vacío de hasta 1000 caracteres.")
    if as_of_date is not None:
        date.fromisoformat(as_of_date)

    if runtime is not None and runtime.available:
        selected = runtime.select_tool(question.strip(), as_of_date)
        try:
            arguments = validate_arguments(selected["tool_name"], selected["arguments"], as_of_date)
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError(
                "OpenCode Go devolvió una selección de tool no autorizada."
            ) from error
        payload = dispatch(service, selected["tool_name"], arguments, as_of_date)
        answer, interpretation_usage = runtime.interpret(question.strip(), payload)
        result = AgentResult(
            answer=answer,
            tool_name=selected["tool_name"],
            tool_arguments=arguments,
            agent_response=payload,
            mode="llm",
            usage=_merge_usage(selected.get("usage", {}), interpretation_usage),
        ).to_dict()
        result["prompt"] = prompt_metadata()
        result["llm"] = runtime.metadata()
        return result

    tool_name, arguments = deterministic_route(question, as_of_date)
    validated = validate_arguments(tool_name, arguments, as_of_date)
    payload = dispatch(service, tool_name, validated, as_of_date)
    answer = _apply_question_guardrails(question, deterministic_narrative(payload))
    return AgentResult(answer, tool_name, validated, payload, "deterministic", {}).to_dict()
