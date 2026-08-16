"""OpenCode Go runtime for grounded BI tool selection and interpretation."""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Callable
from time import perf_counter
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .agent import tool_schemas
from .prompting import SYSTEM_PROMPT

API_URL = "https://opencode.ai/zen/go/v1/chat/completions"
DEFAULT_MODEL = "deepseek-v4-flash"
REQUEST_TIMEOUT_SECONDS = 60
CLIENT_USER_AGENT = "sonia-bi/1.0"
logger = logging.getLogger(__name__)


class OpenCodeRuntime:
    """Minimal OpenAI-compatible client for the OpenCode Go API."""

    def __init__(
        self,
        post: Callable[[dict[str, Any], str], dict[str, Any]] | None = None,
    ) -> None:
        self._post = post or self._http_post

    @property
    def available(self) -> bool:
        """Return whether the runtime has a non-empty repository-injected key."""
        return bool(os.environ.get("OPENCODE_KEY"))

    @property
    def model(self) -> str:
        """Return the configured OpenCode Go model identifier."""
        return os.environ.get("SONIA_BI_MODEL", DEFAULT_MODEL)

    def metadata(self) -> dict[str, str]:
        """Return public runtime metadata without credential material."""
        return {"provider": "opencode-go", "model": self.model}

    @staticmethod
    def _http_post(payload: dict[str, Any], api_key: str) -> dict[str, Any]:
        request = Request(
            API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": CLIENT_USER_AGENT,
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                return cast(dict[str, Any], json.loads(response.read().decode("utf-8")))
        except HTTPError as error:
            detail = OpenCodeRuntime._http_error_detail(error)
            suffix = f" ({detail})" if detail else ""
            raise RuntimeError(f"OpenCode Go devolvió HTTP {error.code}{suffix}.") from error
        except (TimeoutError, URLError) as error:
            raise RuntimeError("No se pudo conectar con OpenCode Go.") from error
        except json.JSONDecodeError as error:
            raise RuntimeError("OpenCode Go devolvió JSON inválido.") from error

    @staticmethod
    def _http_error_detail(error: HTTPError) -> str | None:
        """Extract a non-sensitive Cloudflare code from an HTTP error body."""
        try:
            body = error.read(2048).decode("utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            return None
        match = re.search(r"\berror code:\s*(\d{3,5})\b", body, flags=re.IGNORECASE)
        return f"Cloudflare error {match.group(1)}" if match else None

    @staticmethod
    def _usage(response: dict[str, Any]) -> dict[str, int]:
        usage = response.get("usage")
        if not isinstance(usage, dict):
            return {}
        allowed = ("prompt_tokens", "completion_tokens", "total_tokens")
        return {
            key: value
            for key in allowed
            if isinstance((value := usage.get(key)), int) and not isinstance(value, bool)
        }

    def _invoke(self, payload: dict[str, Any], stage: str) -> dict[str, Any]:
        key = os.environ.get("OPENCODE_KEY")
        if not key:
            raise RuntimeError("OPENCODE_KEY no está configurada; usa el modo determinístico.")
        started_at = perf_counter()
        try:
            response = self._post(payload, key)
        except RuntimeError:
            logger.exception(
                "bi_llm_request_failed",
                extra={
                    "provider": "opencode-go",
                    "model": self.model,
                    "stage": stage,
                    "latency_ms": round((perf_counter() - started_at) * 1000, 3),
                },
            )
            raise
        logger.info(
            "bi_llm_request_completed",
            extra={
                "provider": "opencode-go",
                "model": self.model,
                "stage": stage,
                "latency_ms": round((perf_counter() - started_at) * 1000, 3),
                **self._usage(response),
            },
        )
        return response

    @staticmethod
    def _chat_tools() -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": schema["name"],
                    "description": schema["description"],
                    "parameters": schema["parameters"],
                },
            }
            for schema in tool_schemas()
        ]

    @staticmethod
    def _message(response: dict[str, Any]) -> dict[str, Any]:
        choices = response.get("choices")
        if not isinstance(choices, list) or len(choices) != 1:
            raise RuntimeError("OpenCode Go debe devolver exactamente una respuesta.")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if not isinstance(message, dict):
            raise RuntimeError("OpenCode Go no devolvió un mensaje válido.")
        return cast(dict[str, Any], message)

    def select_tool(self, question: str, as_of_date: str) -> dict[str, Any]:
        """Ask DeepSeek to select exactly one closed BI function."""
        response = self._invoke(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"Fecha de corte obligatoria: {as_of_date}\nPregunta: {question}",
                    },
                ],
                "tools": self._chat_tools(),
                "tool_choice": "required",
                "temperature": 0,
                "max_tokens": 400,
            },
            "tool_selection",
        )
        calls = self._message(response).get("tool_calls")
        if not isinstance(calls, list) or len(calls) != 1:
            raise RuntimeError("El modelo debe seleccionar exactamente una tool BI autorizada.")
        call = calls[0]
        function = call.get("function") if isinstance(call, dict) else None
        if not isinstance(function, dict):
            raise RuntimeError("El modelo devolvió una llamada de tool inválida.")
        try:
            arguments = json.loads(str(function.get("arguments", "{}")))
        except json.JSONDecodeError as error:
            raise RuntimeError("El modelo devolvió argumentos de tool inválidos.") from error
        return {
            "tool_name": function.get("name"),
            "arguments": arguments,
            "call_id": call.get("id"),
        }

    def probe(self) -> None:
        """Perform one minimal authenticated completion for deployment verification."""
        response = self._invoke(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "Responde únicamente OK."},
                    {"role": "user", "content": "Verifica conectividad."},
                ],
                "temperature": 0,
                "max_tokens": 64,
            },
            "connection_probe",
        )
        content = self._message(response).get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("OpenCode Go no respondió al probe de conectividad.")

    def interpret(self, question: str, tool_result: dict[str, Any]) -> str:
        """Generate the visible answer from compact deterministic evidence only."""
        referenced_ids = {
            evidence_id
            for collection in ("findings", "alerts", "recommended_actions")
            for item in tool_result.get(collection, [])
            for evidence_id in item.get("evidence_refs", [])
        }
        compact = {
            "operation": tool_result.get("operation"),
            "as_of_date": tool_result.get("as_of_date"),
            "metrics": tool_result.get("metrics"),
            "findings": tool_result.get("findings"),
            "alerts": tool_result.get("alerts"),
            "recommended_actions": tool_result.get("recommended_actions"),
            "evidence": [
                item for item in tool_result.get("evidence", []) if item.get("id") in referenced_ids
            ],
            "data_quality": tool_result.get("data_quality"),
        }
        response = self._invoke(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            "Interpreta brevemente la pregunta usando exclusivamente el resultado "
                            f"determinístico.\nPregunta: {question}\nResultado: "
                            f"{json.dumps(compact, ensure_ascii=False)}"
                        ),
                    },
                ],
                "temperature": 0,
                "max_tokens": 600,
            },
            "interpretation",
        )
        content = self._message(response).get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("El modelo no devolvió una interpretación textual.")
        return content.strip()
