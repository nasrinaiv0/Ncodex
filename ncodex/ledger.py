"""SQLite-backed double-entry ledger for PAPER trades only.

USD values remain Decimals represented as strings; no binary floats or premature
two-decimal rounding. Journal entries balance exactly at each event.
FIFO lots support partial sells, fees and realized profit/loss.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, getcontext
import json
import sqlite3

from .schema import decimal

getcontext().prec = 50


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PaperLedger:
    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY, kind TEXT NOT NULL, mint TEXT,
            quantity TEXT, unit_price_usd TEXT, fee_usd TEXT,
            gross_usd TEXT, realized_pnl_usd TEXT, source TEXT,
            recorded_at TEXT NOT NULL, fingerprint TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS journal (
            row_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL REFERENCES events(id),
            account TEXT NOT NULL, debit TEXT NOT NULL, credit TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS lots (
            id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL,
            mint TEXT NOT NULL, remaining_quantity TEXT NOT NULL,
            remaining_cost_usd TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_events_day ON events(recorded_at);
        CREATE INDEX IF NOT EXISTS idx_lots_mint ON lots(mint, id);
        """)

    def close(self) -> None:
        self.db.close()

    @staticmethod
    def _fingerprint(kind: str, items: tuple) -> str:
        return json.dumps([kind, *map(str, items)], separators=(",", ":"), ensure_ascii=True)

    def _existing(self, event_id: str, fingerprint: str) -> bool:
        row = self.db.execute("SELECT fingerprint FROM events WHERE id=?", (event_id,)).fetchone()
        if row:
            if row[0] != fingerprint:
                raise ValueError("idempotency key reused with different trade details")
            return True
        return False

    def _event(self, event_id: str, kind: str, fingerprint: str, *,
               mint: str = "", qty: str = "0", price: str = "0", fee: str = "0",
               gross: str = "0", pnl: str = "0", source: str = "paper",
               recorded_at: str | None = None) -> None:
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("event id required")
        self.db.execute(
            """INSERT INTO events (id,kind,mint,quantity,unit_price_usd,fee_usd,
               gross_usd,realized_pnl_usd,source,recorded_at,fingerprint)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (event_id, kind, mint, qty, price, fee, gross, pnl, source,
             recorded_at or _now(), fingerprint))

    def _post(self, event_id: str, account: str, *, debit: Decimal = Decimal(0),
              credit: Decimal = Decimal(0)) -> None:
        if debit < 0 or credit < 0:
            raise ValueError("journal amounts must be nonnegative")
        if debit == 0 and credit == 0:
            return
        self.db.execute("INSERT INTO journal(event_id, account, debit, credit) VALUES(?,?,?,?)",
                        (event_id, account, str(debit), str(credit)))

    def cash_usd(self) -> Decimal:
        return sum((Decimal(d) - Decimal(c) for d, c in
                    self.db.execute("SELECT debit,credit FROM journal WHERE account='cash-usd'")),
                   Decimal(0))

    def fund(self, event_id: str, usd: object) -> bool:
        amount = decimal(usd, "fund_usd", positive=True)
        fp = self._fingerprint("fund", (amount,))
        with self.db:
            if self._existing(event_id, fp):
                return False
            self._event(event_id, "fund", fp, gross=str(amount))
            self._post(event_id, "cash-usd", debit=amount)
            self._post(event_id, "owner-equity", credit=amount)
        return True

    def position(self, mint: str) -> tuple[Decimal, Decimal]:
        qty, cost = Decimal(0), Decimal(0)
        for q, c in self.db.execute(
                "SELECT remaining_quantity,remaining_cost_usd FROM lots WHERE mint=?", (mint,)):
            qty += Decimal(q)
            cost += Decimal(c)
        return qty, cost

    def buy(self, event_id: str, mint: str, qty: object, unit_price_usd: object,
            fee_usd: object = "0", *, source: str = "paper") -> bool:
        q = decimal(qty, "qty", positive=True)
        p = decimal(unit_price_usd, "price", positive=True)
        fee = decimal(fee_usd, "fee")
        gross = q * p
        cost = gross + fee
        fp = self._fingerprint("buy", (mint, q, p, fee, source))
        with self.db:
            if self._existing(event_id, fp):
                return False
            if self.cash_usd() < cost:
                raise ValueError("insufficient paper cash")
            self._event(event_id, "buy", fp, mint=mint, qty=str(q), price=str(p),
                        fee=str(fee), gross=str(gross), source=source)
            self.db.execute("""INSERT INTO lots(event_id,mint,remaining_quantity,remaining_cost_usd)
                               VALUES(?,?,?,?)""", (event_id, mint, str(q), str(cost)))
            self._post(event_id, f"inventory:{mint}", debit=cost)
            self._post(event_id, "cash-usd", credit=cost)
        return True

    def sell(self, event_id: str, mint: str, qty: object, unit_price_usd: object,
             fee_usd: object = "0", *, source: str = "paper") -> Decimal:
        q = decimal(qty, "qty", positive=True)
        p = decimal(unit_price_usd, "price", positive=True)
        fee = decimal(fee_usd, "fee")
        gross = q * p
        if fee > gross:
            raise ValueError("fee cannot exceed gross sale proceeds")
        fp = self._fingerprint("sell", (mint, q, p, fee, source))
        with self.db:
            if self._existing(event_id, fp):
                row = self.db.execute("SELECT realized_pnl_usd FROM events WHERE id=?",
                                      (event_id,)).fetchone()
                return Decimal(row[0])
            available, _ = self.position(mint)
            if available < q:
                raise ValueError("insufficient paper token inventory")
            remaining = q
            cost_basis = Decimal(0)
            rows = self.db.execute(
                """SELECT id,remaining_quantity,remaining_cost_usd
                   FROM lots WHERE mint=? ORDER BY id""", (mint,)).fetchall()
            for lot_id, old_q_text, old_cost_text in rows:
                if remaining == 0:
                    break
                old_q, old_cost = Decimal(old_q_text), Decimal(old_cost_text)
                if old_q == 0:
                    continue
                taken = min(remaining, old_q)
                taken_cost = old_cost if taken == old_q else old_cost * (taken / old_q)
                new_q = old_q - taken
                new_cost = old_cost - taken_cost
                self.db.execute(
                    "UPDATE lots SET remaining_quantity=?, remaining_cost_usd=? WHERE id=?",
                    (str(new_q), str(new_cost), lot_id))
                remaining -= taken
                cost_basis += taken_cost
            net = gross - fee
            pnl = net - cost_basis
            self._event(event_id, "sell", fp, mint=mint, qty=str(q), price=str(p),
                        fee=str(fee), gross=str(gross), pnl=str(pnl), source=source)
            self._post(event_id, "cash-usd", debit=net)
            self._post(event_id, f"inventory:{mint}", credit=cost_basis)
            if pnl >= 0:
                self._post(event_id, "realized-pnl", credit=pnl)
            else:
                self._post(event_id, "realized-pnl", debit=-pnl)
        return pnl

    def realized_pnl_usd(self) -> Decimal:
        return sum((Decimal(x) for (x,) in self.db.execute(
            "SELECT realized_pnl_usd FROM events WHERE kind='sell'")), Decimal(0))

    def daily_buy_notional_usd(self, day: str) -> Decimal:
        # day must be YYYY-MM-DD in UTC
        return sum((Decimal(gross) + Decimal(fee) for gross, fee in self.db.execute(
            "SELECT gross_usd,fee_usd FROM events WHERE kind='buy' AND substr(recorded_at,1,10)=?",
            (day,))), Decimal(0))

    def journal_balanced(self) -> bool:
        by_event: dict[str, Decimal] = {}
        for event_id, debit, credit in self.db.execute(
                "SELECT event_id,debit,credit FROM journal"):
            by_event[event_id] = by_event.get(event_id, Decimal(0)) + Decimal(debit) - Decimal(credit)
        events = self.db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        return len(by_event) == events and all(value == 0 for value in by_event.values())

    def summary(self) -> dict:
        positions = {}
        for (mint,) in self.db.execute("SELECT DISTINCT mint FROM lots"):
            qty, cost = self.position(mint)
            if qty:
                positions[mint] = {"quantity": str(qty), "cost_basis_usd": str(cost)}
        return {"mode": "paper", "cash_usd": str(self.cash_usd()),
                "realized_pnl_usd": str(self.realized_pnl_usd()),
                "positions": positions, "journal_balanced": self.journal_balanced()}
