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
SELECTION_MAX_TOKENS = 800
SELECTION_RETRY_MAX_TOKENS = 1600
PROBE_MAX_TOKENS = 64
PROBE_RETRY_MAX_TOKENS = 512
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
        """Extract an allow-listed, non-sensitive detail from an HTTP error body."""
        try:
            body = error.read(2048).decode("utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            return None
        match = re.search(r"\berror code:\s*(\d{3,5})\b", body, flags=re.IGNORECASE)
        if match:
            return f"Cloudflare error {match.group(1)}"
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return None
        provider_error = payload.get("error") if isinstance(payload, dict) else None
        if not isinstance(provider_error, dict):
            return None
        message = provider_error.get("message")
        thinking_tool_choice_error = (
            isinstance(message, str)
            and "thinking mode does not support this tool_choice" in message.lower()
        )
        if thinking_tool_choice_error:
            return "Provider incompatibility: thinking mode/tool_choice"
        code = provider_error.get("code")
        if isinstance(code, str) and re.fullmatch(r"[a-z0-9_-]{1,64}", code):
            return f"Provider error {code}"
        return None

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

    @staticmethod
    def _selection_diagnostics(response: dict[str, Any]) -> dict[str, Any]:
        """Return safe tool-selection metadata without prompts or model content."""
        choices = response.get("choices")
        choice = choices[0] if isinstance(choices, list) and len(choices) == 1 else None
        message = choice.get("message") if isinstance(choice, dict) else None
        calls = message.get("tool_calls") if isinstance(message, dict) else None
        finish_reason = choice.get("finish_reason") if isinstance(choice, dict) else None
        return {
            "finish_reason": finish_reason if isinstance(finish_reason, str) else "unknown",
            "tool_call_count": len(calls) if isinstance(calls, list) else 0,
        }

    @staticmethod
    def _parse_selection(response: dict[str, Any]) -> dict[str, Any]:
        """Parse exactly one provider-selected BI tool without trusting its arguments."""
        calls = OpenCodeRuntime._message(response).get("tool_calls")
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

    def _selection_payload(
        self,
        question: str,
        as_of_date: str,
        *,
        retry: bool,
    ) -> dict[str, Any]:
        """Build a bounded tool-only request compatible with DeepSeek thinking mode."""
        instruction = (
            "REINTENTO: devuelve exactamente una sola llamada a una tool autorizada. "
            "No respondas con texto, no expliques tu elección y no llames varias tools."
            if retry
            else "Selecciona exactamente una sola tool autorizada para responder. "
            "No respondas con texto ni expliques tu elección."
        )
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"{instruction}\nFecha de corte obligatoria: {as_of_date}"
                        f"\nPregunta: {question}"
                    ),
                },
            ],
            "tools": self._chat_tools(),
            # DeepSeek thinking mode rejects tool_choice="required" at this provider.
            "tool_choice": "auto",
            "temperature": 0,
            "max_tokens": SELECTION_RETRY_MAX_TOKENS if retry else SELECTION_MAX_TOKENS,
        }

    def select_tool(self, question: str, as_of_date: str) -> dict[str, Any]:
        """Ask DeepSeek for one closed BI function, retrying one invalid selection."""
        last_error: RuntimeError | None = None
        for attempt, retry in enumerate((False, True), start=1):
            stage = "tool_selection_retry" if retry else "tool_selection"
            response = self._invoke(
                self._selection_payload(question, as_of_date, retry=retry),
                stage,
            )
            diagnostics = self._selection_diagnostics(response)
            try:
                selection = self._parse_selection(response)
            except RuntimeError as error:
                last_error = error
                logger.warning(
                    "bi_llm_tool_selection_invalid",
                    extra={
                        "provider": "opencode-go",
                        "model": self.model,
                        "attempt": attempt,
                        **diagnostics,
                    },
                )
                continue
            logger.info(
                "bi_llm_tool_selection_valid",
                extra={
                    "provider": "opencode-go",
                    "model": self.model,
                    "attempt": attempt,
                    **diagnostics,
                },
            )
            return selection
        raise RuntimeError(
            "El modelo no seleccionó exactamente una tool BI autorizada tras dos intentos."
        ) from last_error

    def probe(self) -> None:
        """Verify connectivity, retrying once when thinking exhausts the small budget."""
        for attempt, retry in enumerate((False, True), start=1):
            response = self._invoke(
                {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "Responde únicamente OK."},
                        {"role": "user", "content": "Verifica conectividad."},
                    ],
                    "temperature": 0,
                    "max_tokens": PROBE_RETRY_MAX_TOKENS if retry else PROBE_MAX_TOKENS,
                },
                "connection_probe_retry" if retry else "connection_probe",
            )
            message = self._message(response)
            completion_signals = (message.get("content"), message.get("reasoning_content"))
            if any(isinstance(value, str) and value.strip() for value in completion_signals):
                return
            logger.warning(
                "bi_llm_probe_empty",
                extra={
                    "provider": "opencode-go",
                    "model": self.model,
                    "attempt": attempt,
                    **self._selection_diagnostics(response),
                    **self._usage(response),
                },
            )
        raise RuntimeError(
            "OpenCode Go no devolvió contenido ni razonamiento tras dos intentos del probe."
        )

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
