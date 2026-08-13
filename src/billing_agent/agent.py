"""Closed Billing tool catalogue and validated deterministic dispatch."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from .model import parse_date
from .service import BillingService

SYSTEM_PROMPT = """Eres SON-IA Billing Assurance. Solo puedes seleccionar una de las cinco
tools autorizadas. Nunca calcules importes, ratios, materialidad ni quiebres: usa una tool.
No inventes datos, documentos, clientes, causas ni nuevas reglas. No respondas consultas de
pagos, deuda, mora, recupero o BI. HEURISTIC es un candidato de revisión, no un hecho.
Devuelve exclusivamente una selección estructurada de tool y argumentos válidos."""

TOOL_NAMES = frozenset({
    "billing_health_snapshot",
    "customer_billing_check",
    "invoice_quality_check",
    "billing_cycle_gaps",
    "credit_note_review",
})


def tool_schemas() -> list[dict[str, Any]]:
    """Schemas closed to the known BillingService operations only."""
    date_property = {"type": "string", "description": "Fecha ISO YYYY-MM-DD opcional."}
    customer = {"type": "string", "pattern": "^CLIENT_[0-9]+$"}
    account = {"type": "string", "pattern": "^[0-9]+$"}
    invoice = {"type": "string", "description": "NRO_DOC_FISCAL de factura."}
    threshold = {"type": "number", "minimum": 0, "maximum": 1}
    return [
        {"type": "function", "name": "billing_health_snapshot", "description": "Resumen de calidad y excepciones de facturación.", "parameters": {"type": "object", "properties": {"as_of_date": date_property}, "additionalProperties": False}},
        {"type": "function", "name": "customer_billing_check", "description": "Reconstruir cliente, cuentas, planta, facturas y notas de crédito.", "parameters": {"type": "object", "properties": {"customer_id": customer, "account_id": account, "as_of_date": date_property}, "required": ["customer_id"], "additionalProperties": False}},
        {"type": "function", "name": "invoice_quality_check", "description": "Validar campos, cálculo documental y ajustes de una factura.", "parameters": {"type": "object", "properties": {"invoice_id": invoice, "as_of_date": date_property}, "required": ["invoice_id"], "additionalProperties": False}},
        {"type": "function", "name": "billing_cycle_gaps", "description": "Buscar candidatos de ausencia documental entre facturas cíclicas.", "parameters": {"type": "object", "properties": {"customer_id": customer, "account_id": account, "as_of_date": date_property}, "additionalProperties": False}},
        {"type": "function", "name": "credit_note_review", "description": "Revisar ajustes post-emisión y materialidad de notas de crédito.", "parameters": {"type": "object", "properties": {"customer_id": customer, "account_id": account, "invoice_id": invoice, "materiality_threshold": threshold, "as_of_date": date_property}, "additionalProperties": False}},
    ]


_ALLOWED_ARGUMENTS = {
    "billing_health_snapshot": {"as_of_date"},
    "customer_billing_check": {"customer_id", "account_id", "as_of_date"},
    "invoice_quality_check": {"invoice_id", "as_of_date"},
    "billing_cycle_gaps": {"customer_id", "account_id", "as_of_date"},
    "credit_note_review": {"customer_id", "account_id", "invoice_id", "materiality_threshold", "as_of_date"},
}


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} debe ser texto no vacío.")
    return value.strip()


def validate_arguments(tool_name: str, arguments: dict[str, Any], default_as_of_date: str | None = None) -> dict[str, Any]:
    """Normalize only documented scalar arguments; reject extras and executable input."""
    if tool_name not in TOOL_NAMES:
        raise ValueError("La tool solicitada no está autorizada para Facturación.")
    if not isinstance(arguments, dict):
        raise ValueError("Los argumentos de la tool deben ser un objeto JSON.")
    if set(arguments) - _ALLOWED_ARGUMENTS[tool_name]:
        raise ValueError("La tool recibió parámetros no autorizados.")
    values = dict(arguments)
    for key in ("customer_id", "account_id", "invoice_id", "as_of_date"):
        if key in values and values[key] is not None:
            values[key] = _text(values[key], key)
    if "customer_id" in values:
        values["customer_id"] = values["customer_id"].upper()
        if not values["customer_id"].startswith("CLIENT_"):
            raise ValueError("customer_id debe tener formato CLIENT_XXXXX.")
    if "account_id" in values and not values["account_id"].isdigit():
        raise ValueError("account_id debe contener solo dígitos.")
    if "as_of_date" in values:
        parsed = parse_date(values["as_of_date"])
        if not parsed or parsed.isoformat() != values["as_of_date"]:
            raise ValueError("as_of_date debe tener formato YYYY-MM-DD.")
    elif default_as_of_date:
        # The service owns the default criterion; this only makes the selected call explicit.
        parsed = parse_date(default_as_of_date)
        if not parsed:
            raise ValueError("default_as_of_date no es válida.")
        values["as_of_date"] = parsed.isoformat()
    required = {"customer_billing_check": "customer_id", "invoice_quality_check": "invoice_id"}
    if tool_name in required and not values.get(required[tool_name]):
        raise ValueError(f"{required[tool_name]} es obligatorio.")
    if "materiality_threshold" in values:
        try:
            threshold = Decimal(str(values["materiality_threshold"]))
        except (InvalidOperation, ValueError) as error:
            raise ValueError("materiality_threshold debe ser un número entre 0 y 1.") from error
        if not Decimal("0") <= threshold <= Decimal("1"):
            raise ValueError("materiality_threshold debe estar entre 0 y 1.")
        values["materiality_threshold"] = str(threshold)
    return values


def dispatch(service: BillingService, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """The only dynamic call boundary: name and arguments are validated first."""
    values = validate_arguments(tool_name, arguments)
    routes: dict[str, Callable[[], dict[str, Any]]] = {
        "billing_health_snapshot": lambda: service.billing_health_snapshot(values.get("as_of_date")),
        "customer_billing_check": lambda: service.customer_billing_check(values["customer_id"], values.get("account_id"), values.get("as_of_date")),
        "invoice_quality_check": lambda: service.invoice_quality_check(values["invoice_id"], values.get("as_of_date")),
        "billing_cycle_gaps": lambda: service.billing_cycle_gaps(values.get("as_of_date"), values.get("customer_id"), values.get("account_id")),
        "credit_note_review": lambda: service.credit_note_review(values.get("as_of_date"), values.get("customer_id"), values.get("account_id"), values.get("invoice_id"), Decimal(values.get("materiality_threshold", "0.25"))),
    }
    return routes[tool_name]()
