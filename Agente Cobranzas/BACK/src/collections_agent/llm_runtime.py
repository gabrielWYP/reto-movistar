"""OpenCode Go runtime for grounded Collections tool selection and interpretation."""

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
from .config import CollectionsSettings
from .prompting import SYSTEM_PROMPT

API_URL = "https://opencode.ai/zen/go/v1/chat/completions"
REQUEST_TIMEOUT_SECONDS = 60
CLIENT_USER_AGENT = "sonia-collections/1.0"
SELECTION_RETRY_MAX_TOKENS = 800
logger = logging.getLogger(__name__)


class OpenCodeRuntime:
    """Minimal OpenAI-compatible client with a closed two-stage flow."""

    def __init__(
        self,
        settings: CollectionsSettings | None = None,
        post: Callable[[dict[str, Any], str], dict[str, Any]] | None = None,
    ) -> None:
        self._settings = settings or CollectionsSettings.from_environment()
        self._post = post or self._http_post

    @property
    def available(self) -> bool:
        """Return whether the shared repository-injected key is present."""
        return bool(os.environ.get("OPENCODE_KEY", "").strip())

    @property
    def model(self) -> str:
        """Return the configured OpenCode model."""
        return self._settings.model

    def metadata(self) -> dict[str, str]:
        """Return public runtime metadata without authentication material."""
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
        """Extract only allow-listed provider details from an error body."""
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
        key = os.environ.get("OPENCODE_KEY", "").strip()
        if not key:
            raise RuntimeError("OPENCODE_KEY no está configurada; usa el modo determinístico.")
        started_at = perf_counter()
        try:
            response = self._post(payload, key)
        except RuntimeError:
            logger.exception(
                "collections_llm_request_failed",
                extra={
                    "provider": "opencode-go",
                    "model": self.model,
                    "stage": stage,
                    "latency_ms": round((perf_counter() - started_at) * 1000, 3),
                },
            )
            raise
        logger.info(
            "collections_llm_request_completed",
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
        """Parse exactly one provider-selected Collections tool and its JSON arguments."""
        calls = OpenCodeRuntime._message(response).get("tool_calls")
        if not isinstance(calls, list) or len(calls) != 1:
            raise RuntimeError(
                "El modelo debe seleccionar exactamente una tool de Cobranzas autorizada."
            )
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
        }

    def _selection_payload(
        self,
        question: str,
        cutoff: str,
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
        retry_tokens = min(
            max(self._settings.max_selection_tokens * 2, self._settings.max_selection_tokens),
            SELECTION_RETRY_MAX_TOKENS,
        )
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"{instruction}\nFecha de corte: {cutoff}\nPregunta: {question}",
                },
            ],
            "tools": self._chat_tools(),
            # DeepSeek thinking mode rejects tool_choice="required" at this provider.
            "tool_choice": "auto",
            "temperature": 0,
            "max_tokens": retry_tokens if retry else self._settings.max_selection_tokens,
        }

    def select_tool(self, question: str, as_of_date: str | None) -> dict[str, Any]:
        """Require one deterministic tool, retrying one invalid selection."""
        cutoff = as_of_date or "último evento disponible en el dataset"
        total_usage: dict[str, int] = {}
        last_error: RuntimeError | None = None
        for attempt, retry in enumerate((False, True), start=1):
            stage = "tool_selection_retry" if retry else "tool_selection"
            response = self._invoke(
                self._selection_payload(question, cutoff, retry=retry),
                stage,
            )
            for key, value in self._usage(response).items():
                total_usage[key] = total_usage.get(key, 0) + value
            diagnostics = self._selection_diagnostics(response)
            try:
                selection = self._parse_selection(response)
            except RuntimeError as error:
                last_error = error
                logger.warning(
                    "collections_llm_tool_selection_invalid",
                    extra={
                        "provider": "opencode-go",
                        "model": self.model,
                        "attempt": attempt,
                        **diagnostics,
                    },
                )
                continue
            logger.info(
                "collections_llm_tool_selection_valid",
                extra={
                    "provider": "opencode-go",
                    "model": self.model,
                    "attempt": attempt,
                    **diagnostics,
                },
            )
            return {**selection, "usage": total_usage}
        raise RuntimeError(
            "El modelo no seleccionó exactamente una tool de Cobranzas autorizada "
            "tras dos intentos."
        ) from last_error

    def interpret(self, question: str, tool_result: dict[str, Any]) -> tuple[str, dict[str, int]]:
        """Interpret compact deterministic evidence without exposing the full ledger."""
        evidence = tool_result.get("evidence", [])
        compact = {
            "operation": tool_result.get("operation"),
            "as_of_date": tool_result.get("as_of_date"),
            "entity": tool_result.get("entity"),
            "status": tool_result.get("status"),
            "metrics": tool_result.get("metrics"),
            "aging": tool_result.get("aging", [])[:10],
            "findings": tool_result.get("findings"),
            "alerts": tool_result.get("alerts"),
            "recommended_actions": tool_result.get("recommended_actions"),
            "evidence": evidence[:10] if isinstance(evidence, list) else [],
            "evidence_truncated": isinstance(evidence, list) and len(evidence) > 10,
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
                            "Responde brevemente usando exclusivamente el resultado "
                            f"determinístico.\nPregunta: {question}\nResultado: "
                            f"{json.dumps(compact, ensure_ascii=False)}"
                        ),
                    },
                ],
                "temperature": 0,
                "max_tokens": self._settings.max_output_tokens,
            },
            "interpretation",
        )
        content = self._message(response).get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("El modelo no devolvió una interpretación textual.")
        return content.strip(), self._usage(response)

    def probe(self) -> None:
        """Perform a minimal authenticated completion for deployment verification."""
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
        message = self._message(response)
        signals = (message.get("content"), message.get("reasoning_content"))
        if not any(isinstance(value, str) and value.strip() for value in signals):
            raise RuntimeError("OpenCode Go no devolvió contenido en el probe.")
