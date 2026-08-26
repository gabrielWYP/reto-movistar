"""Lossless adapter for the five billing-relevant official SON-IA tables."""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass
from pathlib import Path

TABLE_FILES = {
    "customers": "001_TBL_CLIENTES_B2B.csv",
    "fixed_plant": "002_TBL_PLANTA_FIJA_B2B.csv",
    "mobile_plant": "003_TBL_PLANTA_MOVIL_B2B.csv",
    "invoices": "005_TBL_FACTURAS_B2B.csv",
    "credit_notes": "006_TBL_NOTAS_CREDITO_B2B.csv",
}


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


def _decode_csv(content: bytes, logical_table: str) -> list[dict[str, str]]:
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            reader = csv.DictReader(io.StringIO(content.decode(encoding)), delimiter="|")
            if not reader.fieldnames or len(reader.fieldnames) < 2:
                continue
            rows: list[dict[str, str]] = []
            for row_number, row in enumerate(reader, start=2):
                clean = {key: (value or "") for key, value in row.items()}
                # These metadata fields are deliberately retained for evidence; no source value is changed.
                clean["__source_table"] = logical_table
                clean["__source_row_number"] = str(row_number)
                rows.append(clean)
            return rows
        except UnicodeDecodeError:
            continue
    raise ValueError(f"No se pudo decodificar la tabla {logical_table}")


def _read_zip(path: Path) -> dict[str, list[dict[str, str]]]:
    with zipfile.ZipFile(path) as outer:
        nested_name = next((name for name in outer.namelist() if name.lower().endswith(".zip")), None)
        nested = zipfile.ZipFile(io.BytesIO(outer.read(nested_name))) if nested_name else outer
        try:
            return {
                logical: _decode_csv(
                    nested.read(next(name for name in nested.namelist() if name.endswith(filename))), logical
                )
                for logical, filename in TABLE_FILES.items()
            }
        finally:
            if nested is not outer:
                nested.close()


def load_dataset(path: Path) -> BillingDataset:
    """Load an official CSV directory or official ZIP container without deduplicating rows."""
    if path.is_dir():
        contents = {
            logical: _decode_csv((path / filename).read_bytes(), logical)
            for logical, filename in TABLE_FILES.items()
        }
    elif path.suffix.lower() == ".zip":
        contents = _read_zip(path)
    else:
        raise ValueError("dataset debe ser un directorio con los cinco CSV de Facturación o un archivo .zip")
    return BillingDataset(**contents)
