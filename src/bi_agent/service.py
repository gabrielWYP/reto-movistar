"""Deterministic, evidence-first business intelligence tools for SON-IA."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from .contracts import AgentResponse
from .data import load_dataset
from .integration import collections_response_metadata
from .model import PEN, TOLERANCE, CanonicalRevenueModel, SnapshotInvoice, aging_bucket, build_canonical_model

DEFAULT_AS_OF_DATE = "2026-07-31"
ALLOWED_DIMENSIONS = {"SEGMENTO_PAIS", "SUNAT_DEPARTAMENTO", "SISTEMA", "FUENTE", "SERVICE_PROFILE"}
ALLOWED_METRICS = {"overdue_balance", "outstanding_balance"}
ALLOWED_SCOPES = {"PORTFOLIO"}
SEVERITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "INFO": 3}


def _severity_for_share(share: Decimal) -> str:
    """Documented business-impact rule; it is not a collections score."""
    if share >= Decimal("0.60"):
        return "HIGH"
    if share >= Decimal("0.25"):
        return "MEDIUM"
    return "LOW"


class BIService:
    def __init__(self, dataset_path: Path, collections_response: dict[str, Any] | None = None):
        self.model: CanonicalRevenueModel = build_canonical_model(load_dataset(dataset_path))
        self.collections_upstream = collections_response_metadata(collections_response) if collections_response else None

    @staticmethod
    def _as_of(value: str | None) -> date:
        return date.fromisoformat(value or DEFAULT_AS_OF_DATE)

    @staticmethod
    def _scope(value: str) -> str:
        scope = value.upper()
        if scope not in ALLOWED_SCOPES:
            raise ValueError(f"scope debe ser uno de: {', '.join(sorted(ALLOWED_SCOPES))}")
        return scope

    def _upstream_inputs(self) -> list[dict[str, Any]]:
        values = [{"type": "csv_adapter", "status": "active"}]
        if self.collections_upstream:
            values.append(self.collections_upstream)
        return values

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
        return {
            "SEGMENTO_PAIS": customer.get("SEGMENTO_PAIS", "UNMATCHED_CUSTOMER"),
            "SUNAT_DEPARTAMENTO": customer.get("SUNAT_DEPARTAMENTO", "UNMATCHED_CUSTOMER"),
            "SISTEMA": invoice.system or "MISSING",
            "FUENTE": invoice.source or "MISSING",
            "SERVICE_PROFILE": service_profile,
        }

    @staticmethod
    def _metrics(rows: list[SnapshotInvoice], as_of: date) -> dict[str, Any]:
        billed = sum((row.invoice.total for row in rows), Decimal())
        paid = sum((row.paid for row in rows), Decimal())
        credits = sum((row.credited for row in rows), Decimal())
        outstanding = sum((row.balance for row in rows), Decimal())
        overdue = sum((row.balance for row in rows if row.invoice.due_at and row.invoice.due_at < as_of), Decimal())
        overdue_customers = {
            row.invoice.customer
            for row in rows
            if row.balance > TOLERANCE and row.invoice.due_at and row.invoice.due_at < as_of
        }
        return {
            "currency": PEN,
            "total_billed": billed,
            "total_paid_linked": paid,
            "credit_notes_linked": credits,
            "outstanding_balance": outstanding,
            "overdue_balance": overdue,
            "collection_ratio": paid / billed if billed else Decimal(),
            "invoice_count": len(rows),
            "open_invoice_count": sum(row.balance > TOLERANCE for row in rows),
            "customers_with_overdue_balance": len(overdue_customers),
        }

    @staticmethod
    def _aging(rows: list[SnapshotInvoice], as_of: date) -> list[dict[str, Any]]:
        amounts: dict[str, Decimal] = defaultdict(Decimal)
        documents: Counter[str] = Counter()
        for row in rows:
            if row.balance <= TOLERANCE:
                continue
            bucket = aging_bucket(row.days_past_due(as_of))
            amounts[bucket] += row.balance
            documents[bucket] += 1
        order = ["NO_VENCIDA", "1_30", "31_60", "61_90", "90_PLUS", "SIN_FECHA_VENCIMIENTO"]
        return [
            {"bucket": bucket, "documents": documents[bucket], "outstanding_balance": amounts[bucket]}
            for bucket in order
            if documents[bucket]
        ]

    def _quality(self, as_of: date) -> dict[str, Any]:
        later = self.model.payments_after(as_of)
        limitations = [
            "RAZON_SOCIAL is the temporary canonical customer key; fiscal identifiers are not used for joins.",
            "No bank statements or customer communications are included, so this is not bank reconciliation.",
            "Amounts are analyzed only in PEN; USD and missing-currency items are excluded from monetary KPIs.",
        ]
        if later:
            limitations.append("Payments dated after as_of_date are excluded from balances and reported separately.")
        return {
            "source_counts": self.model.source_counts,
            "join_rules": {
                "customer": "RAZON_SOCIAL",
                "document": "NRO_DOC_FISCAL -> FACTURA_AFECTADA",
                "plant": "COD_CUENTA summarized before enrichment",
            },
            "quality_checks": self.model.quality,
            "as_of_exclusions": {
                "payments_after_as_of_count": len(later),
                "payments_after_as_of_amount_pen": sum((item.amount for item in later if item.currency == PEN), Decimal()),
                "unmatched_payment_count": len(self.model.unmatched_payments),
                "unmatched_payment_amount_pen": sum((item.amount for item in self.model.unmatched_payments if item.currency == PEN), Decimal()),
            },
            "known_limitations": limitations,
        }

    @staticmethod
    def _quality_alerts(quality: dict[str, Any], evidence_id: str) -> list[dict[str, Any]]:
        exclusions = quality["as_of_exclusions"]
        alerts: list[dict[str, Any]] = []
        if exclusions["unmatched_payment_count"]:
            alerts.append({
                "type": "DATA_QUALITY_UNMATCHED_PAYMENTS",
                "severity": "MEDIUM",
                "message": "Payments reference documents unavailable in the supplied invoice set; this limits interpretation of linked collection metrics.",
                "count": exclusions["unmatched_payment_count"],
                "evidence_refs": [evidence_id],
            })
        if exclusions["payments_after_as_of_count"]:
            alerts.append({
                "type": "DATA_QUALITY_PAYMENTS_AFTER_CUTOFF",
                "severity": "INFO",
                "message": "Payments after the selected cut-off are excluded from the as-of balance calculation.",
                "count": exclusions["payments_after_as_of_count"],
                "evidence_refs": [evidence_id],
            })
        return alerts

    def _concentration(
        self,
        rows: list[SnapshotInvoice],
        as_of: date,
        dimension: str,
        metric: str,
        top_n: int,
    ) -> tuple[Decimal, list[dict[str, Any]], list[dict[str, Any]], int]:
        grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {"amount": Decimal(), "customers": set(), "documents": 0})
        customer_amounts: dict[str, dict[str, Any]] = defaultdict(lambda: {"amount": Decimal(), "accounts": set(), "documents": 0})
        for row in rows:
            amount = row.balance if metric == "outstanding_balance" else (
                row.balance if row.invoice.due_at and row.invoice.due_at < as_of else Decimal()
            )
            if amount <= Decimal():
                continue
            group = grouped[self._dimensions(row)[dimension]]
            group["amount"] += amount
            group["customers"].add(row.invoice.customer)
            group["documents"] += 1
            customer = customer_amounts[row.invoice.customer]
            customer["amount"] += amount
            customer["accounts"].add(row.invoice.account_code)
            customer["documents"] += 1
        total = sum((item["amount"] for item in grouped.values()), Decimal())
        concentration = sorted(
            (
                {
                    "dimension": dimension,
                    "value": key,
                    metric: item["amount"],
                    "share": item["amount"] / total if total else Decimal(),
                    "customer_count": len(item["customers"]),
                    "document_count": item["documents"],
                }
                for key, item in grouped.items()
            ),
            key=lambda item: (-item[metric], item["value"]),
        )
        cumulative = Decimal()
        for item in concentration:
            cumulative += item["share"]
            item["cumulative_share"] = cumulative
        top_customers = sorted(
            (
                {
                    "customer": customer,
                    metric: item["amount"],
                    "share": item["amount"] / total if total else Decimal(),
                    "account_count": len(item["accounts"]),
                    "document_count": item["documents"],
                }
                for customer, item in customer_amounts.items()
                if item["amount"] > Decimal()
            ),
            key=lambda item: (-item[metric], item["customer"]),
        )
        running = Decimal()
        for item in top_customers:
            running += item["share"]
            item["cumulative_share"] = running
        return total, concentration[:top_n], top_customers[:top_n], len(concentration)

    def data_quality_report(self, as_of_date: str | None = None) -> dict[str, Any]:
        as_of = self._as_of(as_of_date)
        quality = self._quality(as_of)
        evidence = [
            {"id": "dq_source_counts", "type": "source_counts", "value": self.model.source_counts},
            {"id": "dq_join_rules", "type": "join_rules", "value": quality["join_rules"]},
            {"id": "dq_as_of_exclusions", "type": "as_of_exclusions", "value": quality["as_of_exclusions"]},
        ]
        return AgentResponse(
            operation="data_quality_report",
            as_of_date=as_of,
            status={"data_quality": "REVIEW_REQUIRED" if quality["as_of_exclusions"]["unmatched_payment_count"] else "OK"},
            metrics={
                "source_table_count": len(self.model.source_counts),
                "invoice_rows": self.model.source_counts["invoices"],
                "unmatched_payment_count": quality["as_of_exclusions"]["unmatched_payment_count"],
                "payments_after_as_of_count": quality["as_of_exclusions"]["payments_after_as_of_count"],
            },
            findings=[{
                "type": "DATA_QUALITY_SCOPE",
                "severity": "MEDIUM",
                "message": "Source coverage, joins, cut-off exclusions, and currency scope are explicit.",
                "evidence_refs": [item["id"] for item in evidence],
            }],
            evidence=evidence,
            data_quality=quality,
            analysis_scope={"currency": PEN, "as_of_date_applied": True},
            methodology={"deterministic": True, "financial_calculations": "Python Decimal"},
            upstream_inputs=self._upstream_inputs(),
        ).to_dict()

    def executive_snapshot(self, as_of_date: str | None = None) -> dict[str, Any]:
        as_of = self._as_of(as_of_date)
        rows = self.model.snapshot(as_of)
        metrics = self._metrics(rows, as_of)
        quality = self._quality(as_of)
        evidence = [
            {"id": "kpi_portfolio", "type": "portfolio_metrics", "value": metrics},
            {"id": "ageing_portfolio", "type": "aging", "value": self._aging(rows, as_of)},
            {"id": "dq_as_of_exclusions", "type": "payment_application_scope", "value": quality["as_of_exclusions"]},
        ]
        findings: list[dict[str, Any]] = []
        if metrics["overdue_balance"] > TOLERANCE:
            findings.append({
                "type": "OVERDUE_EXPOSURE",
                "severity": "MEDIUM",
                "message": "There is documented overdue balance at the selected cut-off.",
                "amount": metrics["overdue_balance"],
                "evidence_refs": ["kpi_portfolio", "ageing_portfolio"],
            })
        return AgentResponse(
            operation="executive_snapshot",
            as_of_date=as_of,
            metrics=metrics,
            aging=self._aging(rows, as_of),
            findings=findings,
            alerts=self._quality_alerts(quality, "dq_as_of_exclusions"),
            recommended_actions=[{
                "action": "review_document_scope",
                "reason": "Validate unmatched payments before treating the linked-payment ratio as full cash collection.",
                "evidence_refs": ["dq_as_of_exclusions"],
            }] if quality["as_of_exclusions"]["unmatched_payment_count"] else [],
            evidence=evidence,
            data_quality=quality,
            visualization_hints=[
                {"type": "kpi_cards", "fields": ["total_billed", "total_paid_linked", "outstanding_balance", "overdue_balance", "collection_ratio"]},
                {"type": "aging_bar", "source": "aging"},
            ],
            analysis_scope={"currency": PEN, "invoice_issued_on_or_before": as_of, "applications_on_or_before": as_of},
            methodology={"deterministic": True, "balance": "invoice_total - eligible_payments - eligible_credit_notes, floored at zero"},
            upstream_inputs=self._upstream_inputs(),
        ).to_dict()

    def risk_concentration(
        self,
        dimension: str = "SEGMENTO_PAIS",
        metric: str = "overdue_balance",
        top_n: int = 10,
        as_of_date: str | None = None,
    ) -> dict[str, Any]:
        as_of = self._as_of(as_of_date)
        dimension, metric = dimension.upper(), metric.lower()
        if dimension not in ALLOWED_DIMENSIONS:
            raise ValueError(f"dimension debe ser uno de: {', '.join(sorted(ALLOWED_DIMENSIONS))}")
        if metric not in ALLOWED_METRICS:
            raise ValueError(f"metric debe ser uno de: {', '.join(sorted(ALLOWED_METRICS))}")
        if not 1 <= top_n <= 100:
            raise ValueError("top_n debe estar entre 1 y 100")
        rows = self.model.snapshot(as_of)
        total, concentration, top_customers, groups_available = self._concentration(rows, as_of, dimension, metric, top_n)
        quality = self._quality(as_of)
        evidence = [
            {"id": "concentration_by_dimension", "type": "grouped_metric", "dimension": dimension, "metric": metric, "value": concentration},
            {"id": "top_customers", "type": "top_customers", "metric": metric, "value": top_customers},
            {"id": "dq_as_of_exclusions", "type": "payment_application_scope", "value": quality["as_of_exclusions"]},
        ]
        findings: list[dict[str, Any]] = []
        if concentration:
            leader = concentration[0]
            findings.append({
                "type": "RISK_CONCENTRATION",
                "severity": _severity_for_share(leader["share"]),
                "message": "The leading group concentrates the largest share of the selected exposure; this is concentration, not causality.",
                "dimension": dimension,
                "value": leader["value"],
                "amount": leader[metric],
                "share": leader["share"],
                "evidence_refs": ["concentration_by_dimension"],
            })
        if top_customers:
            findings.append({
                "type": "CUSTOMER_PARETO",
                "severity": _severity_for_share(top_customers[-1]["cumulative_share"]),
                "message": "Top customers are ordered deterministically by selected exposure and customer name for tie-breaking.",
                "evidence_refs": ["top_customers"],
            })
        return AgentResponse(
            operation="risk_concentration",
            as_of_date=as_of,
            entity={"type": "portfolio", "id": "all", "dimension": dimension},
            status={"metric": metric, "currency": PEN},
            metrics={"metric_total": total, "groups_returned": len(concentration), "groups_available": groups_available, "top_n": top_n},
            findings=findings,
            alerts=self._quality_alerts(quality, "dq_as_of_exclusions"),
            recommended_actions=[{
                "action": "focus_review_on_concentrated_exposure",
                "reason": "Start with the highest-exposure groups and customers after operational validation.",
                "evidence_refs": ["concentration_by_dimension", "top_customers"],
            }] if concentration else [],
            evidence=evidence,
            data_quality=quality,
            visualization_hints=[
                {"type": "bar_chart", "source": "evidence[0].value", "x": "value", "y": metric},
                {"type": "ranking_table", "source": "evidence[1].value"},
            ],
            analysis_scope={"currency": PEN, "dimension": dimension, "metric": metric, "as_of_date_applied": True},
            methodology={"deterministic": True, "pareto_sort": f"{metric} descending, label ascending on ties", "causality": "not inferred"},
            upstream_inputs=self._upstream_inputs(),
        ).to_dict()

    def recovery_intelligence(
        self,
        as_of_date: str | None = None,
        scope: str = "PORTFOLIO",
        dimension: str = "SEGMENTO_PAIS",
        top_n: int = 10,
    ) -> dict[str, Any]:
        """Describe business-impact opportunities without generating a collections score."""
        as_of = self._as_of(as_of_date)
        scope = self._scope(scope)
        dimension = dimension.upper()
        if dimension not in ALLOWED_DIMENSIONS:
            raise ValueError(f"dimension debe ser uno de: {', '.join(sorted(ALLOWED_DIMENSIONS))}")
        if not 1 <= top_n <= 100:
            raise ValueError("top_n debe estar entre 1 y 100")
        rows = self.model.snapshot(as_of)
        metrics = self._metrics(rows, as_of)
        quality = self._quality(as_of)
        overdue_total, groups, top_customers, _ = self._concentration(rows, as_of, dimension, "overdue_balance", top_n)
        preventive_rows = [row for row in rows if row.balance > TOLERANCE and (not row.invoice.due_at or row.invoice.due_at >= as_of)]
        preventive_balance = sum((row.balance for row in preventive_rows), Decimal())
        adjustment_rows = [row for row in rows if row.credited > Decimal() and row.balance > TOLERANCE]
        adjustment_balance = sum((row.balance for row in adjustment_rows), Decimal())
        adjustment_credits = sum((row.credited for row in adjustment_rows), Decimal())
        evidence = [
            {"id": "recovery_top_customers", "type": "customer_pareto", "metric": "overdue_balance", "value": top_customers},
            {"id": "recovery_concentration", "type": "dimension_concentration", "dimension": dimension, "metric": "overdue_balance", "value": groups},
            {"id": "recovery_preventive_exposure", "type": "not_due_open_balance", "value": {"balance": preventive_balance, "customer_count": len({row.invoice.customer for row in preventive_rows}), "document_count": len(preventive_rows)}},
            {"id": "recovery_document_adjustments", "type": "open_invoices_with_credit_notes", "value": {"outstanding_balance": adjustment_balance, "credit_notes_linked": adjustment_credits, "customer_count": len({row.invoice.customer for row in adjustment_rows}), "document_count": len(adjustment_rows)}},
            {"id": "dq_as_of_exclusions", "type": "payment_application_scope", "value": quality["as_of_exclusions"]},
        ]
        findings: list[dict[str, Any]] = []
        actions: list[dict[str, Any]] = []
        if top_customers:
            coverage = top_customers[-1]["cumulative_share"]
            findings.append({
                "type": "IMMEDIATE_RECOVERY_OPPORTUNITY",
                "severity": _severity_for_share(coverage),
                "finding": "The leading overdue customers represent a concentrated documented recovery opportunity.",
                "impact": "A focused intervention on this group can address the stated share of overdue exposure without creating a competing collections score.",
                "message": "Top customers are measured by documented overdue exposure and cumulative portfolio coverage.",
                "amount": sum((item["overdue_balance"] for item in top_customers), Decimal()),
                "coverage": coverage,
                "evidence_refs": ["recovery_top_customers"],
            })
            actions.append({
                "action": "focus_recovery_on_top_exposure",
                "reason": "Coordinate a focused recovery workstream for the largest documented overdue exposure; detailed contact priority remains owned by Collections.",
                "evidence_refs": ["recovery_top_customers"],
            })
        if groups:
            leader = groups[0]
            findings.append({
                "type": "DIMENSION_RECOVERY_CONCENTRATION",
                "severity": _severity_for_share(leader["share"]),
                "finding": "The leading business dimension concentrates the largest documented overdue exposure.",
                "impact": "A dimension-level workstream can focus governance and analysis where the largest share is observed; no causal driver is inferred.",
                "message": "The result is a concentration measurement, not a causal claim.",
                "dimension": dimension,
                "value": leader["value"],
                "amount": leader["overdue_balance"],
                "share": leader["share"],
                "evidence_refs": ["recovery_concentration"],
            })
            actions.append({
                "action": "create_dimension_recovery_workstream",
                "reason": "Review the leading dimension and its top-exposure customers as a focused business workstream.",
                "evidence_refs": ["recovery_concentration", "recovery_top_customers"],
            })
        if preventive_balance > TOLERANCE:
            findings.append({
                "type": "PREVENTIVE_FOLLOW_UP_OPPORTUNITY",
                "severity": "MEDIUM",
                "finding": "Open balance remains not yet due at the selected cut-off.",
                "impact": "Preventive monitoring can reduce the chance that this documented balance becomes overdue, but no forecast is asserted.",
                "message": "Not-due open balance is reported separately from overdue recovery exposure.",
                "amount": preventive_balance,
                "evidence_refs": ["recovery_preventive_exposure"],
            })
            actions.append({
                "action": "monitor_preventive_exposure",
                "reason": "Monitor material not-due balances before their due dates rather than treating them as overdue collection cases.",
                "evidence_refs": ["recovery_preventive_exposure"],
            })
        if adjustment_rows:
            findings.append({
                "type": "DOCUMENT_REVIEW_OPPORTUNITY",
                "severity": "MEDIUM",
                "finding": "Some open invoices have associated credit notes in the supplied document set.",
                "impact": "The exposure merits document review before interpreting it as a simple collection opportunity; a credit note does not establish a billing error.",
                "message": "Associated credit notes are a documentary context, not proof of an error.",
                "amount": adjustment_balance,
                "evidence_refs": ["recovery_document_adjustments"],
            })
            actions.append({
                "action": "review_document_adjustments_before_contact",
                "reason": "Validate linked credit-note context before initiating a standard recovery action for these documents.",
                "evidence_refs": ["recovery_document_adjustments"],
            })
        findings.sort(key=lambda item: (SEVERITY_ORDER[item["severity"]], item["type"]))
        return AgentResponse(
            operation="recovery_intelligence",
            as_of_date=as_of,
            entity={"type": "portfolio", "id": "all", "scope": scope, "dimension": dimension},
            status={"currency": PEN, "analysis": "DETERMINISTIC_BUSINESS_IMPACT"},
            metrics={
                "currency": PEN,
                "exposure_total": metrics["outstanding_balance"],
                "overdue_balance": metrics["overdue_balance"],
                "overdue_customer_count": metrics["customers_with_overdue_balance"],
                "addressable_exposure": sum((item["overdue_balance"] for item in top_customers), Decimal()),
                "top_n_customer_coverage": top_customers[-1]["cumulative_share"] if top_customers else Decimal(),
                "preventive_open_balance": preventive_balance,
                "document_review_open_balance": adjustment_balance,
                "document_review_credit_notes": adjustment_credits,
                "opportunity_group_count": len(findings),
            },
            findings=findings,
            alerts=self._quality_alerts(quality, "dq_as_of_exclusions"),
            recommended_actions=actions,
            evidence=evidence,
            data_quality=quality,
            visualization_hints=[
                {"type": "kpi_cards", "fields": ["overdue_balance", "addressable_exposure", "top_n_customer_coverage"]},
                {"type": "pareto_chart", "source": "recovery_top_customers"},
                {"type": "opportunity_table", "source": "findings"},
            ],
            analysis_scope={"scope": scope, "currency": PEN, "dimension": dimension, "as_of_date_applied": True},
            methodology={
                "deterministic": True,
                "recovery_priority": "business impact and concentration only; no collections priority score is calculated",
                "immediate_recovery": "top_n customers ordered by overdue balance descending and customer ascending on ties",
                "document_review": "open invoices with linked credit notes; not a billing-error classification",
                "causality": "not inferred",
            },
            upstream_inputs=self._upstream_inputs(),
        ).to_dict()

    def management_insights(
        self,
        as_of_date: str | None = None,
        dimension: str = "SEGMENTO_PAIS",
        top_n: int = 10,
    ) -> dict[str, Any]:
        """Produce ordered executive findings by composing deterministic tool outputs."""
        as_of = self._as_of(as_of_date)
        dimension = dimension.upper()
        if dimension not in ALLOWED_DIMENSIONS:
            raise ValueError(f"dimension debe ser uno de: {', '.join(sorted(ALLOWED_DIMENSIONS))}")
        executive = self.executive_snapshot(as_of.isoformat())
        recovery = self.recovery_intelligence(as_of.isoformat(), "PORTFOLIO", dimension, top_n)
        concentration = self.risk_concentration(dimension, "overdue_balance", top_n, as_of.isoformat())
        quality = self._quality(as_of)
        executive_metrics = executive["metrics"]
        recovery_metrics = recovery["metrics"]
        group_rows = concentration["evidence"][0]["value"]
        evidence = [
            {"id": "management_executive_metrics", "type": "executive_metrics", "value": executive_metrics},
            {"id": "management_dimension_concentration", "type": "dimension_concentration", "dimension": dimension, "value": group_rows},
            {"id": "management_recovery_pareto", "type": "recovery_pareto", "value": recovery["evidence"][0]["value"]},
            {"id": "management_preventive_exposure", "type": "not_due_open_balance", "value": recovery["evidence"][2]["value"]},
            {"id": "management_document_adjustments", "type": "document_adjustment_context", "value": recovery["evidence"][3]["value"]},
            {"id": "management_data_quality", "type": "data_quality_scope", "value": quality["as_of_exclusions"]},
        ]
        findings: list[dict[str, Any]] = []
        actions: list[dict[str, Any]] = []
        outstanding = Decimal(str(executive_metrics["outstanding_balance"]))
        overdue = Decimal(str(executive_metrics["overdue_balance"]))
        overdue_share = overdue / outstanding if outstanding else Decimal()
        if overdue > TOLERANCE:
            severity = _severity_for_share(overdue_share)
            findings.append({
                "type": "MANAGEMENT_OVERDUE_EXPOSURE",
                "severity": severity,
                "finding": "A material share of the documented open balance is overdue at the selected cut-off.",
                "impact": "Overdue exposure requires management attention because it represents balance already past documented due dates.",
                "message": "Overdue exposure is measured from the as-of portfolio, not forecast.",
                "amount": overdue,
                "share_of_outstanding": overdue_share,
                "evidence_refs": ["management_executive_metrics"],
            })
            actions.append({"action": "govern_overdue_exposure", "reason": "Review the documented overdue portfolio through focused recovery and exception-management workstreams.", "evidence_refs": ["management_executive_metrics", "management_recovery_pareto"]})
        if group_rows:
            leader = group_rows[0]
            findings.append({
                "type": "MANAGEMENT_DIMENSION_CONCENTRATION",
                "severity": _severity_for_share(Decimal(str(leader["share"]))),
                "finding": f"The leading {dimension} group concentrates the largest share of documented overdue exposure.",
                "impact": "Concentrated exposure supports a focused management workstream; the measurement does not establish a causal driver.",
                "message": "Dimension concentration is a deterministic aggregation of the selected dataset.",
                "dimension": dimension,
                "value": leader["value"],
                "amount": leader["overdue_balance"],
                "share": leader["share"],
                "evidence_refs": ["management_dimension_concentration"],
            })
            actions.append({"action": "focus_dimension_governance", "reason": "Start review with the leading concentration group and its largest customer exposures.", "evidence_refs": ["management_dimension_concentration", "management_recovery_pareto"]})
        coverage = Decimal(str(recovery_metrics["top_n_customer_coverage"]))
        if coverage > Decimal():
            findings.append({
                "type": "MANAGEMENT_RECOVERY_COVERAGE",
                "severity": _severity_for_share(coverage),
                "finding": "A limited top-customer set covers a measurable share of documented overdue exposure.",
                "impact": "A focused intervention can address that stated share with a limited number of customer cases; detailed contact priority remains with Collections.",
                "message": "Coverage is a Pareto concentration measure, not a replacement for collections prioritization.",
                "coverage": coverage,
                "amount": recovery_metrics["addressable_exposure"],
                "evidence_refs": ["management_recovery_pareto"],
            })
            actions.append({"action": "coordinate_top_exposure_workstream", "reason": "Coordinate with Collections on the largest-exposure customers using its approved operational priorities where available.", "evidence_refs": ["management_recovery_pareto"]})
        if recovery_metrics["preventive_open_balance"]:
            findings.append({
                "type": "MANAGEMENT_PREVENTIVE_EXPOSURE",
                "severity": "MEDIUM",
                "finding": "Some documented open balance is not yet due at the selected cut-off.",
                "impact": "Preventive monitoring can address the stated balance before its due date; this is not a payment forecast.",
                "message": "Not-due balance is kept separate from overdue recovery exposure.",
                "amount": recovery_metrics["preventive_open_balance"],
                "evidence_refs": ["management_preventive_exposure"],
            })
            actions.append({"action": "monitor_preventive_portfolio", "reason": "Monitor the not-due exposure before its documented due dates.", "evidence_refs": ["management_preventive_exposure"]})
        if recovery_metrics["document_review_open_balance"]:
            findings.append({
                "type": "MANAGEMENT_DOCUMENT_REVIEW_CONTEXT",
                "severity": "MEDIUM",
                "finding": "Some open exposure has associated credit-note context.",
                "impact": "These documents should be reviewed before a standard recovery treatment; credit notes do not by themselves indicate billing error.",
                "message": "This is a documentary-context insight, not an error classification.",
                "amount": recovery_metrics["document_review_open_balance"],
                "evidence_refs": ["management_document_adjustments"],
            })
            actions.append({"action": "review_adjustment_context", "reason": "Validate adjustment context before deciding the next business action for the affected documents.", "evidence_refs": ["management_document_adjustments"]})
        findings.sort(key=lambda item: (SEVERITY_ORDER[item["severity"]], item["type"]))
        alerts = self._quality_alerts(quality, "management_data_quality")
        return AgentResponse(
            operation="management_insights",
            as_of_date=as_of,
            entity={"type": "portfolio", "id": "all", "dimension": dimension},
            status={"currency": PEN, "insight_engine": "DETERMINISTIC_V0_2"},
            metrics={
                "currency": PEN,
                "outstanding_balance": executive_metrics["outstanding_balance"],
                "overdue_balance": executive_metrics["overdue_balance"],
                "overdue_share_of_open_balance": overdue_share,
                "top_n_customer_coverage": recovery_metrics["top_n_customer_coverage"],
                "business_finding_count": len(findings),
                "data_quality_alert_count": len(alerts),
            },
            findings=findings,
            alerts=alerts,
            recommended_actions=actions,
            evidence=evidence,
            data_quality=quality,
            visualization_hints=[
                {"type": "insight_cards", "source": "findings"},
                {"type": "pareto_chart", "source": "management_recovery_pareto"},
                {"type": "bar_chart", "source": "management_dimension_concentration"},
            ],
            analysis_scope={"currency": PEN, "dimension": dimension, "as_of_date_applied": True, "sample_scope": "hackathon dataset"},
            methodology={
                "deterministic": True,
                "composition": ["executive_snapshot", "risk_concentration", "recovery_intelligence", "_quality"],
                "priority_rule": "HIGH >= 60% share, MEDIUM >= 25% share, otherwise LOW; document-review findings are MEDIUM",
                "data_quality": "warnings are emitted as alerts and kept separate from business findings",
                "causality": "not inferred",
            },
            upstream_inputs=self._upstream_inputs(),
        ).to_dict()
