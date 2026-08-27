"""FastAPI application and public single-entry endpoints."""

import logging
from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import Annotated, Any
from uuid import uuid4

from bi_agent.api import create_bi_router
from bi_agent.application import BIBackend
from billing_agent.app import create_app as create_billing_app
from billing_agent.datasets import DatasetRegistry
from billing_agent.openai_runtime import OpenAIRuntime
from billing_agent.runtime import BillingAgentRuntime
from collections_agent.api import create_collections_router
from collections_agent.application import CollectionsBackend
from collections_agent.llm_runtime import OpenCodeRuntime
from fastapi import FastAPI, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from sonia.application.agent_registry import get_agent, list_agents
from sonia.application.dataset_supervisor import SupervisorDatasetCoordinator
from sonia.application.demo_service import build_demo_scenario, transition_demo
from sonia.application.judge import Judge
from sonia.application.judge_evaluator import OpenCodeJudgeEvaluator
from sonia.application.orchestrator import RunOrchestrator
from sonia.application.specialist_adapters import build_specialist_adapters
from sonia.config import Settings, get_settings
from sonia.domain.agents import AgentDescriptor
from sonia.domain.demo import DemoScenarioResponse, DemoTransitionRequest, DemoTransitionResponse
from sonia.domain.health import HealthResponse
from sonia.domain.orchestration import SpecialistPhase
from sonia.entrypoints.run_api import create_run_router, read_dataset_uploads
from sonia.integrations.object_store import object_store_from_environment
from sonia.observability.audit import RunAuditLog
from sonia.observability.logging import configure_logging
from sonia.persistence.backup import StorageHardener
from sonia.persistence.sqlite import SQLiteIntakeRepository

logger = logging.getLogger(__name__)


class _CurrentBilling:
    """Resolve Billing's Supervisor-published default for every attempt."""

    def __init__(self, registry: DatasetRegistry) -> None:
        self.registry = registry

    @property
    def llm_available(self) -> bool:
        return bool(OpenAIRuntime().available)

    def billing_health_snapshot(self, as_of_date: str) -> dict[str, Any]:
        return self.registry.resolve("default").service.billing_health_snapshot(as_of_date)

    def query(self, question: str, as_of_date: str) -> dict[str, Any]:
        """Let Billing route its own tools against the Supervisor-published dataset."""
        record = self.registry.resolve("default")
        return BillingAgentRuntime(record.service, OpenAIRuntime()).ask(question, None, as_of_date)


def _qualitative_judge(runtime: OpenCodeRuntime) -> Judge:
    """Grade specialist output with the model, and escalate when it cannot answer."""
    if not runtime.available:
        logger.info("judge_qualitative_disabled", extra={"reason": "provider_unavailable"})
        return Judge()
    evaluator = OpenCodeJudgeEvaluator(
        lambda messages: runtime.complete(messages, stage="judge_rubric"),
        runtime.output_text,
        runtime.usage,
        runtime.model,
    )
    return Judge(evaluator, qualitative_required=True)


def create_app(
    settings: Settings | None = None,
    bi_backend: BIBackend | None = None,
    collections_backend: CollectionsBackend | None = None,
    run_orchestrator: RunOrchestrator | None = None,
    run_storage: StorageHardener | None = None,
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
    runtime_collections_backend = collections_backend or CollectionsBackend()
    runtime_bi_backend.set_collections_response_provider(
        lambda as_of_date: runtime_collections_backend.execute_tool(
            "portfolio_snapshot",
            {},
            as_of_date,
        )
    )
    application.include_router(create_bi_router(runtime_bi_backend, allow_manual_upload=False))
    application.include_router(
        create_collections_router(
            runtime_collections_backend,
            allow_manual_upload=False,
        )
    )
    billing_application = create_billing_app(
        api_prefix="",
        allow_manual_upload=False,
    )
    billing_registry = billing_application.state.dataset_registry
    runtime_runner, runtime_storage = run_orchestrator, run_storage
    production_intake = (
        SQLiteIntakeRepository(runtime_settings.storage_root)
        if runtime_runner is None and runtime_storage is None and runtime_settings.storage_root
        else None
    )
    dataset_coordinator = SupervisorDatasetCoordinator(
        runtime_bi_backend,
        runtime_collections_backend,
        billing_registry,
        production_intake or (runtime_runner.intake if runtime_runner is not None else None),
    )
    if production_intake is not None and runtime_settings.storage_root:
        runtime_storage = StorageHardener(runtime_settings.storage_root)
        try:
            dataset_coordinator.rehydrate_latest()
        except (KeyError, OSError, RuntimeError, ValueError) as error:
            logger.error(
                "supervisor_dataset_rehydration_failed",
                extra={"error_type": type(error).__name__},
            )
        current_billing = _CurrentBilling(billing_registry)
        run_audit = RunAuditLog(object_store_from_environment())
        runtime_runner = RunOrchestrator(
            runtime_storage.database,
            production_intake,
            build_specialist_adapters(
                current_billing,
                runtime_collections_backend,
                runtime_bi_backend,
                dataset_coordinator.execute_on_revision,
                {
                    SpecialistPhase.BILLING: current_billing,
                    SpecialistPhase.COLLECTIONS: runtime_collections_backend,
                    SpecialistPhase.BI: runtime_bi_backend,
                },
                run_audit.record,
            ),
            _qualitative_judge(OpenCodeRuntime()),
            owner=f"api-{uuid4()}",
            storage_guard=runtime_storage.require_ready,
            audit=run_audit,
        )
        logger.info(
            "production_orchestration_composed",
            extra={
                "storage_root": str(runtime_settings.storage_root),
                "owner": runtime_runner.owner,
                "audit_enabled": run_audit.enabled,
            },
        )
    application.mount("/api/billing", billing_application, name="billing-agent")
    application.state.dataset_coordinator = dataset_coordinator
    application.state.run_orchestrator = runtime_runner
    application.state.run_storage = runtime_storage
    if runtime_runner is not None and runtime_storage is not None:
        application.include_router(
            create_run_router(runtime_runner, runtime_storage, dataset_coordinator)
        )

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

    @application.get("/ready", tags=["operations"])
    async def readiness() -> Response:
        """Fail closed when configured durable storage is unavailable or corrupt."""
        report = runtime_storage.verify() if runtime_storage is not None else None
        ready = report is None or report.ready
        return JSONResponse(
            {
                "status": "ready" if ready else "storage_unready",
                "issue_count": len(report.issues) if report is not None else 0,
            },
            status_code=200 if ready else 503,
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

    @application.get("/api/supervisor/dataset", tags=["supervisor"])
    async def supervisor_dataset_status() -> dict[str, Any]:
        """Expose the only shared dataset state visible to specialist tabs."""
        return dataset_coordinator.status()

    @application.post("/api/supervisor/dataset", tags=["supervisor"])
    async def publish_supervisor_dataset(
        files: list[UploadFile],
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> dict[str, Any]:
        """Validate and publish one six-source dataset to every specialist."""
        if idempotency_key is not None and not idempotency_key.strip():
            raise HTTPException(status_code=422, detail="Idempotency-Key cannot be whitespace-only")
        payload = await read_dataset_uploads(files)
        try:
            return await run_in_threadpool(
                dataset_coordinator.publish,
                payload,
                idempotency_key=idempotency_key.strip() if idempotency_key else f"compat:{uuid4()}",
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

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
