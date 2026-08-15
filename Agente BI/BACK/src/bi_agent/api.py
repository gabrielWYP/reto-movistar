"""FastAPI boundary for the standalone SON-IA BI backend.

The module contains no financial rules.  It validates HTTP input, delegates to
the public agent/service boundary and adds the declarative presentation model
consumed by the shared frontend.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .agent import TOOL_NAMES
from .application import BIBackend
from .config import Settings, get_settings


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


def create_bi_router(backend: BIBackend) -> APIRouter:
    """Create routes mounted by the single shared FastAPI application."""
    router = APIRouter(prefix="/api/bi", tags=["bi"])

    @router.get("/status")
    def status() -> dict[str, Any]:
        return {
            "status": "ready" if backend.configured else "dataset_not_configured",
            "dataset_configured": backend.configured,
            "llm_available": backend.llm_available,
            "tools": sorted(TOOL_NAMES),
        }

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
    runtime_backend = backend or BIBackend(dataset_path=runtime_settings.dataset_path)
    application.include_router(create_bi_router(runtime_backend))

    @application.get("/health", tags=["platform"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "sonia-bi-back"}

    return application


app = create_app()
