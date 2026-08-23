"""FastAPI boundaries for standalone and shared Collections deployments."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from .agent import tool_definitions
from .application import CollectionsBackend
from .config import CollectionsSettings, get_settings
from .service import CollectionsService

UPLOAD_CHUNK_BYTES = 1024 * 1024
logger = logging.getLogger(__name__)


class CollectionsQueryRequest(BaseModel):
    """Natural-language request interpreted through grounded OpenCode tools."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=1000)
    as_of_date: date | None = None


def create_collections_router(
    backend: CollectionsBackend,
    *,
    allow_manual_upload: bool = True,
) -> APIRouter:
    """Create routes mounted by the single shared FastAPI application."""
    router = APIRouter(prefix="/api/collections", tags=["collections"])

    def service() -> CollectionsService:
        try:
            return backend.service()
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @router.get("/status")
    def status() -> dict[str, Any]:
        settings = backend.settings
        return {
            **backend.dataset_status(),
            "llm_available": backend.llm_available,
            "llm": backend.llm_metadata,
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
        if not allow_manual_upload:
            raise HTTPException(
                status_code=403,
                detail="La carga manual está centralizada en Supervisor SON-IA.",
            )
        settings = backend.settings
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
            logger.warning(
                "collections_dataset_rejected",
                extra={"uploaded_files": len(payload), "uploaded_bytes": request_bytes},
            )
            raise HTTPException(status_code=422, detail=result)
        logger.info(
            "collections_dataset_loaded",
            extra={"uploaded_files": len(payload), "uploaded_bytes": request_bytes},
        )
        return result

    @router.post("/query")
    def query(request: CollectionsQueryRequest) -> dict[str, Any]:
        try:
            cutoff = request.as_of_date.isoformat() if request.as_of_date else None
            return backend.query(request.question, cutoff)
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    return router


def create_app(
    settings: CollectionsSettings | None = None,
    backend: CollectionsBackend | None = None,
) -> FastAPI:
    """Create the independent backend while preserving the shared API contract."""
    runtime_settings = settings or get_settings()
    application = FastAPI(
        title="SON-IA Agente de Cobranzas y Recaudación",
        version="1.0.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    runtime_backend = backend or CollectionsBackend(settings=runtime_settings)
    application.state.collections_settings = runtime_settings
    application.include_router(create_collections_router(runtime_backend))

    @application.get("/health", tags=["platform"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "sonia-collections-back"}

    return application


app = create_app()
