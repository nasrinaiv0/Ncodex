"""Human-gated paper workflow. No connection to live-wallet code."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from .ledger import PaperLedger
from .memory import PatternMemory
from .risk import RiskPolicy, Verdict, evaluate
from .schema import Candidate, decimal


class PaperDesk:
    def __init__(self, ledger: PaperLedger, memory: PatternMemory | None = None,
                 policy: RiskPolicy | None = None):
        self.ledger = ledger
        self.memory = memory
        self.policy = policy or RiskPolicy()

    def review(self, candidate: Candidate, usd: object, now: datetime | None = None) -> Verdict:
        now = now or datetime.now(timezone.utc)
        spent = self.ledger.daily_buy_notional_usd(now.astimezone(timezone.utc).date().isoformat())
        return evaluate(candidate, usd, spent, now, self.policy)

    def buy(self, event_id: str, candidate: Candidate, usd: object, *,
            approved: bool, now: datetime | None = None, fee_usd: object = "0") -> dict:
        if not approved:
            raise PermissionError("paper trade requires explicit human approval")
        fee = decimal(fee_usd, "fee")
        notional = decimal(usd, "usd", positive=True)
        if fee >= notional:
            raise ValueError("fee must be less than paper buy budget")
        verdict = self.review(candidate, notional, now=now)
        if not verdict.allowed_for_paper:
            raise ValueError("paper buy blocked: " + ",".join(verdict.reasons))
        # USD means total budget including fee; journal never rounds token quantity.
        qty = (notional - fee) / candidate.price_usd
        inserted = self.ledger.buy(event_id, candidate.mint, qty, candidate.price_usd,
                                   fee, source=candidate.source)
        if self.memory:
            self.memory.observe(event_id, candidate.source, candidate.mint, True, ())
        return {"mode": "paper", "inserted": inserted, "quantity": str(qty),
                "budget_usd": str(notional), "mint": candidate.mint}
