"""FastAPI boundary for the standalone SON-IA BI backend.

The module contains no financial rules.  It validates HTTP input, delegates to
the public agent/service boundary and adds the declarative presentation model
consumed by the shared frontend.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, FastAPI, File, HTTPException, UploadFile
from fastapi import status as http_status
from pydantic import BaseModel, ConfigDict, Field

from .agent import TOOL_NAMES
from .application import BIBackend
from .config import Settings, get_settings

MAX_DATASET_UPLOAD_BYTES = 25 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024
logger = logging.getLogger(__name__)


class BIQueryRequest(BaseModel):
    """Natural-language request accepted by the shared backend."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=1000)
    as_of_date: date


class BIToolRequest(BaseModel):
    """Validated direct invocation for one of the five approved BI tools."""

    model_config = ConfigDict(extra="forbid")

    as_of_date: date
    parameters: dict[str, Any] = Field(default_factory=dict)


def create_bi_router(
    backend: BIBackend,
    *,
    allow_manual_upload: bool = True,
) -> APIRouter:
    """Create routes mounted by the single shared FastAPI application."""
    router = APIRouter(prefix="/api/bi", tags=["bi"])

    @router.get("/status")
    def status() -> dict[str, Any]:
        return {
            **backend.dataset_status(),
            "llm_available": backend.llm_available,
            "llm": backend.llm_metadata,
            "tools": sorted(TOOL_NAMES),
        }

    @router.post("/dataset", status_code=http_status.HTTP_200_OK)
    async def upload_dataset(
        files: Annotated[list[UploadFile], File(...)],
    ) -> dict[str, Any]:
        if not allow_manual_upload:
            raise HTTPException(
                status_code=403,
                detail="La carga manual está centralizada en Supervisor SON-IA.",
            )
        if not files:
            raise HTTPException(status_code=422, detail="Selecciona al menos un CSV o ZIP.")
        payload: dict[str, bytes] = {}
        request_bytes = 0
        for upload in files:
            filename = Path(upload.filename or "").name
            if not filename or Path(filename).suffix.lower() not in {".csv", ".zip"}:
                raise HTTPException(status_code=422, detail="Solo se aceptan archivos CSV o ZIP.")
            if filename in payload:
                raise HTTPException(status_code=422, detail=f"Archivo duplicado: {filename}.")
            chunks: list[bytes] = []
            while chunk := await upload.read(UPLOAD_CHUNK_BYTES):
                request_bytes += len(chunk)
                if request_bytes > MAX_DATASET_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="La carga excede 25 MiB.")
                chunks.append(chunk)
            payload[filename] = b"".join(chunks)
        try:
            result = backend.upload_dataset(payload, MAX_DATASET_UPLOAD_BYTES)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        logger.info(
            "bi_dataset_uploaded",
            extra={
                "uploaded_file_count": len(payload),
                "uploaded_bytes": request_bytes,
                "dataset_status": result["status"],
                "dataset_bytes": result["dataset_bytes"],
            },
        )
        return result

    @router.post("/query")
    def query(request: BIQueryRequest) -> dict[str, Any]:
        try:
            return backend.query(request.question, request.as_of_date.isoformat())
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except (KeyError, ValueError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/tools/{operation}")
    def execute_tool(operation: str, request: BIToolRequest) -> dict[str, Any]:
        if operation not in TOOL_NAMES:
            raise HTTPException(status_code=404, detail="Operación BI no autorizada.")
        try:
            return backend.execute_tool(
                operation,
                request.parameters,
                request.as_of_date.isoformat(),
            )
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except (KeyError, ValueError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    return router


def create_app(
    settings: Settings | None = None,
    backend: BIBackend | None = None,
) -> FastAPI:
    """Create the independent backend while preserving the shared API contract."""
    runtime_settings = settings or get_settings()
    application = FastAPI(
        title="SON-IA Business Intelligence Agent",
        version="1.0.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    application.state.bi_settings = runtime_settings
    runtime_backend = backend or BIBackend()
    application.include_router(create_bi_router(runtime_backend))

    @application.get("/health", tags=["platform"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "sonia-bi-back"}

    return application


app = create_app()
