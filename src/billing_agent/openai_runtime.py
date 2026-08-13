"""Optional two-phase OpenAI Responses API adapter for Billing conversations.

It is intentionally isolated: phase one receives a question plus closed tool
schemas; phase two receives only a compact AgentResponse derivative.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .agent import SYSTEM_PROMPT, tool_schemas

API_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5.6-terra"


class OpenAIRuntime:
    def __init__(self, post: Callable[[dict[str, Any], str], dict[str, Any]] | None = None):
        self._post = post or self._http_post

    @property
    def available(self) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

    @staticmethod
    def _http_post(payload: dict[str, Any], api_key: str) -> dict[str, Any]:
        request = Request(API_URL, data=json.dumps(payload).encode("utf-8"), headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(request, timeout=45) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            raise RuntimeError(f"OpenAI Responses API devolvió HTTP {error.code}.") from error

    def select_tool(self, question: str) -> dict[str, Any]:
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY no está configurada.")
        response = self._post({
            "model": os.environ.get("SONIA_BILLING_MODEL", DEFAULT_MODEL), "store": False,
            "instructions": SYSTEM_PROMPT, "input": question, "tools": tool_schemas(),
            "tool_choice": "required", "max_output_tokens": 300,
        }, key)
        calls = [item for item in response.get("output", []) if item.get("type") == "function_call"]
        if len(calls) != 1:
            raise RuntimeError("El modelo debe seleccionar exactamente una tool Billing autorizada.")
        call = calls[0]
        try:
            arguments = json.loads(call.get("arguments", "{}"))
        except json.JSONDecodeError as error:
            raise RuntimeError("El modelo devolvió argumentos de tool inválidos.") from error
        return {"tool_name": call.get("name"), "arguments": arguments}

    def interpret(self, question: str, compact_result: dict[str, Any]) -> str:
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY no está configurada.")
        response = self._post({
            "model": os.environ.get("SONIA_BILLING_MODEL", DEFAULT_MODEL), "store": False,
            "instructions": SYSTEM_PROMPT + "\nRedacta una respuesta breve usando exclusivamente el resultado compacto recibido. No agregues cifras ni causas.",
            "input": [{"role": "user", "content": [{"type": "input_text", "text": f"Pregunta: {question}\nResultado compacto: {json.dumps(compact_result, ensure_ascii=False)}"}]}],
            "max_output_tokens": 500,
        }, key)
        answer = response.get("output_text", "").strip()
        if not answer:
            raise RuntimeError("El modelo no devolvió una interpretación textual.")
        return answer
