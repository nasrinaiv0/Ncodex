"""Minimal offline CLI; never imports or executes upstream bot dependencies."""
from __future__ import annotations

import argparse
from datetime import datetime
from decimal import Decimal
import json
import sys

from .ledger import PaperLedger
from .pipeline import PaperDesk
from .schema import Candidate, timestamp


def _candidate(path: str) -> Candidate:
    with open(path, encoding="utf-8") as handle:
        return Candidate.from_mapping(json.load(handle, parse_float=Decimal))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ncodex offline paper trading (NO LIVE ORDERS)")
    sub = parser.add_subparsers(dest="command", required=True)
    analyze = sub.add_parser("analyze")
    analyze.add_argument("--candidate", required=True)
    analyze.add_argument("--usd", required=True)
    analyze.add_argument("--now")
    analyze.add_argument("--db", default=":memory:")
    fund = sub.add_parser("fund")
    fund.add_argument("--db", required=True)
    fund.add_argument("--usd", required=True)
    fund.add_argument("--id", required=True)
    buy = sub.add_parser("paper-buy")
    buy.add_argument("--db", required=True)
    buy.add_argument("--candidate", required=True)
    buy.add_argument("--usd", required=True, help="Total USD budget INCLUDING fee")
    buy.add_argument("--fee-usd", default="0")
    buy.add_argument("--id", required=True)
    buy.add_argument("--approve", action="store_true", help="Human approves PAPER order only")
    buy.add_argument("--now")
    sell = sub.add_parser("paper-sell")
    sell.add_argument("--db", required=True)
    sell.add_argument("--mint", required=True)
    sell.add_argument("--qty", required=True)
    sell.add_argument("--price-usd", required=True)
    sell.add_argument("--fee-usd", default="0")
    sell.add_argument("--id", required=True)
    sell.add_argument("--approve", action="store_true")
    summary = sub.add_parser("summary")
    summary.add_argument("--db", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    ledger = PaperLedger(getattr(args, "db", ":memory:"))
    try:
        if args.command == "analyze":
            verdict = PaperDesk(ledger).review(
                _candidate(args.candidate), args.usd,
                now=timestamp(args.now, "now") if args.now else None)
            out = verdict.as_dict()
        elif args.command == "fund":
            out = {"mode": "paper", "inserted": ledger.fund(args.id, args.usd)}
        elif args.command == "paper-buy":
            out = PaperDesk(ledger).buy(
                args.id, _candidate(args.candidate), args.usd,
                approved=args.approve,
                now=timestamp(args.now, "now") if args.now else None,
                fee_usd=args.fee_usd)
        elif args.command == "paper-sell":
            if not args.approve:
                raise PermissionError("paper sale requires explicit human approval")
            pnl = ledger.sell(args.id, args.mint, args.qty,
                              args.price_usd, args.fee_usd)
            out = {"mode": "paper", "realized_pnl_usd": str(pnl)}
        else:
            out = ledger.summary()
        print(json.dumps(out, indent=2, sort_keys=True))
        return 0
    except (ValueError, PermissionError) as error:
        print(json.dumps({"error": str(error), "mode": "paper"}), file=sys.stderr)
        return 2
    finally:
        ledger.close()


if __name__ == "__main__":
    raise SystemExit(main())
