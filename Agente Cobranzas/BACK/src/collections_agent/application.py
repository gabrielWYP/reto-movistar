"""UI-independent application boundary for the collections agent."""

from __future__ import annotations

import os
from threading import RLock
from typing import Any

from .agent import dispatch, tool_definitions
from .config import CollectionsSettings
from .openai_runtime import ask
from .service import CollectionsService
from .uploads import load_uploaded_csvs


class CollectionsBackend:
    """Process-local facade shared by FastAPI and a future Supervisor."""

    def __init__(
        self,
        *,
        service: CollectionsService | None = None,
        settings: CollectionsSettings | None = None,
    ) -> None:
        self._settings = settings or CollectionsSettings.from_environment()
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
            self._dataset_error = f"No se encontró el dataset configurado: {dataset_path}"
            return
        try:
            self._service = CollectionsService(dataset_path)
            self._dataset_source = "configured_file"
        except (KeyError, OSError, ValueError) as error:
            self._dataset_error = f"No se pudo cargar el dataset configurado: {error}"

    @property
    def configured(self) -> bool:
        return self._service is not None

    @property
    def settings(self) -> CollectionsSettings:
        return self._settings

    @property
    def llm_available(self) -> bool:
        return bool(os.getenv("OPENAI_API_KEY", "").strip())

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

    def execute_tool(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        allowed = {tool.name for tool in tool_definitions()}
        if operation not in allowed:
            raise KeyError(f"Operación de Cobranzas no autorizada: {operation}")
        return dispatch(self.service(), operation, arguments)

    def query(self, question: str) -> dict[str, Any]:
        return ask(self.service(), question, settings=self._settings)
