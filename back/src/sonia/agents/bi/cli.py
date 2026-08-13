"""JSON CLI for deterministic BI Core v0.1."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .service import ALLOWED_DIMENSIONS, ALLOWED_METRICS, BIService


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="SON-IA BI Intelligence v0.2")
    result.add_argument("--dataset", type=Path, required=True, help="Directorio de los 6 CSV oficiales o ZIP oficial")
    result.add_argument("--as-of-date", default="2026-07-31", help="Corte ISO YYYY-MM-DD")
    result.add_argument("--collections-response", type=Path, help="JSON AgentResponse público de Cobranzas (referencia futura, no recalcula su score)")
    sub = result.add_subparsers(dest="command", required=True)
    sub.add_parser("data-quality")
    sub.add_parser("executive")
    risk = sub.add_parser("risk-concentration")
    risk.add_argument("--dimension", choices=sorted(ALLOWED_DIMENSIONS), default="SEGMENTO_PAIS")
    risk.add_argument("--metric", choices=sorted(ALLOWED_METRICS), default="overdue_balance")
    risk.add_argument("--top-n", type=int, default=10)
    recovery = sub.add_parser("recovery")
    recovery.add_argument("--scope", default="PORTFOLIO")
    recovery.add_argument("--dimension", choices=sorted(ALLOWED_DIMENSIONS), default="SEGMENTO_PAIS")
    recovery.add_argument("--top-n", type=int, default=10)
    insights = sub.add_parser("insights")
    insights.add_argument("--dimension", choices=sorted(ALLOWED_DIMENSIONS), default="SEGMENTO_PAIS")
    insights.add_argument("--top-n", type=int, default=10)
    return result


def main() -> None:
    args = parser().parse_args()
    collections_payload = json.loads(args.collections_response.read_text(encoding="utf-8")) if args.collections_response else None
    service = BIService(args.dataset, collections_payload)
    if args.command == "data-quality":
        payload = service.data_quality_report(args.as_of_date)
    elif args.command == "executive":
        payload = service.executive_snapshot(args.as_of_date)
    elif args.command == "recovery":
        payload = service.recovery_intelligence(args.as_of_date, args.scope, args.dimension, args.top_n)
    elif args.command == "insights":
        payload = service.management_insights(args.as_of_date, args.dimension, args.top_n)
    else:
        payload = service.risk_concentration(args.dimension, args.metric, args.top_n, args.as_of_date)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
