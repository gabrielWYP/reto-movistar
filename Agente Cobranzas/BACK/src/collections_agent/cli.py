"""CLI to demo each tool with no API key or LLM token consumption."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import CollectionsSettings
from .service import CollectionsService


def default_dataset() -> Path | None:
    return CollectionsSettings.from_environment().dataset_path


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="SON-IA Cobranzas/Recaudación")
    result.add_argument("--dataset", type=Path, default=default_dataset())
    sub = result.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--as-of-date", help="Fecha de corte ISO: YYYY-MM-DD")
    sub.add_parser("portfolio", parents=[common])
    customer = sub.add_parser("customer", parents=[common])
    customer.add_argument("customer_id")
    invoice = sub.add_parser("invoice", parents=[common])
    invoice.add_argument("document")
    priorities = sub.add_parser("priorities", parents=[common])
    priorities.add_argument("--limit", type=int, default=20)
    exceptions = sub.add_parser("exceptions", parents=[common])
    exceptions.add_argument("--limit", type=int, default=20)
    ask = sub.add_parser("ask", parents=[common])
    ask.add_argument("question")
    ask.add_argument("--model")
    return result


def main() -> None:
    args = parser().parse_args()
    if args.dataset is None:
        raise SystemExit(
            "Configura SONIA_COLLECTIONS_DATASET o usa --dataset con un ZIP compatible."
        )
    service = CollectionsService(args.dataset)
    if args.command == "portfolio":
        payload = service.portfolio_snapshot(args.as_of_date)
    elif args.command == "customer":
        payload = service.customer_snapshot(args.customer_id, args.as_of_date)
    elif args.command == "invoice":
        payload = service.invoice_trace(args.document, args.as_of_date)
    elif args.command == "priorities":
        payload = service.collection_priorities(args.limit, args.as_of_date)
    elif args.command == "exceptions":
        payload = service.reconciliation_exceptions(args.limit, args.as_of_date)
    else:
        from .openai_runtime import ask

        payload = ask(service, args.question, args.model)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
