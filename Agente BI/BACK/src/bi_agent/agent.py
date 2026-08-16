"""Public BI Agent boundary: intent routing, safe dispatch and deterministic narration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from .prompting import prompt_metadata
from .service import ALLOWED_DIMENSIONS, ALLOWED_METRICS, BIService

TOOL_NAMES = {
    "executive_snapshot",
    "risk_concentration",
    "recovery_intelligence",
    "management_insights",
    "data_quality_report",
}


@dataclass(frozen=True, slots=True)
class AgentResult:
    answer: str
    tool_name: str
    tool_arguments: dict[str, Any]
    agent_response: dict[str, Any]
    mode: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "tool_used": self.tool_name,
            "tool_arguments": self.tool_arguments,
            "agent_response": self.agent_response,
            "mode": self.mode,
        }


def tool_schemas() -> list[dict[str, Any]]:
    """Closed schemas for direct function calling; no arbitrary expressions are allowed."""
    date_property = {"type": "string", "description": "Fecha de corte ISO YYYY-MM-DD."}
    dimension = {"type": "string", "enum": sorted(ALLOWED_DIMENSIONS)}
    top_n = {"type": "integer", "minimum": 1, "maximum": 100}
    return [
        {
            "type": "function",
            "name": "executive_snapshot",
            "description": "Resumen ejecutivo del ciclo de ingresos, cartera y ageing.",
            "parameters": {
                "type": "object",
                "properties": {"as_of_date": date_property},
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "risk_concentration",
            "description": "Concentración/Pareto de riesgo por dimensión autorizada.",
            "parameters": {
                "type": "object",
                "properties": {
                    "as_of_date": date_property,
                    "dimension": dimension,
                    "metric": {"type": "string", "enum": sorted(ALLOWED_METRICS)},
                    "top_n": top_n,
                },
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "recovery_intelligence",
            "description": "Oportunidades de recupero por impacto, concentración y contexto documental.",
            "parameters": {
                "type": "object",
                "properties": {
                    "as_of_date": date_property,
                    "scope": {"type": "string", "enum": ["PORTFOLIO"]},
                    "dimension": dimension,
                    "top_n": top_n,
                },
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "management_insights",
            "description": "Síntesis ejecutiva de riesgos, oportunidades y acciones.",
            "parameters": {
                "type": "object",
                "properties": {"as_of_date": date_property, "dimension": dimension, "top_n": top_n},
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "data_quality_report",
            "description": "Limitaciones, joins, exclusiones y calidad de los datos.",
            "parameters": {
                "type": "object",
                "properties": {"as_of_date": date_property},
                "additionalProperties": False,
            },
        },
    ]


def _dimension_from_question(question: str) -> str:
    normalized = question.lower()
    options = [
        ("SUNAT_DEPARTAMENTO", ("departamento", "zona", "geograf")),
        ("SISTEMA", ("sistema",)),
        ("FUENTE", ("fuente", "facturaci")),
        ("SERVICE_PROFILE", ("producto", "servicio", "tecnolog", "planta")),
    ]
    return next(
        (dimension for dimension, terms in options if any(term in normalized for term in terms)),
        "SEGMENTO_PAIS",
    )


def deterministic_route(question: str, as_of_date: str) -> tuple[str, dict[str, Any]]:
    """Safe no-key fallback for Spanish demo questions; it is an intent router, not a calculator."""
    text = question.lower().strip()
    if any(
        term in text for term in ("limitaci", "calidad", "confiable", "join", "asociar", "excluid")
    ):
        return "data_quality_report", {"as_of_date": as_of_date}
    if any(
        term in text
        for term in ("recuper", "abordable", "preventiv", "documento", "atacar primero")
    ):
        return "recovery_intelligence", {
            "as_of_date": as_of_date,
            "scope": "PORTFOLIO",
            "dimension": _dimension_from_question(text),
            "top_n": 10,
        }
    if any(
        term in text
        for term in (
            "gerencia",
            "priorizar",
            "principal",
            "recomendar",
            "qué debería",
            "que deberia",
            "riesgo más",
        )
    ):
        return "management_insights", {
            "as_of_date": as_of_date,
            "dimension": _dimension_from_question(text),
            "top_n": 10,
        }
    if any(
        term in text
        for term in (
            "concentr",
            "distribu",
            "segmento",
            "departamento",
            "sistema",
            "fuente",
            "mayor parte",
            "pareto",
        )
    ):
        return "risk_concentration", {
            "as_of_date": as_of_date,
            "dimension": _dimension_from_question(text),
            "metric": "overdue_balance",
            "top_n": 10,
        }
    return "executive_snapshot", {"as_of_date": as_of_date}


def validate_arguments(
    tool_name: str, arguments: dict[str, Any], as_of_date: str
) -> dict[str, Any]:
    if tool_name not in TOOL_NAMES:
        raise ValueError("La tool solicitada no está autorizada para BI.")
    if not isinstance(arguments, dict):
        raise ValueError("Los argumentos de la tool deben ser un objeto JSON.")
    allowed = {
        "executive_snapshot": {"as_of_date"},
        "data_quality_report": {"as_of_date"},
        "risk_concentration": {"as_of_date", "dimension", "metric", "top_n"},
        "recovery_intelligence": {"as_of_date", "scope", "dimension", "top_n"},
        "management_insights": {"as_of_date", "dimension", "top_n"},
    }[tool_name]
    if set(arguments) - allowed:
        raise ValueError("La tool recibió parámetros no autorizados.")
    values = dict(arguments)
    values["as_of_date"] = as_of_date  # UI/supervisor cut-off wins over an LLM suggestion.
    date.fromisoformat(values["as_of_date"])
    if "dimension" in values:
        values["dimension"] = str(values["dimension"]).upper()
        if values["dimension"] not in ALLOWED_DIMENSIONS:
            raise ValueError("Dimensión no autorizada.")
    if "metric" in values:
        values["metric"] = str(values["metric"]).lower()
        if values["metric"] not in ALLOWED_METRICS:
            raise ValueError("Métrica no autorizada.")
    if "scope" in values and values["scope"].upper() != "PORTFOLIO":
        raise ValueError("El alcance autorizado es PORTFOLIO.")
    if "scope" in values:
        values["scope"] = "PORTFOLIO"
    if "top_n" in values:
        if (
            isinstance(values["top_n"], bool)
            or not isinstance(values["top_n"], int)
            or not 1 <= values["top_n"] <= 100
        ):
            raise ValueError("top_n debe ser un entero entre 1 y 100.")
    return values


def dispatch(
    service: BIService, tool_name: str, arguments: dict[str, Any], as_of_date: str
) -> dict[str, Any]:
    values = validate_arguments(tool_name, arguments, as_of_date)
    routes: dict[str, Callable[[], dict[str, Any]]] = {
        "executive_snapshot": lambda: service.executive_snapshot(values["as_of_date"]),
        "data_quality_report": lambda: service.data_quality_report(values["as_of_date"]),
        "risk_concentration": lambda: service.risk_concentration(
            values.get("dimension", "SEGMENTO_PAIS"),
            values.get("metric", "overdue_balance"),
            values.get("top_n", 10),
            values["as_of_date"],
        ),
        "recovery_intelligence": lambda: service.recovery_intelligence(
            values["as_of_date"],
            values.get("scope", "PORTFOLIO"),
            values.get("dimension", "SEGMENTO_PAIS"),
            values.get("top_n", 10),
        ),
        "management_insights": lambda: service.management_insights(
            values["as_of_date"], values.get("dimension", "SEGMENTO_PAIS"), values.get("top_n", 10)
        ),
    }
    return routes[tool_name]()


def _money(value: Any) -> str:
    return f"S/ {float(value or 0):,.2f}"


def deterministic_narrative(payload: dict[str, Any]) -> str:
    """Compact, grounded fallback that only reads the original AgentResponse."""
    metrics, findings, alerts, actions = (
        payload.get("metrics", {}),
        payload.get("findings", []),
        payload.get("alerts", []),
        payload.get("recommended_actions", []),
    )
    operation = payload.get("operation")
    if operation == "executive_snapshot":
        answer = f"Al {payload['as_of_date']}, el saldo pendiente documentado es {_money(metrics.get('outstanding_balance'))}; {_money(metrics.get('overdue_balance'))} está vencido."
    elif operation == "risk_concentration":
        lead = findings[0] if findings else {}
        answer = f"La exposición analizada es {_money(metrics.get('metric_total'))}. El principal foco es {lead.get('value', 'sin grupo dominante')} con {float(lead.get('share', 0)):.0%} del saldo vencido analizado."
    elif operation == "recovery_intelligence":
        answer = f"La oportunidad de recupero documentada alcanza {_money(metrics.get('addressable_exposure'))}, equivalente a {float(metrics.get('top_n_customer_coverage', 0)):.0%} del saldo vencido en los principales casos."
    elif operation == "management_insights":
        answer = f"La gerencia debería focalizar el saldo vencido documentado de {_money(metrics.get('overdue_balance'))}; los hallazgos están ordenados por impacto y respaldados por evidencia."
    else:
        exclusions = payload.get("data_quality", {}).get("as_of_exclusions", {})
        answer = f"La evaluación de calidad identifica {exclusions.get('unmatched_payment_count', 0)} pagos sin factura disponible en el conjunto analizado."
    finding_labels = {
        "OVERDUE_EXPOSURE": "existe saldo documentado que ya superó su fecha de vencimiento.",
        "RISK_CONCENTRATION": "la exposición está concentrada; esta medición no prueba causalidad.",
        "IMMEDIATE_RECOVERY_OPPORTUNITY": "un grupo limitado de clientes concentra una oportunidad material de recupero.",
        "DIMENSION_RECOVERY_CONCENTRATION": "una dimensión de negocio concentra la mayor parte de la exposición vencida.",
        "MANAGEMENT_DIMENSION_CONCENTRATION": "la concentración por dimensión merece una gestión focalizada.",
        "MANAGEMENT_OVERDUE_EXPOSURE": "la mayor parte del saldo abierto ya está vencida.",
        "MANAGEMENT_RECOVERY_COVERAGE": "los principales clientes cubren una porción relevante del riesgo documentado.",
        "DATA_QUALITY_SCOPE": "las reglas de join, moneda y exclusiones están documentadas para revisión.",
    }
    action_labels = {
        "review_document_scope": "validar los pagos sin factura disponible antes de interpretar el ratio vinculado como recaudo total.",
        "focus_review_on_concentrated_exposure": "revisar primero los grupos y clientes con mayor exposición documentada.",
        "focus_recovery_on_top_exposure": "coordinar una gestión focalizada sobre las mayores exposiciones; la prioridad operativa sigue siendo de Cobranzas.",
        "govern_overdue_exposure": "gestionar la exposición vencida mediante un frente de recupero y validación de excepciones.",
    }
    if findings:
        answer += f" Hallazgo principal: {finding_labels.get(findings[0].get('type'), 'el hallazgo está respaldado por la evidencia mostrada.')}"
    if actions:
        answer += f" Acción sugerida: {action_labels.get(actions[0].get('action'), 'revisar la evidencia antes de ejecutar una acción de negocio.')}"
    if alerts:
        answer += " Limitación: existen pagos que apuntan a documentos no disponibles en el conjunto de facturas; el recaudo vinculado no equivale necesariamente al recaudo total."
    return answer.strip()


def _apply_question_guardrails(question: str, answer: str) -> str:
    """Add deterministic scope clarification without creating new metrics."""
    normalized = question.casefold()
    if any(
        term in normalized
        for term in ("predice", "predicción", "pronóstico", "forecast", "próximo mes")
    ):
        return (
            "No existe una herramienta predictiva en este MVP, por lo que no puedo "
            "afirmar la mora futura. " + answer
        )
    if "por qué" in normalized and any(term in normalized for term in ("no paga", "mora", "deuda")):
        return (
            "La información disponible permite describir concentración o asociación, "
            "pero no demostrar la causa del comportamiento de pago. " + answer
        )
    mentions_usd = any(term in normalized for term in ("dólar", "dolar", "usd"))
    mentions_pen = any(term in normalized for term in ("soles", "pen", "sol "))
    if mentions_usd and mentions_pen:
        return (
            "No se suman PEN y USD: los KPIs monetarios de este MVP consideran "
            "únicamente PEN. " + answer
        )
    return answer


def ask(
    service: BIService, question: str, as_of_date: str, runtime: Any | None = None
) -> dict[str, Any]:
    """Public supervisor/UI interface. Runtime is optional; deterministic mode always works."""
    if not isinstance(question, str) or not question.strip() or len(question) > 1000:
        raise ValueError("La pregunta debe ser texto no vacío de hasta 1000 caracteres.")
    if runtime and runtime.available:
        selected = runtime.select_tool(question, as_of_date)
        payload = dispatch(service, selected["tool_name"], selected["arguments"], as_of_date)
        answer = runtime.interpret(question, payload)
        mode = "llm"
        tool_name, arguments = (
            selected["tool_name"],
            validate_arguments(selected["tool_name"], selected["arguments"], as_of_date),
        )
    else:
        tool_name, arguments = deterministic_route(question, as_of_date)
        payload = dispatch(service, tool_name, arguments, as_of_date)
        answer = _apply_question_guardrails(question, deterministic_narrative(payload))
        mode = "deterministic"
    result = AgentResult(answer, tool_name, arguments, payload, mode).to_dict()
    if mode == "llm" and runtime is not None:
        result["prompt"] = prompt_metadata()
        result["llm"] = runtime.metadata()
    return result
