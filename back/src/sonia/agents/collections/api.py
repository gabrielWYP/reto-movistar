"""FastAPI router for the collections module inside the shared backend."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from .agent import tool_definitions
from .application import CollectionsBackend
from .config import CollectionsSettings

UPLOAD_CHUNK_BYTES = 1024 * 1024


class CollectionsQueryRequest(BaseModel):
    """Natural-language request interpreted through OpenAI tool selection."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=1000)


def create_collections_router(backend: CollectionsBackend) -> APIRouter:
    """Create routes mounted by the single shared FastAPI application."""
    router = APIRouter(prefix="/api/collections", tags=["collections"])

    def service():  # type: ignore[no-untyped-def]
        try:
            return backend.service()
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @router.get("/status")
    def status() -> dict[str, Any]:
        settings = CollectionsSettings.from_environment()
        return {
            **backend.dataset_status(),
            "openai_enabled": backend.llm_available,
            "model": settings.model,
            "tools": sorted(tool.name for tool in tool_definitions()),
        }

    @router.get("/portfolio")
    def portfolio(as_of_date: str | None = None) -> dict[str, Any]:
        try:
            return service().portfolio_snapshot(as_of_date)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.get("/customer")
    def customer(id: str, as_of_date: str | None = None) -> dict[str, Any]:
        try:
            return service().customer_snapshot(id, as_of_date)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.get("/invoice")
    def invoice(id: str, as_of_date: str | None = None) -> dict[str, Any]:
        try:
            return service().invoice_trace(id, as_of_date)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.get("/priorities")
    def priorities(limit: int = 10, as_of_date: str | None = None) -> dict[str, Any]:
        try:
            return service().collection_priorities(max(1, min(limit, 50)), as_of_date)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.get("/exceptions")
    def exceptions(limit: int = 10, as_of_date: str | None = None) -> dict[str, Any]:
        try:
            return service().reconciliation_exceptions(max(1, min(limit, 50)), as_of_date)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/dataset")
    async def upload_dataset(
        files: Annotated[list[UploadFile], File(...)],
    ) -> dict[str, object]:
        settings = CollectionsSettings.from_environment()
        if not files:
            raise HTTPException(status_code=422, detail="Selecciona al menos un CSV.")
        if len(files) > settings.max_upload_files:
            raise HTTPException(
                status_code=422,
                detail=f"Puedes cargar como máximo {settings.max_upload_files} archivos.",
            )

        payload: list[tuple[str, bytes]] = []
        request_bytes = 0
        for upload in files:
            filename = Path(upload.filename or "").name
            if not filename or Path(filename).suffix.lower() != ".csv":
                raise HTTPException(status_code=422, detail="Solo se aceptan archivos CSV.")
            chunks: list[bytes] = []
            while chunk := await upload.read(UPLOAD_CHUNK_BYTES):
                request_bytes += len(chunk)
                if request_bytes > settings.max_upload_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail="La carga excede el tamaño máximo permitido.",
                    )
                chunks.append(chunk)
            payload.append((filename, b"".join(chunks)))

        result = backend.upload_dataset(payload)
        if not result["ready_for_analysis"]:
            raise HTTPException(status_code=422, detail=result)
        return result

    @router.post("/query")
    def query(request: CollectionsQueryRequest) -> dict[str, Any]:
        try:
            return backend.query(request.question)
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    return router
