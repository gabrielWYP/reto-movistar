"""OpenAI Responses integration with deterministic local function tools."""

from __future__ import annotations

import json
import os
from typing import Any

from .agent import SYSTEM_PROMPT, dispatch
from .config import CollectionsSettings
from .service import CollectionsService


def _schemas() -> list[dict[str, Any]]:
    """Expose only the five approved deterministic calculations."""
    return [
        {
            "type": "function",
            "name": "portfolio_snapshot",
            "description": "Obtiene KPIs, saldo vencido y antigüedad de la cartera.",
            "parameters": {
                "type": "object",
                "properties": {"as_of_date": {"type": "string"}},
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "customer_snapshot",
            "description": "Analiza la situación de cobranza de un cliente.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string"},
                    "as_of_date": {"type": "string"},
                },
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
                "properties": {
                    "document": {"type": "string"},
                    "as_of_date": {"type": "string"},
                },
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
                "properties": {
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                    "as_of_date": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "reconciliation_exceptions",
            "description": "Lista documentos que requieren validación de aplicación.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                    "as_of_date": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
    ]


def _client(api_key: str) -> Any:
    """Load the official SDK only when a conversational request needs it."""
    try:
        from openai import OpenAI
    except ImportError as error:
        raise RuntimeError(
            "Falta el SDK de OpenAI en el backend; instala sus dependencias."
        ) from error
    return OpenAI(api_key=api_key, timeout=60.0, max_retries=2)


def _post(client: Any, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return client.responses.create(**payload).model_dump(mode="json")
    except Exception as error:
        raise RuntimeError(
            "OpenAI no pudo completar la consulta; revisa la clave y el acceso al modelo."
        ) from error


def _function_calls(response: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in response.get("output", []) if item.get("type") == "function_call"]


def _usage_total(responses: list[dict[str, Any]]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for response in responses:
        for key, value in response.get("usage", {}).items():
            if isinstance(value, int):
                totals[key] = totals.get(key, 0) + value
    return totals


def ask(
    service: CollectionsService,
    question: str,
    model: str | None = None,
    settings: CollectionsSettings | None = None,
) -> dict[str, Any]:
    """Let the model choose tools while all financial calculations remain local."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "La consulta con IA no está habilitada en este entorno. "
            "Los análisis determinísticos siguen disponibles."
        )
    if not question.strip():
        raise ValueError("Escribe una consulta para el agente.")

    runtime_settings = settings or CollectionsSettings.from_environment()
    selected_model = model or runtime_settings.model
    client = _client(api_key)
    responses: list[dict[str, Any]] = []
    conversation: list[dict[str, Any]] = [
        {"role": "user", "content": question.strip()}
    ]
    response = _post(
        client,
        {
            "model": selected_model,
            "store": False,
            "instructions": SYSTEM_PROMPT,
            "input": conversation,
            "tools": _schemas(),
            "tool_choice": "auto",
            "reasoning": {"effort": runtime_settings.reasoning_effort},
            "max_output_tokens": runtime_settings.max_output_tokens,
        },
    )
    responses.append(response)
    tool_results: list[dict[str, Any]] = []

    calls_used = 0
    for _ in range(runtime_settings.max_tool_calls):
        calls = _function_calls(response)
        if not calls:
            break
        calls_used += len(calls)
        if calls_used > runtime_settings.max_tool_calls:
            raise RuntimeError(
                "La consulta excede el límite de herramientas; formula una pregunta más específica."
            )
        outputs: list[dict[str, str]] = []
        for call in calls:
            try:
                arguments = json.loads(call.get("arguments", "{}"))
                result = dispatch(service, call["name"], arguments)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
                result = {"error": f"No se pudo ejecutar la consulta solicitada: {error}"}
            tool_results.append({"tool": call.get("name", ""), "result": result})
            outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": call["call_id"],
                    "output": json.dumps(result, ensure_ascii=False),
                }
            )
        conversation.extend(response.get("output", []))
        conversation.extend(outputs)
        response = _post(
            client,
            {
                "model": selected_model,
                "store": False,
                "instructions": SYSTEM_PROMPT,
                "input": conversation,
                "tools": _schemas(),
                "tool_choice": "auto",
                "reasoning": {"effort": runtime_settings.reasoning_effort},
                "max_output_tokens": runtime_settings.max_output_tokens,
            },
        )
        responses.append(response)

    if _function_calls(response):
        raise RuntimeError(
            "La consulta requiere más pasos de los permitidos; formula una pregunta más específica."
        )
    return {
        "answer": response.get("output_text", ""),
        "tool_results": tool_results,
        "usage": _usage_total(responses),
        "model": selected_model,
    }
