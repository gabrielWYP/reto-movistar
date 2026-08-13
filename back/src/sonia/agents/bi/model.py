"""Canonical revenue model and deterministic data-quality rules for BI v0.1."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Iterable

from .data import SoniaDataset

ZERO = Decimal("0")
TOLERANCE = Decimal("0.01")
PEN = "PEN"


def money(value: str | Decimal | None) -> Decimal:
    try:
        return Decimal(str(value or "0").strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        return ZERO


def parse_date(value: str | None) -> date | None:
    text = (value or "").strip().split(" ")[0]
    for layout in ("%Y-%m-%d", "%Y%m%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, layout).date()
        except ValueError:
            continue
    return None


def _unique_rows(rows: Iterable[dict[str, str]]) -> int:
    return len(list(rows)) - len({tuple(sorted(row.items())) for row in rows})


@dataclass(frozen=True, slots=True)
class Payment:
    document: str
    customer: str
    account_code: str
    paid_at: date | None
    currency: str
    amount: Decimal


@dataclass(frozen=True, slots=True)
class CreditNote:
    document: str
    affected_invoice: str
    issued_at: date | None
    currency: str
    amount: Decimal


@dataclass(slots=True)
class Invoice:
    document: str
    customer: str
    customer_code: str
    account_code: str
    issued_at: date | None
    due_at: date | None
    source: str
    system: str
    currency: str
    total: Decimal
    payments: list[Payment] = field(default_factory=list)
    credits: list[CreditNote] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class SnapshotInvoice:
    invoice: Invoice
    paid: Decimal
    credited: Decimal

    @property
    def raw_balance(self) -> Decimal:
        return self.invoice.total - self.paid - self.credited

    @property
    def balance(self) -> Decimal:
        return max(self.raw_balance, ZERO)

    def days_past_due(self, as_of: date) -> int | None:
        return max(0, (as_of - self.invoice.due_at).days) if self.invoice.due_at else None


@dataclass(slots=True)
class CanonicalRevenueModel:
    invoices: dict[str, Invoice]
    customer_master: dict[str, dict[str, str]]
    plant_by_account: dict[str, dict[str, object]]
    source_counts: dict[str, int]
    quality: dict[str, object]
    all_payments: list[Payment]
    unmatched_payments: list[Payment]
    unmatched_credits: list[CreditNote]

    def snapshot(self, as_of: date) -> list[SnapshotInvoice]:
        """An as-of snapshot: only documents and applications known by the cut-off."""
        rows: list[SnapshotInvoice] = []
        for invoice in self.invoices.values():
            if not invoice.issued_at or invoice.issued_at > as_of or invoice.currency != PEN:
                continue
            payments = sum((item.amount for item in invoice.payments if item.paid_at and item.paid_at <= as_of and item.currency == PEN), ZERO)
            credits = sum((item.amount for item in invoice.credits if item.issued_at and item.issued_at <= as_of and item.currency == PEN), ZERO)
            rows.append(SnapshotInvoice(invoice, payments, credits))
        return rows

    def payments_after(self, as_of: date) -> list[Payment]:
        return [item for item in self.all_payments if item.paid_at and item.paid_at > as_of]


def _plant_summary(fixed_rows: list[dict[str, str]], mobile_rows: list[dict[str, str]]) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for kind, rows, product in (("fixed", fixed_rows, "SUB_MAIN_OFFER_DESC"), ("mobile", mobile_rows, "PRODUCT_DESC")):
        for row in rows:
            account = row.get("COD_CUENTA", "").strip()
            if not account:
                continue
            summary = result.setdefault(account, {"fixed_records": 0, "mobile_records": 0, "fixed_offers": set(), "mobile_products": set()})
            summary[f"{kind}_records"] = int(summary[f"{kind}_records"]) + 1
            value = row.get(product, "").strip()
            if value:
                cast = summary["fixed_offers" if kind == "fixed" else "mobile_products"]
                assert isinstance(cast, set)
                cast.add(value)
    for summary in result.values():
        summary["fixed_offers"] = sorted(summary["fixed_offers"])
        summary["mobile_products"] = sorted(summary["mobile_products"])
    return result


def build_canonical_model(dataset: SoniaDataset) -> CanonicalRevenueModel:
    invoices: dict[str, Invoice] = {}
    invalid_dates: Counter[str] = Counter()
    excluded_invoice_currencies: Counter[str] = Counter()
    for row in dataset.invoices:
        document = row.get("NRO_DOC_FISCAL", "").strip()
        if not document:
            raise ValueError("Factura sin NRO_DOC_FISCAL")
        if document in invoices:
            raise ValueError(f"NRO_DOC_FISCAL duplicado: {document}")
        issued_at = parse_date(row.get("FECHA_EMISION"))
        due_at = parse_date(row.get("FECHA_VTO"))
        if not issued_at:
            invalid_dates["invoice_issued_at"] += 1
        if row.get("FECHA_VTO", "").strip() and not due_at:
            invalid_dates["invoice_due_at"] += 1
        currency = row.get("MONEDA", "").strip().upper()
        if currency != PEN:
            excluded_invoice_currencies[currency or "MISSING"] += 1
        invoices[document] = Invoice(document, row.get("RAZON_SOCIAL", "").strip(), row.get("COD_CLIENTE", "").strip(), row.get("COD_CUENTA", "").strip(), issued_at, due_at, row.get("FUENTE", "").strip(), row.get("SISTEMA", "").strip(), currency, money(row.get("CHARGE_TOTAL_AMOUNT")))

    unmatched_payments: list[Payment] = []
    all_payments: list[Payment] = []
    payment_currency_mismatch = 0
    for row in dataset.payments:
        item = Payment(row.get("FACTURA_AFECTADA", "").strip(), row.get("RAZON_SOCIAL", "").strip(), row.get("COD_CUENTA", "").strip(), parse_date(row.get("FECHA_PAGO")), row.get("MONEDA_FACTURA", "").strip().upper(), money(row.get("MONTO_PAGADO")))
        all_payments.append(item)
        invoice = invoices.get(item.document)
        if not invoice:
            unmatched_payments.append(item)
        elif item.currency != invoice.currency:
            payment_currency_mismatch += 1
        else:
            invoice.payments.append(item)

    unmatched_credits: list[CreditNote] = []
    credit_currency_mismatch = 0
    for row in dataset.credit_notes:
        item = CreditNote(row.get("NRO_DOC_FISCAL", "").strip(), row.get("FACTURA_AFECTADA", "").strip(), parse_date(row.get("FECHAEMISION")), row.get("MONEDA", "").strip().upper(), money(row.get("MONTO")))
        invoice = invoices.get(item.affected_invoice)
        if not invoice:
            unmatched_credits.append(item)
        elif item.currency != invoice.currency:
            credit_currency_mismatch += 1
        else:
            invoice.credits.append(item)

    master = {row.get("RAZON_SOCIAL", "").strip(): row for row in dataset.customers}
    linked_by_name = sum(invoice.customer in master for invoice in invoices.values())
    quality = {
        "duplicate_full_rows": {"fixed_plant": _unique_rows(dataset.fixed_plant), "mobile_plant": _unique_rows(dataset.mobile_plant)},
        "invalid_dates": dict(invalid_dates),
        "excluded_invoice_currencies": dict(excluded_invoice_currencies),
        "payment_currency_mismatch_count": payment_currency_mismatch,
        "credit_note_currency_mismatch_count": credit_currency_mismatch,
        "customer_master_name_coverage": {"matched_invoice_rows": linked_by_name, "invoice_rows": len(invoices)},
        "invoice_plant_account_coverage": sum(invoice.account_code in _plant_summary(dataset.fixed_plant, dataset.mobile_plant) for invoice in invoices.values()),
        "ruc_join_disabled": True,
    }
    return CanonicalRevenueModel(invoices, master, _plant_summary(dataset.fixed_plant, dataset.mobile_plant), {"customers": len(dataset.customers), "fixed_plant": len(dataset.fixed_plant), "mobile_plant": len(dataset.mobile_plant), "payments": len(dataset.payments), "invoices": len(dataset.invoices), "credit_notes": len(dataset.credit_notes)}, quality, all_payments, unmatched_payments, unmatched_credits)


def aging_bucket(days: int | None) -> str:
    if days is None:
        return "SIN_FECHA_VENCIMIENTO"
    if days == 0:
        return "NO_VENCIDA"
    if days <= 30:
        return "1_30"
    if days <= 60:
        return "31_60"
    if days <= 90:
        return "61_90"
    return "90_PLUS"
