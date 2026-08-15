"""Adapters for the six official SON-IA CSV tables.

The adapter deliberately preserves source strings. Parsing and business rules belong
to the canonical model so every transformation is traceable.
"""

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
    "payments": "004_TBL_PAGOS_B2B.csv",
    "invoices": "005_TBL_FACTURAS_B2B.csv",
    "credit_notes": "006_TBL_NOTAS_CREDITO_B2B.csv",
}


@dataclass(frozen=True, slots=True)
class SoniaDataset:
    customers: list[dict[str, str]]
    fixed_plant: list[dict[str, str]]
    mobile_plant: list[dict[str, str]]
    payments: list[dict[str, str]]
    invoices: list[dict[str, str]]
    credit_notes: list[dict[str, str]]


def _decode_csv(content: bytes) -> list[dict[str, str]]:
    for encoding in ("utf-8-sig", "utf-8", "latin1", "cp1252"):
        try:
            reader = csv.DictReader(io.StringIO(content.decode(encoding)), delimiter="|")
            if reader.fieldnames and len(reader.fieldnames) > 1:
                return [{key: (value or "") for key, value in row.items()} for row in reader]
        except UnicodeDecodeError:
            continue
    raise ValueError("No se pudo decodificar un CSV del dataset")


def _read_zip(path: Path) -> dict[str, list[dict[str, str]]]:
    with zipfile.ZipFile(path) as outer:
        nested_name = next(
            (name for name in outer.namelist() if name.lower().endswith(".zip")), None
        )
        nested = zipfile.ZipFile(io.BytesIO(outer.read(nested_name))) if nested_name else outer
        try:
            return {
                logical: _decode_csv(
                    nested.read(next(name for name in nested.namelist() if name.endswith(filename)))
                )
                for logical, filename in TABLE_FILES.items()
            }
        finally:
            if nested is not outer:
                nested.close()


def load_dataset(path: Path) -> SoniaDataset:
    """Load an official CSV directory, DATASET.zip, or outer SONIA ZIP container."""
    if path.is_dir():
        contents = {
            logical: _decode_csv((path / filename).read_bytes())
            for logical, filename in TABLE_FILES.items()
        }
    elif path.suffix.lower() == ".zip":
        contents = _read_zip(path)
    else:
        raise ValueError("dataset debe ser un directorio con los 6 CSV o un archivo .zip")
    return SoniaDataset(**contents)
