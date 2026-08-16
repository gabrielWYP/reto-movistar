"""Deterministic document ledger and business rules; no LLM calculations occur here."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from .data import SoniaDataset
from .rules import TOLERANCE

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
    affected_document: str


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

    def payments_as_of(self, as_of: date) -> list[Payment]:
        """Return applications observable at the requested historical cutoff."""
        return [
            payment
            for payment in self.payments
            if payment.paid_at is not None and payment.paid_at <= as_of
        ]

    def paid_as_of(self, as_of: date) -> Decimal:
        return sum((payment.amount for payment in self.payments_as_of(as_of)), ZERO)

    @property
    def credited(self) -> Decimal:
        return sum((credit.amount for credit in self.credits), ZERO)

    def credits_as_of(self, as_of: date) -> list[CreditNote]:
        """Return credit notes observable at the requested historical cutoff."""
        return [
            credit
            for credit in self.credits
            if credit.issued_at is not None and credit.issued_at <= as_of
        ]

    def credited_as_of(self, as_of: date) -> Decimal:
        return sum((credit.amount for credit in self.credits_as_of(as_of)), ZERO)

    @property
    def net_obligation(self) -> Decimal:
        return self.total - self.credited

    @property
    def raw_balance(self) -> Decimal:
        return self.net_obligation - self.paid

    @property
    def open_balance(self) -> Decimal:
        return max(self.raw_balance, ZERO)

    def net_obligation_as_of(self, as_of: date) -> Decimal:
        return self.total - self.credited_as_of(as_of)

    def raw_balance_as_of(self, as_of: date) -> Decimal:
        return self.net_obligation_as_of(as_of) - self.paid_as_of(as_of)

    def open_balance_as_of(self, as_of: date) -> Decimal:
        return max(self.raw_balance_as_of(as_of), ZERO)

    def settlement_state(self, as_of: date | None = None) -> str:
        raw_balance = self.raw_balance if as_of is None else self.raw_balance_as_of(as_of)
        paid = self.paid if as_of is None else self.paid_as_of(as_of)
        if raw_balance < -TOLERANCE:
            return "SALDO_A_FAVOR"
        if abs(raw_balance) <= TOLERANCE:
            return "PAGADA"
        if paid > ZERO:
            return "PAGO_PARCIAL"
        return "PENDIENTE"

    def delinquency_state(self, as_of: date) -> str:
        if self.open_balance_as_of(as_of) <= TOLERANCE or not self.due_at:
            return "NO_APLICA"
        days = max(0, (as_of - self.due_at).days)
        if days >= 90:
            return "CRITICA"
        if self.due_at < as_of:
            return "VENCIDA"
        return "NO_VENCIDA"

    def days_past_due(self, as_of: date) -> int | None:
        return max(0, (as_of - self.due_at).days) if self.due_at else None

    def reconciliation_state(self, as_of: date | None = None) -> str:
        raw_balance = self.raw_balance if as_of is None else self.raw_balance_as_of(as_of)
        paid = self.paid if as_of is None else self.paid_as_of(as_of)
        credited = self.credited if as_of is None else self.credited_as_of(as_of)
        if raw_balance < -TOLERANCE:
            return "REQUIERE_REVISION"
        if abs(raw_balance) <= TOLERANCE:
            return "CONCILIADA"
        if paid > ZERO or credited > ZERO:
            return "PARCIALMENTE_CONCILIADA"
        return "PENDIENTE_DE_PAGO"


@dataclass(slots=True)
class Ledger:
    invoices: dict[str, InvoiceLedger]
    unmatched_payments: list[Payment]
    mismatched_payments: list[Payment]
    unmatched_credit_notes: list[CreditNote]
    customer_master: dict[str, dict[str, str]]
    source_counts: dict[str, int]

    @property
    def latest_event_date(self) -> date:
        dates = (
            [item.issued_at for item in self.invoices.values()]
            + [payment.paid_at for item in self.invoices.values() for payment in item.payments]
            + [credit.issued_at for item in self.invoices.values() for credit in item.credits]
        )
        return max(value for value in dates if value is not None)


def build_ledger(dataset: SoniaDataset) -> Ledger:
    invoices: dict[str, InvoiceLedger] = {}
    for row in dataset.invoices:
        document = row["NRO_DOC_FISCAL"].strip()
        if document in invoices:
            raise ValueError(f"Factura duplicada en el dataset: {document}")
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
    mismatched: list[Payment] = []
    for row in dataset.payments:
        payment = Payment(
            amount=money(row.get("MONTO_PAGADO")),
            paid_at=parse_date(row.get("FECHA_PAGO")),
            customer=row["RAZON_SOCIAL"].strip(),
            account_code=row["COD_CUENTA"].strip(),
            document=row["FACTURA_AFECTADA"].strip(),
        )
        invoice = invoices.get(payment.document)
        if invoice and (
            payment.customer != invoice.customer or payment.account_code != invoice.account_code
        ):
            mismatched.append(payment)
        elif invoice:
            invoice.payments.append(payment)
        else:
            unmatched.append(payment)

    unmatched_credit_notes: list[CreditNote] = []
    for row in dataset.credit_notes:
        affected_document = row["FACTURA_AFECTADA"].strip()
        invoice = invoices.get(affected_document)
        credit = CreditNote(
            amount=money(row.get("MONTO")),
            issued_at=parse_date(row.get("FECHAEMISION")),
            document=row["NRO_DOC_FISCAL"].strip(),
            affected_document=affected_document,
        )
        if invoice:
            invoice.credits.append(credit)
        else:
            unmatched_credit_notes.append(credit)

    master = {row["RAZON_SOCIAL"].strip(): row for row in dataset.customers}
    return Ledger(
        invoices=invoices,
        unmatched_payments=unmatched,
        mismatched_payments=mismatched,
        unmatched_credit_notes=unmatched_credit_notes,
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
