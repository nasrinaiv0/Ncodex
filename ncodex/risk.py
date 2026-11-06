"""Fail-closed policy gate. A green result authorizes analysis/paper only."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from .schema import Candidate, decimal


@dataclass(frozen=True)
class RiskPolicy:
    max_order_usd: Decimal = Decimal("50")
    max_daily_buy_usd: Decimal = Decimal("100")
    min_liquidity_usd: Decimal = Decimal("10000")
    max_top10_holder_pct: Decimal = Decimal("60")
    max_developer_holder_pct: Decimal = Decimal("15")
    min_token_age_seconds: int = 60
    max_quote_age_seconds: int = 30
    max_observation_age_seconds: int = 60


@dataclass(frozen=True)
class Verdict:
    allowed_for_paper: bool
    reasons: tuple[str, ...]

    def as_dict(self) -> dict:
        return {"allowed_for_paper": self.allowed_for_paper, "reasons": list(self.reasons),
                "live_trading_allowed": False}


def evaluate(candidate: Candidate, order_usd: object, spent_today_usd: object,
             now: datetime | None = None, policy: RiskPolicy | None = None) -> Verdict:
    policy = policy or RiskPolicy()
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must include timezone")
    now = now.astimezone(timezone.utc)
    usd = decimal(order_usd, "order_usd", positive=True)
    spent = decimal(spent_today_usd, "spent_today_usd")
    reasons: list[str] = []
    if usd > policy.max_order_usd:
        reasons.append("trade_notional_exceeds_limit")
    if usd + spent > policy.max_daily_buy_usd:
        reasons.append("daily_buy_budget_exceeded")
    if candidate.liquidity_usd < policy.min_liquidity_usd:
        reasons.append("insufficient_liquidity")
    if candidate.top10_holder_pct > policy.max_top10_holder_pct:
        reasons.append("concentrated_holders")
    if candidate.developer_holder_pct > policy.max_developer_holder_pct:
        reasons.append("developer_concentration")
    if candidate.honeypot:
        reasons.append("honeypot_flag")
    if not candidate.mint_authority_disabled:
        reasons.append("mint_authority_enabled")
    if not candidate.freeze_authority_disabled:
        reasons.append("freeze_authority_enabled")
    if candidate.token_age_seconds < policy.min_token_age_seconds:
        reasons.append("new_token_cooldown")
    quote_age = (now - candidate.quote_at).total_seconds()
    observation_age = (now - candidate.observed_at).total_seconds()
    if not 0 <= quote_age <= policy.max_quote_age_seconds:
        reasons.append("stale_or_future_quote")
    if not 0 <= observation_age <= policy.max_observation_age_seconds:
        reasons.append("stale_or_future_observation")
    return Verdict(not reasons, tuple(reasons))
