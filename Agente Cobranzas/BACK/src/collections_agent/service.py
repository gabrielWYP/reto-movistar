"""Tool service: compact deterministic results for a UI, Supervisor, or LLM."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Any, NotRequired, TypedDict, cast

from .contracts import AgentResponse
from .data import SoniaDataset, load_dataset
from .ledger import InvoiceLedger, Ledger, build_ledger, by_customer
from .rules import (
    EXCEPTION_SEVERITY_ORDER,
    PRIORITY_DPD_CAP,
    PRIORITY_WEIGHTS,
    TOLERANCE,
    aging_bucket,
    priority_level,
)

ZERO = Decimal()
RATIO_PRECISION = Decimal("0.0001")
DAY_PRECISION = Decimal("0.1")


class PriorityRow(TypedDict):
    """Typed intermediate used by the deterministic priority calculation."""

    customer: str
    outstanding_balance: Decimal
    overdue_balance: Decimal
    max_days_past_due: int
    overdue_share: Decimal
    partial_payment_invoice_count: int
    score_components: NotRequired[dict[str, Decimal]]
    priority_score: NotRequired[Decimal]
    priority: NotRequired[str]


class CollectionsService:
    def __init__(self, dataset_path: Path | SoniaDataset) -> None:
        dataset = (
            dataset_path if isinstance(dataset_path, SoniaDataset) else load_dataset(dataset_path)
        )
        self.ledger: Ledger = build_ledger(dataset)

    @classmethod
    def from_dataset(cls, dataset: SoniaDataset) -> CollectionsService:
        """Create an isolated service from already-validated in-memory data."""
        return cls(dataset)

    def _as_of(self, value: str | None) -> date:
        return date.fromisoformat(value) if value else self.ledger.latest_event_date

    @staticmethod
    def _aging(invoices: list[InvoiceLedger], as_of: date) -> list[dict[str, Any]]:
        totals: dict[str, Decimal] = defaultdict(Decimal)
        docs: Counter[str] = Counter()
        for invoice in invoices:
            open_balance = invoice.open_balance_as_of(as_of)
            if open_balance <= TOLERANCE:
                continue
            bucket = aging_bucket(invoice.days_past_due(as_of))
            totals[bucket] += open_balance
            docs[bucket] += 1
        order = ["NO_VENCIDA", "1_30", "31_60", "61_90", "90_PLUS", "SIN_FECHA_VENCIMIENTO"]
        return [
            {"bucket": bucket, "documents": docs[bucket], "outstanding_balance": totals[bucket]}
            for bucket in order
            if docs[bucket]
        ]

    @staticmethod
    def _invoice_evidence(invoice: InvoiceLedger, as_of: date) -> dict[str, Any]:
        paid = invoice.paid_as_of(as_of)
        credited = invoice.credited_as_of(as_of)
        return {
            "document": invoice.document,
            "customer": invoice.customer,
            "account_code": invoice.account_code,
            "issued_at": invoice.issued_at,
            "due_at": invoice.due_at,
            "days_past_due": invoice.days_past_due(as_of),
            "invoice_total": invoice.total,
            "credit_notes": credited,
            "paid": paid,
            "outstanding_balance": invoice.open_balance_as_of(as_of),
            "settlement_state": invoice.settlement_state(as_of),
            "delinquency_state": invoice.delinquency_state(as_of),
            "reconciliation_state": invoice.reconciliation_state(as_of),
        }

    @staticmethod
    def _metrics(invoices: list[InvoiceLedger], as_of: date) -> dict[str, Any]:
        total_billed = sum((invoice.total for invoice in invoices), Decimal())
        total_paid = sum((invoice.paid_as_of(as_of) for invoice in invoices), Decimal())
        outstanding = sum((invoice.open_balance_as_of(as_of) for invoice in invoices), Decimal())
        overdue = sum(
            (
                invoice.open_balance_as_of(as_of)
                for invoice in invoices
                if invoice.due_at and invoice.due_at < as_of
            ),
            Decimal(),
        )
        collection_ratio = total_paid / total_billed if total_billed else ZERO
        return {
            "total_billed": total_billed,
            "total_paid_linked": total_paid,
            "credit_notes_linked": sum(
                (invoice.credited_as_of(as_of) for invoice in invoices), Decimal()
            ),
            "outstanding_balance": outstanding,
            "overdue_balance": overdue,
            "collection_ratio": float(collection_ratio.quantize(RATIO_PRECISION)),
            "invoice_count": len(invoices),
            "open_invoice_count": sum(
                invoice.open_balance_as_of(as_of) > TOLERANCE for invoice in invoices
            ),
            "overdue_invoice_count": sum(
                invoice.open_balance_as_of(as_of) > TOLERANCE
                and invoice.due_at is not None
                and invoice.due_at < as_of
                for invoice in invoices
            ),
            "partial_payment_invoice_count": sum(
                invoice.settlement_state(as_of) == "PAGO_PARCIAL" for invoice in invoices
            ),
            "payment_application_count": sum(
                len(invoice.payments_as_of(as_of)) for invoice in invoices
            ),
        }

    @staticmethod
    def _currency_status(invoices: list[InvoiceLedger]) -> dict[str, str]:
        """Describe the existing KPI universe without changing its calculations."""
        declared = sorted(
            {
                invoice.currency.strip().upper()
                for invoice in invoices
                if isinstance(invoice.currency, str) and invoice.currency.strip()
            }
        )
        unspecified = sum(not (invoice.currency or "").strip() for invoice in invoices)
        if len(declared) == 1:
            scope = (
                "single_declared_currency_with_unspecified_records"
                if unspecified
                else "single_declared_currency"
            )
            return {"currency": declared[0], "currency_scope": scope}
        if len(declared) > 1:
            return {"currency": "MIXED", "currency_scope": "multiple_declared_currencies"}
        return {"currency": "UNKNOWN", "currency_scope": "no_declared_currency"}

    @staticmethod
    def _kpis(invoices: list[InvoiceLedger], as_of: date) -> dict[str, Any]:
        """Calculate challenge KPIs from valid, linked applications only."""
        eligible_cutoff = as_of - timedelta(days=30)
        eligible = [
            invoice
            for invoice in invoices
            if invoice.issued_at is not None
            and invoice.issued_at <= eligible_cutoff
            and invoice.total > ZERO
        ]
        eligible_documents = {invoice.document for invoice in eligible}
        eligible_billed = sum((invoice.total for invoice in eligible), ZERO)
        collected_within_30_days = ZERO
        weighted_days = ZERO
        weighted_amount = ZERO
        contributing_applications = 0
        excluded_temporal_applications = 0

        for invoice in invoices:
            if invoice.issued_at is None or invoice.total <= ZERO:
                continue
            remaining = invoice.total
            valid_payments = sorted(
                invoice.payments_as_of(as_of),
                key=lambda payment: payment.paid_at or date.max,
            )
            for payment in valid_payments:
                if payment.amount <= ZERO or payment.paid_at is None:
                    continue
                if payment.paid_at < invoice.issued_at:
                    excluded_temporal_applications += 1
                    continue
                applied = min(payment.amount, remaining)
                if applied <= ZERO:
                    continue
                elapsed_days = (payment.paid_at - invoice.issued_at).days
                weighted_days += applied * elapsed_days
                weighted_amount += applied
                contributing_applications += 1
                if invoice.document in eligible_documents and elapsed_days <= 30:
                    collected_within_30_days += applied
                remaining -= applied

        ratio_30_days = collected_within_30_days / eligible_billed if eligible_billed else ZERO
        average_days = weighted_days / weighted_amount if weighted_amount else None
        return {
            "collection_ratio_general": {
                "value": CollectionsService._metrics(invoices, as_of)["collection_ratio"],
                "unit": "ratio",
                "definition": "Pagos vinculados observados al corte divididos entre facturación.",
            },
            "collection_ratio_30_days": {
                "value": float(ratio_30_days.quantize(RATIO_PRECISION)),
                "unit": "ratio",
                "definition": (
                    "Pagos aplicados entre la emisión y el día 30 inclusive, divididos entre "
                    "facturación con una ventana completa de 30 días al corte."
                ),
                "eligible_invoice_count": len(eligible),
                "eligible_billed_amount": eligible_billed,
                "collected_within_30_days_amount": collected_within_30_days,
            },
            "average_collection_period": {
                "value": (
                    float(average_days.quantize(DAY_PRECISION))
                    if average_days is not None
                    else None
                ),
                "unit": "days",
                "definition": (
                    "Promedio de días desde emisión hasta pago, ponderado por importe aplicado "
                    "y limitado al importe de cada factura."
                ),
                "payment_application_count": contributing_applications,
                "linked_payment_amount": weighted_amount,
                "excluded_temporal_application_count": excluded_temporal_applications,
            },
        }

    def portfolio_snapshot(self, as_of_date: str | None = None) -> dict[str, Any]:
        as_of = self._as_of(as_of_date)
        invoices = list(self.ledger.invoices.values())
        metrics = self._metrics(invoices, as_of)
        kpis = self._kpis(invoices, as_of)
        currency_status = self._currency_status(invoices)
        unspecified_currency_count = sum(
            not (invoice.currency or "").strip() for invoice in invoices
        )
        metrics["collection_ratio_30_days"] = kpis["collection_ratio_30_days"]["value"]
        metrics["average_collection_period_days"] = kpis["average_collection_period"]["value"]
        metrics["unmatched_payment_amount"] = sum(
            (
                payment.amount
                for payment in self.ledger.unmatched_payments
                if payment.paid_at is not None and payment.paid_at <= as_of
            ),
            Decimal(),
        )
        metrics["unmatched_payment_count"] = sum(
            payment.paid_at is not None and payment.paid_at <= as_of
            for payment in self.ledger.unmatched_payments
        )
        response = AgentResponse(
            operation="portfolio_snapshot",
            as_of_date=as_of,
            status=currency_status,
            metrics=metrics,
            kpis=kpis,
            aging=self._aging(invoices, as_of),
            findings=(
                [
                    {
                        "type": "UNMATCHED_PAYMENT_CUTOFF",
                        "severity": "MEDIUM",
                        "message": (
                            "Pagos que apuntan a documentos no presentes en el corte de facturas."
                        ),
                        "count": metrics["unmatched_payment_count"],
                        "amount": metrics["unmatched_payment_amount"],
                    }
                ]
                if metrics["unmatched_payment_count"]
                else []
            ),
            recommended_actions=[
                {
                    "action": "review_collection_priorities",
                    "reason": "Enfocar gestores en saldo vencido y antigüedad.",
                },
                {
                    "action": "review_unmatched_payments",
                    "reason": "Confirmar si las facturas faltantes pertenecen a otro corte.",
                },
            ],
            data_quality={
                "source_counts": self.ledger.source_counts,
                "relationship_checks": {
                    "unmatched_payment_count": metrics["unmatched_payment_count"],
                    "mismatched_payment_count": len(self.ledger.mismatched_payments),
                    "unmatched_credit_note_count": len(self.ledger.unmatched_credit_notes),
                    "unspecified_invoice_currency_count": unspecified_currency_count,
                },
                "known_limitations": [
                    "El dataset no contiene extractos bancarios ni comunicaciones.",
                    "El RUC está anonimizado de forma inconsistente; los joins de cliente usan RAZON_SOCIAL.",
                    "Los KPIs de plazo excluyen pagos anteriores a la emisión.",
                    *(
                        [
                            "Existen facturas sin moneda declarada; la moneda informada refleja las monedas explícitas observadas y esta limitación acompaña los KPIs."
                        ]
                        if unspecified_currency_count
                        else []
                    ),
                ],
            },
            visualization_hints=[
                {
                    "type": "kpi_cards",
                    "fields": [
                        "total_billed",
                        "total_paid_linked",
                        "outstanding_balance",
                        "overdue_balance",
                        "collection_ratio",
                        "collection_ratio_30_days",
                        "average_collection_period_days",
                    ],
                },
                {"type": "aging_bar", "source": "aging"},
            ],
        )
        return response.to_dict()

    def customer_snapshot(self, customer_id: str, as_of_date: str | None = None) -> dict[str, Any]:
        as_of = self._as_of(as_of_date)
        customer = customer_id.strip().upper()
        invoices = [
            invoice
            for invoice in self.ledger.invoices.values()
            if invoice.customer.upper() == customer
        ]
        if not invoices:
            raise KeyError(f"Cliente no encontrado: {customer_id}")
        metrics = self._metrics(invoices, as_of)
        kpis = self._kpis(invoices, as_of)
        metrics["collection_ratio_30_days"] = kpis["collection_ratio_30_days"]["value"]
        metrics["average_collection_period_days"] = kpis["average_collection_period"]["value"]
        priority = self._priority_rows(as_of)
        priority_row = next(
            (row for row in priority if row["customer"] == invoices[0].customer),
            cast(
                PriorityRow,
                {
                    "customer": invoices[0].customer,
                    "outstanding_balance": ZERO,
                    "overdue_balance": ZERO,
                    "max_days_past_due": 0,
                    "overdue_share": ZERO,
                    "partial_payment_invoice_count": 0,
                    "score_components": {},
                    "priority_score": ZERO,
                    "priority": "LOW",
                },
            ),
        )
        overdue = [
            invoice
            for invoice in invoices
            if invoice.open_balance_as_of(as_of) > TOLERANCE
            and invoice.due_at
            and invoice.due_at < as_of
        ]
        response = AgentResponse(
            operation="customer_snapshot",
            as_of_date=as_of,
            entity={"type": "customer", "id": invoices[0].customer},
            status={
                "priority": priority_row["priority"],
                "collection_state": "VENCIDA" if overdue else "AL_DIA",
            },
            metrics={**metrics, "priority_score": priority_row["priority_score"]},
            kpis=kpis,
            aging=self._aging(invoices, as_of),
            findings=[
                {
                    "type": "OVERDUE_EXPOSURE",
                    "severity": priority_row["priority"],
                    "message": "Saldo vencido priorizado con reglas reproducibles.",
                    "amount": metrics["overdue_balance"],
                }
            ],
            recommended_actions=[
                {
                    "action": "prioritize_internal_management",
                    "reason": "Existe saldo vencido o pago parcial para análisis operativo.",
                    "priority": priority_row["priority"],
                }
            ]
            if overdue
            else [{"action": "monitor", "reason": "No hay saldo vencido al corte."}],
            evidence=[
                self._invoice_evidence(invoice, as_of)
                for invoice in sorted(
                    invoices,
                    key=lambda item: item.open_balance_as_of(as_of),
                    reverse=True,
                )
            ],
            visualization_hints=[
                {"type": "customer_kpis", "source": "metrics"},
                {"type": "invoice_table", "source": "evidence"},
            ],
        )
        return response.to_dict()

    def invoice_trace(self, document: str, as_of_date: str | None = None) -> dict[str, Any]:
        as_of = self._as_of(as_of_date)
        invoice = self.ledger.invoices.get(document.strip())
        if not invoice:
            raise KeyError(f"Factura no encontrada: {document}")
        evidence = self._invoice_evidence(invoice, as_of)
        evidence["payments"] = [
            {
                "amount": payment.amount,
                "paid_at": payment.paid_at,
                "account_code": payment.account_code,
            }
            for payment in sorted(
                invoice.payments_as_of(as_of), key=lambda item: item.paid_at or date.max
            )
        ]
        evidence["credit_note_documents"] = [
            {"document": note.document, "amount": note.amount, "issued_at": note.issued_at}
            for note in sorted(
                invoice.credits_as_of(as_of), key=lambda item: item.issued_at or date.max
            )
        ]
        invoice_cases = [
            item
            for item in self._reconciliation_exception_rows(as_of)
            if item.get("document") == invoice.document
        ]
        evidence["reconciliation_case_ids"] = [item["case_id"] for item in invoice_cases]
        evidence["reconciliation_case_count"] = len(invoice_cases)
        state = invoice.reconciliation_state(as_of)
        response = AgentResponse(
            operation="invoice_trace",
            as_of_date=as_of,
            entity={"type": "invoice", "id": invoice.document},
            status={
                "settlement": invoice.settlement_state(as_of),
                "delinquency": invoice.delinquency_state(as_of),
                "reconciliation": state,
            },
            metrics={
                key: evidence[key]
                for key in (
                    "invoice_total",
                    "credit_notes",
                    "paid",
                    "outstanding_balance",
                    "days_past_due",
                )
            },
            reconciliation={
                "state": state,
                "payment_count": len(invoice.payments),
                "credit_note_count": len(invoice.credits),
                "case_ids": [item["case_id"] for item in invoice_cases],
            },
            findings=self._invoice_findings(invoice, as_of),
            recommended_actions=self._invoice_actions(invoice, as_of),
            evidence=[evidence],
            visualization_hints=[{"type": "payment_timeline", "source": "evidence[0].payments"}],
        )
        return response.to_dict()

    def _invoice_findings(self, invoice: InvoiceLedger, as_of: date) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        raw_balance = invoice.raw_balance_as_of(as_of)
        open_balance = invoice.open_balance_as_of(as_of)
        if raw_balance < -TOLERANCE:
            findings.append(
                {
                    "type": "OVERAPPLICATION",
                    "severity": "HIGH",
                    "message": "Pagos y créditos exceden la obligación neta.",
                    "amount": -raw_balance,
                }
            )
        if open_balance > TOLERANCE:
            findings.append(
                {
                    "type": "OPEN_BALANCE",
                    "severity": invoice.delinquency_state(as_of),
                    "message": "La factura mantiene saldo abierto.",
                    "amount": open_balance,
                }
            )
        if invoice.issued_at and any(
            payment.paid_at and payment.paid_at < invoice.issued_at
            for payment in invoice.payments_as_of(as_of)
        ):
            findings.append(
                {
                    "type": "TEMPORAL_ANOMALY",
                    "severity": "MEDIUM",
                    "message": "Hay pago fechado antes de la emisión; validar el corte o aplicación.",
                }
            )
        return findings or [
            {
                "type": "DOCUMENT_SETTLED",
                "severity": "INFO",
                "message": "No se detectaron excepciones documentales.",
            }
        ]

    def _invoice_actions(self, invoice: InvoiceLedger, as_of: date) -> list[dict[str, Any]]:
        raw_balance = invoice.raw_balance_as_of(as_of)
        open_balance = invoice.open_balance_as_of(as_of)
        if raw_balance < -TOLERANCE:
            return [
                {
                    "action": "review_overapplication",
                    "reason": "El saldo a favor requiere validar aplicación, devolución o compensación.",
                }
            ]
        if open_balance > TOLERANCE and invoice.due_at and invoice.due_at < as_of:
            return [{"action": "start_collection", "reason": "Saldo vencido documentado."}]
        if open_balance > TOLERANCE:
            return [{"action": "monitor_due_date", "reason": "Factura pendiente aún no vencida."}]
        return [{"action": "close_case", "reason": "Documento liquidado dentro de la tolerancia."}]

    def _priority_rows(self, as_of: date) -> list[PriorityRow]:
        rows: list[PriorityRow] = []
        for customer, invoices in by_customer(self.ledger.invoices.values()).items():
            open_invoices = [
                invoice for invoice in invoices if invoice.open_balance_as_of(as_of) > TOLERANCE
            ]
            if not open_invoices:
                continue
            outstanding = sum(
                (invoice.open_balance_as_of(as_of) for invoice in open_invoices), Decimal()
            )
            overdue = sum(
                (
                    invoice.open_balance_as_of(as_of)
                    for invoice in open_invoices
                    if invoice.due_at and invoice.due_at < as_of
                ),
                Decimal(),
            )
            max_dpd = max(
                (invoice.days_past_due(as_of) or 0 for invoice in open_invoices), default=0
            )
            rows.append(
                {
                    "customer": customer,
                    "outstanding_balance": outstanding,
                    "overdue_balance": overdue,
                    "max_days_past_due": max_dpd,
                    "overdue_share": overdue / outstanding if outstanding else Decimal(),
                    "partial_payment_invoice_count": sum(
                        invoice.settlement_state(as_of) == "PAGO_PARCIAL"
                        for invoice in open_invoices
                    ),
                }
            )
        # A portfolio with no overdue balance still scores; the divisor must never be zero.
        max_overdue = max((row["overdue_balance"] for row in rows), default=Decimal(1)) or Decimal(1)
        max_outstanding = (
            max((row["outstanding_balance"] for row in rows), default=Decimal(1)) or Decimal(1)
        )
        for row in rows:
            # Transparent score; weights and thresholds are centralized in rules.py.
            row["score_components"] = {
                "overdue_amount": min(
                    PRIORITY_WEIGHTS["overdue_amount"],
                    PRIORITY_WEIGHTS["overdue_amount"] * row["overdue_balance"] / max_overdue,
                ),
                "days_past_due": min(
                    PRIORITY_WEIGHTS["days_past_due"],
                    PRIORITY_WEIGHTS["days_past_due"]
                    * Decimal(row["max_days_past_due"])
                    / PRIORITY_DPD_CAP,
                ),
                "overdue_share": PRIORITY_WEIGHTS["overdue_share"] * row["overdue_share"],
                "portfolio_concentration": PRIORITY_WEIGHTS["portfolio_concentration"]
                * row["outstanding_balance"]
                / max_outstanding,
            }
            row["priority_score"] = sum(row["score_components"].values(), Decimal()).quantize(
                Decimal("0.1")
            )
            row["priority"] = priority_level(row["priority_score"])
        return sorted(rows, key=lambda row: row["priority_score"], reverse=True)

    def collection_priorities(
        self, limit: int = 20, as_of_date: str | None = None
    ) -> dict[str, Any]:
        as_of = self._as_of(as_of_date)
        rows = self._priority_rows(as_of)[:limit]
        evidence_rows: list[dict[str, Any]] = [dict(row) for row in rows]
        response = AgentResponse(
            operation="collection_priorities",
            as_of_date=as_of,
            status={"priority_model": "DETERMINISTIC_V1"},
            metrics={"customers_ranked": len(self._priority_rows(as_of)), "returned": len(rows)},
            findings=[
                {
                    "type": "SCORING_RULE",
                    "severity": "INFO",
                    "message": (
                        "Score = monto vencido "
                        f"({PRIORITY_WEIGHTS['overdue_amount']}) + atraso "
                        f"({PRIORITY_WEIGHTS['days_past_due']}) + porcentaje vencido "
                        f"({PRIORITY_WEIGHTS['overdue_share']}) + concentración "
                        f"({PRIORITY_WEIGHTS['portfolio_concentration']})."
                    ),
                }
            ],
            recommended_actions=[
                {
                    "action": "assign_collection_queue",
                    "reason": "Atender primero prioridades HIGH y documentar resultados de gestión.",
                }
            ],
            evidence=evidence_rows,
            visualization_hints=[
                {"type": "priority_ranking", "source": "evidence", "sort": "priority_score_desc"}
            ],
        )
        return response.to_dict()

    def reconciliation_exceptions(
        self, limit: int = 20, as_of_date: str | None = None
    ) -> dict[str, Any]:
        as_of = self._as_of(as_of_date)
        exceptions = self._reconciliation_exception_rows(as_of)
        payments_analyzed = sum(
            len(invoice.payments_as_of(as_of)) for invoice in self.ledger.invoices.values()
        )
        partial_invoices = sum(
            invoice.settlement_state(as_of) == "PAGO_PARCIAL"
            for invoice in self.ledger.invoices.values()
        )
        response = AgentResponse(
            operation="reconciliation_exceptions",
            as_of_date=as_of,
            status={"reconciliation": "REQUIERE_REVISION" if exceptions else "CONCILIADA"},
            metrics={
                "payment_applications_analyzed": payments_analyzed,
                "partial_payment_invoice_count": partial_invoices,
                "exception_count": len(exceptions),
                "high_priority_exception_count": sum(
                    item["severity"] == "HIGH" for item in exceptions
                ),
                "returned": min(limit, len(exceptions)),
            },
            alerts=[
                {"type": item["type"], "severity": item["severity"]}
                for item in exceptions[:limit]
            ],
            recommended_actions=[
                {
                    "action": "review_exceptions",
                    "reason": (
                        "Las excepciones no son automáticamente errores; requieren validar "
                        "la fuente o el corte."
                    ),
                }
            ],
            evidence=exceptions[:limit],
            visualization_hints=[{"type": "exception_table", "source": "evidence"}],
        )
        return response.to_dict()

    @staticmethod
    def _case_id(*parts: object) -> str:
        identity = "|".join(str(part or "") for part in parts)
        return f"COL-{sha256(identity.encode()).hexdigest()[:12].upper()}"

    def _reconciliation_exception_rows(self, as_of: date) -> list[dict[str, Any]]:
        """Build traceable documentary cases once for the API, invoice view and UI."""
        exceptions: list[dict[str, Any]] = []
        for payment in self.ledger.unmatched_payments:
            if payment.paid_at is None or payment.paid_at > as_of:
                continue
            exceptions.append(
                {
                    "case_id": self._case_id(
                        "PAYMENT_OUTSIDE_INVOICE_CUTOFF",
                        payment.document,
                        payment.customer,
                        payment.paid_at,
                        payment.amount,
                    ),
                    "type": "PAYMENT_OUTSIDE_INVOICE_CUTOFF",
                    "severity": "MEDIUM",
                    "document": payment.document,
                    "customer": payment.customer,
                    "amount": payment.amount,
                    "paid_at": payment.paid_at,
                    "account_code": payment.account_code,
                    "invoice_available": False,
                    "customer_available": any(
                        invoice.customer == payment.customer
                        for invoice in self.ledger.invoices.values()
                    ),
                    "payment": {
                        "amount": payment.amount,
                        "paid_at": payment.paid_at,
                        "account_code": payment.account_code,
                    },
                    "reason": "La factura referenciada no está presente en el corte publicado.",
                    "evidence": "Relación FACTURA_AFECTADA sin documento fiscal en el ledger.",
                    "operational_state": "PENDIENTE_VALIDACION",
                    "recommended_action": "Confirmar si la factura pertenece a otro corte o sistema.",
                }
            )
        for payment in self.ledger.mismatched_payments:
            if payment.paid_at is None or payment.paid_at > as_of:
                continue
            invoice = self.ledger.invoices.get(payment.document)
            exceptions.append(
                {
                    "case_id": self._case_id(
                        "PAYMENT_LINK_MISMATCH",
                        payment.document,
                        payment.customer,
                        payment.paid_at,
                        payment.amount,
                    ),
                    "type": "PAYMENT_LINK_MISMATCH",
                    "severity": "HIGH",
                    "document": payment.document,
                    "customer": payment.customer,
                    "amount": payment.amount,
                    "paid_at": payment.paid_at,
                    "account_code": payment.account_code,
                    "invoice_available": invoice is not None,
                    "customer_available": any(
                        item.customer == payment.customer
                        for item in self.ledger.invoices.values()
                    ),
                    "payment": {
                        "amount": payment.amount,
                        "paid_at": payment.paid_at,
                        "account_code": payment.account_code,
                    },
                    "expected_customer": invoice.customer if invoice else None,
                    "expected_account_code": invoice.account_code if invoice else None,
                    "outstanding_balance": (
                        invoice.open_balance_as_of(as_of) if invoice else None
                    ),
                    "reason": "Cliente o cuenta del pago no coincide con la factura referenciada.",
                    "evidence": "Comparación documental cliente-cuenta-factura.",
                    "operational_state": "PENDIENTE_VALIDACION",
                    "recommended_action": (
                        "Validar que cliente, cuenta y factura correspondan antes de aplicar el pago."
                    ),
                }
            )
        for credit in self.ledger.unmatched_credit_notes:
            if credit.issued_at is None or credit.issued_at > as_of:
                continue
            exceptions.append(
                {
                    "case_id": self._case_id(
                        "CREDIT_NOTE_OUTSIDE_INVOICE_CUTOFF",
                        credit.document,
                        credit.affected_document,
                        credit.issued_at,
                        credit.amount,
                    ),
                    "type": "CREDIT_NOTE_OUTSIDE_INVOICE_CUTOFF",
                    "severity": "MEDIUM",
                    "document": credit.affected_document,
                    "credit_note_document": credit.document,
                    "amount": credit.amount,
                    "issued_at": credit.issued_at,
                    "credit_note": {
                        "document": credit.document,
                        "amount": credit.amount,
                        "issued_at": credit.issued_at,
                    },
                    "invoice_available": False,
                    "customer_available": False,
                    "reason": "La factura afectada no está presente en el corte publicado.",
                    "evidence": "Relación de nota de crédito sin factura en el ledger.",
                    "operational_state": "PENDIENTE_VALIDACION",
                    "recommended_action": (
                        "Confirmar si la factura afectada pertenece a otro corte o sistema."
                    ),
                }
            )
        for invoice in self.ledger.invoices.values():
            raw_balance = invoice.raw_balance_as_of(as_of)
            if raw_balance < -TOLERANCE:
                exceptions.append(
                    {
                        "case_id": self._case_id(
                            "OVERAPPLICATION", invoice.document, as_of, -raw_balance
                        ),
                        "type": "OVERAPPLICATION",
                        "severity": "HIGH",
                        "document": invoice.document,
                        "customer": invoice.customer,
                        "amount": -raw_balance,
                        "account_code": invoice.account_code,
                        "invoice_available": True,
                        "customer_available": True,
                        "outstanding_balance": invoice.open_balance_as_of(as_of),
                        "payment": (
                            {
                                "amount": invoice.payments_as_of(as_of)[-1].amount,
                                "paid_at": invoice.payments_as_of(as_of)[-1].paid_at,
                                "account_code": invoice.account_code,
                            }
                            if invoice.payments_as_of(as_of)
                            else None
                        ),
                        "credit_notes": [
                            {
                                "document": note.document,
                                "amount": note.amount,
                                "issued_at": note.issued_at,
                            }
                            for note in invoice.credits_as_of(as_of)
                        ],
                        "reason": "Pagos y notas de crédito exceden la obligación neta.",
                        "evidence": "Saldo documental bruto menor que la tolerancia permitida.",
                        "operational_state": "PENDIENTE_VALIDACION",
                        "recommended_action": "Validar aplicación de pago y nota de crédito.",
                    }
                )
            temporal_payments = [
                payment
                for payment in invoice.payments_as_of(as_of)
                if invoice.issued_at and payment.paid_at and payment.paid_at < invoice.issued_at
            ]
            for payment in temporal_payments:
                exceptions.append(
                    {
                        "case_id": self._case_id(
                            "PAYMENT_BEFORE_ISSUANCE",
                            invoice.document,
                            payment.paid_at,
                            payment.amount,
                        ),
                        "type": "PAYMENT_BEFORE_ISSUANCE",
                        "severity": "MEDIUM",
                        "document": invoice.document,
                        "customer": invoice.customer,
                        "amount": payment.amount,
                        "paid_at": payment.paid_at,
                        "account_code": invoice.account_code,
                        "invoice_available": True,
                        "customer_available": True,
                        "outstanding_balance": invoice.open_balance_as_of(as_of),
                        "payment": {
                            "amount": payment.amount,
                            "paid_at": payment.paid_at,
                            "account_code": payment.account_code,
                        },
                        "reason": "La fecha del pago es anterior a la emisión de la factura.",
                        "evidence": "Comparación determinística FECHA_PAGO < FECHA_EMISION.",
                        "operational_state": "PENDIENTE_VALIDACION",
                        "recommended_action": "Validar fecha de pago, emisión o carga histórica.",
                    }
                )
        exceptions.sort(
            key=lambda item: (
                EXCEPTION_SEVERITY_ORDER.get(str(item["severity"]), 99),
                -(item.get("amount") or Decimal()),
            )
        )
        return exceptions
