"""FastAPI application and public single-entry endpoints."""

import logging
from collections.abc import Awaitable, Callable
from time import perf_counter
from uuid import uuid4

from bi_agent.api import create_bi_router
from bi_agent.application import BIBackend
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from sonia.agents.collections.api import create_collections_router
from sonia.agents.collections.application import CollectionsBackend
from sonia.application.agent_registry import get_agent, list_agents
from sonia.application.demo_service import build_demo_scenario, transition_demo
from sonia.config import Settings, get_settings
from sonia.domain.agents import AgentDescriptor
from sonia.domain.demo import DemoScenarioResponse, DemoTransitionRequest, DemoTransitionResponse
from sonia.domain.health import HealthResponse
from sonia.observability.logging import configure_logging

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    bi_backend: BIBackend | None = None,
    collections_backend: CollectionsBackend | None = None,
) -> FastAPI:
    """Create an application instance with explicit runtime dependencies."""
    runtime_settings = settings or get_settings()
    configure_logging(runtime_settings.log_level)

    application = FastAPI(
        title=runtime_settings.app_name,
        version=runtime_settings.app_version,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    runtime_bi_backend = bi_backend or BIBackend()
    application.include_router(create_bi_router(runtime_bi_backend))
    runtime_collections_backend = collections_backend or CollectionsBackend()
    application.include_router(create_collections_router(runtime_collections_backend))

    @application.middleware("http")
    async def request_observability(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("x-request-id", str(uuid4()))
        started_at = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request_failed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "latency_ms": round((perf_counter() - started_at) * 1000, 3),
                },
            )
            raise

        response.headers["x-request-id"] = request_id
        logger.info(
            "request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "latency_ms": round((perf_counter() - started_at) * 1000, 3),
            },
        )
        return response

    @application.get("/health", response_model=HealthResponse, tags=["operations"])
    async def health() -> HealthResponse:
        """Return a stable health contract for K3S probes and smoke tests."""
        return HealthResponse(
            service=runtime_settings.app_name,
            version=runtime_settings.app_version,
            environment=runtime_settings.environment,
        )

    @application.get("/api/agents", response_model=list[AgentDescriptor], tags=["agents"])
    async def agents() -> tuple[AgentDescriptor, ...]:
        """List the three agents available behind the backend boundary."""
        return list_agents()

    @application.get("/api/agents/{agent_id}", response_model=AgentDescriptor, tags=["agents"])
    async def agent(agent_id: str) -> AgentDescriptor:
        """Return metadata for one registered specialist agent."""
        descriptor = get_agent(agent_id)
        if descriptor is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        return descriptor

    @application.get(
        "/api/demo/scenario",
        response_model=DemoScenarioResponse,
        tags=["demo"],
    )
    async def demo_scenario() -> DemoScenarioResponse:
        """Return the synthetic, non-sensitive scenario for the visual MVP."""
        return build_demo_scenario()

    @application.post(
        "/api/demo/transition",
        response_model=DemoTransitionResponse,
        tags=["demo"],
    )
    async def demo_transition(request: DemoTransitionRequest) -> DemoTransitionResponse:
        """Apply one explicit and stateless transition in the visual journey."""
        try:
            return transition_demo(request)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    assets_dir = runtime_settings.frontend_dir / "assets"
    agent_assets_dir = runtime_settings.frontend_dir / "agents"
    bi_frontend_dir = runtime_settings.frontend_dir / "bi"
    index_file = runtime_settings.frontend_dir / "index.html"
    if assets_dir.is_dir():
        application.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
    if agent_assets_dir.is_dir():
        application.mount(
            "/agents",
            StaticFiles(directory=agent_assets_dir),
            name="agent-assets",
        )
    if bi_frontend_dir.is_dir():
        application.mount(
            "/bi",
            StaticFiles(directory=bi_frontend_dir, html=True),
            name="bi-frontend",
        )

    @application.get("/", include_in_schema=False)
    async def root() -> Response:
        """Serve the visual MVP or a safe fallback when assets are unavailable."""
        if index_file.is_file():
            return FileResponse(index_file)
        return JSONResponse(
            {
                "service": runtime_settings.app_name,
                "status": "frontend_unavailable",
                "docs": "/api/docs",
            }
        )

    return application


app = create_app()
