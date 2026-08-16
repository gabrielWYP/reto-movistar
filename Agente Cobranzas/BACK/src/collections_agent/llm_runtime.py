"""Official OpenAI Responses runtime for grounded Collections tool use."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from time import perf_counter
from typing import Any, cast

from .agent import tool_schemas
from .config import CollectionsSettings
from .prompting import SYSTEM_PROMPT

REQUEST_TIMEOUT_SECONDS = 60.0
logger = logging.getLogger(__name__)


class OpenAIRuntime:
    """Lazy OpenAI SDK adapter; financial calculations never run in the model."""

    def __init__(
        self,
        settings: CollectionsSettings | None = None,
        create_response: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self._settings = settings or CollectionsSettings.from_environment()
        self._create_response = create_response
        self._client: Any | None = None

    @property
    def available(self) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY", "").strip())

    @property
    def model(self) -> str:
        return self._settings.model

    @property
    def max_tool_calls(self) -> int:
        return self._settings.max_tool_calls

    def metadata(self) -> dict[str, str]:
        return {"provider": "openai", "model": self.model}

    @staticmethod
    def _usage(response: dict[str, Any]) -> dict[str, int]:
        usage = response.get("usage")
        if not isinstance(usage, dict):
            return {}
        allowed = ("input_tokens", "output_tokens", "total_tokens")
        return {
            key: value
            for key in allowed
            if isinstance((value := usage.get(key)), int) and not isinstance(value, bool)
        }

    def _sdk_create(self, payload: dict[str, Any]) -> dict[str, Any]:
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "La consulta con IA requiere OPENAI_API_KEY; las vistas determinísticas "
                "continúan disponibles."
            )
        try:
            from openai import OpenAI
        except ImportError as error:
            raise RuntimeError(
                "Falta el SDK oficial de OpenAI en el backend de Cobranzas."
            ) from error
        if self._client is None:
            self._client = OpenAI(
                api_key=api_key,
                timeout=REQUEST_TIMEOUT_SECONDS,
                max_retries=2,
            )
        try:
            response = self._client.responses.create(**payload)
            result = cast(dict[str, Any], response.model_dump(mode="json"))
            result["output_text"] = response.output_text
            return result
        except Exception as error:
            raise RuntimeError(
                "OpenAI no pudo completar la consulta; revisa la clave, el modelo y la conexión."
            ) from error

    def create(
        self,
        input_items: list[dict[str, Any]],
        *,
        require_tool: bool,
        stage: str,
    ) -> dict[str, Any]:
        """Create one bounded response with only the closed Collections tools."""
        if not self.available:
            raise RuntimeError(
                "La consulta con IA requiere OPENAI_API_KEY; las vistas determinísticas "
                "continúan disponibles."
            )
        payload: dict[str, Any] = {
            "model": self.model,
            "store": False,
            "instructions": SYSTEM_PROMPT,
            "input": input_items,
            "tools": tool_schemas(),
            "tool_choice": "required" if require_tool else "auto",
            "reasoning": {"effort": self._settings.reasoning_effort},
            "max_output_tokens": self._settings.max_output_tokens,
        }
        started_at = perf_counter()
        try:
            response = (
                self._create_response(payload)
                if self._create_response is not None
                else self._sdk_create(payload)
            )
        except RuntimeError:
            logger.exception(
                "collections_openai_request_failed",
                extra={
                    **self.metadata(),
                    "stage": stage,
                    "latency_ms": round((perf_counter() - started_at) * 1000, 3),
                },
            )
            raise
        logger.info(
            "collections_openai_request_completed",
            extra={
                **self.metadata(),
                "stage": stage,
                "latency_ms": round((perf_counter() - started_at) * 1000, 3),
                **self._usage(response),
            },
        )
        return response

    @staticmethod
    def function_calls(response: dict[str, Any]) -> list[dict[str, Any]]:
        output = response.get("output")
        if not isinstance(output, list):
            return []
        return [
            cast(dict[str, Any], item)
            for item in output
            if isinstance(item, dict) and item.get("type") == "function_call"
        ]

    @staticmethod
    def output_items(response: dict[str, Any]) -> list[dict[str, Any]]:
        output = response.get("output")
        return [cast(dict[str, Any], item) for item in output] if isinstance(output, list) else []

    @staticmethod
    def output_text(response: dict[str, Any]) -> str:
        text = response.get("output_text")
        return text.strip() if isinstance(text, str) else ""

    @classmethod
    def usage(cls, response: dict[str, Any]) -> dict[str, int]:
        return cls._usage(response)

    def probe(self) -> None:
        response = self.create(
            [{"role": "user", "content": "Verifica conectividad y responde OK."}],
            require_tool=False,
            stage="connection_probe",
        )
        if not self.output_text(response):
            raise RuntimeError("OpenAI no devolvió contenido en la prueba de conexión.")
