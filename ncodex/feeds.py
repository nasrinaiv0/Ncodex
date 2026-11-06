"""Offline intake for normalized watcher/crawler events: read, validate, dedupe, alert.

No network access or wallet signing. Upstream payload adapters must be reviewed
separately. A malformed record cannot result in a buy order.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import hashlib
import json
from typing import Iterable, Iterator

from .memory import PatternMemory
from .pipeline import PaperDesk
from .schema import Candidate


MAX_LINE_BYTES = 262_144


def watch_records(lines: Iterable[str], desk: PaperDesk, memory: PatternMemory,
                  order_usd: object, *, now: datetime | None = None) -> Iterator[dict]:
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        if len(line.encode("utf-8")) > MAX_LINE_BYTES:
            yield {"line": number, "error": "record_too_large", "live_trading_allowed": False}
            continue
        try:
            payload = json.loads(line, parse_float=Decimal)
            if not isinstance(payload, dict):
                raise ValueError("candidate must be a JSON object")
            event_id = payload.get("event_id") or hashlib.sha256(
                line.strip().encode("utf-8")).hexdigest()
            if (not isinstance(event_id, str) or not event_id.isascii()
                    or not 1 <= len(event_id) <= 128 or not event_id.isprintable()):
                raise ValueError("invalid event_id")
            candidate = Candidate.from_mapping(payload)
            verdict = desk.review(candidate, order_usd, now=now)
            added = memory.observe(event_id, candidate.source, candidate.mint,
                                   verdict.allowed_for_paper, verdict.reasons)
            yield {"line": number, "event_id": event_id, "first_seen": added,
                   "mint": candidate.mint, "source": candidate.source, **verdict.as_dict()}
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            yield {"line": number, "error": str(exc), "live_trading_allowed": False}
