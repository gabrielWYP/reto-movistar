"""Canonical billing model. Raw source rows stay attached for audit evidence."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Iterable

from .data import BillingDataset

ZERO = Decimal("0")


def money(value: str) -> Decimal:
    try:
        return Decimal(value.strip() or "0")
    except InvalidOperation as error:
        raise ValueError(f"Importe no válido: {value!r}") from error


def parse_date(value: str) -> date | None:
    """Accept official AMDOCS, ISIS and plant date formats; retain nulls as nulls."""
    text = (value or "").strip()
    if not text:
        return None
    for pattern in ("%Y-%m-%d", "%Y%m%d", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    raise ValueError(f"Fecha no reconocida: {value!r}")


def source_ref(row: dict[str, str]) -> dict[str, str]:
    return {
        "table": row["__source_table"],
        "row_number": row["__source_row_number"],
    }


@dataclass(frozen=True, slots=True)
class Invoice:
    document: str
    customer: str
    customer_code: str
    account: str
    fiscal_id: str
    source: str
    system: str
    issued_at: date | None
    due_at: date | None
    currency: str
    net: Decimal
    tax: Decimal
    total: Decimal
    raw: dict[str, str]

    @property
    def evidence(self) -> dict:
        return {
            "document": self.document,
            "customer": self.customer,
            "customer_code": self.customer_code,
            "account": self.account,
            "fiscal_id": self.fiscal_id,
            "source": self.source,
            "system": self.system,
            "issued_at": self.issued_at,
            "due_at": self.due_at,
            "currency": self.currency or None,
            "net": self.net,
            "tax": self.tax,
            "total": self.total,
            "source_ref": source_ref(self.raw),
        }


@dataclass(frozen=True, slots=True)
class CreditNote:
    document: str
    affected_invoice: str
    customer: str
    account: str
    fiscal_id: str
    issued_at: date | None
    currency: str
    net: Decimal
    tax: Decimal
    total: Decimal
    raw: dict[str, str]

    @property
    def evidence(self) -> dict:
        return {
            "document": self.document,
            "affected_invoice": self.affected_invoice,
            "customer": self.customer,
            "account": self.account,
            "fiscal_id": self.fiscal_id,
            "issued_at": self.issued_at,
            "currency": self.currency or None,
            "net": self.net,
            "tax": self.tax,
            "total": self.total,
            "source_ref": source_ref(self.raw),
        }


@dataclass(slots=True)
class BillingModel:
    dataset: BillingDataset
    customers: dict[str, dict[str, str]]
    invoices: dict[str, Invoice]
    credit_notes: list[CreditNote]
    credits_by_invoice: dict[str, list[CreditNote]]
    invoices_by_customer: dict[str, list[Invoice]]
    invoices_by_customer_account: dict[tuple[str, str], list[Invoice]]
    plants_by_customer_account: dict[tuple[str, str], list[dict[str, str]]]

    def plant_rows(self, customer: str, account: str) -> list[dict[str, str]]:
        return self.plants_by_customer_account.get((customer, account), [])

    def all_plant_accounts(self) -> Iterable[tuple[str, str]]:
        return self.plants_by_customer_account.keys()


def _invoice(row: dict[str, str]) -> Invoice:
    return Invoice(
        document=row["NRO_DOC_FISCAL"].strip(),
        customer=row["RAZON_SOCIAL"].strip(),
        customer_code=row["COD_CLIENTE"].strip(),
        account=row["COD_CUENTA"].strip(),
        fiscal_id=row["NUMERO_IDENTIFICACION_FISCAL"].strip(),
        source=row["FUENTE"].strip(),
        system=row["SISTEMA"].strip(),
        issued_at=parse_date(row.get("FECHA_EMISION", "")),
        due_at=parse_date(row.get("FECHA_VTO", "")),
        currency=row.get("MONEDA", "").strip(),
        net=money(row.get("CHARGE_NET_AMOUNT", "")),
        tax=money(row.get("CHARGE_IGV_INVOICE", "")),
        total=money(row.get("CHARGE_TOTAL_AMOUNT", "")),
        raw=row,
    )


def _credit_note(row: dict[str, str]) -> CreditNote:
    return CreditNote(
        document=row["NRO_DOC_FISCAL"].strip(),
        affected_invoice=row["FACTURA_AFECTADA"].strip(),
        customer=row["RAZON_SOCIAL"].strip(),
        account=row["COD_CUENTA"].strip(),
        fiscal_id=row["NUMERO_IDENTIFICACION_FISCAL"].strip(),
        issued_at=parse_date(row.get("FECHAEMISION", "")),
        currency=row.get("MONEDA", "").strip(),
        net=money(row.get("MONTO_SIN_IGV", "")),
        tax=money(row.get("SUBTOTAL", "")),
        total=money(row.get("MONTO", "")),
        raw=row,
    )


def build_model(dataset: BillingDataset) -> BillingModel:
    customers = {row["RAZON_SOCIAL"].strip(): row for row in dataset.customers}
    invoice_rows = [_invoice(row) for row in dataset.invoices]
    invoices = {item.document: item for item in invoice_rows}
    if len(invoices) != len(invoice_rows):
        raise ValueError("NRO_DOC_FISCAL no es único; no se puede construir una traza auditable")
    credit_notes = [_credit_note(row) for row in dataset.credit_notes]
    credits_by_invoice: dict[str, list[CreditNote]] = defaultdict(list)
    for note in credit_notes:
        credits_by_invoice[note.affected_invoice].append(note)
    invoices_by_customer: dict[str, list[Invoice]] = defaultdict(list)
    invoices_by_customer_account: dict[tuple[str, str], list[Invoice]] = defaultdict(list)
    for item in invoice_rows:
        invoices_by_customer[item.customer].append(item)
        invoices_by_customer_account[(item.customer, item.account)].append(item)
    plants_by_customer_account: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    # Deliberately append every mobile record, including exact duplicates.
    for row in [*dataset.fixed_plant, *dataset.mobile_plant]:
        account = row.get("COD_CUENTA", "").strip()
        customer = row.get("RAZON_SOCIAL", "").strip()
        if customer and account:
            plants_by_customer_account[(customer, account)].append(row)
    return BillingModel(
        dataset=dataset,
        customers=customers,
        invoices=invoices,
        credit_notes=credit_notes,
        credits_by_invoice=dict(credits_by_invoice),
        invoices_by_customer=dict(invoices_by_customer),
        invoices_by_customer_account=dict(invoices_by_customer_account),
        plants_by_customer_account=dict(plants_by_customer_account),
    )
