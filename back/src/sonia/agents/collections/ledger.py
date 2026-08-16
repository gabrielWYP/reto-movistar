"""Deterministic document ledger and business rules; no LLM calculations occur here."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Iterable

from .data import SoniaDataset
from .rules import TOLERANCE, aging_bucket

ZERO = Decimal("0")


def money(value: str | Decimal | None) -> Decimal:
    try:
        return Decimal(str(value or "0").strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        return ZERO


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    value = value.strip().split(" ")[0]
    for format_ in ("%Y-%m-%d", "%Y%m%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, format_).date()
        except ValueError:
            pass
    return None


@dataclass(slots=True)
class Payment:
    amount: Decimal
    paid_at: date | None
    customer: str
    account_code: str
    document: str


@dataclass(slots=True)
class CreditNote:
    amount: Decimal
    issued_at: date | None
    document: str


@dataclass(slots=True)
class InvoiceLedger:
    document: str
    customer: str
    customer_code: str
    account_code: str
    issued_at: date | None
    due_at: date | None
    currency: str | None
    total: Decimal
    payments: list[Payment] = field(default_factory=list)
    credits: list[CreditNote] = field(default_factory=list)

    @property
    def paid(self) -> Decimal:
        return sum((payment.amount for payment in self.payments), ZERO)

    @property
    def credited(self) -> Decimal:
        return sum((credit.amount for credit in self.credits), ZERO)

    @property
    def net_obligation(self) -> Decimal:
        return self.total - self.credited

    @property
    def raw_balance(self) -> Decimal:
        return self.net_obligation - self.paid

    @property
    def open_balance(self) -> Decimal:
        return max(self.raw_balance, ZERO)

    def settlement_state(self) -> str:
        if self.raw_balance < -TOLERANCE:
            return "SALDO_A_FAVOR"
        if abs(self.raw_balance) <= TOLERANCE:
            return "PAGADA"
        if self.paid > ZERO:
            return "PAGO_PARCIAL"
        return "PENDIENTE"

    def delinquency_state(self, as_of: date) -> str:
        if self.open_balance <= TOLERANCE or not self.due_at:
            return "NO_APLICA"
        days = max(0, (as_of - self.due_at).days)
        if days >= 90:
            return "CRITICA"
        if self.due_at < as_of:
            return "VENCIDA"
        return "NO_VENCIDA"

    def days_past_due(self, as_of: date) -> int | None:
        return max(0, (as_of - self.due_at).days) if self.due_at else None

    def reconciliation_state(self) -> str:
        if self.raw_balance < -TOLERANCE:
            return "REQUIERE_REVISION"
        if abs(self.raw_balance) <= TOLERANCE:
            return "CONCILIADA"
        if self.paid > ZERO or self.credited > ZERO:
            return "PARCIALMENTE_CONCILIADA"
        return "PENDIENTE_DE_PAGO"


@dataclass(slots=True)
class Ledger:
    invoices: dict[str, InvoiceLedger]
    unmatched_payments: list[Payment]
    customer_master: dict[str, dict[str, str]]
    source_counts: dict[str, int]

    @property
    def latest_event_date(self) -> date:
        dates = [
            item.issued_at for item in self.invoices.values()
        ] + [
            payment.paid_at for item in self.invoices.values() for payment in item.payments
        ] + [
            credit.issued_at for item in self.invoices.values() for credit in item.credits
        ]
        return max(value for value in dates if value is not None)


def build_ledger(dataset: SoniaDataset) -> Ledger:
    invoices: dict[str, InvoiceLedger] = {}
    for row in dataset.invoices:
        document = row["NRO_DOC_FISCAL"].strip()
        invoices[document] = InvoiceLedger(
            document=document,
            customer=row["RAZON_SOCIAL"].strip(),
            customer_code=row["COD_CLIENTE"].strip(),
            account_code=row["COD_CUENTA"].strip(),
            issued_at=parse_date(row.get("FECHA_EMISION")),
            due_at=parse_date(row.get("FECHA_VTO")),
            currency=(row.get("MONEDA") or "").strip() or None,
            total=money(row.get("CHARGE_TOTAL_AMOUNT")),
        )

    unmatched: list[Payment] = []
    for row in dataset.payments:
        payment = Payment(
            amount=money(row.get("MONTO_PAGADO")),
            paid_at=parse_date(row.get("FECHA_PAGO")),
            customer=row["RAZON_SOCIAL"].strip(),
            account_code=row["COD_CUENTA"].strip(),
            document=row["FACTURA_AFECTADA"].strip(),
        )
        invoice = invoices.get(payment.document)
        if invoice:
            invoice.payments.append(payment)
        else:
            unmatched.append(payment)

    for row in dataset.credit_notes:
        invoice = invoices.get(row["FACTURA_AFECTADA"].strip())
        if invoice:
            invoice.credits.append(
                CreditNote(
                    amount=money(row.get("MONTO")),
                    issued_at=parse_date(row.get("FECHAEMISION")),
                    document=row["NRO_DOC_FISCAL"].strip(),
                )
            )

    master = {row["RAZON_SOCIAL"].strip(): row for row in dataset.customers}
    return Ledger(
        invoices=invoices,
        unmatched_payments=unmatched,
        customer_master=master,
        source_counts={
            "customers": len(dataset.customers),
            "invoices": len(dataset.invoices),
            "payments": len(dataset.payments),
            "credit_notes": len(dataset.credit_notes),
            "fixed_plant": len(dataset.fixed_plant),
            "mobile_plant": len(dataset.mobile_plant),
        },
    )


def by_customer(invoices: Iterable[InvoiceLedger]) -> dict[str, list[InvoiceLedger]]:
    result: dict[str, list[InvoiceLedger]] = defaultdict(list)
    for invoice in invoices:
        result[invoice.customer].append(invoice)
    return result
