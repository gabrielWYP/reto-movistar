"""Explicit deterministic business rules for collections and reconciliation."""

from __future__ import annotations

from decimal import Decimal


TOLERANCE = Decimal("0.01")
PRIORITY_WEIGHTS = {
    "overdue_amount": Decimal("45"),
    "days_past_due": Decimal("30"),
    "overdue_share": Decimal("15"),
    "portfolio_concentration": Decimal("10"),
}
PRIORITY_HIGH_THRESHOLD = Decimal("60")
PRIORITY_MEDIUM_THRESHOLD = Decimal("30")


def aging_bucket(days: int | None) -> str:
    if days is None:
        return "SIN_FECHA_VENCIMIENTO"
    if days == 0:
        return "NO_VENCIDA"
    if days <= 30:
        return "1_30"
    if days <= 60:
        return "31_60"
    if days <= 90:
        return "61_90"
    return "90_PLUS"


def priority_level(score: Decimal) -> str:
    if score >= PRIORITY_HIGH_THRESHOLD:
        return "HIGH"
    if score >= PRIORITY_MEDIUM_THRESHOLD:
        return "MEDIUM"
    return "LOW"
