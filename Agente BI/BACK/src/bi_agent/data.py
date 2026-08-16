"""Adapters for the six official SON-IA CSV tables.

The adapter deliberately preserves source strings. Parsing and business rules belong
to the canonical model so every transformation is traceable.
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections.abc import Mapping
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
MAX_UNCOMPRESSED_DATASET_BYTES = 50 * 1024 * 1024


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


def _matching_zip_entry(archive: zipfile.ZipFile, filename: str) -> zipfile.ZipInfo:
    match = next(
        (item for item in archive.infolist() if Path(item.filename).name == filename),
        None,
    )
    if match is None:
        raise ValueError(f"El ZIP no contiene {filename}.")
    return match


def _bounded_zip_read(archive: zipfile.ZipFile, entry: zipfile.ZipInfo) -> bytes:
    if entry.file_size > MAX_UNCOMPRESSED_DATASET_BYTES:
        raise ValueError("El dataset descomprimido excede 50 MiB.")
    return archive.read(entry)


def _extract_zip_files(content: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(content)) as outer:
        nested_name = next(
            (name for name in outer.namelist() if name.lower().endswith(".zip")), None
        )
        if nested_name:
            nested_info = outer.getinfo(nested_name)
            nested = zipfile.ZipFile(io.BytesIO(_bounded_zip_read(outer, nested_info)))
        else:
            nested = outer
        try:
            entries = {
                filename: _matching_zip_entry(nested, filename) for filename in TABLE_FILES.values()
            }
            total_size = sum(entry.file_size for entry in entries.values())
            if total_size > MAX_UNCOMPRESSED_DATASET_BYTES:
                raise ValueError("El dataset descomprimido excede 50 MiB.")
            return {
                filename: _bounded_zip_read(nested, entry) for filename, entry in entries.items()
            }
        finally:
            if nested is not outer:
                nested.close()


def normalize_dataset_files(files: Mapping[str, bytes]) -> dict[str, bytes]:
    """Validate uploaded names and expand a single ZIP into canonical CSV entries."""
    normalized = {Path(name).name: content for name, content in files.items()}
    zip_names = [name for name in normalized if name.lower().endswith(".zip")]
    if zip_names:
        if len(normalized) != 1:
            raise ValueError("Carga el ZIP solo, sin mezclarlo con archivos CSV.")
        try:
            return _extract_zip_files(normalized[zip_names[0]])
        except zipfile.BadZipFile as error:
            raise ValueError("El archivo ZIP no es válido.") from error

    unknown = sorted(set(normalized) - set(TABLE_FILES.values()))
    if unknown:
        raise ValueError(f"Archivos no reconocidos: {', '.join(unknown)}.")
    return normalized


def missing_dataset_files(files: Mapping[str, bytes]) -> list[str]:
    """Return the official table names not present in an in-memory upload."""
    return sorted(set(TABLE_FILES.values()) - set(files))


def _load_memory_dataset(files: Mapping[str, bytes]) -> SoniaDataset:
    missing = missing_dataset_files(files)
    if missing:
        raise ValueError(f"Faltan archivos del dataset: {', '.join(missing)}.")
    contents = {logical: _decode_csv(files[filename]) for logical, filename in TABLE_FILES.items()}
    return SoniaDataset(**contents)


def load_dataset(source: Path | Mapping[str, bytes]) -> SoniaDataset:
    """Load an official CSV directory, DATASET.zip, or outer SONIA ZIP container."""
    if not isinstance(source, Path):
        return _load_memory_dataset(normalize_dataset_files(source))
    if source.is_dir():
        contents = {
            logical: _decode_csv((source / filename).read_bytes())
            for logical, filename in TABLE_FILES.items()
        }
    elif source.suffix.lower() == ".zip":
        return _load_memory_dataset(_extract_zip_files(source.read_bytes()))
    else:
        raise ValueError("dataset debe ser un directorio con los 6 CSV o un archivo .zip")
    return SoniaDataset(**contents)
