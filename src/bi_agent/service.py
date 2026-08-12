"""Deterministic BI tools. The LLM-facing layer is intentionally out of scope for v0.1."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

from .contracts import AgentResponse
from .data import load_dataset
from .model import PEN, TOLERANCE, CanonicalRevenueModel, SnapshotInvoice, aging_bucket, build_canonical_model

DEFAULT_AS_OF_DATE = "2026-07-31"
ALLOWED_DIMENSIONS = {"SEGMENTO_PAIS", "SUNAT_DEPARTAMENTO", "SISTEMA", "FUENTE", "SERVICE_PROFILE"}
ALLOWED_METRICS = {"overdue_balance", "outstanding_balance"}


class BIService:
    def __init__(self, dataset_path: Path):
        self.model: CanonicalRevenueModel = build_canonical_model(load_dataset(dataset_path))

    @staticmethod
    def _as_of(value: str | None) -> date:
        return date.fromisoformat(value or DEFAULT_AS_OF_DATE)

    def _dimensions(self, item: SnapshotInvoice) -> dict[str, str]:
        invoice = item.invoice
        customer = self.model.customer_master.get(invoice.customer, {})
        plant = self.model.plant_by_account.get(invoice.account_code)
        if not plant:
            service_profile = "NO_LINKED_PLANT"
        elif plant["fixed_records"] and plant["mobile_records"]:
            service_profile = "FIXED_AND_MOBILE"
        elif plant["fixed_records"]:
            service_profile = "FIXED_ONLY"
        else:
            service_profile = "MOBILE_ONLY"
        return {"SEGMENTO_PAIS": customer.get("SEGMENTO_PAIS", "UNMATCHED_CUSTOMER"), "SUNAT_DEPARTAMENTO": customer.get("SUNAT_DEPARTAMENTO", "UNMATCHED_CUSTOMER"), "SISTEMA": invoice.system or "MISSING", "FUENTE": invoice.source or "MISSING", "SERVICE_PROFILE": service_profile}

    @staticmethod
    def _metrics(rows: list[SnapshotInvoice], as_of: date) -> dict:
        billed = sum((row.invoice.total for row in rows), Decimal())
        paid = sum((row.paid for row in rows), Decimal())
        credits = sum((row.credited for row in rows), Decimal())
        outstanding = sum((row.balance for row in rows), Decimal())
        overdue = sum((row.balance for row in rows if row.invoice.due_at and row.invoice.due_at < as_of), Decimal())
        overdue_customers = {row.invoice.customer for row in rows if row.balance > TOLERANCE and row.invoice.due_at and row.invoice.due_at < as_of}
        return {"currency": PEN, "total_billed": billed, "total_paid_linked": paid, "credit_notes_linked": credits, "outstanding_balance": outstanding, "overdue_balance": overdue, "collection_ratio": paid / billed if billed else Decimal(), "invoice_count": len(rows), "open_invoice_count": sum(row.balance > TOLERANCE for row in rows), "customers_with_overdue_balance": len(overdue_customers)}

    @staticmethod
    def _aging(rows: list[SnapshotInvoice], as_of: date) -> list[dict]:
        amounts: dict[str, Decimal] = defaultdict(Decimal)
        documents: Counter[str] = Counter()
        for row in rows:
            if row.balance <= TOLERANCE:
                continue
            bucket = aging_bucket(row.days_past_due(as_of))
            amounts[bucket] += row.balance
            documents[bucket] += 1
        order = ["NO_VENCIDA", "1_30", "31_60", "61_90", "90_PLUS", "SIN_FECHA_VENCIMIENTO"]
        return [{"bucket": bucket, "documents": documents[bucket], "outstanding_balance": amounts[bucket]} for bucket in order if documents[bucket]]

    def _quality(self, as_of: date) -> dict:
        later = self.model.payments_after(as_of)
        limitations = [
            "RAZON_SOCIAL is the temporary canonical customer key; fiscal identifiers are not used for joins.",
            "No bank statements or customer communications are included, so this is not bank reconciliation.",
            "Amounts are analyzed only in PEN; USD and missing-currency items are excluded from monetary KPIs.",
        ]
        if later:
            limitations.append("Payments dated after as_of_date are excluded from balances and reported separately.")
        return {"source_counts": self.model.source_counts, "join_rules": {"customer": "RAZON_SOCIAL", "document": "NRO_DOC_FISCAL -> FACTURA_AFECTADA", "plant": "COD_CUENTA summarized before enrichment"}, "quality_checks": self.model.quality, "as_of_exclusions": {"payments_after_as_of_count": len(later), "payments_after_as_of_amount_pen": sum((item.amount for item in later if item.currency == PEN), Decimal()), "unmatched_payment_count": len(self.model.unmatched_payments), "unmatched_payment_amount_pen": sum((item.amount for item in self.model.unmatched_payments if item.currency == PEN), Decimal())}, "known_limitations": limitations}

    def data_quality_report(self, as_of_date: str | None = None) -> dict:
        as_of = self._as_of(as_of_date)
        quality = self._quality(as_of)
        evidence = [{"id": "dq_source_counts", "type": "source_counts", "value": self.model.source_counts}, {"id": "dq_join_rules", "type": "join_rules", "value": quality["join_rules"]}, {"id": "dq_as_of_exclusions", "type": "as_of_exclusions", "value": quality["as_of_exclusions"]}]
        return AgentResponse(operation="data_quality_report", as_of_date=as_of, status={"data_quality": "REVIEW_REQUIRED" if quality["as_of_exclusions"]["unmatched_payment_count"] else "OK"}, metrics={"source_table_count": len(self.model.source_counts), "invoice_rows": self.model.source_counts["invoices"], "unmatched_payment_count": quality["as_of_exclusions"]["unmatched_payment_count"], "payments_after_as_of_count": quality["as_of_exclusions"]["payments_after_as_of_count"]}, findings=[{"type": "DATA_QUALITY_SCOPE", "severity": "MEDIUM", "message": "Source coverage, joins, cut-off exclusions, and currency scope are explicit.", "evidence_refs": [item["id"] for item in evidence]}], evidence=evidence, data_quality=quality, analysis_scope={"currency": PEN, "as_of_date_applied": True}, methodology={"deterministic": True, "financial_calculations": "Python Decimal"}, upstream_inputs=[{"type": "csv_adapter", "status": "active"}]).to_dict()

    def executive_snapshot(self, as_of_date: str | None = None) -> dict:
        as_of = self._as_of(as_of_date)
        rows = self.model.snapshot(as_of)
        metrics = self._metrics(rows, as_of)
        evidence = [{"id": "kpi_portfolio", "type": "portfolio_metrics", "value": metrics}, {"id": "ageing_portfolio", "type": "aging", "value": self._aging(rows, as_of)}]
        findings = []
        if metrics["overdue_balance"] > TOLERANCE:
            findings.append({"type": "OVERDUE_EXPOSURE", "severity": "MEDIUM", "message": "There is documented overdue balance at the selected cut-off.", "amount": metrics["overdue_balance"], "evidence_refs": ["kpi_portfolio", "ageing_portfolio"]})
        if self.model.unmatched_payments:
            findings.append({"type": "UNMATCHED_PAYMENTS", "severity": "MEDIUM", "message": "Some payments reference invoices unavailable in the supplied invoice set.", "count": len(self.model.unmatched_payments), "evidence_refs": ["dq_as_of_exclusions"]})
            evidence.append({"id": "dq_as_of_exclusions", "type": "payment_application_scope", "value": self._quality(as_of)["as_of_exclusions"]})
        return AgentResponse(operation="executive_snapshot", as_of_date=as_of, metrics=metrics, aging=self._aging(rows, as_of), findings=findings, alerts=[{"type": finding["type"], "severity": finding["severity"], "evidence_refs": finding["evidence_refs"]} for finding in findings], recommended_actions=[{"action": "review_document_scope", "reason": "Validate unmatched payments before treating the linked-payment ratio as full cash collection.", "evidence_refs": ["dq_as_of_exclusions"]}] if self.model.unmatched_payments else [], evidence=evidence, data_quality=self._quality(as_of), visualization_hints=[{"type": "kpi_cards", "fields": ["total_billed", "total_paid_linked", "outstanding_balance", "overdue_balance", "collection_ratio"]}, {"type": "aging_bar", "source": "aging"}], analysis_scope={"currency": PEN, "invoice_issued_on_or_before": as_of, "applications_on_or_before": as_of}, methodology={"deterministic": True, "balance": "invoice_total - eligible_payments - eligible_credit_notes, floored at zero"}, upstream_inputs=[{"type": "csv_adapter", "status": "active"}]).to_dict()

    def risk_concentration(self, dimension: str = "SEGMENTO_PAIS", metric: str = "overdue_balance", top_n: int = 10, as_of_date: str | None = None) -> dict:
        as_of = self._as_of(as_of_date)
        dimension, metric = dimension.upper(), metric.lower()
        if dimension not in ALLOWED_DIMENSIONS:
            raise ValueError(f"dimension debe ser uno de: {', '.join(sorted(ALLOWED_DIMENSIONS))}")
        if metric not in ALLOWED_METRICS:
            raise ValueError(f"metric debe ser uno de: {', '.join(sorted(ALLOWED_METRICS))}")
        if not 1 <= top_n <= 100:
            raise ValueError("top_n debe estar entre 1 y 100")
        rows = self.model.snapshot(as_of)
        grouped: dict[str, dict] = defaultdict(lambda: {"amount": Decimal(), "customers": set(), "documents": 0})
        for row in rows:
            amount = row.balance if metric == "outstanding_balance" else (row.balance if row.invoice.due_at and row.invoice.due_at < as_of else Decimal())
            if amount <= Decimal():
                continue
            group = grouped[self._dimensions(row)[dimension]]
            group["amount"] += amount
            group["customers"].add(row.invoice.customer)
            group["documents"] += 1
        total = sum((item["amount"] for item in grouped.values()), Decimal())
        concentration = sorted(({"dimension": dimension, "value": key, metric: item["amount"], "share": item["amount"] / total if total else Decimal(), "customer_count": len(item["customers"]), "document_count": item["documents"]} for key, item in grouped.items()), key=lambda item: (-item[metric], item["value"]))
        cumulative = Decimal()
        for item in concentration:
            cumulative += item["share"]
            item["cumulative_share"] = cumulative
        customer_amounts: dict[str, Decimal] = defaultdict(Decimal)
        for row in rows:
            amount = row.balance if metric == "outstanding_balance" else (row.balance if row.invoice.due_at and row.invoice.due_at < as_of else Decimal())
            customer_amounts[row.invoice.customer] += amount
        top_customers = sorted(({"customer": key, metric: value, "share": value / total if total else Decimal()} for key, value in customer_amounts.items() if value > Decimal()), key=lambda item: (-item[metric], item["customer"]))[:top_n]
        evidence = [{"id": "concentration_by_dimension", "type": "grouped_metric", "dimension": dimension, "metric": metric, "value": concentration[:top_n]}, {"id": "top_customers", "type": "top_customers", "metric": metric, "value": top_customers}]
        findings = []
        if concentration:
            leader = concentration[0]
            findings.append({"type": "RISK_CONCENTRATION", "severity": "MEDIUM", "message": "The leading group concentrates the largest share of the selected exposure; this is concentration, not causality.", "dimension": dimension, "value": leader["value"], "amount": leader[metric], "share": leader["share"], "evidence_refs": ["concentration_by_dimension"]})
        if top_customers:
            findings.append({"type": "CUSTOMER_PARETO", "severity": "MEDIUM", "message": "Top customers are ordered deterministically by selected exposure and customer name for tie-breaking.", "evidence_refs": ["top_customers"]})
        return AgentResponse(operation="risk_concentration", as_of_date=as_of, entity={"type": "portfolio", "id": "all", "dimension": dimension}, status={"metric": metric, "currency": PEN}, metrics={"metric_total": total, "groups_returned": len(concentration[:top_n]), "groups_available": len(concentration), "top_n": top_n}, findings=findings, recommended_actions=[{"action": "focus_review_on_concentrated_exposure", "reason": "Start with the highest-exposure groups and customers after operational validation.", "evidence_refs": ["concentration_by_dimension", "top_customers"]}] if concentration else [], evidence=evidence, data_quality=self._quality(as_of), visualization_hints=[{"type": "bar_chart", "source": "evidence[0].value", "x": "value", "y": metric}, {"type": "ranking_table", "source": "evidence[1].value"}], analysis_scope={"currency": PEN, "dimension": dimension, "metric": metric, "as_of_date_applied": True}, methodology={"deterministic": True, "pareto_sort": f"{metric} descending, label ascending on ties", "causality": "not inferred"}, upstream_inputs=[{"type": "csv_adapter", "status": "active"}]).to_dict()
