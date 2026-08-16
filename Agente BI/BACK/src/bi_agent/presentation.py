"""Human-readable presentation model for the SON-IA BI web experience.

This module deliberately sits after the deterministic service.  It never
changes an ``AgentResponse``; it creates a Spanish, business-facing view that
the UI can render while the original response remains available for audit.
"""

from __future__ import annotations

from datetime import date
from typing import Any, cast

METRIC_LABELS: dict[str, tuple[str, str, str]] = {
    "total_billed": ("Facturación emitida", "Importe facturado hasta la fecha de corte.", "money"),
    "total_paid_linked": (
        "Pagos vinculados",
        "Pagos asociados a facturas disponibles hasta el corte.",
        "money",
    ),
    "credit_notes_linked": (
        "Notas de crédito vinculadas",
        "Ajustes documentales asociados a facturas disponibles.",
        "money",
    ),
    "outstanding_balance": (
        "Saldo pendiente",
        "Facturación menos pagos y notas de crédito vinculados hasta el corte.",
        "money",
    ),
    "overdue_balance": (
        "Saldo vencido",
        "Saldo pendiente cuya fecha de vencimiento ya pasó al corte seleccionado.",
        "money",
    ),
    "collection_ratio": (
        "Cobertura de pagos vinculados",
        "Proporción facturada cubierta por pagos vinculados; no equivale necesariamente al recaudo total.",
        "percent",
    ),
    "metric_total": (
        "Saldo vencido total",
        "Saldo vencido analizado en la dimensión seleccionada.",
        "money",
    ),
    "exposure_total": (
        "Exposición pendiente",
        "Saldo pendiente documentado incluido en el análisis.",
        "money",
    ),
    "addressable_exposure": (
        "Oportunidad de recupero focalizada",
        "Saldo vencido cubierto por los principales casos identificados.",
        "money",
    ),
    "top_n_customer_coverage": (
        "Cobertura de los principales clientes",
        "Porcentaje del saldo vencido cubierto por los clientes de mayor exposición.",
        "percent",
    ),
    "preventive_open_balance": (
        "Saldo para seguimiento preventivo",
        "Saldo pendiente que todavía no vencía al corte seleccionado.",
        "money",
    ),
    "overdue_share_of_open_balance": (
        "Peso del saldo vencido",
        "Proporción del saldo pendiente que ya está vencida.",
        "percent",
    ),
    "unmatched_payment_count": (
        "Pagos sin factura vinculada",
        "Pagos que no pudieron asociarse a una factura disponible en el dataset.",
        "count",
    ),
    "payments_after_as_of_count": (
        "Pagos posteriores al corte",
        "Pagos excluidos por ser posteriores a la fecha de corte.",
        "count",
    ),
    "source_table_count": (
        "Fuentes analizadas",
        "Tablas de origen consideradas en el análisis.",
        "count",
    ),
    "invoice_rows": (
        "Facturas disponibles",
        "Registros de factura presentes en el dataset.",
        "count",
    ),
}

OPERATION_LABELS = {
    "executive_snapshot": (
        "Resumen del ciclo de ingresos",
        "Visión ejecutiva de facturación, pagos vinculados y cartera.",
    ),
    "risk_concentration": (
        "Concentración de riesgo",
        "Dónde se concentra el saldo vencido documentado.",
    ),
    "recovery_intelligence": (
        "Oportunidades de recupero",
        "Exposición cuya gestión focalizada puede tener mayor impacto.",
    ),
    "management_insights": (
        "Prioridades para la gerencia",
        "Hallazgos ejecutivos respaldados por métricas y evidencia.",
    ),
    "data_quality_report": (
        "Calidad y alcance de la información",
        "Limitaciones y reglas aplicadas a la muestra analizada.",
    ),
}

DIMENSION_LABELS = {
    "SEGMENTO_PAIS": "segmento",
    "SUNAT_DEPARTAMENTO": "departamento",
    "SISTEMA": "sistema de origen",
    "FUENTE": "fuente de facturación",
    "SERVICE_PROFILE": "perfil de servicio",
}

COLUMN_LABELS = {
    "customer": "Cliente",
    "value": "Grupo",
    "overdue_balance": "Saldo vencido",
    "outstanding_balance": "Saldo pendiente",
    "share": "% del saldo vencido",
    "cumulative_share": "% acumulado",
    "customer_count": "N.º de clientes",
    "account_count": "N.º de cuentas",
    "document_count": "N.º de facturas",
    "bucket": "Tramo de antigüedad",
    "documents": "N.º de facturas",
    "amount": "Importe",
    "coverage": "Cobertura",
    "severity": "Prioridad",
}

_MONEY_FIELDS = {
    "total_billed",
    "total_paid_linked",
    "credit_notes_linked",
    "outstanding_balance",
    "overdue_balance",
    "metric_total",
    "exposure_total",
    "addressable_exposure",
    "preventive_open_balance",
    "amount",
}
_PERCENT_FIELDS = {
    "collection_ratio",
    "top_n_customer_coverage",
    "overdue_share_of_open_balance",
    "share",
    "cumulative_share",
    "coverage",
    "share_of_outstanding",
}


def format_date(as_of_date: str) -> str:
    """Return a business-friendly date without changing the source date."""
    try:
        return date.fromisoformat(as_of_date).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return str(as_of_date)


def display_value(value: Any, field: str | None = None) -> str:
    """Format a raw value for a visible UI element while keeping it unchanged elsewhere."""
    if value is None:
        return "—"
    if field in _MONEY_FIELDS and isinstance(value, (int, float)):
        return f"S/ {value:,.2f}"
    if field in _PERCENT_FIELDS and isinstance(value, (int, float)):
        return f"{value * 100:.0f}%"
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value)


def display_dimension_value(dimension: str | None, value: Any) -> str:
    """Humanize a synthetic category label, never inventing a real customer or segment."""
    raw = str(value)
    if dimension == "SEGMENTO_PAIS" and raw.startswith("SEGMENTO_"):
        return f"Segmento {raw.removeprefix('SEGMENTO_')}"
    return raw


def _evidence(response: dict[str, Any], evidence_id: str) -> Any:
    for item in response.get("evidence", []):
        if item.get("id") == evidence_id:
            return item.get("value")
    return None


def _leading(response: dict[str, Any], evidence_id: str) -> dict[str, Any]:
    values = _evidence(response, evidence_id)
    return values[0] if isinstance(values, list) and values else {}


def _pareto(response: dict[str, Any], evidence_id: str) -> tuple[int, float | None, float | None]:
    values = _evidence(response, evidence_id)
    if not isinstance(values, list) or not values:
        return 0, None, None
    last = values[-1]
    return (
        len(values),
        last.get("cumulative_share"),
        sum(float(row.get("overdue_balance", 0)) for row in values),
    )


def _finding_copy(item: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    """Translate one deterministic finding into a readable story, preserving references."""
    item_type = item.get("type", "")
    dimension_key = cast(str, item.get("dimension"))
    dimension = DIMENSION_LABELS.get(dimension_key, "grupo")
    value = display_dimension_value(item.get("dimension"), item.get("value"))
    amount = display_value(item.get("amount"), "amount")
    share = display_value(item.get("share"), "share")
    title = "Hallazgo del análisis"
    detail = "El análisis identificó una situación que merece revisión."
    impact = "La interpretación se apoya en la evidencia disponible para el corte seleccionado."

    if item_type in {
        "RISK_CONCENTRATION",
        "DIMENSION_RECOVERY_CONCENTRATION",
        "MANAGEMENT_DIMENSION_CONCENTRATION",
    }:
        title = "Alta concentración del saldo vencido"
        detail = f"{value} concentra {share} del saldo vencido, equivalente a {amount}."
        impact = f"Una parte importante de la exposición está concentrada en este {dimension}. Esta medición identifica concentración, no una relación causal."
    elif item_type in {
        "CUSTOMER_PARETO",
        "IMMEDIATE_RECOVERY_OPPORTUNITY",
        "MANAGEMENT_RECOVERY_COVERAGE",
    }:
        evidence_id = (item.get("evidence_refs") or [""])[0]
        count, coverage, covered_amount = _pareto(response, evidence_id)
        title = "La deuda está concentrada en pocos clientes"
        if coverage is not None:
            detail = f"Los {count} clientes con mayor exposición cubren {display_value(coverage, 'coverage')} del saldo vencido, equivalente a {display_value(covered_amount, 'amount')}."
        else:
            detail = (
                "Los clientes de mayor exposición concentran una parte relevante del saldo vencido."
            )
        impact = "Una gestión focalizada puede abordar una proporción significativa de la exposición sin crear un ranking alternativo de Cobranzas."
    elif item_type in {"OVERDUE_EXPOSURE", "MANAGEMENT_OVERDUE_EXPOSURE"}:
        title = "Saldo pendiente ya vencido"
        detail = f"Al corte seleccionado, hay {amount} de saldo pendiente cuya fecha de vencimiento ya pasó."
        impact = "Esta exposición requiere seguimiento de gestión; se trata de una medición al corte, no de un pronóstico."
    elif item_type in {"DOCUMENT_REVIEW_OPPORTUNITY", "MANAGEMENT_DOCUMENT_REVIEW_CONTEXT"}:
        title = "Documentos que requieren revisión previa"
        detail = f"Hay {amount} de saldo pendiente con notas de crédito asociadas en el conjunto documental disponible."
        impact = "Conviene revisar el contexto documental antes de una gestión estándar. Una nota de crédito no prueba un error de facturación."
    elif item_type in {"PREVENTIVE_FOLLOW_UP_OPPORTUNITY", "MANAGEMENT_PREVENTIVE_EXPOSURE"}:
        title = "Saldo para seguimiento preventivo"
        detail = f"Hay {amount} de saldo pendiente que todavía no vencía al corte seleccionado."
        impact = (
            "Puede monitorearse antes del vencimiento; esto no constituye un pronóstico de pago."
        )
    elif item_type == "DATA_QUALITY_SCOPE":
        title = "Alcance y reglas de calidad documentados"
        detail = "Las fuentes, reglas de unión, moneda y exclusiones por fecha de corte están explícitas."
        impact = "Esto permite interpretar los resultados considerando las limitaciones de la muestra del hackathon."

    return {
        "title": title,
        "detail": detail,
        "impact": impact,
        "severity": item.get("severity", "INFO"),
        "evidence_refs": list(item.get("evidence_refs", [])),
        "technical_type": item_type,
    }


_ACTION_COPY = {
    "review_document_scope": (
        "Validar el alcance documental",
        "Revisar los pagos sin factura disponible antes de interpretar los pagos vinculados como el recaudo total.",
    ),
    "focus_review_on_concentrated_exposure": (
        "Priorizar clientes de mayor exposición",
        "Comenzar por los segmentos y clientes que concentran la mayor parte del saldo vencido, validando antes las incidencias documentales.",
    ),
    "focus_recovery_on_top_exposure": (
        "Focalizar el recupero en la mayor exposición",
        "Coordinar la gestión sobre los clientes con mayor saldo vencido; la prioridad de contacto sigue siendo responsabilidad de Cobranzas.",
    ),
    "create_dimension_recovery_workstream": (
        "Crear una gestión focalizada por segmento",
        "Revisar el segmento con mayor exposición y sus clientes principales como un frente de trabajo específico.",
    ),
    "monitor_preventive_exposure": (
        "Dar seguimiento preventivo",
        "Monitorear el saldo aún no vencido antes de su fecha de pago, sin tratarlo como cartera vencida.",
    ),
    "review_document_adjustments_before_contact": (
        "Revisar ajustes documentales antes de contactar",
        "Validar el contexto de notas de crédito asociadas antes de iniciar una gestión estándar.",
    ),
    "govern_overdue_exposure": (
        "Gestionar el saldo vencido",
        "Revisar la cartera vencida mediante recupero focalizado y manejo de excepciones.",
    ),
    "focus_dimension_governance": (
        "Empezar por la mayor concentración",
        "Iniciar la revisión con el grupo de mayor exposición y sus clientes principales.",
    ),
    "coordinate_top_exposure_workstream": (
        "Coordinar la gestión de clientes principales",
        "Alinear con Cobranzas la gestión de los clientes de mayor exposición usando sus prioridades operativas cuando estén disponibles.",
    ),
    "monitor_preventive_portfolio": (
        "Monitorear la cartera preventiva",
        "Dar seguimiento al saldo aún no vencido antes de sus fechas documentadas.",
    ),
    "review_adjustment_context": (
        "Validar el contexto de los ajustes",
        "Revisar los ajustes documentales antes de definir la siguiente acción de negocio.",
    ),
}


def _action_copy(item: dict[str, Any]) -> dict[str, Any]:
    action = item.get("action", "")
    title, detail = _ACTION_COPY.get(
        action,
        (
            "Acción recomendada",
            "Revisar la evidencia disponible antes de definir la siguiente acción.",
        ),
    )
    return {
        "title": title,
        "detail": detail,
        "evidence_refs": list(item.get("evidence_refs", [])),
        "technical_action": action,
    }


def _alert_copy(item: dict[str, Any]) -> dict[str, Any]:
    alert_type = item.get("type", "")
    if alert_type == "DATA_QUALITY_UNMATCHED_PAYMENTS":
        count = item.get("count", 0)
        return {
            "title": "Pagos sin factura vinculada",
            "detail": f"Se identificaron {count} pagos que no pudieron asociarse a una factura disponible en el dataset.",
            "impact": "Los pagos vinculados no deben interpretarse necesariamente como el recaudo total.",
            "severity": item.get("severity", "MEDIUM"),
            "evidence_refs": list(item.get("evidence_refs", [])),
            "technical_type": alert_type,
        }
    return {
        "title": "Limitación de calidad de información",
        "detail": "La evidencia disponible debe revisarse antes de tomar una decisión operativa.",
        "impact": "La limitación se mantiene separada de los hallazgos de negocio.",
        "severity": item.get("severity", "INFO"),
        "evidence_refs": list(item.get("evidence_refs", [])),
        "technical_type": alert_type,
    }


def _card(key: str, value: Any) -> dict[str, Any]:
    label, help_text, kind = METRIC_LABELS.get(
        key, ("Indicador", "Métrica calculada para el corte seleccionado.", "text")
    )
    return {
        "key": key,
        "label": label,
        "help": help_text,
        "value": value,
        "display_value": display_value(value, key),
        "kind": kind,
    }


def _kpis(response: dict[str, Any]) -> list[dict[str, Any]]:
    metrics = response.get("metrics", {})
    operation = response.get("operation")
    if operation == "executive_snapshot":
        keys = [
            "total_billed",
            "total_paid_linked",
            "outstanding_balance",
            "overdue_balance",
            "collection_ratio",
        ]
        return [_card(key, metrics[key]) for key in keys if key in metrics]
    if operation == "recovery_intelligence":
        keys = [
            "overdue_balance",
            "addressable_exposure",
            "top_n_customer_coverage",
            "preventive_open_balance",
        ]
        return [_card(key, metrics[key]) for key in keys if key in metrics]
    if operation == "management_insights":
        keys = [
            "outstanding_balance",
            "overdue_balance",
            "overdue_share_of_open_balance",
            "top_n_customer_coverage",
        ]
        return [_card(key, metrics[key]) for key in keys if key in metrics]
    if operation == "data_quality_report":
        keys = [
            "source_table_count",
            "invoice_rows",
            "unmatched_payment_count",
            "payments_after_as_of_count",
        ]
        return [_card(key, metrics[key]) for key in keys if key in metrics]
    if operation == "risk_concentration":
        cards = [_card("metric_total", metrics.get("metric_total"))]
        leading = _leading(response, "concentration_by_dimension")
        if leading:
            cards.append(
                {
                    "key": "leading_share",
                    "label": "Principal concentración",
                    "help": "Participación del grupo con mayor saldo vencido.",
                    "value": leading.get("share"),
                    "display_value": display_value(leading.get("share"), "share"),
                    "kind": "percent",
                }
            )
        count, coverage, _ = _pareto(response, "top_customers")
        if coverage is not None:
            cards.append(
                {
                    "key": "top_customers_coverage",
                    "label": f"Cobertura de los {count} principales clientes",
                    "help": "Porcentaje acumulado del saldo vencido cubierto por los clientes del ranking.",
                    "value": coverage,
                    "display_value": display_value(coverage, "coverage"),
                    "kind": "percent",
                }
            )
        return cards
    return []


def _chart_rows(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    result = []
    for row in rows:
        dimension = row.get("dimension")
        label = (
            display_dimension_value(dimension, row.get("value"))
            if row.get("value") is not None
            else str(row.get("customer") or row.get("bucket") or "Sin categoría")
        )
        amount = row.get("overdue_balance", row.get("outstanding_balance", 0))
        result.append(
            {
                "label": label,
                "amount": amount,
                "share": row.get("share"),
                "display_amount": display_value(amount, "overdue_balance"),
                "display_share": display_value(row.get("share"), "share")
                if row.get("share") is not None
                else None,
            }
        )
    return result


def _table(response: dict[str, Any], component: dict[str, Any]) -> dict[str, Any]:
    data = component.get("data")
    if component.get("type") == "opportunity_table":
        rows = [_finding_copy(item, response) for item in data] if isinstance(data, list) else []
        return {
            "title": "Oportunidades identificadas",
            "description": "Situaciones que requieren recupero, seguimiento preventivo o revisión documental.",
            "columns": ["Oportunidad", "Impacto", "Prioridad"],
            "rows": [[row["title"], row["detail"], row["severity"]] for row in rows],
        }
    rows = data if isinstance(data, list) else []
    columns = [
        "customer",
        "overdue_balance",
        "share",
        "account_count",
        "document_count",
        "cumulative_share",
    ]
    usable = [column for column in columns if rows and column in rows[0]]
    return {
        "title": "Clientes con mayor saldo vencido",
        "description": "Ranking por saldo vencido documentado al corte seleccionado.",
        "columns": [COLUMN_LABELS[column] for column in usable],
        "rows": [[display_value(row.get(column), column) for column in usable] for row in rows],
    }


def _components(response: dict[str, Any], dashboard: dict[str, Any]) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    for component in dashboard.get("components", []):
        kind = component.get("type")
        if kind == "kpi_cards":
            continue
        if kind == "aging_bar":
            components.append(
                {
                    "type": "bar_chart",
                    "title": "Antigüedad del saldo pendiente",
                    "description": "Saldo pendiente distribuido según días de vencimiento.",
                    "data": _chart_rows(component.get("data")),
                }
            )
        elif kind == "bar_chart":
            rows = component.get("data") or []
            dimension = cast(str, rows[0].get("dimension")) if rows else ""
            label = DIMENSION_LABELS.get(dimension, "grupo")
            components.append(
                {
                    "type": "bar_chart",
                    "title": f"Saldo vencido por {label}",
                    "description": "Cada barra muestra el importe y su participación en el saldo vencido analizado.",
                    "data": _chart_rows(rows),
                }
            )
        elif kind == "pareto_chart":
            rows = component.get("data") or []
            components.append(
                {
                    "type": "pareto_chart",
                    "title": "Saldo vencido concentrado en los principales clientes",
                    "description": f"Los {len(rows)} clientes del ranking se ordenan por saldo vencido y muestran su participación acumulada.",
                    "data": _chart_rows(rows),
                }
            )
        elif kind in {"ranking_table", "opportunity_table", "evidence_table"}:
            components.append({"type": "table", **_table(response, component)})
    return components


def presentation_for(response: dict[str, Any], dashboard: dict[str, Any]) -> dict[str, Any]:
    """Build the UI-only view model without mutating the technical response."""
    operation = response.get("operation", "")
    title, description = OPERATION_LABELS.get(
        operation, ("Análisis de negocio", "Resultado del análisis determinístico.")
    )
    return {
        "analysis": {
            "title": title,
            "description": description,
            "as_of_date": format_date(response.get("as_of_date", "")),
        },
        "kpis": _kpis(response),
        "components": _components(response, dashboard),
        "findings": [_finding_copy(item, response) for item in response.get("findings", [])],
        "recommended_actions": [
            _action_copy(item) for item in response.get("recommended_actions", [])
        ],
        "alerts": [_alert_copy(item) for item in response.get("alerts", [])],
    }
