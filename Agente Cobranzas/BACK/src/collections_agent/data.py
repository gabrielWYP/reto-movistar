"""Dataset adapter. It reads the official nested ZIP without third-party packages."""

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
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            text = content.decode(encoding)
            reader = csv.DictReader(io.StringIO(text), delimiter="|")
            if reader.fieldnames and len(reader.fieldnames) > 1:
                return [dict(row) for row in reader]
        except UnicodeDecodeError:
            continue
    raise ValueError("No se pudo decodificar un CSV del dataset")


def load_dataset(path: Path) -> SoniaDataset:
    """Load either DATASET.zip or the official SONIA_DESAFIO_03.zip container."""
    with zipfile.ZipFile(path) as outer:
        nested = next((name for name in outer.namelist() if name.lower().endswith(".zip")), None)
        if nested:
            source = zipfile.ZipFile(io.BytesIO(outer.read(nested)))
        else:
            source = outer
        try:
            contents = {
                logical_name: _decode_csv(
                    source.read(
                        next(name for name in source.namelist() if name.endswith(file_name))
                    )
                )
                for logical_name, file_name in TABLE_FILES.items()
            }
        finally:
            if source is not outer:
                source.close()
    return SoniaDataset(**contents)
