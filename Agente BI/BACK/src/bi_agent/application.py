"""UI-independent application boundary for the integrated BI agent."""

from __future__ import annotations

from collections.abc import Callable
from threading import Lock
from typing import Any

from .agent import ask, dispatch, validate_arguments
from .data import missing_dataset_files, normalize_dataset_files
from .llm_runtime import OpenCodeRuntime
from .presentation import presentation_for
from .prompting import prompt_metadata
from .service import BIService
from .visuals import dashboard_spec


class BIBackend:
    """Facade suitable for FastAPI, CLI adapters and the future Supervisor."""

    def __init__(
        self,
        *,
        service: BIService | None = None,
        runtime: OpenCodeRuntime | None = None,
        collections_response_provider: Callable[[str], object] | None = None,
    ) -> None:
        self._service = service
        self._dataset_files: dict[str, bytes] = {}
        self._dataset_bytes = 0
        self._dataset_source = "injected" if service is not None else None
        self._runtime = runtime or OpenCodeRuntime()
        self._collections_response_provider = collections_response_provider
        self._service_lock = Lock()
        if self._service is not None and collections_response_provider is not None:
            self._service.set_collections_response_provider(collections_response_provider)

    @property
    def configured(self) -> bool:
        """Report availability without loading the potentially large dataset."""
        return self._service is not None

    @property
    def llm_available(self) -> bool:
        return self._runtime.available

    @property
    def llm_metadata(self) -> dict[str, str]:
        """Expose provider and model without leaking authentication state."""
        return self._runtime.metadata()

    def set_collections_response_provider(
        self,
        provider: Callable[[str], object] | None,
    ) -> None:
        """Bind a read-only JSON provider used by management insights."""
        with self._service_lock:
            self._collections_response_provider = provider
            if self._service is not None:
                self._service.set_collections_response_provider(provider)

    def dataset_status(self) -> dict[str, Any]:
        """Return non-sensitive metadata for the process-local dataset."""
        missing = missing_dataset_files(self._dataset_files) if not self.configured else []
        if self.configured:
            status = "ready"
        elif self._dataset_files:
            status = "dataset_incomplete"
        else:
            status = "dataset_not_configured"
        return {
            "status": status,
            "dataset_configured": self.configured,
            "dataset_source": self._dataset_source,
            "dataset_file_count": len(self._dataset_files),
            "dataset_bytes": self._dataset_bytes,
            "missing_files": missing,
        }

    def upload_dataset(self, files: dict[str, bytes], max_bytes: int) -> dict[str, Any]:
        """Merge uploaded CSVs in memory and atomically rebuild when complete."""
        incoming = normalize_dataset_files(files)
        with self._service_lock:
            candidate = {**self._dataset_files, **incoming}
            total_bytes = sum(len(content) for content in candidate.values())
            if total_bytes > max_bytes:
                raise ValueError("El dataset en memoria excede el límite de 25 MiB.")
            missing = missing_dataset_files(candidate)
            if missing:
                self._dataset_files = candidate
                self._dataset_bytes = total_bytes
                self._dataset_source = "memory"
                return self.dataset_status()

            service = BIService(
                candidate,
                collections_response_provider=self._collections_response_provider,
            )
            self._dataset_files = candidate
            self._dataset_bytes = total_bytes
            self._dataset_source = "memory"
            self._service = service
            return self.dataset_status()

    def publish_dataset(
        self,
        service: BIService,
        files: dict[str, bytes],
        *,
        source: str,
    ) -> dict[str, Any]:
        """Publish a dataset already validated by the shared Supervisor."""
        with self._service_lock:
            service.set_collections_response_provider(self._collections_response_provider)
            self._service = service
            self._dataset_files = dict(files)
            self._dataset_bytes = sum(len(content) for content in files.values())
            self._dataset_source = source
            return self.dataset_status()

    def service(self) -> BIService:
        """Lazily build the deterministic service once for the backend process."""
        if self._service is None:
            raise RuntimeError(
                "Dataset BI no configurado; carga los seis CSV o un ZIP "
                "mediante POST /api/bi/dataset."
            )
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
            result["prompt"] = prompt_metadata()
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
