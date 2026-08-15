"""UI-independent application boundary for the integrated BI agent."""

from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Any

from .agent import ask, dispatch, validate_arguments
from .llm_runtime import OpenAIRuntime
from .presentation import presentation_for
from .service import BIService
from .visuals import dashboard_spec


class BIBackend:
    """Facade suitable for FastAPI, CLI adapters and the future Supervisor."""

    def __init__(
        self,
        dataset_path: Path | None = None,
        *,
        service: BIService | None = None,
        runtime: OpenAIRuntime | None = None,
    ) -> None:
        self._dataset_path = dataset_path
        self._service = service
        self._runtime = runtime or OpenAIRuntime()
        self._service_lock = Lock()

    @property
    def configured(self) -> bool:
        """Report availability without loading the potentially large dataset."""
        return self._service is not None or bool(
            self._dataset_path and self._dataset_path.exists()
        )

    @property
    def llm_available(self) -> bool:
        return self._runtime.available

    def service(self) -> BIService:
        """Lazily build the deterministic service once for the backend process."""
        if self._service is None:
            with self._service_lock:
                if self._service is None:
                    if not self._dataset_path or not self._dataset_path.exists():
                        raise RuntimeError(
                            "Dataset BI no configurado; define SONIA_BI_DATASET_PATH "
                            "con un directorio de seis CSV o un ZIP oficial."
                        )
                    self._service = BIService(self._dataset_path)
        return self._service

    @staticmethod
    def _present(result: dict[str, Any]) -> dict[str, Any]:
        dashboard = dashboard_spec(result["agent_response"])
        return {
            **result,
            "dashboard": dashboard,
            "presentation": presentation_for(result["agent_response"], dashboard),
        }

    def query(self, question: str, as_of_date: str) -> dict[str, Any]:
        """Ask BI using optional LLM routing with deterministic fail-safe behavior."""
        try:
            result = ask(self.service(), question, as_of_date, self._runtime)
        except RuntimeError as error:
            if not self._runtime.available:
                raise
            result = ask(self.service(), question, as_of_date, None)
            result["mode"] = "deterministic_fallback"
            result["runtime_warning"] = str(error)
        return self._present(result)

    def execute_tool(
        self,
        operation: str,
        parameters: dict[str, Any],
        as_of_date: str,
    ) -> dict[str, Any]:
        """Execute exactly one approved deterministic tool."""
        validated = validate_arguments(operation, parameters, as_of_date)
        payload = dispatch(self.service(), operation, validated, as_of_date)
        result = {
            "answer": "Resultado determinístico solicitado.",
            "tool_used": operation,
            "tool_arguments": validated,
            "agent_response": payload,
            "mode": "deterministic",
        }
        return self._present(result)
