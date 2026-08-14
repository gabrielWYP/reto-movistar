"""Validated, lossless ingestion boundary for the five Billing sources."""

from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

TABLE_FILES = {
    "customers": "001_TBL_CLIENTES_B2B.csv",
    "fixed_plant": "002_TBL_PLANTA_FIJA_B2B.csv",
    "mobile_plant": "003_TBL_PLANTA_MOVIL_B2B.csv",
    "invoices": "005_TBL_FACTURAS_B2B.csv",
    "credit_notes": "006_TBL_NOTAS_CREDITO_B2B.csv",
}

REQUIRED_COLUMNS = {
    "customers": {"NUMERO_IDENTIFICACION_FISCAL", "RAZON_SOCIAL"},
    "fixed_plant": {"RAZON_SOCIAL", "COD_CUENTA", "STATUS_DESC"},
    "mobile_plant": {"RAZON_SOCIAL", "COD_CUENTA", "ESTADO_LINEA"},
    "invoices": {
        "NUMERO_IDENTIFICACION_FISCAL", "RAZON_SOCIAL", "COD_CLIENTE",
        "COD_CUENTA", "NRO_DOC_FISCAL", "FUENTE", "SISTEMA",
        "FECHA_EMISION", "FECHA_VTO", "MONEDA", "CHARGE_NET_AMOUNT",
        "CHARGE_IGV_INVOICE", "CHARGE_TOTAL_AMOUNT",
    },
    "credit_notes": {
        "NUMERO_IDENTIFICACION_FISCAL", "RAZON_SOCIAL", "COD_CUENTA",
        "NRO_DOC_FISCAL", "FACTURA_AFECTADA", "FECHAEMISION", "MONEDA",
        "MONTO_SIN_IGV", "SUBTOTAL", "MONTO",
    },
}


class DatasetValidationError(ValueError):
    """Structured incompatibility that is safe to expose through the API."""

    def __init__(self, message: str, *, source: str | None = None, missing: list[str] | None = None):
        super().__init__(message)
        self.source = source
        self.missing = missing or []

    def to_dict(self) -> dict[str, object]:
        return {"message": str(self), "source": self.source, "missing_columns": self.missing}


@dataclass(frozen=True, slots=True)
class BillingDataset:
    customers: list[dict[str, str]]
    fixed_plant: list[dict[str, str]]
    mobile_plant: list[dict[str, str]]
    invoices: list[dict[str, str]]
    credit_notes: list[dict[str, str]]

    def source_counts(self) -> dict[str, int]:
        return {
            "customers": len(self.customers),
            "fixed_plant": len(self.fixed_plant),
            "mobile_plant": len(self.mobile_plant),
            "invoices": len(self.invoices),
            "credit_notes": len(self.credit_notes),
        }


class DatasetSource(Protocol):
    """Replaceable boundary for future database/API/data-lake adapters."""

    def load(self) -> BillingDataset: ...


@dataclass(frozen=True, slots=True)
class FileDatasetSource:
    path: Path

    def load(self) -> BillingDataset:
        return load_dataset(self.path)


def _decode_csv(content: bytes, logical_table: str) -> list[dict[str, str]]:
    if not content or not content.strip():
        raise DatasetValidationError("El archivo CSV está vacío.", source=TABLE_FILES[logical_table])
    for encoding in ("utf-8-sig", "utf-8", "latin1", "cp1252"):
        try:
            text = content.decode(encoding)
        except UnicodeDecodeError:
            continue
        lines = text.splitlines()
        header = lines[0] if lines else ""
        delimiter = max(("|", ";", ",", "\t"), key=header.count)
        if header.count(delimiter) == 0:
            continue
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        fields = [field.strip() for field in (reader.fieldnames or []) if field]
        missing = sorted(REQUIRED_COLUMNS[logical_table] - set(fields))
        if missing:
            raise DatasetValidationError(
                "Dataset incompatible: faltan columnas obligatorias.",
                source=TABLE_FILES[logical_table], missing=missing,
            )
        rows: list[dict[str, str]] = []
        for row_number, row in enumerate(reader, start=2):
            clean = {(key or "").strip(): (value or "") for key, value in row.items() if key}
            clean["__source_table"] = logical_table
            clean["__source_row_number"] = str(row_number)
            rows.append(clean)
        return rows
    raise DatasetValidationError(
        "No se pudo reconocer encoding o delimitador del CSV.",
        source=TABLE_FILES[logical_table],
    )


def _safe_zip_members(archive: zipfile.ZipFile) -> dict[str, str]:
    members: dict[str, str] = {}
    for info in archive.infolist():
        normalized = info.filename.replace("\\", "/")
        if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized) or ".." in Path(normalized).parts:
            raise DatasetValidationError("El ZIP contiene una ruta no permitida.")
        members[Path(normalized).name.lower()] = info.filename
    return members


def _read_zip(path: Path) -> dict[str, list[dict[str, str]]]:
    try:
        with zipfile.ZipFile(path) as archive:
            members = _safe_zip_members(archive)
            missing = [filename for filename in TABLE_FILES.values() if filename.lower() not in members]
            if missing:
                raise DatasetValidationError(
                    "Dataset incompatible: faltan fuentes obligatorias.", missing=missing,
                )
            return {
                logical: _decode_csv(archive.read(members[filename.lower()]), logical)
                for logical, filename in TABLE_FILES.items()
            }
    except zipfile.BadZipFile as error:
        raise DatasetValidationError("El archivo ZIP no es válido.") from error


def load_dataset(path: Path) -> BillingDataset:
    """Load a CSV directory or ZIP without deduplicating or altering source values."""
    if path.is_dir():
        missing = [filename for filename in TABLE_FILES.values() if not (path / filename).is_file()]
        if missing:
            raise DatasetValidationError(
                "Dataset incompatible: faltan fuentes obligatorias.", missing=missing,
            )
        contents = {
            logical: _decode_csv((path / filename).read_bytes(), logical)
            for logical, filename in TABLE_FILES.items()
        }
    elif path.is_file() and path.suffix.lower() == ".zip":
        contents = _read_zip(path)
    else:
        raise DatasetValidationError(
            "dataset debe ser un directorio con los cinco CSV de Facturación o un archivo .zip"
        )
    return BillingDataset(**contents)
