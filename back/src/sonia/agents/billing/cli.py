"""Small local CLI for deterministic technical demonstrations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .agent import dispatch
from .service import BillingService


def main() -> None:
    parser = argparse.ArgumentParser(description="SON-IA Billing Assurance Agent v0.1")
    parser.add_argument("--dataset", required=True, type=Path, help="Directorio oficial de CSV o ZIP")
    parser.add_argument("--as-of-date", help="Corte YYYY-MM-DD; por defecto, última fecha observada")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("health")
    customer = sub.add_parser("customer"); customer.add_argument("customer_id"); customer.add_argument("--account")
    invoice = sub.add_parser("invoice"); invoice.add_argument("invoice_id")
    gaps = sub.add_parser("gaps"); gaps.add_argument("--customer"); gaps.add_argument("--account")
    notes = sub.add_parser("credit-notes"); notes.add_argument("--customer"); notes.add_argument("--account"); notes.add_argument("--invoice"); notes.add_argument("--threshold", default="0.25")
    args = parser.parse_args()
    common = {"as_of_date": args.as_of_date} if args.as_of_date else {}
    if args.command == "health":
        tool, parameters = "billing_health_snapshot", common
    elif args.command == "customer":
        tool, parameters = "customer_billing_check", {**common, "customer_id": args.customer_id, "account_id": args.account}
    elif args.command == "invoice":
        tool, parameters = "invoice_quality_check", {**common, "invoice_id": args.invoice_id}
    elif args.command == "gaps":
        tool, parameters = "billing_cycle_gaps", {**common, "customer_id": args.customer, "account_id": args.account}
    else:
        tool, parameters = "credit_note_review", {**common, "customer_id": args.customer, "account_id": args.account, "invoice_id": args.invoice, "materiality_threshold": args.threshold}
    print(json.dumps(dispatch(BillingService(args.dataset), tool, parameters), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
