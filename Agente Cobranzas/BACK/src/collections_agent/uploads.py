"""Strict in-memory CSV validation for the collections data model."""

from __future__ import annotations

import csv
import io
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation

from .data import TABLE_FILES, SoniaDataset

TABLE_REQUIREMENTS: dict[str, set[str]] = {
    "customers": {"RAZON_SOCIAL"},
    "fixed_plant": {"RAZON_SOCIAL", "COD_CLIENTE", "COD_CUENTA", "CICLO"},
    "mobile_plant": {"RAZON_SOCIAL", "COD_CLIENTE", "COD_CUENTA", "PRODUCTO"},
    "payments": {
        "RAZON_SOCIAL",
        "COD_CUENTA",
        "FACTURA_AFECTADA",
        "FECHA_PAGO",
        "MONTO_PAGADO",
    },
    "invoices": {
        "RAZON_SOCIAL",
        "COD_CLIENTE",
        "COD_CUENTA",
        "NRO_DOC_FISCAL",
        "FECHA_EMISION",
        "FECHA_VTO",
        "CHARGE_TOTAL_AMOUNT",
    },
    "credit_notes": {"NRO_DOC_FISCAL", "FACTURA_AFECTADA", "FECHAEMISION", "MONTO"},
}

DATE_COLUMNS = {
    "payments": {"FECHA_PAGO"},
    "invoices": {"FECHA_EMISION", "FECHA_VTO"},
    "credit_notes": {"FECHAEMISION"},
}
MONEY_COLUMNS = {
    "payments": {"MONTO_PAGADO"},
    "invoices": {"CHARGE_TOTAL_AMOUNT"},
    "credit_notes": {"MONTO"},
}
NULLABLE_DATA_COLUMNS = {"mobile_plant": {"COD_CUENTA"}}
_FILE_TO_TABLE = {name.lower(): table for table, name in TABLE_FILES.items()}


class CsvValidationError(ValueError):
    """Raised when uploaded data cannot safely enter the agent."""


@dataclass(slots=True)
class UploadReport:
    accepted_tables: list[dict[str, object]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    ready_for_analysis: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "accepted_tables": self.accepted_tables,
            "errors": self.errors,
            "warnings": self.warnings,
            "ready_for_analysis": self.ready_for_analysis,
            "message": (
                "Archivos validados y cargados temporalmente para el análisis."
                if self.ready_for_analysis
                else "Los archivos no se utilizaron; revisa las observaciones."
            ),
        }


def _decode(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise CsvValidationError("No se pudo leer el CSV. Usa UTF-8, ANSI o Windows-1252.")


def _rows(content: bytes) -> tuple[list[str], list[dict[str, str]]]:
    text = _decode(content)
    try:
        delimiter = csv.Sniffer().sniff(text[:4096], delimiters="|,;\t").delimiter
    except csv.Error:
        delimiter = "|"
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    headers = [header.strip() for header in reader.fieldnames or [] if header]
    if not headers:
        raise CsvValidationError("El CSV no contiene una fila de encabezados.")
    if len(headers) != len(set(headers)):
        raise CsvValidationError("El CSV contiene encabezados repetidos.")
    rows = [
        {key.strip(): (value or "").strip() for key, value in row.items() if key} for row in reader
    ]
    if not rows:
        raise CsvValidationError("El CSV no contiene registros.")
    return headers, rows


def _detect_table(filename: str, headers: list[str]) -> str:
    named = _FILE_TO_TABLE.get(filename.lower())
    header_set = set(headers)
    candidates = [name for name, required in TABLE_REQUIREMENTS.items() if required <= header_set]
    if named:
        if TABLE_REQUIREMENTS[named] <= header_set:
            return named
        missing = ", ".join(sorted(TABLE_REQUIREMENTS[named] - header_set))
        raise CsvValidationError(f"{filename}: faltan columnas requeridas: {missing}.")
    if candidates:
        specificity = max(len(TABLE_REQUIREMENTS[name]) for name in candidates)
        best = [name for name in candidates if len(TABLE_REQUIREMENTS[name]) == specificity]
        if len(best) == 1:
            return best[0]
    if not candidates:
        raise CsvValidationError(f"{filename}: no coincide con una tabla compatible del agente.")
    raise CsvValidationError(
        f"{filename}: no se puede identificar la tabla; usa el nombre oficial."
    )


def _is_date(value: str) -> bool:
    return any(_try_date(value, pattern) for pattern in ("%Y-%m-%d", "%Y%m%d", "%d/%m/%Y"))


def _try_date(value: str, pattern: str) -> bool:
    try:
        datetime.strptime(value.split(" ")[0], pattern)
        return True
    except ValueError:
        return False


def _is_money(value: str) -> bool:
    try:
        Decimal(value.replace(",", "."))
        return True
    except (InvalidOperation, AttributeError):
        return False


def _date_value(value: str) -> datetime | None:
    for pattern in ("%Y-%m-%d", "%Y%m%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value.split(" ")[0], pattern)
        except ValueError:
            continue
    return None


def _validate_rows(table: str, rows: list[dict[str, str]]) -> list[str]:
    errors: list[str] = []
    required = TABLE_REQUIREMENTS[table]
    for index, row in enumerate(rows, start=2):
        for column in required:
            if not row.get(column) and column not in NULLABLE_DATA_COLUMNS.get(table, set()):
                errors.append(f"Fila {index}: {column} está vacío.")
        for column in DATE_COLUMNS.get(table, set()):
            if row.get(column) and not _is_date(row[column]):
                errors.append(f"Fila {index}: {column} no tiene una fecha válida.")
        for column in MONEY_COLUMNS.get(table, set()):
            if row.get(column) and not _is_money(row[column]):
                errors.append(f"Fila {index}: {column} no tiene un importe válido.")
            elif row.get(column):
                amount = Decimal(row[column].replace(",", "."))
                if amount < 0 or (table != "invoices" and amount == 0):
                    errors.append(f"Fila {index}: {column} debe ser mayor que cero.")
        if len(errors) >= 10:
            return errors
    if table == "invoices":
        duplicates = [
            document
            for document, count in Counter(row["NRO_DOC_FISCAL"] for row in rows).items()
            if count > 1
        ]
        if duplicates:
            errors.append("Existen facturas repetidas; no se cargaron para evitar sobrescrituras.")
    return errors


def _validate_relationships(
    tables: dict[str, list[dict[str, str]]],
) -> tuple[list[str], list[str]]:
    """Validate joins without hiding legitimate out-of-cutoff business exceptions."""
    errors: list[str] = []
    warnings: list[str] = []
    invoices = {row["NRO_DOC_FISCAL"].strip(): row for row in tables.get("invoices", [])}
    unmatched_payments = 0
    temporal_payments = 0
    for payment in tables.get("payments", []):
        invoice = invoices.get(payment["FACTURA_AFECTADA"].strip())
        if invoice is None:
            unmatched_payments += 1
            continue
        if (
            payment["RAZON_SOCIAL"].strip() != invoice["RAZON_SOCIAL"].strip()
            or payment["COD_CUENTA"].strip() != invoice["COD_CUENTA"].strip()
        ):
            errors.append(
                "Un pago asociado a una factura no coincide en cliente o cuenta; "
                "el paquete no se cargó para evitar una aplicación incorrecta."
            )
            break
        paid_at = _date_value(payment["FECHA_PAGO"])
        issued_at = _date_value(invoice["FECHA_EMISION"])
        if paid_at is not None and issued_at is not None and paid_at < issued_at:
            temporal_payments += 1

    unmatched_credits = sum(
        row["FACTURA_AFECTADA"].strip() not in invoices for row in tables.get("credit_notes", [])
    )
    invalid_due_dates = sum(
        (due := _date_value(row["FECHA_VTO"])) is not None
        and (issued := _date_value(row["FECHA_EMISION"])) is not None
        and due < issued
        for row in tables.get("invoices", [])
    )
    zero_value_invoices = sum(
        Decimal(row["CHARGE_TOTAL_AMOUNT"].replace(",", ".")) == 0
        for row in tables.get("invoices", [])
    )
    mobile_rows_without_account = sum(
        not row.get("COD_CUENTA") for row in tables.get("mobile_plant", [])
    )
    if unmatched_payments:
        warnings.append(
            f"{unmatched_payments} pagos apuntan a facturas no incluidas; se analizarán "
            "como casos para validar, sin asociarlos a otra factura."
        )
    if temporal_payments:
        warnings.append(
            f"{temporal_payments} aplicaciones tienen fecha anterior a la emisión; se "
            "conservarán como excepciones y no ingresarán a los KPIs de plazo de cobro."
        )
    if unmatched_credits:
        warnings.append(
            f"{unmatched_credits} notas de crédito apuntan a facturas no incluidas; se "
            "reportarán como casos para validar."
        )
    if invalid_due_dates:
        warnings.append(
            f"{invalid_due_dates} facturas vencen antes de su emisión; revisa las fechas de origen."
        )
    if zero_value_invoices:
        warnings.append(
            f"{zero_value_invoices} facturas tienen importe cero; se conservan para trazabilidad "
            "y se excluyen de los KPIs que requieren facturación positiva."
        )
    if mobile_rows_without_account:
        warnings.append(
            f"{mobile_rows_without_account} registros de planta móvil no tienen cuenta; no se "
            "usan para relacionar facturas o pagos."
        )
    return errors, warnings


def load_uploaded_csvs(
    files: Iterable[tuple[str, bytes]], max_files: int, max_bytes: int
) -> tuple[SoniaDataset | None, UploadReport]:
    """Validate a complete or partial package without writing it to disk."""
    incoming = list(files)
    report = UploadReport()
    if not incoming:
        report.errors.append("Selecciona al menos un archivo CSV.")
        return None, report
    if len(incoming) > max_files:
        report.errors.append(f"Puedes cargar como máximo {max_files} archivos a la vez.")
        return None, report
    if sum(len(content) for _, content in incoming) > max_bytes:
        report.errors.append("Los archivos exceden el tamaño máximo permitido.")
        return None, report

    tables: dict[str, list[dict[str, str]]] = {}
    for filename, content in incoming:
        if not filename.lower().endswith(".csv"):
            report.errors.append(f"{filename}: solo se aceptan archivos .csv.")
            continue
        try:
            headers, rows = _rows(content)
            table = _detect_table(filename, headers)
            if table in tables:
                raise CsvValidationError(
                    f"{filename}: se recibió más de un archivo para la tabla {table}."
                )
            errors = _validate_rows(table, rows)
            if errors:
                raise CsvValidationError(f"{filename}: " + " ".join(errors))
            tables[table] = rows
            report.accepted_tables.append({"table": table, "file": filename, "records": len(rows)})
        except CsvValidationError as error:
            report.errors.append(str(error))

    if report.errors:
        report.accepted_tables.clear()
        return None, report
    if "invoices" not in tables:
        report.errors.append(
            "Falta el archivo de facturas, obligatorio para calcular cartera y saldos."
        )
        report.accepted_tables.clear()
        return None, report

    relationship_errors, relationship_warnings = _validate_relationships(tables)
    if relationship_errors:
        report.errors.extend(relationship_errors)
        report.accepted_tables.clear()
        return None, report
    report.warnings.extend(relationship_warnings)

    dataset = SoniaDataset(
        customers=tables.get("customers", []),
        fixed_plant=tables.get("fixed_plant", []),
        mobile_plant=tables.get("mobile_plant", []),
        payments=tables.get("payments", []),
        invoices=tables["invoices"],
        credit_notes=tables.get("credit_notes", []),
    )
    report.ready_for_analysis = True
    return dataset, report
