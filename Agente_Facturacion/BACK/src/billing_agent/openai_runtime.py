"""OpenCode Go adapter for closed Billing tool selection and interpretation."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from time import perf_counter
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .agent import SYSTEM_PROMPT, tool_schemas

API_URL = "https://opencode.ai/zen/go/v1/chat/completions"
DEFAULT_MODEL = "deepseek-v4-flash"
REQUEST_TIMEOUT_SECONDS = 60
SELECTION_TOKENS = 400
SELECTION_RETRY_TOKENS = 800
CLIENT_USER_AGENT = "sonia-billing/1.0"
LOG = logging.getLogger(__name__)


def extract_output_text(response: dict[str, Any]) -> str:
    """Extract visible text from one OpenAI-compatible chat completion."""
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        return ""
    choice = choices[0]
    message = choice.get("message") if isinstance(choice, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    return content.strip() if isinstance(content, str) else ""


class OpenCodeRuntime:
    """Minimal two-stage runtime that never executes provider-generated code."""

    def __init__(
        self,
        post: Callable[[dict[str, Any], str], dict[str, Any]] | None = None,
    ) -> None:
        self._post = post or self._http_post

    @property
    def available(self) -> bool:
        """Return whether the repository-injected provider key is configured."""
        return bool(os.environ.get("OPENCODE_KEY", "").strip())

    @property
    def model(self) -> str:
        """Return the configured Billing model identifier."""
        return os.environ.get("SONIA_BILLING_MODEL", "").strip() or DEFAULT_MODEL

    def metadata(self) -> dict[str, str]:
        """Expose public provider metadata without authentication material."""
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
            raise RuntimeError(f"OpenCode Go devolvió HTTP {error.code}.") from error
        except (TimeoutError, URLError) as error:
            raise RuntimeError("No se pudo conectar con OpenCode Go.") from error
        except json.JSONDecodeError as error:
            raise RuntimeError("OpenCode Go devolvió JSON inválido.") from error

    @staticmethod
    def _usage(response: dict[str, Any]) -> dict[str, int]:
        usage = response.get("usage")
        if not isinstance(usage, dict):
            return {}
        return {
            key: value
            for key in ("prompt_tokens", "completion_tokens", "total_tokens")
            if isinstance((value := usage.get(key)), int) and not isinstance(value, bool)
        }

    def _invoke(self, payload: dict[str, Any], stage: str) -> dict[str, Any]:
        key = os.environ.get("OPENCODE_KEY", "").strip()
        if not key:
            raise RuntimeError("OPENCODE_KEY no está configurada.")
        started_at = perf_counter()
        try:
            response = self._post(payload, key)
        except RuntimeError:
            LOG.exception(
                "billing_llm_request_failed",
                extra={
                    **self.metadata(),
                    "stage": stage,
                    "latency_ms": round((perf_counter() - started_at) * 1000, 3),
                },
            )
            raise
        LOG.info(
            "billing_llm_request_completed",
            extra={
                **self.metadata(),
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

    @classmethod
    def _parse_selection(cls, response: dict[str, Any]) -> dict[str, Any]:
        calls = cls._message(response).get("tool_calls")
        if not isinstance(calls, list) or len(calls) != 1:
            raise RuntimeError("El modelo debe seleccionar exactamente una tool Billing autorizada.")
        call = calls[0]
        function = call.get("function") if isinstance(call, dict) else None
        if not isinstance(function, dict):
            raise RuntimeError("El modelo devolvió una llamada de tool inválida.")
        try:
            arguments = json.loads(str(function.get("arguments", "{}")))
        except json.JSONDecodeError as error:
            raise RuntimeError("El modelo devolvió argumentos de tool inválidos.") from error
        return {"tool_name": function.get("name"), "arguments": arguments}

    def select_tool(self, question: str) -> dict[str, Any]:
        """Select one closed Billing tool, retrying one incomplete response."""
        last_error: RuntimeError | None = None
        for attempt, max_tokens in enumerate((SELECTION_TOKENS, SELECTION_RETRY_TOKENS), start=1):
            retry = attempt == 2
            instruction = (
                "REINTENTO: devuelve exactamente una llamada de tool; no respondas texto."
                if retry
                else "Selecciona exactamente una tool; no respondas texto ni expliques."
            )
            response = self._invoke(
                {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"{instruction}\nPregunta: {question}"},
                    ],
                    "tools": self._chat_tools(),
                    "tool_choice": "auto",
                    "temperature": 0,
                    "max_tokens": max_tokens,
                },
                "tool_selection_retry" if retry else "tool_selection",
            )
            try:
                return self._parse_selection(response)
            except RuntimeError as error:
                last_error = error
                choices = response.get("choices")
                choice = choices[0] if isinstance(choices, list) and choices else {}
                message = choice.get("message", {}) if isinstance(choice, dict) else {}
                calls = message.get("tool_calls") if isinstance(message, dict) else None
                LOG.warning(
                    "billing_llm_tool_selection_invalid",
                    extra={
                        **self.metadata(),
                        "attempt": attempt,
                        "finish_reason": choice.get("finish_reason", "unknown"),
                        "tool_call_count": len(calls) if isinstance(calls, list) else 0,
                    },
                )
        raise RuntimeError(
            "El modelo no seleccionó exactamente una tool Billing autorizada tras dos intentos."
        ) from last_error

    def interpret(self, question: str, compact_result: dict[str, Any]) -> str:
        """Narrate only compact deterministic Billing evidence."""
        response = self._invoke(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            "Responde brevemente usando exclusivamente el resultado determinístico. "
                            "No agregues cifras ni causas.\n"
                            f"Pregunta: {question}\nResultado: "
                            f"{json.dumps(compact_result, ensure_ascii=False)}"
                        ),
                    },
                ],
                "temperature": 0,
                "max_tokens": 600,
            },
            "interpretation",
        )
        answer = extract_output_text(response)
        if not answer:
            raise RuntimeError("El modelo no devolvió una interpretación textual.")
        return answer

# Compatibility for Camila's public package imports; new code uses OpenCodeRuntime.
OpenAIRuntime = OpenCodeRuntime
