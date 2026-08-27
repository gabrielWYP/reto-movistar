"""FastAPI boundary for the canonical SON-IA Billing implementation."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .config import Settings
from .data import DatasetValidationError
from .datasets import DatasetRegistry
from .openai_runtime import OpenAIRuntime
from .presentation import presentation_for
from .runtime import BillingAgentRuntime, SessionContext
from .work_queue import build_work_queue

LOG = logging.getLogger("sonia.billing")


class ConversationContext(BaseModel):
    customer_id: str | None = None
    account_id: str | None = None
    invoice_id: str | None = None
    last_tool: str | None = None


class ConversationRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    dataset_id: str | None = None
    as_of_date: str | None = None
    context: ConversationContext = Field(default_factory=ConversationContext)


def create_app(
    settings: Settings | None = None,
    *,
    api_prefix: str = "/api",
    allow_manual_upload: bool = True,
) -> FastAPI:
    """Create the standalone app or a namespaced shared-backend sub-application."""
    runtime_settings = settings or Settings.from_environment()
    normalized_prefix = api_prefix.rstrip("/")
    if normalized_prefix and not normalized_prefix.startswith("/"):
        raise ValueError("api_prefix debe ser una ruta absoluta.")

    def api_path(path: str) -> str:
        return f"{normalized_prefix}{path}"

    logging.basicConfig(level=runtime_settings.log_level)
    application = FastAPI(
        title="SON-IA Billing Assurance",
        version="1.0.0",
        docs_url=api_path("/docs"),
    )
    registry = DatasetRegistry(runtime_settings)
    application.state.dataset_registry = registry
    application.state.settings = runtime_settings

    @application.exception_handler(DatasetValidationError)
    async def dataset_error(_: Request, error: DatasetValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"error": "Dataset incompatible", "detail": error.to_dict()})

    @application.exception_handler(KeyError)
    async def missing_error(_: Request, error: KeyError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"error": str(error).strip("'")})

    @application.exception_handler(ValueError)
    async def input_error(_: Request, error: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"error": "Entrada inválida", "detail": str(error)})

    infrastructure_health_path = "/health" if normalized_prefix else "/infrastructure-health"

    @application.get(infrastructure_health_path, tags=["operations"])
    async def infrastructure_health() -> dict[str, str]:
        return {"status": "ok", "service": "sonia-billing-back", "version": "1.0.0"}

    @application.get(api_path("/status"), tags=["billing"])
    async def status(dataset_id: str | None = None) -> dict[str, Any]:
        try:
            record = registry.resolve(dataset_id)
        except KeyError:
            if dataset_id not in {None, "default"}:
                raise
            return {
                "status": "dataset_not_configured",
                "agent": "billing",
                "dataset_configured": False,
                "llm_available": OpenAIRuntime().available,
            }
        return {"status": "ok", "agent": "billing", "llm_available": OpenAIRuntime().available, **record.public_status()}

    def response(record: Any, payload: dict[str, Any]) -> dict[str, Any]:
        return {"dataset_id": record.dataset_id, "agent_response": payload, "presentation": presentation_for(payload)}

    @application.get(api_path("/health"), tags=["billing"])
    async def billing_health(dataset_id: str | None = None, as_of_date: str | None = None) -> dict[str, Any]:
        record = registry.resolve(dataset_id)
        return response(record, record.service.billing_health_snapshot(as_of_date))

    @application.get(api_path("/work-queue"), tags=["billing"])
    async def work_queue(
        dataset_id: str | None = None,
        as_of_date: str | None = None,
    ) -> dict[str, Any]:
        record = registry.resolve(dataset_id)
        return {"dataset_id": record.dataset_id, **build_work_queue(record.service, as_of_date)}

    @application.get(api_path("/customer"), tags=["billing"])
    async def customer(customer_id: str, account_id: str | None = None, dataset_id: str | None = None, as_of_date: str | None = None) -> dict[str, Any]:
        record = registry.resolve(dataset_id)
        return response(record, record.service.customer_billing_check(customer_id, account_id, as_of_date))

    @application.get(api_path("/invoice"), tags=["billing"])
    async def invoice(invoice_id: str, dataset_id: str | None = None, as_of_date: str | None = None) -> dict[str, Any]:
        record = registry.resolve(dataset_id)
        return response(record, record.service.invoice_quality_check(invoice_id, as_of_date))

    @application.get(api_path("/gaps"), tags=["billing"])
    async def gaps(dataset_id: str | None = None, as_of_date: str | None = None, customer_id: str | None = None, account_id: str | None = None) -> dict[str, Any]:
        record = registry.resolve(dataset_id)
        return response(record, record.service.billing_cycle_gaps(as_of_date, customer_id, account_id))

    @application.get(api_path("/credit-notes"), tags=["billing"])
    async def credit_notes(dataset_id: str | None = None, as_of_date: str | None = None, customer_id: str | None = None, account_id: str | None = None, invoice_id: str | None = None, materiality_threshold: Decimal = Query(default=Decimal("0.25"), ge=0, le=1)) -> dict[str, Any]:
        record = registry.resolve(dataset_id)
        return response(record, record.service.credit_note_review(as_of_date, customer_id, account_id, invoice_id, materiality_threshold))

    @application.post(api_path("/conversation"), tags=["billing"])
    async def conversation(body: ConversationRequest) -> dict[str, Any]:
        record = registry.resolve(body.dataset_id)
        context = SessionContext(
            customer_id=body.context.customer_id,
            account_id=body.context.account_id,
            invoice_id=body.context.invoice_id,
            last_tool=body.context.last_tool,
        )
        result = BillingAgentRuntime(record.service, OpenAIRuntime()).ask(body.question, context, body.as_of_date)
        result["dataset_id"] = record.dataset_id
        if result.get("agent_response"):
            result["presentation"] = presentation_for(result["agent_response"])
        result["context"] = {
            "customer_id": context.customer_id,
            "account_id": context.account_id,
            "invoice_id": context.invoice_id,
            "last_tool": context.last_tool,
        }
        return result

    @application.post(api_path("/datasets"), status_code=201, tags=["datasets"])
    async def upload_dataset(files: list[UploadFile] = File(...)) -> dict[str, object]:
        if not allow_manual_upload:
            raise HTTPException(
                status_code=403,
                detail="La carga manual está centralizada en Supervisor SON-IA.",
            )
        uploads: list[tuple[str, bytes]] = []
        accumulated = 0
        for upload in files:
            remaining = runtime_settings.max_upload_bytes - accumulated
            content = await upload.read(remaining + 1)
            accumulated += len(content)
            if accumulated > runtime_settings.max_upload_bytes:
                raise DatasetValidationError("La carga supera el tamaño máximo permitido.")
            uploads.append((upload.filename or "", content))
        return registry.register_upload(uploads).public_status()

    @application.get(api_path("/datasets/{dataset_id}/status"), tags=["datasets"])
    async def dataset_status(dataset_id: str) -> dict[str, object]:
        return registry.resolve(dataset_id).public_status()

    @application.delete(api_path("/datasets/{dataset_id}"), status_code=204, tags=["datasets"])
    async def delete_dataset(dataset_id: str) -> None:
        if not allow_manual_upload:
            raise HTTPException(
                status_code=403,
                detail="La fuente compartida solo se administra desde Supervisor SON-IA.",
            )
        try:
            registry.delete(dataset_id)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    return application


app = create_app()
