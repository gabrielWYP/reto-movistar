"""Optional OpenAI Responses API runtime. It never receives CSVs or the canonical model."""

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

    @staticmethod
    def _first_function_call(response: dict[str, Any]) -> dict[str, Any]:
        calls = [item for item in response.get("output", []) if item.get("type") == "function_call"]
        if len(calls) != 1:
            raise RuntimeError("El modelo debe seleccionar exactamente una tool BI autorizada.")
        return calls[0]

    def select_tool(self, question: str, as_of_date: str) -> dict[str, Any]:
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY no está configurada; usa el modo determinístico.")
        response = self._post({"model": os.environ.get("SONIA_BI_MODEL", DEFAULT_MODEL), "store": False, "instructions": SYSTEM_PROMPT, "input": question, "tools": tool_schemas(), "tool_choice": "required", "max_output_tokens": 400}, key)
        call = self._first_function_call(response)
        try:
            arguments = json.loads(call.get("arguments", "{}"))
        except json.JSONDecodeError as error:
            raise RuntimeError("El modelo devolvió argumentos de tool inválidos.") from error
        return {"tool_name": call.get("name"), "arguments": arguments, "call_id": call.get("call_id")}

    def interpret(self, question: str, tool_result: dict[str, Any]) -> str:
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY no está configurada; usa el modo determinístico.")
        compact = {
            "operation": tool_result.get("operation"), "as_of_date": tool_result.get("as_of_date"), "metrics": tool_result.get("metrics"),
            "findings": tool_result.get("findings"), "alerts": tool_result.get("alerts"), "recommended_actions": tool_result.get("recommended_actions"),
            "evidence": tool_result.get("evidence"), "data_quality": tool_result.get("data_quality"),
        }
        response = self._post({"model": os.environ.get("SONIA_BI_MODEL", DEFAULT_MODEL), "store": False, "instructions": SYSTEM_PROMPT + "\nRedacta una respuesta breve usando exclusivamente el JSON recibido.", "input": [{"role": "user", "content": [{"type": "input_text", "text": f"Pregunta: {question}\nResultado determinístico: {json.dumps(compact, ensure_ascii=False)}"}]}], "max_output_tokens": 600}, key)
        answer = response.get("output_text", "").strip()
        if not answer:
            raise RuntimeError("El modelo no devolvió una interpretación textual.")
        return answer
