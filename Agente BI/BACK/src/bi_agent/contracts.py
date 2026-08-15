"""JSON-safe response contract compatible with the SON-IA agent pattern."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

CONTRACT_VERSION = "1.0"


def json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value.quantize(Decimal("0.01")))
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    return value


@dataclass(slots=True)
class AgentResponse:
    operation: str
    as_of_date: date
    entity: dict[str, Any] = field(default_factory=lambda: {"type": "portfolio", "id": "all"})
    status: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    aging: list[dict[str, Any]] = field(default_factory=list)
    reconciliation: dict[str, Any] = field(default_factory=dict)
    findings: list[dict[str, Any]] = field(default_factory=list)
    alerts: list[dict[str, Any]] = field(default_factory=list)
    recommended_actions: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    data_quality: dict[str, Any] = field(default_factory=dict)
    visualization_hints: list[dict[str, Any]] = field(default_factory=list)
    analysis_scope: dict[str, Any] = field(default_factory=dict)
    methodology: dict[str, Any] = field(default_factory=dict)
    upstream_inputs: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return json_value({"contract_version": CONTRACT_VERSION, "agent": "bi", **asdict(self)})
