"""Closed Collections agent boundary for tool validation and orchestration."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from .contracts import CONTRACT_VERSION
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
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AgentResult:
    """Stable conversational envelope with full deterministic tool outputs."""

    answer: str
    tool_results: list[dict[str, Any]]
    usage: dict[str, int]
    llm: dict[str, str]
    as_of_date: str | None

    def to_dict(self) -> dict[str, Any]:
        executed = [item for item in self.tool_results if "result" in item]
        tools_used = [str(item["tool"]) for item in executed]
        primary = executed[0] if executed else None
        if len(executed) == 1:
            structured = executed[0]["result"]
        else:
            structured = {
                "contract_version": CONTRACT_VERSION,
                "agent": "collections",
                "operation": "multi_tool_analysis" if executed else "clarification_required",
                "as_of_date": self.as_of_date,
                "results": [item["result"] for item in executed],
            }
        return {
            "answer": self.answer,
            "mode": "llm",
            "tools_used": tools_used,
            "tool_results": self.tool_results,
            "tool_used": primary["tool"] if primary else None,
            "tool_arguments": primary["arguments"] if primary else {},
            "agent_response": structured,
            "usage": self.usage,
            "llm": self.llm,
            "prompt": prompt_metadata(),
        }


def tool_schemas() -> list[dict[str, Any]]:
    """Expose only the five deterministic Collections calculations."""
    date_property = {
        "type": ["string", "null"],
        "description": "Fecha ISO YYYY-MM-DD o null para usar el último corte disponible.",
    }
    limit_property = {"type": "integer", "minimum": 1, "maximum": 50}
    identifier = {"type": "string", "minLength": 1, "maxLength": 128}
    return [
        {
            "type": "function",
            "name": "portfolio_snapshot",
            "description": (
                "Obtiene KPIs de cobranza, saldos, facturas, pagos y antigüedad de cartera."
            ),
            "parameters": {
                "type": "object",
                "properties": {"as_of_date": date_property},
                "required": ["as_of_date"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "type": "function",
            "name": "customer_snapshot",
            "description": "Analiza saldos, pagos, KPIs y prioridad de un cliente identificado.",
            "parameters": {
                "type": "object",
                "properties": {"customer_id": identifier, "as_of_date": date_property},
                "required": ["customer_id", "as_of_date"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "type": "function",
            "name": "invoice_trace",
            "description": "Reconstruye pagos, créditos, saldo, vencimiento y estado de una factura.",
            "parameters": {
                "type": "object",
                "properties": {"document": identifier, "as_of_date": date_property},
                "required": ["document", "as_of_date"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "type": "function",
            "name": "collection_priorities",
            "description": "Obtiene el ranking explicable de clientes por gestionar.",
            "parameters": {
                "type": "object",
                "properties": {"limit": limit_property, "as_of_date": date_property},
                "required": ["limit", "as_of_date"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "type": "function",
            "name": "reconciliation_exceptions",
            "description": (
                "Analiza aplicaciones documentales, pagos parciales y casos que requieren revisión."
            ),
            "parameters": {
                "type": "object",
                "properties": {"limit": limit_property, "as_of_date": date_property},
                "required": ["limit", "as_of_date"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    ]


def tool_definitions() -> list[ToolDefinition]:
    return [
        ToolDefinition(schema["name"], schema["description"], schema["parameters"])
        for schema in tool_schemas()
    ]


def validate_arguments(
    tool_name: str, arguments: dict[str, Any], as_of_date: str | None = None
) -> dict[str, Any]:
    """Reject model-proposed tools and arguments outside the closed contract."""
    if tool_name not in TOOL_NAMES:
        raise ValueError("La herramienta solicitada no está autorizada para Cobranzas.")
    if not isinstance(arguments, dict):
        raise ValueError("Los argumentos de la herramienta deben ser un objeto JSON.")
    allowed = {
        "portfolio_snapshot": {"as_of_date"},
        "customer_snapshot": {"customer_id", "as_of_date"},
        "invoice_trace": {"document", "as_of_date"},
        "collection_priorities": {"limit", "as_of_date"},
        "reconciliation_exceptions": {"limit", "as_of_date"},
    }[tool_name]
    if set(arguments) - allowed:
        raise ValueError("La herramienta recibió parámetros no autorizados.")

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
        identifier_value = values.get(required_identifier)
        if not isinstance(identifier_value, str) or not identifier_value.strip():
            raise ValueError(f"{required_identifier} es obligatorio para esta consulta.")
        if len(identifier_value.strip()) > 128:
            raise ValueError(f"{required_identifier} excede el máximo de 128 caracteres.")
        values[required_identifier] = identifier_value.strip()

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


def _compact_result(result: dict[str, Any]) -> dict[str, Any]:
    """Bound evidence sent to the model while returning the full result to callers."""
    evidence = result.get("evidence", [])
    return {
        "operation": result.get("operation"),
        "as_of_date": result.get("as_of_date"),
        "entity": result.get("entity"),
        "status": result.get("status"),
        "metrics": result.get("metrics"),
        "kpis": result.get("kpis"),
        "aging": result.get("aging", [])[:10],
        "reconciliation": result.get("reconciliation"),
        "findings": result.get("findings"),
        "alerts": result.get("alerts"),
        "recommended_actions": result.get("recommended_actions"),
        "evidence": evidence[:10] if isinstance(evidence, list) else [],
        "evidence_truncated": isinstance(evidence, list) and len(evidence) > 10,
        "data_quality": result.get("data_quality"),
    }


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
    """Let OpenCode select tools, then explain their deterministic results."""
    if not isinstance(question, str) or not question.strip() or len(question) > 1000:
        raise ValueError("La pregunta debe ser texto no vacío de hasta 1000 caracteres.")
    if as_of_date is not None:
        date.fromisoformat(as_of_date)
    if runtime is None or not runtime.available:
        raise RuntimeError(
            "La consulta en lenguaje natural requiere OPENCODE_KEY. "
            "Las cinco vistas determinísticas continúan disponibles sin IA."
        )

    cutoff_instruction = as_of_date or "usa la última fecha observable del dataset"
    conversation: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": f"Fecha de corte: {cutoff_instruction}\nPregunta: {question.strip()}",
        }
    ]
    responses: list[dict[str, Any]] = []
    tool_results: list[dict[str, Any]] = []
    calls_used = 0
    response = runtime.create(conversation, require_tool=True, stage="tool_selection")
    responses.append(response)
    if not runtime.function_calls(response):
        raise RuntimeError("OpenCode Go no seleccionó una herramienta de Cobranzas autorizada.")

    while calls := runtime.function_calls(response):
        if calls_used + len(calls) > runtime.max_tool_calls:
            raise RuntimeError(
                "La consulta excede el límite de herramientas; formula una pregunta más específica."
            )
        calls_used += len(calls)
        outputs: list[dict[str, Any]] = []
        for call in calls:
            call_id = call.get("call_id")
            tool_name = call.get("name")
            try:
                arguments = json.loads(str(call.get("arguments", "{}")))
                if not isinstance(tool_name, str) or not isinstance(call_id, str):
                    raise ValueError("La llamada de herramienta está incompleta.")
                validated = validate_arguments(tool_name, arguments, as_of_date)
                result = dispatch(service, tool_name, validated, as_of_date)
                tool_results.append({"tool": tool_name, "arguments": validated, "result": result})
                output_payload: dict[str, Any] = _compact_result(result)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
                output_payload = {"error": str(error)}
                tool_results.append(
                    {
                        "tool": tool_name if isinstance(tool_name, str) else "invalid",
                        "arguments": {},
                        "error": str(error),
                    }
                )
            if not isinstance(call_id, str):
                raise RuntimeError("OpenCode Go devolvió una llamada sin identificador.")
            outputs.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": json.dumps(output_payload, ensure_ascii=False),
                }
            )

        conversation.extend(runtime.output_items(response))
        conversation.extend(outputs)
        response = runtime.create(
            conversation,
            require_tool=False,
            stage="tool_follow_up",
        )
        responses.append(response)

    answer = runtime.output_text(response)
    if not answer:
        raise RuntimeError("OpenCode Go no devolvió una explicación final sustentada.")
    return AgentResult(
        answer=answer,
        tool_results=tool_results,
        usage=_merge_usage(*(runtime.usage(item) for item in responses)),
        llm=runtime.metadata(),
        as_of_date=as_of_date,
    ).to_dict()
