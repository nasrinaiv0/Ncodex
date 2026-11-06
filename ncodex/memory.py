"""Explainable observation and outcome store; NOT autonomous strategy training."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
import json
import sqlite3


class PatternMemory:
    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path)
        self.db.execute("""CREATE TABLE IF NOT EXISTS observations (
            id TEXT PRIMARY KEY, source TEXT NOT NULL, mint TEXT NOT NULL,
            verdict TEXT NOT NULL, reasons TEXT NOT NULL,
            realized_pnl_usd TEXT
        )""")

    def observe(self, observation_id: str, source: str, mint: str,
                allowed: bool, reasons: tuple[str, ...]) -> bool:
        verdict = "paper-eligible" if allowed else "rejected"
        encoded_reasons = json.dumps(reasons)
        with self.db:
            existing = self.db.execute(
                "SELECT source,mint,verdict,reasons FROM observations WHERE id=?",
                (observation_id,)).fetchone()
            record = (source, mint, verdict, encoded_reasons)
            if existing is not None:
                if existing != record:
                    raise ValueError("observation id reused with different content")
                return False
            self.db.execute(
                """INSERT INTO observations(id,source,mint,verdict,reasons)
                   VALUES(?,?,?,?,?)""", (observation_id, *record))
            return True

    def record_outcome(self, observation_id: str, realized_pnl_usd: object) -> None:
        pnl = Decimal(str(realized_pnl_usd))
        if not pnl.is_finite():
            raise ValueError("outcome must be finite")
        with self.db:
            row = self.db.execute(
                "SELECT realized_pnl_usd FROM observations WHERE id=?", (observation_id,)
            ).fetchone()
            if row is None:
                raise ValueError("unknown observation")
            if row[0] is not None and Decimal(row[0]) != pnl:
                raise ValueError("outcome already recorded")
            self.db.execute("UPDATE observations SET realized_pnl_usd=? WHERE id=?",
                            (str(pnl), observation_id))

    def report(self) -> dict:
        groups = defaultdict(lambda: {"observations": 0, "completed": 0,
                                       "wins": 0, "net_realized_usd": Decimal(0)})
        for source, pnl in self.db.execute(
                "SELECT source,realized_pnl_usd FROM observations"):
            data = groups[source]
            data["observations"] += 1
            if pnl is not None:
                amount = Decimal(pnl)
                data["completed"] += 1
                data["wins"] += int(amount > 0)
                data["net_realized_usd"] += amount
        return {source: {**data, "net_realized_usd": str(data["net_realized_usd"])}
                for source, data in sorted(groups.items())}

    def close(self) -> None:
        self.db.close()
