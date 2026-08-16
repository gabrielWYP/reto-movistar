"""Conversational runtime above the deterministic BillingService boundary.

It is deliberately finite: one classified intent may invoke one closed-catalogue
tool, then returns a grounded explanation. Session context is memory-only and
never contains raw CSV rows.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from .agent import TOOL_NAMES, dispatch, validate_arguments
from .presentation import conversational_narrative
from .service import BillingService

CUSTOMER_RE = re.compile(r"\b(CLIENT_\d+)\b", re.IGNORECASE)
ACCOUNT_RE = re.compile(r"\b(?:cuenta\s*(?:n[°ºo.]?\s*)?)?(\d{6,})\b", re.IGNORECASE)
INVOICE_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,8}-\d{4,})\b", re.IGNORECASE)
DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
PERCENT_RE = re.compile(r"(?:mayor(?:es)?\s+(?:al|a)|sobre|superior(?:es)?\s+(?:al|a)|>=?\s*)?(\d{1,3}(?:[.,]\d+)?)\s*%", re.IGNORECASE)

COLLECTIONS_TERMS = ("debe", "deuda", "pago", "pagó", "pago", "vencid", "mora", "cobrar", "cobranza", "recaud", "saldo")
BI_TERMS = ("segmento", "estrategia", "recuper", "concentr", "riesgo de recuper")
INJECTION_TERMS = ("os.system", "subprocess", "delete_invoice", "delete invoice", "nueva herramienta", "new tool", "ejecuta python", "run python", "ignore previous")


class LLMRuntime(Protocol):
    @property
    def available(self) -> bool: ...

    def select_tool(self, question: str) -> dict[str, Any]: ...

    def interpret(self, question: str, compact_result: dict[str, Any]) -> str: ...


@dataclass
class SessionContext:
    customer_id: str | None = None
    account_id: str | None = None
    invoice_id: str | None = None
    last_tool: str | None = None
    last_response: dict[str, Any] | None = None


@dataclass(frozen=True)
class RoutingDecision:
    intent: str
    tool: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    status: str = "READY"
    target_agent: str | None = None
    answer: str | None = None


@dataclass(frozen=True)
class AgentResult:
    intent: str
    route: str
    answer: str
    status: str
    tool: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    agent_response: dict[str, Any] | None = None
    trace: dict[str, Any] = field(default_factory=dict)
    target_agent: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": "billing",
            "intent": self.intent,
            "route": self.route,
            "tool": self.tool,
            "arguments": self.arguments,
            "answer": self.answer,
            "status": self.status,
            "agent_response": self.agent_response,
            "trace": self.trace,
            **({"target_agent": self.target_agent} if self.target_agent else {}),
        }


def _identifiers(question: str, context: SessionContext) -> dict[str, str]:
    customer = CUSTOMER_RE.search(question)
    invoice = INVOICE_RE.search(question)
    account = ACCOUNT_RE.search(question)
    found: dict[str, str] = {}
    if customer:
        found["customer_id"] = customer.group(1).upper()
    elif context.customer_id and not invoice:
        found["customer_id"] = context.customer_id
    text = question.lower()
    if invoice:
        found["invoice_id"] = invoice.group(1).upper()
    elif context.invoice_id and any(term in text for term in ("por qué", "porque", "marcada", "requiere valid", "esta factura", "la factura", "ese documento")):
        found["invoice_id"] = context.invoice_id
    # Numeric dates are not accepted as accounts, and an account only inherits from
    # context when the user refers to an account/this account.
    if account and "-" not in account.group(1) and ("cuenta" in text or not invoice):
        found["account_id"] = account.group(1)
    elif context.account_id and any(term in question.lower() for term in ("cuenta", "esta cuenta", "la cuenta", "quiebre", "ciclo", "en junio")):
        found["account_id"] = context.account_id
    date_value = DATE_RE.search(question)
    if date_value:
        found["as_of_date"] = date_value.group(1)
    return found


def _threshold(question: str) -> str | None:
    match = PERCENT_RE.search(question)
    if not match:
        return None
    value = float(match.group(1).replace(",", ".")) / 100
    return str(value)


def deterministic_route(question: str, context: SessionContext | None = None) -> RoutingDecision:
    """Classify Spanish demo phrasing without calling a provider or making calculations."""
    context = context or SessionContext()
    text = question.strip().lower()
    ids = _identifiers(question, context)
    if not text:
        return RoutingDecision("clarification_required", status="CLARIFICATION_REQUIRED", answer="Escribe una consulta de Facturación, por ejemplo: “Revisa la factura S300-0256413”.")
    if any(term in text for term in INJECTION_TERMS):
        return RoutingDecision("out_of_scope", status="SAFETY_REJECTED", answer="Solo puedo usar el catálogo cerrado de validaciones de Facturación; no ejecuto código ni herramientas nuevas.")
    if any(term in text for term in BI_TERMS):
        return RoutingDecision("out_of_scope", status="HANDOFF_RECOMMENDED", target_agent="bi", answer="Esta consulta requiere el Agente de BI; Facturación no calcula estrategia, concentración ni riesgo de recupero.")
    if re.search(r"\bdebe\b", text) or any(re.search(rf"\b{re.escape(term)}", text) for term in COLLECTIONS_TERMS if term != "debe"):
        return RoutingDecision("out_of_scope", status="HANDOFF_RECOMMENDED", target_agent="collections", answer="Esta consulta corresponde al Agente de Cobranzas/Recaudación. Facturación no usa pagos, deuda, mora ni recupero.")
    if ("por qué" in text or "porque" in text) and ("nota" in text or "crédito" in text or "credito" in text) and ("ocurri" in text or "gener" in text):
        return RoutingDecision("data_limitation", status="DATA_LIMITATION", answer="El dataset no contiene el motivo de la nota de crédito. Puedo mostrar su factura afectada, materialidad y trazabilidad documental, pero no determinar la causa.")
    if any(term in text for term in ("quiebre", "quiebres", "ciclo", "sin evidencia", "en junio")):
        if not ids.get("customer_id") and ids.get("account_id"):
            return RoutingDecision("clarification_required", status="CLARIFICATION_REQUIRED", answer="Indica el CLIENT_XXXXX de la cuenta para revisar un posible quiebre documental.")
        return RoutingDecision("cycle_gap_review", "billing_cycle_gaps", {key: ids[key] for key in ("customer_id", "account_id", "as_of_date") if key in ids})
    if any(term in text for term in ("nota de crédito", "nota de credito", "notas de crédito", "notas de credito", "ajuste", "nc")):
        args = {key: ids[key] for key in ("customer_id", "account_id", "invoice_id", "as_of_date") if key in ids}
        threshold = _threshold(question)
        if threshold:
            args["materiality_threshold"] = threshold
        return RoutingDecision("credit_note_review", "credit_note_review", args)
    if "factura" in text or ids.get("invoice_id"):
        if not ids.get("invoice_id"):
            return RoutingDecision("clarification_required", status="CLARIFICATION_REQUIRED", answer="Indica el NRO_DOC_FISCAL de la factura que deseas revisar.")
        return RoutingDecision("invoice_review", "invoice_quality_check", {key: ids[key] for key in ("invoice_id", "as_of_date") if key in ids})
    if "cliente" in text or ids.get("customer_id") or ("cuenta" in text and context.customer_id):
        if not ids.get("customer_id"):
            return RoutingDecision("clarification_required", status="CLARIFICATION_REQUIRED", answer="Indica el identificador del cliente, por ejemplo CLIENT_00434.")
        return RoutingDecision("customer_review", "customer_billing_check", {key: ids[key] for key in ("customer_id", "account_id", "as_of_date") if key in ids})
    if any(term in text for term in ("revisar hoy", "qué debería", "que deberia", "resumen", "estado", "excepciones", "hoy")):
        return RoutingDecision("portfolio_health", "billing_health_snapshot", {key: ids[key] for key in ("as_of_date",) if key in ids})
    return RoutingDecision("clarification_required", status="CLARIFICATION_REQUIRED", answer="Puedo revisar el portafolio, un CLIENT_XXXXX, una factura, quiebres de ciclo o notas de crédito. ¿Qué deseas consultar?")


def compact_for_llm(payload: dict[str, Any]) -> dict[str, Any]:
    """Bounded derivative of AgentResponse: no CSV rows or unrestricted evidence."""
    findings = payload.get("findings", [])[:12]
    return {
        "operation": payload.get("operation"),
        "as_of_date": payload.get("as_of_date"),
        "entity": payload.get("entity"),
        "status": payload.get("status"),
        "metrics": payload.get("metrics"),
        "findings": [{key: item.get(key) for key in ("type", "severity", "rule_category", "message", "observed_value", "evidence_refs", "recommended_validation")} for item in findings],
        "recommended_actions": payload.get("recommended_actions", [])[:5],
        "evidence_refs": [item.get("id") for item in payload.get("evidence", [])[:20]],
        "data_quality": {"known_limitations": payload.get("data_quality", {}).get("known_limitations", [])[:8]},
    }


class BillingAgentRuntime:
    """Reusable supervisor-facing runtime; it is independent from HTTP and HTML."""

    def __init__(self, service: BillingService, llm: LLMRuntime | None = None):
        self.service = service
        self.llm = llm

    def ask(self, question: str, context: SessionContext | None = None, as_of_date: str | None = None) -> dict[str, Any]:
        if not isinstance(question, str) or not question.strip() or len(question) > 1000:
            raise ValueError("La pregunta debe ser texto no vacío de hasta 1000 caracteres.")
        context = context or SessionContext()
        started = time.perf_counter()
        selected = deterministic_route(question, context)
        route = "deterministic"
        if selected.status != "READY":
            return AgentResult(selected.intent, route, selected.answer or "", selected.status, target_agent=selected.target_agent, trace={"intent": selected.intent, "router": route, "tool": None, "arguments": {}, "elapsed_ms": round((time.perf_counter() - started) * 1000, 2)}).to_dict()

        # An optional provider can improve flexible phrasing. It receives only the
        # question and the closed schemas in phase one. Any fault stays local.
        if self.llm and self.llm.available and not (context.last_response and not re.search(r"CLIENT_|[A-Z0-9]+-\d+", question, re.I)):
            try:
                proposal = self.llm.select_tool(question)
                proposed_tool = proposal.get("tool_name")
                proposed_args = proposal.get("arguments")
                if proposed_tool not in TOOL_NAMES:
                    raise ValueError("La tool propuesta por el LLM no está autorizada.")
                selected = RoutingDecision(selected.intent, proposed_tool, validate_arguments(proposed_tool, proposed_args, as_of_date or self.service.default_as_of_date().isoformat()))
                route = "llm"
            except Exception as error:
                route = "fallback"

        arguments = dict(selected.arguments)
        if as_of_date and "as_of_date" not in arguments:
            arguments["as_of_date"] = as_of_date
        arguments = validate_arguments(selected.tool or "", arguments, self.service.default_as_of_date().isoformat())
        try:
            response = dispatch(self.service, selected.tool or "", arguments)
        except (KeyError, ValueError) as error:
            return AgentResult(selected.intent, route, str(error), "INPUT_ERROR", selected.tool, arguments, trace={"intent": selected.intent, "router": route, "tool": selected.tool, "arguments": arguments, "elapsed_ms": round((time.perf_counter() - started) * 1000, 2)}).to_dict()
        answer = conversational_narrative(response)
        if route == "llm" and self.llm:
            try:
                answer = self.llm.interpret(question, compact_for_llm(response))
            except Exception:
                route = "fallback"
                answer = conversational_narrative(response)
        context.customer_id = arguments.get("customer_id") or response.get("entity", {}).get("customer_id") or context.customer_id
        context.account_id = arguments.get("account_id") or response.get("entity", {}).get("account_id") or context.account_id
        context.invoice_id = arguments.get("invoice_id") or (response.get("entity", {}).get("id") if response.get("entity", {}).get("type") == "invoice" else context.invoice_id)
        context.last_tool, context.last_response = selected.tool, response
        status = response.get("status", {}).get("billing_assurance", "RESULT_AVAILABLE")
        trace = {
            "intent": selected.intent,
            "router": route,
            "tool": selected.tool,
            "arguments": arguments,
            "status": status,
            "evidence_refs": [item.get("id") for item in response.get("evidence", [])[:20]],
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        }
        return AgentResult(selected.intent, route, answer, status, selected.tool, arguments, response, trace).to_dict()
