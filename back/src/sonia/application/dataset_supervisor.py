"""Single publication boundary for the shared SON-IA dataset."""

from __future__ import annotations

import logging
from threading import RLock
from typing import Any

from bi_agent.application import BIBackend
from bi_agent.data import missing_dataset_files, normalize_dataset_files
from bi_agent.service import BIService
from billing_agent.data import TABLE_FILES as BILLING_TABLE_FILES
from billing_agent.data import DatasetValidationError
from billing_agent.data import load_dataset_bytes as load_billing_dataset
from billing_agent.datasets import DatasetRegistry
from billing_agent.service import BillingService
from collections_agent.application import CollectionsBackend
from collections_agent.service import CollectionsService
from collections_agent.uploads import load_uploaded_csvs

from sonia.persistence.sqlite import SQLiteIntakeRepository

MAX_DATASET_BYTES = 25 * 1024 * 1024
MAX_DATASET_FILES = 6
SUPERVISOR_SOURCE = "supervisor"
SUPERVISOR_ORIGIN = "Supervisor SON-IA"
logger = logging.getLogger(__name__)


class SupervisorDatasetCoordinator:
    """Validate once and atomically publish one dataset to all specialists."""

    def __init__(
        self,
        bi_backend: BIBackend,
        collections_backend: CollectionsBackend,
        billing_registry: DatasetRegistry,
        intake_repository: SQLiteIntakeRepository | None = None,
    ) -> None:
        self._bi = bi_backend
        self._collections = collections_backend
        self._billing = billing_registry
        self._intake = intake_repository
        self._lock = RLock()

    def _billing_status(self) -> dict[str, Any]:
        try:
            record = self._billing.resolve("default")
        except (KeyError, ValueError):
            return {
                "dataset_configured": False,
                "dataset_source": None,
                "source_counts": {},
            }
        return {
            "dataset_configured": True,
            "dataset_source": (
                SUPERVISOR_SOURCE if record.origin == SUPERVISOR_ORIGIN else "configured_file"
            ),
            "source_counts": record.service.model.dataset.source_counts(),
        }

    def status(self) -> dict[str, Any]:
        """Return the shared publication state without exposing source rows."""
        bi = self._bi.dataset_status()
        collections = self._collections.dataset_status()
        billing = self._billing_status()
        agents = {
            "billing": billing,
            "collections": {
                "dataset_configured": collections["dataset_configured"],
                "dataset_source": collections["dataset_source"],
                "source_counts": collections["source_counts"],
            },
            "bi": {
                "dataset_configured": bi["dataset_configured"],
                "dataset_source": bi["dataset_source"],
                "source_counts": {},
            },
        }
        ready = all(item["dataset_configured"] for item in agents.values())
        supervisor_owned = ready and all(
            item["dataset_source"] == SUPERVISOR_SOURCE for item in agents.values()
        )
        return {
            "status": "ready" if ready else "dataset_not_configured",
            "dataset_configured": ready,
            "dataset_source": SUPERVISOR_SOURCE if supervisor_owned else None,
            "dataset_file_count": bi["dataset_file_count"] if supervisor_owned else 0,
            "dataset_bytes": bi["dataset_bytes"] if supervisor_owned else 0,
            "agents": agents,
        }

    def publish(
        self,
        files: dict[str, bytes],
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Validate the complete six-file contract before changing any agent."""
        normalized = normalize_dataset_files(files)
        missing = missing_dataset_files(normalized)
        if missing:
            raise ValueError(
                "Supervisor requiere las seis fuentes oficiales. Faltan: " + ", ".join(missing)
            )
        total_bytes = sum(len(content) for content in normalized.values())
        if total_bytes > MAX_DATASET_BYTES:
            raise ValueError("El dataset descomprimido excede el límite de 25 MiB.")

        bi_service = BIService(normalized)
        collections_dataset, report = load_uploaded_csvs(
            normalized.items(),
            MAX_DATASET_FILES,
            MAX_DATASET_BYTES,
        )
        if collections_dataset is None or not report.ready_for_analysis:
            detail = " ".join(report.errors) or "Dataset incompatible con Cobranzas."
            raise ValueError(detail)
        collections_service = CollectionsService.from_dataset(collections_dataset)
        billing_files = {
            filename: normalized[filename] for filename in BILLING_TABLE_FILES.values()
        }
        try:
            billing_service = BillingService.from_dataset(load_billing_dataset(billing_files))
        except DatasetValidationError as error:
            missing_detail = f" Faltan: {', '.join(error.missing)}." if error.missing else ""
            raise ValueError(f"{error}{missing_detail}") from error

        revision = None
        if self._intake is not None:
            if not idempotency_key:
                raise ValueError("An idempotency key is required for durable publication")
            revision = self._intake.publish_dataset(normalized, idempotency_key)

        with self._lock:
            self._bi.publish_dataset(bi_service, normalized, source=SUPERVISOR_SOURCE)
            self._collections.publish_dataset(
                collections_service,
                source=SUPERVISOR_SOURCE,
            )
            self._billing.publish_default(billing_service, origin=SUPERVISOR_ORIGIN)

        result = self.status()
        if revision is not None:
            result["dataset_revision"] = revision.revision_id
        result["warnings"] = report.warnings
        logger.info(
            "supervisor_dataset_published",
            extra={
                "dataset_file_count": len(normalized),
                "dataset_bytes": total_bytes,
                "agents_ready": sum(
                    int(item["dataset_configured"]) for item in result["agents"].values()
                ),
            },
        )
        return result
