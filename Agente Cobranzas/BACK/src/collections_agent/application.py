"""UI-independent application boundary for the collections agent."""

from __future__ import annotations

import logging
from threading import RLock
from time import perf_counter
from typing import Any

from .agent import ask, dispatch, tool_definitions, validate_arguments
from .config import CollectionsSettings
from .llm_runtime import OpenCodeRuntime
from .service import CollectionsService
from .uploads import load_uploaded_csvs

logger = logging.getLogger(__name__)


class CollectionsBackend:
    """Process-local facade shared by FastAPI and a future Supervisor."""

    def __init__(
        self,
        *,
        service: CollectionsService | None = None,
        settings: CollectionsSettings | None = None,
        runtime: OpenCodeRuntime | None = None,
    ) -> None:
        self._settings = settings or CollectionsSettings.from_environment()
        self._runtime = runtime or OpenCodeRuntime(self._settings)
        self._service = service
        self._dataset_source = "injected" if service is not None else None
        self._dataset_error: str | None = None
        self._lock = RLock()
        self._load_configured_dataset()

    def _load_configured_dataset(self) -> None:
        dataset_path = self._settings.dataset_path
        if self._service is not None or dataset_path is None:
            return
        if not dataset_path.is_file():
            self._dataset_error = "No se encontró el dataset configurado."
            return
        try:
            self._service = CollectionsService(dataset_path)
            self._dataset_source = "configured_file"
        except (KeyError, OSError, ValueError) as error:
            self._dataset_error = (
                f"No se pudo cargar el dataset configurado: {type(error).__name__}"
            )

    @property
    def configured(self) -> bool:
        return self._service is not None

    @property
    def settings(self) -> CollectionsSettings:
        return self._settings

    @property
    def llm_available(self) -> bool:
        return self._runtime.available

    @property
    def llm_metadata(self) -> dict[str, str]:
        """Expose provider and model without revealing credential state."""
        return self._runtime.metadata()

    def dataset_status(self) -> dict[str, Any]:
        service = self._service
        return {
            "status": "ready" if service is not None else "dataset_not_configured",
            "dataset_configured": service is not None,
            "dataset_source": self._dataset_source,
            "dataset_error": self._dataset_error,
            "source_counts": service.ledger.source_counts if service is not None else {},
        }

    def service(self) -> CollectionsService:
        with self._lock:
            if self._service is None:
                raise RuntimeError(
                    "Dataset de Cobranzas no configurado; carga al menos el CSV de facturas."
                )
            return self._service

    def upload_dataset(self, files: list[tuple[str, bytes]]) -> dict[str, object]:
        dataset, report = load_uploaded_csvs(
            files,
            self._settings.max_upload_files,
            self._settings.max_upload_bytes,
        )
        if dataset is None:
            return report.to_dict()
        candidate = CollectionsService.from_dataset(dataset)
        with self._lock:
            self._service = candidate
            self._dataset_source = "memory"
            self._dataset_error = None
        return report.to_dict()

    def publish_dataset(
        self,
        service: CollectionsService,
        *,
        source: str,
    ) -> dict[str, Any]:
        """Publish a dataset already validated by the shared Supervisor."""
        with self._lock:
            self._service = service
            self._dataset_source = source
            self._dataset_error = None
            return self.dataset_status()

    def execute_tool(
        self,
        operation: str,
        arguments: dict[str, Any],
        as_of_date: str | None = None,
    ) -> dict[str, Any]:
        allowed = {tool.name for tool in tool_definitions()}
        if operation not in allowed:
            raise KeyError(f"Operación de Cobranzas no autorizada: {operation}")
        validated = validate_arguments(operation, arguments, as_of_date)
        return dispatch(self.service(), operation, validated, as_of_date)

    def query(self, question: str, as_of_date: str | None = None) -> dict[str, Any]:
        """Query OpenCode while keeping calculations inside deterministic tools."""
        started_at = perf_counter()
        service = self.service()
        result = ask(service, question, as_of_date, self._runtime)

        logger.info(
            "collections_query_completed",
            extra={
                "mode": result["mode"],
                "tool_used": result["tool_used"],
                "provider": self._runtime.metadata()["provider"],
                "model": self._runtime.metadata()["model"],
                "latency_ms": round((perf_counter() - started_at) * 1000, 3),
                **result.get("usage", {}),
            },
        )
        return result
