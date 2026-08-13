"""Tool service: compact, deterministic results for a UI, Supervisor, or GPT-5.6."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

from .contracts import AgentResponse
from .data import load_dataset
from .ledger import Ledger, InvoiceLedger, TOLERANCE, aging_bucket, build_ledger, by_customer


class CollectionsService:
    def __init__(self, dataset_path: Path):
        self.ledger: Ledger = build_ledger(load_dataset(dataset_path))

    def _as_of(self, value: str | None) -> date:
        return date.fromisoformat(value) if value else self.ledger.latest_event_date

    @staticmethod
    def _aging(invoices: list[InvoiceLedger], as_of: date) -> list[dict]:
        totals: dict[str, Decimal] = defaultdict(Decimal)
        docs: Counter[str] = Counter()
        for invoice in invoices:
            if invoice.open_balance <= TOLERANCE:
                continue
            bucket = aging_bucket(invoice.days_past_due(as_of))
            totals[bucket] += invoice.open_balance
            docs[bucket] += 1
        order = ["NO_VENCIDA", "1_30", "31_60", "61_90", "90_PLUS", "SIN_FECHA_VENCIMIENTO"]
        return [{"bucket": bucket, "documents": docs[bucket], "outstanding_balance": totals[bucket]} for bucket in order if docs[bucket]]

    @staticmethod
    def _invoice_evidence(invoice: InvoiceLedger, as_of: date) -> dict:
        return {
            "document": invoice.document,
            "customer": invoice.customer,
            "account_code": invoice.account_code,
            "issued_at": invoice.issued_at,
            "due_at": invoice.due_at,
            "days_past_due": invoice.days_past_due(as_of),
            "invoice_total": invoice.total,
            "credit_notes": invoice.credited,
            "paid": invoice.paid,
            "outstanding_balance": invoice.open_balance,
            "settlement_state": invoice.settlement_state(),
            "delinquency_state": invoice.delinquency_state(as_of),
            "reconciliation_state": invoice.reconciliation_state(),
        }

    @staticmethod
    def _metrics(invoices: list[InvoiceLedger], as_of: date) -> dict:
        total_billed = sum((invoice.total for invoice in invoices), Decimal())
        total_paid = sum((invoice.paid for invoice in invoices), Decimal())
        outstanding = sum((invoice.open_balance for invoice in invoices), Decimal())
        overdue = sum(
            (invoice.open_balance for invoice in invoices if invoice.due_at and invoice.due_at < as_of),
            Decimal(),
        )
        return {
            "total_billed": total_billed,
            "total_paid_linked": total_paid,
            "credit_notes_linked": sum((invoice.credited for invoice in invoices), Decimal()),
            "outstanding_balance": outstanding,
            "overdue_balance": overdue,
            "collection_ratio": (total_paid / total_billed) if total_billed else Decimal(),
            "invoice_count": len(invoices),
            "open_invoice_count": sum(invoice.open_balance > TOLERANCE for invoice in invoices),
        }

    def portfolio_snapshot(self, as_of_date: str | None = None) -> dict:
        as_of = self._as_of(as_of_date)
        invoices = list(self.ledger.invoices.values())
        metrics = self._metrics(invoices, as_of)
        metrics["unmatched_payment_amount"] = sum((payment.amount for payment in self.ledger.unmatched_payments), Decimal())
        metrics["unmatched_payment_count"] = len(self.ledger.unmatched_payments)
        response = AgentResponse(
            operation="portfolio_snapshot",
            as_of_date=as_of,
            metrics=metrics,
            aging=self._aging(invoices, as_of),
            findings=[
                {
                    "type": "UNMATCHED_PAYMENT_CUTOFF",
                    "severity": "MEDIUM",
                    "message": "Pagos que apuntan a documentos no presentes en el corte de facturas.",
                    "count": len(self.ledger.unmatched_payments),
                    "amount": metrics["unmatched_payment_amount"],
                }
            ],
            recommended_actions=[
                {"action": "review_collection_priorities", "reason": "Enfocar gestores en saldo vencido y antigüedad."},
                {"action": "review_unmatched_payments", "reason": "Confirmar si las facturas faltantes pertenecen a otro corte."},
            ],
            data_quality={
                "source_counts": self.ledger.source_counts,
                "known_limitations": [
                    "El dataset no contiene extractos bancarios ni comunicaciones.",
                    "El RUC está anonimizado de forma inconsistente; los joins de cliente usan RAZON_SOCIAL.",
                ],
            },
            visualization_hints=[
                {"type": "kpi_cards", "fields": ["total_billed", "total_paid_linked", "outstanding_balance", "overdue_balance", "collection_ratio"]},
                {"type": "aging_bar", "source": "aging"},
            ],
        )
        return response.to_dict()

    def customer_snapshot(self, customer_id: str, as_of_date: str | None = None) -> dict:
        as_of = self._as_of(as_of_date)
        customer = customer_id.strip().upper()
        invoices = [invoice for invoice in self.ledger.invoices.values() if invoice.customer.upper() == customer]
        if not invoices:
            raise KeyError(f"Cliente no encontrado: {customer_id}")
        metrics = self._metrics(invoices, as_of)
        priority = self._priority_rows(as_of)
        priority_row = next(row for row in priority if row["customer"] == invoices[0].customer)
        overdue = [invoice for invoice in invoices if invoice.open_balance > TOLERANCE and invoice.due_at and invoice.due_at < as_of]
        response = AgentResponse(
            operation="customer_snapshot",
            as_of_date=as_of,
            entity={"type": "customer", "id": invoices[0].customer},
            status={"priority": priority_row["priority"], "collection_state": "VENCIDA" if overdue else "AL_DIA"},
            metrics={**metrics, "priority_score": priority_row["priority_score"]},
            aging=self._aging(invoices, as_of),
            findings=[
                {"type": "OVERDUE_EXPOSURE", "severity": priority_row["priority"], "message": "Saldo vencido priorizado con reglas reproducibles.", "amount": metrics["overdue_balance"]}
            ],
            recommended_actions=[
                {"action": "contact_customer", "reason": "Existe saldo vencido o pago parcial.", "priority": priority_row["priority"]}
            ] if overdue else [{"action": "monitor", "reason": "No hay saldo vencido al corte."}],
            evidence=[self._invoice_evidence(invoice, as_of) for invoice in sorted(invoices, key=lambda item: item.open_balance, reverse=True)[:20]],
            visualization_hints=[{"type": "customer_kpis", "source": "metrics"}, {"type": "invoice_table", "source": "evidence"}],
        )
        return response.to_dict()

    def invoice_trace(self, document: str, as_of_date: str | None = None) -> dict:
        as_of = self._as_of(as_of_date)
        invoice = self.ledger.invoices.get(document.strip())
        if not invoice:
            raise KeyError(f"Factura no encontrada: {document}")
        evidence = self._invoice_evidence(invoice, as_of)
        evidence["payments"] = [{"amount": payment.amount, "paid_at": payment.paid_at, "account_code": payment.account_code} for payment in invoice.payments]
        evidence["credit_note_documents"] = [{"document": note.document, "amount": note.amount, "issued_at": note.issued_at} for note in invoice.credits]
        state = invoice.reconciliation_state()
        response = AgentResponse(
            operation="invoice_trace",
            as_of_date=as_of,
            entity={"type": "invoice", "id": invoice.document},
            status={"settlement": invoice.settlement_state(), "delinquency": invoice.delinquency_state(as_of), "reconciliation": state},
            metrics={key: evidence[key] for key in ("invoice_total", "credit_notes", "paid", "outstanding_balance", "days_past_due")},
            reconciliation={"state": state, "payment_count": len(invoice.payments), "credit_note_count": len(invoice.credits)},
            findings=self._invoice_findings(invoice, as_of),
            recommended_actions=self._invoice_actions(invoice, as_of),
            evidence=[evidence],
            visualization_hints=[{"type": "payment_timeline", "source": "evidence[0].payments"}],
        )
        return response.to_dict()

    def _invoice_findings(self, invoice: InvoiceLedger, as_of: date) -> list[dict]:
        findings: list[dict] = []
        if invoice.raw_balance < -TOLERANCE:
            findings.append({"type": "OVERAPPLICATION", "severity": "HIGH", "message": "Pagos y créditos exceden la obligación neta.", "amount": -invoice.raw_balance})
        if invoice.open_balance > TOLERANCE:
            findings.append({"type": "OPEN_BALANCE", "severity": invoice.delinquency_state(as_of), "message": "La factura mantiene saldo abierto.", "amount": invoice.open_balance})
        if invoice.issued_at and any(payment.paid_at and payment.paid_at < invoice.issued_at for payment in invoice.payments):
            findings.append({"type": "TEMPORAL_ANOMALY", "severity": "MEDIUM", "message": "Hay pago fechado antes de la emisión; validar el corte o aplicación."})
        return findings or [{"type": "DOCUMENT_SETTLED", "severity": "INFO", "message": "No se detectaron excepciones documentales."}]

    def _invoice_actions(self, invoice: InvoiceLedger, as_of: date) -> list[dict]:
        if invoice.raw_balance < -TOLERANCE:
            return [{"action": "review_overapplication", "reason": "El saldo a favor requiere validar aplicación, devolución o compensación."}]
        if invoice.open_balance > TOLERANCE and invoice.due_at and invoice.due_at < as_of:
            return [{"action": "start_collection", "reason": "Saldo vencido documentado."}]
        if invoice.open_balance > TOLERANCE:
            return [{"action": "monitor_due_date", "reason": "Factura pendiente aún no vencida."}]
        return [{"action": "close_case", "reason": "Documento liquidado dentro de la tolerancia."}]

    def _priority_rows(self, as_of: date) -> list[dict]:
        rows = []
        for customer, invoices in by_customer(self.ledger.invoices.values()).items():
            open_invoices = [invoice for invoice in invoices if invoice.open_balance > TOLERANCE]
            if not open_invoices:
                continue
            outstanding = sum((invoice.open_balance for invoice in open_invoices), Decimal())
            overdue = sum((invoice.open_balance for invoice in open_invoices if invoice.due_at and invoice.due_at < as_of), Decimal())
            max_dpd = max((invoice.days_past_due(as_of) or 0 for invoice in open_invoices), default=0)
            rows.append({"customer": customer, "outstanding_balance": outstanding, "overdue_balance": overdue, "max_days_past_due": max_dpd, "overdue_share": overdue / outstanding if outstanding else Decimal()})
        max_overdue = max((row["overdue_balance"] for row in rows), default=Decimal(1))
        max_outstanding = max((row["outstanding_balance"] for row in rows), default=Decimal(1))
        for row in rows:
            # Transparent score: 45 amount, 30 age, 15 overdue concentration, 10 total concentration.
            row["score_components"] = {
                "overdue_amount": min(Decimal(45), Decimal(45) * row["overdue_balance"] / max_overdue),
                "days_past_due": min(Decimal(30), Decimal(30) * Decimal(row["max_days_past_due"]) / Decimal(90)),
                "overdue_share": Decimal(15) * row["overdue_share"],
                "portfolio_concentration": Decimal(10) * row["outstanding_balance"] / max_outstanding,
            }
            row["priority_score"] = sum(row["score_components"].values(), Decimal()).quantize(Decimal("0.1"))
            row["priority"] = "HIGH" if row["priority_score"] >= Decimal(60) else "MEDIUM" if row["priority_score"] >= Decimal(30) else "LOW"
        return sorted(rows, key=lambda row: row["priority_score"], reverse=True)

    def collection_priorities(self, limit: int = 20, as_of_date: str | None = None) -> dict:
        as_of = self._as_of(as_of_date)
        rows = self._priority_rows(as_of)[:limit]
        response = AgentResponse(
            operation="collection_priorities",
            as_of_date=as_of,
            status={"priority_model": "DETERMINISTIC_V1"},
            metrics={"customers_ranked": len(self._priority_rows(as_of)), "returned": len(rows)},
            findings=[{"type": "SCORING_RULE", "severity": "INFO", "message": "Score = monto vencido (45) + atraso (30) + porcentaje vencido (15) + concentración (10)."}],
            recommended_actions=[{"action": "assign_collection_queue", "reason": "Atender primero prioridades HIGH y documentar resultados de gestión."}],
            evidence=rows,
            visualization_hints=[{"type": "priority_ranking", "source": "evidence", "sort": "priority_score_desc"}],
        )
        return response.to_dict()

    def reconciliation_exceptions(self, limit: int = 20, as_of_date: str | None = None) -> dict:
        as_of = self._as_of(as_of_date)
        exceptions: list[dict] = []
        for payment in self.ledger.unmatched_payments:
            exceptions.append({"type": "PAYMENT_OUTSIDE_INVOICE_CUTOFF", "severity": "MEDIUM", "document": payment.document, "customer": payment.customer, "amount": payment.amount, "paid_at": payment.paid_at, "recommended_action": "Confirmar si la factura pertenece a otro corte o sistema."})
        for invoice in self.ledger.invoices.values():
            if invoice.raw_balance < -TOLERANCE:
                exceptions.append({"type": "OVERAPPLICATION", "severity": "HIGH", "document": invoice.document, "customer": invoice.customer, "amount": -invoice.raw_balance, "recommended_action": "Validar aplicación de pago y nota de crédito."})
            elif invoice.issued_at and any(payment.paid_at and payment.paid_at < invoice.issued_at for payment in invoice.payments):
                exceptions.append({"type": "PAYMENT_BEFORE_ISSUANCE", "severity": "MEDIUM", "document": invoice.document, "customer": invoice.customer, "recommended_action": "Validar fecha de pago, emisión o carga histórica."})
        severity_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        exceptions.sort(key=lambda item: (severity_order[item["severity"]], -(item.get("amount") or Decimal())))
        response = AgentResponse(
            operation="reconciliation_exceptions",
            as_of_date=as_of,
            status={"reconciliation": "REQUIERE_REVISION" if exceptions else "CONCILIADA"},
            metrics={"exception_count": len(exceptions), "returned": min(limit, len(exceptions))},
            alerts=[{"type": item["type"], "severity": item["severity"]} for item in exceptions[:limit]],
            recommended_actions=[{"action": "review_exceptions", "reason": "Las excepciones no son automáticamente errores; requieren validar la fuente o el corte."}],
            evidence=exceptions[:limit],
            visualization_hints=[{"type": "exception_table", "source": "evidence"}],
        )
        return response.to_dict()

