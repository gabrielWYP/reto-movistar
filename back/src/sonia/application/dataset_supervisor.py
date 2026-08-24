"""Single publication boundary for the shared SON-IA dataset."""

from __future__ import annotations

import csv
import io
import logging
import re
import zipfile
from collections.abc import Callable
from pathlib import PurePosixPath
from threading import RLock
from typing import Any

from bi_agent.application import BIBackend
from bi_agent.data import TABLE_FILES as BI_TABLE_FILES
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
MAX_CSV_ROWS = 250_000
MAX_CSV_FIELDS = 256
SUPERVISOR_SOURCE = "supervisor"
SUPERVISOR_ORIGIN = "Supervisor SON-IA"
logger = logging.getLogger(__name__)
_NEGATIVE_NUMBER = re.compile(
    r"-(?:\d+(?:[.,]\d+)?|\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d{1,3}(?:,\d{3})+(?:\.\d+)?)"
)


def _is_formula(value: str) -> bool:
    value = value.lstrip()
    if value.startswith(("=", "+", "@")):
        return True
    return value.startswith("-") and _NEGATIVE_NUMBER.fullmatch(value) is None


def _safe_upload_name(value: str) -> str:
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or len(path.parts) != 1:
        raise ValueError(f"Upload path is not allowed: {value}")
    return path.name


def _inspect_zip(content: bytes, depth: int = 0) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) == 1 and _safe_upload_name(entries[0].filename).lower().endswith(
                ".zip"
            ):
                if depth >= 1:
                    raise ValueError("ZIP nesting exceeds one wrapper")
                if entries[0].file_size > MAX_DATASET_BYTES:
                    raise ValueError("The uncompressed dataset exceeds 25 MiB")
                _inspect_zip(archive.read(entries[0]), depth + 1)
                return
            seen: set[str] = set()
            total = 0
            for entry in entries:
                name = _safe_upload_name(entry.filename)
                if name not in BI_TABLE_FILES.values():
                    raise ValueError(f"ZIP entry is outside the source allow-list: {name}")
                if name in seen:
                    raise ValueError(f"ZIP contains duplicate source: {name}")
                if entry.external_attr >> 16 & 0o170000 == 0o120000:
                    raise ValueError(f"ZIP symlink is not allowed: {name}")
                seen.add(name)
                total += entry.file_size
            if total > MAX_DATASET_BYTES:
                raise ValueError("The uncompressed dataset exceeds 25 MiB")
    except zipfile.BadZipFile as error:
        raise ValueError("The ZIP file is invalid") from error


def validate_dataset_files(
    files: dict[str, bytes], *, max_rows: int = MAX_CSV_ROWS, max_fields: int = MAX_CSV_FIELDS
) -> dict[str, bytes]:
    """Return canonical CSV bytes after bounded data-only validation."""
    expected = set(BI_TABLE_FILES.values())
    for name, content in files.items():
        _safe_upload_name(name)
        if name.lower().endswith(".zip"):
            _inspect_zip(content)
    if not any(name.lower().endswith(".zip") for name in files) and set(files) != expected:
        detail = "six official sources" if set(files) < expected else "source allow-list"
        missing = sorted(expected - set(files))
        suffix = f". Faltan: {', '.join(missing)}" if missing else ""
        raise ValueError(f"Publication must contain only the {detail}{suffix}")
    normalized = normalize_dataset_files(files)
    if set(normalized) != expected:
        detail = "six official sources" if set(normalized) < expected else "source allow-list"
        raise ValueError(f"Publication must contain only the {detail}")
    for name, content in normalized.items():
        if len(content) > MAX_DATASET_BYTES or b"\0" in content:
            raise ValueError(f"{name}: invalid encoding or size")
        text = None
        for encoding in ("utf-8-sig", "cp1252"):
            try:
                text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if text is None or any(
            ord(character) < 32 and character not in "\r\n\t" for character in text
        ):
            raise ValueError(f"{name}: invalid encoding")
        reader = csv.reader(io.StringIO(text), delimiter="|")
        try:
            header = next(reader)
        except StopIteration as error:
            raise ValueError(f"{name}: missing header") from error
        if not header or len(header) != len(set(header)):
            raise ValueError(f"{name}: invalid or duplicate header")
        if len(header) > max_fields:
            raise ValueError(f"{name}: field limit exceeded")
        row_count = 0
        for row in reader:
            row_count += 1
            if row_count > max_rows:
                raise ValueError(f"{name}: row limit exceeded")
            if not row or not any(cell.strip() for cell in row):
                continue
            if len(row) != len(header) or len(row) > max_fields:
                raise ValueError(f"{name}: schema or field limit violation")
            if any(_is_formula(cell) for cell in row):
                raise ValueError(f"{name}: spreadsheet formula is not allowed")
    return normalized


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
        self._active_revision: str | None = None

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

    def _rehydrate(self, revision_id: str) -> dict[str, Any]:
        if self._intake is None:
            raise RuntimeError("Durable intake is unavailable")
        if self._active_revision == revision_id:
            return self.status()
        restored = self.publish(
            self._intake.read_dataset_files(revision_id),
            idempotency_key=f"rehydrate:{revision_id}",
        )
        logger.info(
            "supervisor_dataset_rehydrated",
            extra={"dataset_revision": revision_id, "agents_ready": 3},
        )
        return restored

    def rehydrate_latest(self) -> dict[str, Any] | None:
        """Restore the latest durable Supervisor revision into all specialist registries."""
        revision = self._intake.latest_dataset() if self._intake else None
        return self._rehydrate(revision.revision_id) if revision else None

    def execute_on_revision(
        self, revision_id: str, operation: Callable[[], dict[str, Any]]
    ) -> dict[str, Any]:
        """Execute one specialist operation while its bound revision is active."""
        with self._lock:
            self._rehydrate(revision_id)
            return operation()

    def publish(
        self,
        files: dict[str, bytes],
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Validate the complete six-file contract before changing any agent."""
        normalized = validate_dataset_files(files)
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
            self._active_revision = revision.revision_id if revision else None

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
