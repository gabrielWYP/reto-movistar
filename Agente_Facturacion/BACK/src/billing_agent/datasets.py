"""Secure, process-local registry for isolated in-memory Billing datasets."""

from __future__ import annotations

import io
import secrets
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .config import Settings
from .data import (
    TABLE_FILES,
    DatasetValidationError,
    load_dataset_bytes,
    load_dataset_zip_bytes,
)
from .service import BillingService


@dataclass(slots=True)
class DatasetRecord:
    dataset_id: str
    origin: str
    service: BillingService
    created_at: float
    expires_at: float | None

    def public_status(self) -> dict[str, object]:
        counts = self.service.model.dataset.source_counts()
        return {
            "dataset_id": self.dataset_id,
            "status": "READY",
            "origin": self.origin,
            "max_as_of_date": self.service.default_as_of_date().isoformat(),
            "source_counts": counts,
            "sources": [
                {"key": key, "filename": TABLE_FILES[key], "status": "VALID", "records": counts[key]}
                for key in TABLE_FILES
            ],
            "temporary": self.origin == "Dataset cargado",
        }


class DatasetRegistry:
    """Dataset IDs isolate services; there is no mutable process-wide current dataset."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._records: dict[str, DatasetRecord] = {}
        self._default_error: DatasetValidationError | None = None
        if settings.dataset_path:
            try:
                self._records["default"] = DatasetRecord(
                    "default", "Dataset predeterminado", BillingService(settings.dataset_path),
                    time.time(), None,
                )
            except (OSError, ValueError) as error:
                self._default_error = error if isinstance(error, DatasetValidationError) else DatasetValidationError(str(error))

    def _cleanup_expired(self) -> None:
        now = time.time()
        for dataset_id, record in list(self._records.items()):
            if record.expires_at and record.expires_at <= now:
                self.delete(dataset_id)

    def resolve(self, dataset_id: str | None) -> DatasetRecord:
        self._cleanup_expired()
        selected = dataset_id or "default"
        record = self._records.get(selected)
        if record:
            return record
        if selected == "default" and self._default_error:
            raise DatasetValidationError(f"Dataset predeterminado incompatible: {self._default_error}")
        raise KeyError("Dataset no encontrado o expirado.")

    @staticmethod
    def _safe_filename(filename: str) -> str:
        normalized = filename.replace("\\", "/")
        pure = PurePosixPath(normalized)
        if pure.is_absolute() or ".." in pure.parts or len(pure.parts) != 1:
            raise DatasetValidationError("El nombre de archivo contiene una ruta no permitida.")
        name = pure.name.strip()
        if not name or name in {".", ".."}:
            raise DatasetValidationError("El nombre de archivo no es válido.")
        return name

    def _validate_zip_limits(self, content: bytes) -> None:
        if not content.startswith(b"PK"):
            raise DatasetValidationError("El contenido no corresponde a un ZIP válido.")
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                total = 0
                files = [item for item in archive.infolist() if not item.is_dir()]
                for item in files:
                    normalized = item.filename.replace("\\", "/")
                    pure = PurePosixPath(normalized)
                    if pure.is_absolute() or ".." in pure.parts:
                        raise DatasetValidationError("El ZIP contiene una ruta no permitida.")
                if len(files) > self.settings.max_upload_files:
                    raise DatasetValidationError("El ZIP supera la cantidad máxima de archivos permitida.")
                names = {PurePosixPath(item.filename.replace("\\", "/")).name.lower() for item in files}
                expected = {name.lower() for name in TABLE_FILES.values()}
                if names != expected:
                    raise DatasetValidationError(
                        "El ZIP debe contener únicamente las cinco fuentes reconocidas de Facturación.",
                        missing=sorted(expected - names) + sorted(names - expected),
                    )
                for item in files:
                    total += item.file_size
                    if total > self.settings.max_uncompressed_bytes:
                        raise DatasetValidationError("El ZIP supera el tamaño máximo descomprimido permitido.")
        except zipfile.BadZipFile as error:
            raise DatasetValidationError("El archivo ZIP no es válido.") from error

    def register_upload(self, uploads: list[tuple[str, bytes]]) -> DatasetRecord:
        if not uploads or len(uploads) > self.settings.max_upload_files:
            raise DatasetValidationError(
                f"Debes cargar un ZIP o hasta {self.settings.max_upload_files} archivos CSV."
            )
        sanitized = [(self._safe_filename(name), content) for name, content in uploads]
        if any(not content for _, content in sanitized):
            raise DatasetValidationError("Ningún archivo puede estar vacío.")
        total_bytes = sum(len(content) for _, content in sanitized)
        if total_bytes > self.settings.max_upload_bytes:
            raise DatasetValidationError("La carga supera el tamaño máximo permitido.")
        suffixes = {Path(name).suffix.lower() for name, _ in sanitized}
        is_zip = len(sanitized) == 1 and suffixes == {".zip"}
        if not is_zip and suffixes != {".csv"}:
            raise DatasetValidationError("Solo se permiten cinco CSV reconocidos o un único ZIP.")
        if not is_zip and len(sanitized) != len(TABLE_FILES):
            raise DatasetValidationError("Debes cargar exactamente las cinco fuentes CSV de Facturación.")

        dataset_id = secrets.token_urlsafe(18)
        if is_zip:
            _, content = sanitized[0]
            self._validate_zip_limits(content)
            dataset = load_dataset_zip_bytes(content)
        else:
            by_name = {name.lower(): content for name, content in sanitized}
            missing = [name for name in TABLE_FILES.values() if name.lower() not in by_name]
            unknown = [name for name, _ in sanitized if name.lower() not in {value.lower() for value in TABLE_FILES.values()}]
            if missing or unknown:
                raise DatasetValidationError(
                    "Los nombres de las fuentes no corresponden al catálogo Billing.",
                    missing=missing + unknown,
                )
            dataset = load_dataset_bytes(by_name)
        try:
            service = BillingService.from_dataset(dataset)
        except DatasetValidationError:
            raise
        except (KeyError, OSError, ValueError) as error:
            raise DatasetValidationError(f"La estructura o los valores del dataset son incompatibles: {error}") from error
        now = time.time()
        record = DatasetRecord(
            dataset_id, "Dataset cargado", service, now,
            now + self.settings.dataset_ttl_seconds if self.settings.dataset_ttl_seconds > 0 else None,
        )
        self._records[dataset_id] = record
        return record

    def delete(self, dataset_id: str) -> None:
        if dataset_id == "default":
            raise ValueError("El dataset predeterminado no se elimina por API.")
        if not self._records.pop(dataset_id, None):
            raise KeyError("Dataset no encontrado o expirado.")
