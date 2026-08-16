"""Five deterministic, evidence-first tools for SON-IA Billing Assurance."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from .contracts import AgentResponse
from .data import load_dataset
from .model import BillingModel, CreditNote, Invoice, ZERO, build_model, parse_date, source_ref
from .rules import (
    DATA_QUALITY,
    DETERMINISTIC,
    HEURISTIC,
    MATERIAL_MEDIUM,
    TOLERANCE,
    finding,
    invoice_findings,
    materiality,
)


class BillingService:
    def __init__(self, dataset_path: Path):
        self.model: BillingModel = build_model(load_dataset(dataset_path))

    def _as_of(self, value: str | None) -> date:
        if value:
            parsed = parse_date(value)
            if not parsed:
                raise ValueError("as_of_date no puede estar vacío")
            return parsed
        dates = [
            item.issued_at for item in self.model.invoices.values() if item.issued_at
        ] + [note.issued_at for note in self.model.credit_notes if note.issued_at]
        return max(dates)

    def _invoices_as_of(self, as_of: date) -> list[Invoice]:
        return [item for item in self.model.invoices.values() if item.issued_at and item.issued_at <= as_of]

    def _notes_as_of(self, as_of: date) -> list[CreditNote]:
        return [item for item in self.model.credit_notes if item.issued_at and item.issued_at <= as_of]

    def _notes_for_invoice(self, document: str, as_of: date) -> list[CreditNote]:
        return [note for note in self.model.credits_by_invoice.get(document, []) if note.issued_at and note.issued_at <= as_of]

    @staticmethod
    def _plant_evidence(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        for row in rows:
            table = row["__source_table"]
            evidence.append({
                "source_ref": source_ref(row),
                "plant_type": "fixed" if table == "fixed_plant" else "mobile",
                "account": row.get("COD_CUENTA", ""),
                "fixed_status": row.get("STATUS_DESC", "") or None,
                "mobile_status": row.get("ESTADO_LINEA", "") or None,
                "activation_date": row.get("FECHAALTA", "") or row.get("FECHA_ALTA", "") or None,
                "plan": row.get("SUB_MAIN_OFFER_DESC", "") or row.get("PLAN_PRINCIPAL", "") or None,
            })
        return evidence

    def _quality(self, as_of: date) -> dict[str, Any]:
        invoices = self._invoices_as_of(as_of)
        invoice_accounts = {(item.customer, item.account) for item in invoices}
        plant_accounts = set(self.model.all_plant_accounts())
        matched = invoice_accounts & plant_accounts
        master_mismatch = sum(
            1 for item in invoices
            if self.model.customers.get(item.customer, {}).get("NUMERO_IDENTIFICACION_FISCAL", "") != item.fiscal_id
        )
        mobile_signatures = Counter(
            tuple((key, value) for key, value in row.items() if not key.startswith("__"))
            for row in self.model.dataset.mobile_plant
        )
        duplicate_groups = sum(count > 1 for count in mobile_signatures.values())
        duplicate_extra_rows = sum(count - 1 for count in mobile_signatures.values() if count > 1)
        return {
            "source_counts": self.model.dataset.source_counts(),
            "canonical_customer_key": "RAZON_SOCIAL",
            "join_rules": {
                "customer": "RAZON_SOCIAL (NIF is evidence only)",
                "invoice_to_credit_note": "NRO_DOC_FISCAL -> FACTURA_AFECTADA",
                "invoice_to_plant": "RAZON_SOCIAL + COD_CUENTA, left join",
            },
            "join_coverage": {
                "invoiced_customer_accounts": len(invoice_accounts),
                "matched_to_plant": len(matched),
                "unmatched_to_plant": len(invoice_accounts - plant_accounts),
                "matched_share": Decimal(len(matched)) / Decimal(len(invoice_accounts)) if invoice_accounts else ZERO,
            },
            "quality_checks": {
                "invoice_fiscal_id_mismatches_to_customer_master": master_mismatch,
                "mobile_exact_duplicate_groups_preserved": duplicate_groups,
                "mobile_exact_duplicate_extra_rows_preserved": duplicate_extra_rows,
            },
            "known_limitations": [
                "NIF/RUC is inconsistent across source tables and is not used as an inter-table key.",
                "Plant-to-invoice coverage is partial; an unmatched account is not proof of non-billing.",
                "Exact-looking mobile rows are retained because anonymization may hide individual line identifiers.",
                "The supplied extracts may represent partial time windows rather than complete contractual history.",
                "No contractual PxQ, tariff catalogue, credit-note reason, or evidence of the expected billed amount is available.",
            ],
        }

    def _cycle_gaps(self, as_of: date) -> list[dict[str, Any]]:
        periodic: dict[tuple[str, str], dict[str, list[Invoice]]] = defaultdict(lambda: defaultdict(list))
        for item in self._invoices_as_of(as_of):
            if item.source == "FACTURACION CICLICA" and item.issued_at:
                periodic[(item.customer, item.account)][item.issued_at.strftime("%Y-%m")].append(item)
        gaps: list[dict[str, Any]] = []
        for (customer, account), by_month in periodic.items():
            months = set(by_month)
            for before in sorted(months):
                before_date = date.fromisoformat(f"{before}-01")
                missing = (before_date.replace(day=28) + timedelta(days=4)).replace(day=1)
                after = (missing.replace(day=28) + timedelta(days=4)).replace(day=1)
                missing_key, after_key = missing.strftime("%Y-%m"), after.strftime("%Y-%m")
                if after_key not in months or missing_key in months:
                    continue
                before_invoice = sorted(by_month[before], key=lambda item: item.document)[0]
                after_invoice = sorted(by_month[after_key], key=lambda item: item.document)[0]
                plants = self.model.plant_rows(customer, account)
                gaps.append({
                    "customer": customer,
                    "account": account,
                    "before_period": before,
                    "missing_period": missing_key,
                    "after_period": after_key,
                    "before_invoice": before_invoice,
                    "after_invoice": after_invoice,
                    "plant_rows": plants,
                })
        return gaps

    def _active_plant_without_invoice(self, as_of: date) -> list[tuple[str, str, list[dict[str, str]]]]:
        invoice_accounts = {(item.customer, item.account) for item in self._invoices_as_of(as_of)}
        candidates = []
        for key, rows in self.model.plants_by_customer_account.items():
            active = any(
                row.get("STATUS_DESC") == "Active" or row.get("ESTADO_LINEA") == "Activo"
                for row in rows
            )
            if active and key not in invoice_accounts:
                candidates.append((key[0], key[1], rows))
        return candidates

    def billing_health_snapshot(self, as_of_date: str | None = None) -> dict[str, Any]:
        as_of = self._as_of(as_of_date)
        invoices = self._invoices_as_of(as_of)
        notes = self._notes_as_of(as_of)
        exception_counts: Counter[str] = Counter()
        material_notes = 0
        for item in invoices:
            item_notes = self._notes_for_invoice(item.document, as_of)
            for result in invoice_findings(item, item_notes, f"invoice:{item.document}"):
                exception_counts[result["type"]] += 1
                material_notes += result["type"] == "MATERIAL_CREDIT_NOTE"
        gaps = self._cycle_gaps(as_of)
        plant_without_invoice = self._active_plant_without_invoice(as_of)
        quality = self._quality(as_of)
        evidence = [
            {"id": "portfolio_universe", "type": "universe", "value": {
                "invoice_documents": len(invoices), "credit_note_documents": len(notes),
                "customers_with_invoices": len({item.customer for item in invoices}),
                "customer_accounts_with_invoices": len({(item.customer, item.account) for item in invoices}),
            }},
            {"id": "join_coverage", "type": "join_coverage", "value": quality["join_coverage"]},
            {"id": "exception_counts", "type": "exception_counts", "value": dict(exception_counts)},
            {"id": "cycle_gap_summary", "type": "cycle_gap_summary", "value": {"count": len(gaps), "rule": "M, M+2 present and M+1 absent for same customer-account"}},
            {"id": "active_plant_without_invoice_summary", "type": "exploratory_candidate_summary", "value": {"count": len(plant_without_invoice)}},
        ]
        findings = [
            finding("DATA_QUALITY_JOIN_GAP", "MEDIUM", DATA_QUALITY,
                    "Parte de las cuentas facturadas no tiene planta enlazada en el extracto; se conserva el left join.",
                    ["join_coverage"], "Factura a planta por RAZON_SOCIAL + COD_CUENTA.",
                    "Validar cobertura de extractos antes de interpretar ausencias de planta.", quality["join_coverage"]),
            finding("BILLING_CYCLE_GAP", "MEDIUM", HEURISTIC,
                    "Se encontraron candidatos de ausencia documental mensual entre dos emisiones cíclicas.",
                    ["cycle_gap_summary"], "M y M+2 cíclicos presentes; M+1 ausente para mismo cliente-cuenta.",
                    "Validar suspensión, corte, sistema y cobertura del periodo; no denominarlo fuga de ingresos.", {"count": len(gaps)}),
            finding("PLANT_WITHOUT_BILLING_EVIDENCE", "LOW", HEURISTIC,
                    "Hay cuentas de planta activa sin factura asociada en el corte; es una señal exploratoria, no un ingreso omitido confirmado.",
                    ["active_plant_without_invoice_summary"], "Planta Active/Activo y sin factura en el extracto hasta el corte.",
                    "Contrastar vigencia del servicio y cobertura del dataset antes de escalar el caso.", {"count": len(plant_without_invoice)}),
        ]
        return AgentResponse(
            operation="billing_health_snapshot", as_of_date=as_of,
            status={"billing_assurance": "REQUIERE_VALIDACION" if exception_counts or gaps else "SIN_EXCEPCIONES_RELEVANTES"},
            metrics={"invoice_documents": len(invoices), "credit_note_documents": len(notes), "exception_counts": dict(exception_counts), "material_credit_note_count": material_notes, "cycle_gap_candidates": len(gaps), "active_plant_without_invoice_candidates": len(plant_without_invoice)},
            findings=findings,
            alerts=[finding("DATA_QUALITY_NIF_INCONSISTENT", "MEDIUM", DATA_QUALITY,
                            "El NIF/RUC no es estable entre fuentes; RAZON_SOCIAL se utiliza como identidad temporal.", ["join_coverage"],
                            "NIF no se usa para joins inter-tabla.", "No sustituir la llave canónica sin validación de origen.", quality["quality_checks"]["invoice_fiscal_id_mismatches_to_customer_master"])],
            recommended_actions=[
                {"action": "review_cycle_gap_candidates", "reason": "Contrastar primero los casos con evidencia antes/después."},
                {"action": "review_material_credit_notes", "reason": "Validar ajustes materiales post-emisión y su soporte."},
                {"action": "validate_data_coverage", "reason": "Confirmar cobertura de planta, sistemas y ventana temporal."},
            ], evidence=evidence, data_quality=quality,
            visualization_hints=[{"type": "kpi_cards", "fields": ["invoice_documents", "material_credit_note_count", "cycle_gap_candidates"]}],
            analysis_scope={"as_of_date_applied": True, "payments_excluded": True, "currency_scope": "source values; no cross-currency conversion"},
            methodology={"deterministic": True, "arithmetic_tolerance": TOLERANCE, "materiality": "25% MEDIUM, 50% HIGH", "cycle_gap": "M and M+2 present, M+1 absent"},
            upstream_inputs=[{"type": "csv_adapter", "tables": list(self.model.dataset.source_counts()), "status": "active"}],
        ).to_dict()

    def customer_billing_check(self, customer_id: str, account_id: str | None = None, as_of_date: str | None = None) -> dict[str, Any]:
        as_of = self._as_of(as_of_date)
        customer = customer_id.strip().upper()
        if customer not in self.model.customers:
            raise KeyError(f"Cliente no encontrado: {customer_id}")
        account = account_id.strip() if account_id else None
        invoices = [item for item in self._invoices_as_of(as_of) if item.customer == customer and (not account or item.account == account)]
        invoice_account_keys = {(customer, item.account) for item in invoices}
        plant_account_keys = {key for key in self.model.all_plant_accounts() if key[0] == customer}
        # Without an account filter, customer scope must include all available plant
        # accounts as well as billed accounts. Set semantics avoid artificial account
        # duplication while plant evidence retains every raw plant row.
        account_keys = {(customer, account)} if account else invoice_account_keys | plant_account_keys
        evidence: list[dict[str, Any]] = [{"id": "customer_master", "type": "customer", "value": {"customer": customer, "source_ref": source_ref(self.model.customers[customer])}}]
        findings: list[dict[str, Any]] = []
        for key in sorted(account_keys):
            plants = self.model.plant_rows(*key)
            plant_ref = f"plant:{key[1]}"
            plant_evidence = self._plant_evidence(plants)
            evidence.append({"id": plant_ref, "type": "plant", "value": plant_evidence})
            has_invoice = key in invoice_account_keys
            if plants and not has_invoice:
                findings.append(finding(
                    "PLANT_WITHOUT_BILLING_EVIDENCE", "LOW", HEURISTIC,
                    "La cuenta tiene planta en el extracto pero no evidencia de factura hasta el corte; no prueba servicio no facturado ni fuga de ingresos.",
                    [plant_ref],
                    "Cuenta presente en Planta y sin factura del cliente-cuenta dentro del corte seleccionado.",
                    "Validar cobertura temporal, vigencia contractual y sistema de origen antes de escalar el caso.",
                    {
                        "account": key[1],
                        "plant_record_count": len(plants),
                        "plant_types": sorted({item["plant_type"] for item in plant_evidence}),
                        "invoice_evidence_count": 0,
                        "as_of_date": as_of,
                    },
                ))
        for item in sorted(invoices, key=lambda value: (value.issued_at or date.min, value.document)):
            ref = f"invoice:{item.document}"
            notes = self._notes_for_invoice(item.document, as_of)
            evidence.append({"id": ref, "type": "invoice", "value": item.evidence})
            for note in notes:
                evidence.append({"id": f"credit_note:{note.document}", "type": "credit_note", "value": note.evidence})
            findings.extend(invoice_findings(item, notes, ref))
        for index, gap in enumerate(self._cycle_gaps(as_of), start=1):
            if gap["customer"] != customer or (account and gap["account"] != account):
                continue
            gap_id = f"customer_cycle_gap:{index}"
            before_ref, after_ref = f"invoice:{gap['before_invoice'].document}", f"invoice:{gap['after_invoice'].document}"
            evidence.append({"id": gap_id, "type": "cycle_gap", "value": {
                "customer": customer, "account": gap["account"], "before_period": gap["before_period"],
                "missing_period": gap["missing_period"], "after_period": gap["after_period"],
                "before_invoice": before_ref, "after_invoice": after_ref,
            }})
            findings.append(finding(
                "BILLING_CYCLE_GAP", "MEDIUM", HEURISTIC,
                "Existe una ausencia documental mensual entre dos facturas cíclicas de esta cuenta.",
                [gap_id, before_ref, after_ref],
                "FACTURACION CICLICA en M y M+2; sin documento cíclico en M+1.",
                "Validar cobertura, suspensión, cambio de sistema y vigencia contractual; no clasificar como fuga de ingresos.",
                {"before_period": gap["before_period"], "missing_period": gap["missing_period"], "after_period": gap["after_period"]},
            ))
        status = "REQUIERE_VALIDACION" if findings else "SIN_EXCEPCIONES_DOCUMENTALES"
        return AgentResponse(
            operation="customer_billing_check", as_of_date=as_of, entity={"type": "customer", "id": customer, "account_id": account},
            status={"billing_assurance": status},
            metrics={"invoice_count": len(invoices), "account_count": len(account_keys), "invoice_account_count": len(invoice_account_keys), "plant_account_count": len(plant_account_keys if not account else ({(customer, account)} & plant_account_keys)), "credit_note_count": sum(len(self._notes_for_invoice(item.document, as_of)) for item in invoices)},
            findings=findings,
            recommended_actions=[{"action": "review_document_evidence", "reason": "Validar cada excepción usando el documento y registro fuente enlazados."}],
            evidence=evidence, data_quality=self._quality(as_of),
            analysis_scope={"customer": customer, "account_filter": account, "payments_excluded": True},
            methodology={"deterministic": True, "customer_join": "RAZON_SOCIAL"},
            upstream_inputs=[{"type": "csv_adapter", "status": "active"}],
        ).to_dict()

    def invoice_quality_check(self, invoice_id: str, as_of_date: str | None = None) -> dict[str, Any]:
        as_of = self._as_of(as_of_date)
        document = invoice_id.strip()
        invoice = self.model.invoices.get(document)
        if not invoice:
            raise KeyError(f"Factura no encontrada: {invoice_id}")
        notes = self._notes_for_invoice(document, as_of)
        evidence = [{"id": f"invoice:{document}", "type": "invoice", "value": invoice.evidence}]
        evidence.extend({"id": f"credit_note:{note.document}", "type": "credit_note", "value": note.evidence} for note in notes)
        findings = invoice_findings(invoice, notes, f"invoice:{document}")
        return AgentResponse(
            operation="invoice_quality_check", as_of_date=as_of, entity={"type": "invoice", "id": document},
            status={"billing_assurance": "REQUIERE_VALIDACION" if findings else "SIN_EXCEPCIONES_DOCUMENTALES"},
            metrics={"net": invoice.net, "tax": invoice.tax, "reported_total": invoice.total, "derived_total": invoice.net + invoice.tax, "difference": invoice.net + invoice.tax - invoice.total, "credit_note_count": len(notes)},
            findings=findings,
            recommended_actions=[{"action": "validate_source_document", "reason": "Contrastar los campos mostrados con el sistema de origen antes de concluir una incidencia."}],
            evidence=evidence, data_quality=self._quality(as_of),
            analysis_scope={"invoice_id": document, "payments_excluded": True},
            methodology={"deterministic": True, "arithmetic_tolerance": TOLERANCE, "date_formats": ["YYYY-MM-DD", "YYYYMMDD"]},
            upstream_inputs=[{"type": "csv_adapter", "status": "active"}],
        ).to_dict()

    def billing_cycle_gaps(self, as_of_date: str | None = None, customer_id: str | None = None, account_id: str | None = None) -> dict[str, Any]:
        as_of = self._as_of(as_of_date)
        customer = customer_id.strip().upper() if customer_id else None
        account = account_id.strip() if account_id else None
        all_gaps = self._cycle_gaps(as_of)
        gaps = [item for item in all_gaps if (not customer or item["customer"] == customer) and (not account or item["account"] == account)]
        evidence: list[dict[str, Any]] = []
        findings: list[dict[str, Any]] = []
        for index, gap in enumerate(gaps, start=1):
            gap_id = f"cycle_gap:{index}"
            before_ref, after_ref = f"invoice:{gap['before_invoice'].document}", f"invoice:{gap['after_invoice'].document}"
            plant_ref = f"plant:{gap['customer']}:{gap['account']}"
            evidence.extend([
                {"id": before_ref, "type": "invoice_before_gap", "value": gap["before_invoice"].evidence},
                {"id": after_ref, "type": "invoice_after_gap", "value": gap["after_invoice"].evidence},
                {"id": plant_ref, "type": "linked_plant", "value": self._plant_evidence(gap["plant_rows"])},
                {"id": gap_id, "type": "cycle_gap", "value": {
                    **{key: gap[key] for key in ("customer", "account", "before_period", "missing_period", "after_period")},
                    "before_document": gap["before_invoice"].document,
                    "after_document": gap["after_invoice"].document,
                }},
            ])
            findings.append(finding(
                "BILLING_CYCLE_GAP", "MEDIUM", HEURISTIC,
                "Existe una ausencia documental mensual entre dos facturas cíclicas para el mismo cliente y cuenta.",
                [gap_id, before_ref, after_ref, plant_ref],
                "FACTURACION CICLICA en M y M+2; sin documento cíclico en M+1.",
                "Validar cobertura, suspensión, cambio de sistema y vigencia contractual; no clasificar como fuga de ingresos.",
                {"before_period": gap["before_period"], "missing_period": gap["missing_period"], "after_period": gap["after_period"], "plant_linked": bool(gap["plant_rows"])},
            ))
        cyclic = [item for item in self._invoices_as_of(as_of) if item.source == "FACTURACION CICLICA"]
        months = sorted({item.issued_at.strftime("%Y-%m") for item in cyclic if item.issued_at})
        return AgentResponse(
            operation="billing_cycle_gaps", as_of_date=as_of, entity={"type": "portfolio", "id": "all", "customer_id": customer, "account_id": account},
            status={"billing_assurance": "REQUIERE_VALIDACION" if gaps else "SIN_CANDIDATOS"},
            metrics={"candidate_count": len(gaps), "portfolio_candidate_count": len(all_gaps), "cyclic_invoice_count": len(cyclic)},
            findings=findings,
            recommended_actions=[{"action": "validate_cycle_gap", "reason": "Revisar primero los documentos antes/después y la situación de planta enlazada."}] if gaps else [],
            evidence=evidence, data_quality=self._quality(as_of),
            analysis_scope={"source": "FACTURACION CICLICA", "window_months_observed": months, "rule_requires_future_document": True},
            methodology={"deterministic": True, "rule_category": HEURISTIC, "cycle_gap": "same customer + account: M and M+2 present, M+1 absent"},
            upstream_inputs=[{"type": "csv_adapter", "status": "active"}],
        ).to_dict()

    def credit_note_review(self, as_of_date: str | None = None, customer_id: str | None = None, account_id: str | None = None, invoice_id: str | None = None, materiality_threshold: Decimal | str = MATERIAL_MEDIUM) -> dict[str, Any]:
        as_of = self._as_of(as_of_date)
        threshold = Decimal(str(materiality_threshold))
        if not ZERO <= threshold <= Decimal("1"):
            raise ValueError("materiality_threshold debe estar entre 0 y 1")
        customer = customer_id.strip().upper() if customer_id else None
        account = account_id.strip() if account_id else None
        document = invoice_id.strip() if invoice_id else None
        evidence: list[dict[str, Any]] = []
        findings: list[dict[str, Any]] = []
        notes = []
        for note in self._notes_as_of(as_of):
            invoice = self.model.invoices.get(note.affected_invoice)
            if not invoice or (customer and invoice.customer != customer) or (account and invoice.account != account) or (document and invoice.document != document):
                continue
            notes.append((note, invoice))
        for note, invoice in sorted(notes, key=lambda pair: (pair[1].document, pair[0].document)):
            invoice_ref, note_ref = f"invoice:{invoice.document}", f"credit_note:{note.document}"
            evidence.extend([{"id": invoice_ref, "type": "invoice", "value": invoice.evidence}, {"id": note_ref, "type": "credit_note", "value": note.evidence}])
            ratio, severity = materiality(note.total, invoice.total, threshold)
            findings.append(finding(
                "CREDIT_NOTE_PRESENT", "INFO", DETERMINISTIC,
                "La nota de crédito está vinculada documentalmente a la factura afectada.", [invoice_ref, note_ref],
                "FACTURA_AFECTADA coincide con NRO_DOC_FISCAL.", "Revisar el ajuste post-emisión y su soporte.",
                {"invoice_total": invoice.total, "credit_note_total": note.total, "ratio": ratio},
            ))
            if severity:
                findings.append(finding(
                    "MATERIAL_CREDIT_NOTE", severity, HEURISTIC,
                    "La nota de crédito supera el umbral solicitado y merece revisión por materialidad.", [invoice_ref, note_ref],
                    f"importe NC / importe factura >= {threshold}.",
                    "Validar motivo y autorización; materialidad no implica error confirmado.",
                    {"invoice_total": invoice.total, "credit_note_total": note.total, "ratio": ratio, "threshold": threshold},
                ))
        return AgentResponse(
            operation="credit_note_review", as_of_date=as_of, entity={"type": "credit_note_scope", "customer_id": customer, "account_id": account, "invoice_id": document},
            status={"billing_assurance": "REQUIERE_VALIDACION" if notes else "SIN_NOTAS_DE_CREDITO_EN_EL_ALCANCE"},
            metrics={"credit_note_count": len(notes), "materiality_threshold": threshold, "material_credit_note_count": sum(item["type"] == "MATERIAL_CREDIT_NOTE" for item in findings)},
            findings=findings,
            recommended_actions=[{"action": "review_post_billing_adjustment", "reason": "Contrastar cada ajuste con su soporte y motivo operativo."}] if notes else [],
            evidence=evidence, data_quality=self._quality(as_of),
            analysis_scope={"customer_id": customer, "account_id": account, "invoice_id": document, "payments_excluded": True},
            methodology={"deterministic": True, "materiality": "NC total / invoice total", "threshold": threshold, "classification": HEURISTIC},
            upstream_inputs=[{"type": "csv_adapter", "status": "active"}],
        ).to_dict()
