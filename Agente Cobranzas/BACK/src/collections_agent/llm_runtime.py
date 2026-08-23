"""OpenCode Go runtime for grounded Collections tool use."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from time import perf_counter
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .agent import tool_schemas
from .config import CollectionsSettings
from .prompting import SYSTEM_PROMPT

API_URL = "https://opencode.ai/zen/go/v1/chat/completions"
DEFAULT_MODEL = "deepseek-v4-flash"
REQUEST_TIMEOUT_SECONDS = 60
CLIENT_USER_AGENT = "sonia-collections/1.0"
SELECTION_RETRY_MAX_TOKENS = 1600
PROBE_MAX_TOKENS = 64
PROBE_RETRY_MAX_TOKENS = 512
logger = logging.getLogger(__name__)


class OpenCodeRuntime:
    """Minimal OpenCode adapter; calculations stay in local tools."""

    def __init__(
        self,
        settings: CollectionsSettings | None = None,
        post: Callable[[dict[str, Any], str], dict[str, Any]] | None = None,
    ) -> None:
        self._settings = settings or CollectionsSettings.from_environment()
        self._post = post or self._http_post

    @property
    def available(self) -> bool:
        return bool(os.environ.get("OPENCODE_KEY", "").strip())

    @property
    def model(self) -> str:
        return self._settings.model

    @property
    def max_tool_calls(self) -> int:
        return self._settings.max_tool_calls

    def metadata(self) -> dict[str, str]:
        return {"provider": "opencode-go", "model": self.model}

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

    def _invoke(self, payload: dict[str, Any], stage: str) -> dict[str, Any]:
        api_key = os.environ.get("OPENCODE_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "La consulta con IA requiere OPENCODE_KEY; las vistas determinísticas "
                "continúan disponibles."
            )
        started_at = perf_counter()
        try:
            response = self._post(payload, api_key)
        except RuntimeError:
            logger.exception(
                "collections_opencode_request_failed",
                extra={
                    **self.metadata(),
                    "stage": stage,
                    "latency_ms": round((perf_counter() - started_at) * 1000, 3),
                },
            )
            raise
        logger.info(
            "collections_opencode_request_completed",
            extra={
                **self.metadata(),
                "stage": stage,
                "latency_ms": round((perf_counter() - started_at) * 1000, 3),
                **self._usage(response),
            },
        )
        return response

    def create(
        self,
        messages: list[dict[str, Any]],
        *,
        require_tool: bool,
        stage: str,
    ) -> dict[str, Any]:
        """Create a bounded chat completion with only closed Collections tools."""
        limits: tuple[int, ...] = (self._settings.max_output_tokens,)
        if require_tool:
            limits += (min(self._settings.max_output_tokens * 2, SELECTION_RETRY_MAX_TOKENS),)
        response: dict[str, Any] = {}
        for attempt, max_tokens in enumerate(limits, start=1):
            request_messages = [{"role": "system", "content": SYSTEM_PROMPT}, *messages]
            if attempt > 1:
                request_messages.append(
                    {
                        "role": "user",
                        "content": (
                            "REINTENTO: devuelve al menos una llamada a una tool autorizada. "
                            "No respondas únicamente con texto."
                        ),
                    }
                )
            response = self._invoke(
                {
                    "model": self.model,
                    "messages": request_messages,
                    "tools": self._chat_tools(),
                    "tool_choice": "auto",
                    "temperature": 0,
                    "max_tokens": max_tokens,
                },
                f"{stage}_retry" if attempt > 1 else stage,
            )
            if not require_tool or self.function_calls(response):
                return response
            logger.warning(
                "collections_opencode_tool_selection_invalid",
                extra={**self.metadata(), "attempt": attempt},
            )
        return response

    @staticmethod
    def function_calls(response: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            calls = OpenCodeRuntime._message(response).get("tool_calls")
        except RuntimeError:
            return []
        if not isinstance(calls, list):
            return []
        normalized: list[dict[str, Any]] = []
        for item in calls:
            function = item.get("function") if isinstance(item, dict) else None
            if not isinstance(function, dict):
                continue
            normalized.append(
                {
                    "call_id": item.get("id"),
                    "name": function.get("name"),
                    "arguments": function.get("arguments", "{}"),
                }
            )
        return normalized

    @staticmethod
    def output_items(response: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            return [OpenCodeRuntime._message(response)]
        except RuntimeError:
            return []

    @staticmethod
    def output_text(response: dict[str, Any]) -> str:
        try:
            text = OpenCodeRuntime._message(response).get("content")
        except RuntimeError:
            return ""
        return text.strip() if isinstance(text, str) else ""

    @classmethod
    def usage(cls, response: dict[str, Any]) -> dict[str, int]:
        return cls._usage(response)

    def probe(self) -> None:
        for attempt, max_tokens in enumerate((PROBE_MAX_TOKENS, PROBE_RETRY_MAX_TOKENS), start=1):
            response = self._invoke(
                {
                    "model": self.model,
                    "messages": [{"role": "user", "content": "Responde únicamente OK."}],
                    "temperature": 0,
                    "max_tokens": max_tokens,
                },
                "connection_probe_retry" if attempt > 1 else "connection_probe",
            )
            message = self._message(response)
            visible = message.get("content")
            reasoning = message.get("reasoning_content")
            if any(isinstance(value, str) and value.strip() for value in (visible, reasoning)):
                return
        raise RuntimeError("OpenCode Go no devolvió contenido en la prueba de conexión.")
