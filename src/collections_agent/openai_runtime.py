"""Optional GPT-5.6 Responses API runner with local deterministic function tools.

The dataset never leaves the process. At most one compact tool result is sent back to
the model so it can formulate an evidence-based answer.
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .agent import SYSTEM_PROMPT, dispatch
from .config import Settings
from .service import CollectionsService

API_URL = "https://api.openai.com/v1/responses"


def _schemas() -> list[dict[str, Any]]:
    return [
        {"type": "function", "name": "portfolio_snapshot", "description": "Obtiene KPIs, saldo vencido y antigüedad de la cartera a una fecha de corte.", "parameters": {"type": "object", "properties": {"as_of_date": {"type": "string", "description": "Fecha de corte YYYY-MM-DD."}}, "additionalProperties": False}},
        {"type": "function", "name": "customer_snapshot", "description": "Analiza la situación de cobranza de un cliente identificado.", "parameters": {"type": "object", "properties": {"customer_id": {"type": "string"}, "as_of_date": {"type": "string"}}, "required": ["customer_id"], "additionalProperties": False}},
        {"type": "function", "name": "invoice_trace", "description": "Reconstruye pagos, créditos, saldo y estados de una factura identificada.", "parameters": {"type": "object", "properties": {"document": {"type": "string"}, "as_of_date": {"type": "string"}}, "required": ["document"], "additionalProperties": False}},
        {"type": "function", "name": "collection_priorities", "description": "Obtiene el ranking determinístico y explicable de clientes para gestión de cobranza.", "parameters": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 50}, "as_of_date": {"type": "string"}}, "additionalProperties": False}},
        {"type": "function", "name": "reconciliation_exceptions", "description": "Lista casos documentales que requieren validar aplicación de pagos, facturas o notas de crédito.", "parameters": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 50}, "as_of_date": {"type": "string"}}, "additionalProperties": False}},
    ]


def _post(payload: dict[str, Any], api_key: str) -> dict[str, Any]:
    request = Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        message = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI no pudo completar la consulta (HTTP {error.code}).") from error
    except URLError as error:
        raise RuntimeError("No fue posible conectar con OpenAI. Revisa la conexión a internet.") from error


def _function_calls(response: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in response.get("output", []) if item.get("type") == "function_call"]


def _usage_total(responses: list[dict[str, Any]]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for response in responses:
        for key, value in response.get("usage", {}).items():
            if isinstance(value, int):
                totals[key] = totals.get(key, 0) + value
    return totals


def ask(service: CollectionsService, question: str, model: str | None = None) -> dict[str, Any]:
    """Let the model choose deterministic tools, then explain only tool-backed facts."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("La consulta con IA requiere OPENAI_API_KEY. Los análisis determinísticos siguen disponibles sin esa clave.")
    if not question.strip():
        raise ValueError("Escribe una consulta para el agente.")
    settings = Settings.from_env()
    responses: list[dict[str, Any]] = []
    response = _post(
        {
            "model": model or settings.model,
            "store": False,
            "instructions": SYSTEM_PROMPT,
            "input": question,
            "tools": _schemas(),
            "tool_choice": "auto",
            "reasoning": {"effort": settings.reasoning_effort},
            "max_output_tokens": settings.max_output_tokens,
        },
        api_key,
    )
    responses.append(response)
    tool_results: list[dict[str, Any]] = []
    for _ in range(settings.max_tool_calls):
        calls = _function_calls(response)
        if not calls:
            break
        outputs: list[dict[str, Any]] = []
        for call in calls:
            try:
                arguments = json.loads(call.get("arguments", "{}"))
                result = dispatch(service, call["name"], arguments)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
                result = {"error": f"No se pudo ejecutar la consulta solicitada: {error}"}
            tool_results.append({"tool": call.get("name", ""), "result": result})
            outputs.append({"type": "function_call_output", "call_id": call["call_id"], "output": json.dumps(result, ensure_ascii=False)})
        response = _post(
            {
                "model": model or settings.model,
                "store": False,
                "instructions": SYSTEM_PROMPT,
                "previous_response_id": response["id"],
                "input": outputs,
                "tools": _schemas(),
                "tool_choice": "auto",
                "reasoning": {"effort": settings.reasoning_effort},
                "max_output_tokens": settings.max_output_tokens,
            },
            api_key,
        )
        responses.append(response)
    if _function_calls(response):
        raise RuntimeError("La consulta requiere más pasos de los permitidos. Formula una pregunta más específica.")
    return {
        "answer": response.get("output_text", ""),
        "tool_results": tool_results,
        "usage": _usage_total(responses),
        "model": model or settings.model,
    }
