"""Optional GPT-5.6 Responses API runner with local deterministic function tools.

The dataset never leaves the process. At most one compact tool result is sent back to
the model so it can formulate an evidence-based answer.
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .agent import SYSTEM_PROMPT, dispatch
from .service import CollectionsService

API_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5.6-terra"


def _schemas() -> list[dict[str, Any]]:
    return [
        {"type": "function", "name": "portfolio_snapshot", "description": "Obtener KPIs y ageing de cartera.", "parameters": {"type": "object", "properties": {"as_of_date": {"type": "string", "description": "Fecha de corte YYYY-MM-DD."}}}},
        {"type": "function", "name": "customer_snapshot", "description": "Analizar la situación de cobranza de un cliente.", "parameters": {"type": "object", "properties": {"customer_id": {"type": "string"}, "as_of_date": {"type": "string"}}, "required": ["customer_id"]}},
        {"type": "function", "name": "invoice_trace", "description": "Reconstruir pagos, créditos, saldo y estado de una factura.", "parameters": {"type": "object", "properties": {"document": {"type": "string"}, "as_of_date": {"type": "string"}}, "required": ["document"]}},
        {"type": "function", "name": "collection_priorities", "description": "Obtener ranking determinístico y explicable de cobranza.", "parameters": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 50}, "as_of_date": {"type": "string"}}}},
        {"type": "function", "name": "reconciliation_exceptions", "description": "Listar excepciones de aplicación documental que requieren revisión.", "parameters": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 50}, "as_of_date": {"type": "string"}}}},
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
        raise RuntimeError(f"OpenAI Responses API devolvió HTTP {error.code}: {message}") from error


def _function_calls(response: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in response.get("output", []) if item.get("type") == "function_call"]


def ask(service: CollectionsService, question: str, model: str | None = None) -> dict[str, Any]:
    """Run at most one model-selected deterministic tool, then request a concise answer."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Define OPENAI_API_KEY para usar el modo GPT-5.6; las tools/CLI no lo requieren.")
    first = _post(
        {
            "model": model or os.environ.get("SONIA_MODEL", DEFAULT_MODEL),
            "store": False,
            "instructions": SYSTEM_PROMPT,
            "input": question,
            "tools": _schemas(),
            "tool_choice": "auto",
            "max_output_tokens": 700,
        },
        api_key,
    )
    calls = _function_calls(first)
    if not calls:
        return {"answer": first.get("output_text", ""), "tool_result": None, "usage": first.get("usage", {})}
    call = calls[0]
    arguments = json.loads(call.get("arguments", "{}"))
    result = dispatch(service, call["name"], arguments)
    second = _post(
        {
            "model": model or os.environ.get("SONIA_MODEL", DEFAULT_MODEL),
            "store": False,
            "instructions": SYSTEM_PROMPT,
            "previous_response_id": first["id"],
            "input": [{"type": "function_call_output", "call_id": call["call_id"], "output": json.dumps(result, ensure_ascii=False)}],
            "max_output_tokens": 700,
        },
        api_key,
    )
    return {"answer": second.get("output_text", ""), "tool_result": result, "usage": second.get("usage", {})}

