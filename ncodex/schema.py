"""Validated, normalized external token data (never directly trust a crawler)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import re
from typing import Any, Mapping

SOLANA_ADDRESS = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


def decimal(value: object, label: str, *, positive: bool = False) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{label} must be a finite decimal number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{label} must be a finite decimal number") from exc
    if not result.is_finite() or (positive and result <= 0) or (not positive and result < 0):
        raise ValueError(f"{label} must be {'positive' if positive else 'nonnegative'} and finite")
    return result


def timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO-8601 timestamp with timezone")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be ISO-8601") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"{label} must include timezone")
    return result.astimezone(timezone.utc)


def strict_bool(mapping: Mapping[str, Any], key: str) -> bool:
    if key not in mapping or type(mapping[key]) is not bool:
        raise ValueError(f"security.{key} must be explicitly true or false")
    return mapping[key]


@dataclass(frozen=True)
class Candidate:
    mint: str
    source: str
    observed_at: datetime
    quote_at: datetime
    price_usd: Decimal
    liquidity_usd: Decimal
    top10_holder_pct: Decimal
    developer_holder_pct: Decimal
    honeypot: bool
    mint_authority_disabled: bool
    freeze_authority_disabled: bool
    token_age_seconds: int

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "Candidate":
        """Accept a *normalized* candidate, never an arbitrary provider response."""
        if payload.get("chain") != "solana":
            raise ValueError("only Solana candidates supported")
        mint = payload.get("mint")
        if not isinstance(mint, str) or not SOLANA_ADDRESS.fullmatch(mint):
            raise ValueError("invalid Solana mint address")
        source = payload.get("source")
        if source not in ("gmgn", "chainstack+gmgn", "manual-reviewed"):
            raise ValueError("source must be a known normalized source")
        security = payload.get("security")
        if not isinstance(security, dict):
            raise ValueError("security evidence is required")
        age = payload.get("token_age_seconds")
        if type(age) is not int or age < 0:
            raise ValueError("token_age_seconds must be a nonnegative integer")
        top = decimal(security.get("top10_holder_pct"), "top10_holder_pct")
        dev = decimal(security.get("developer_holder_pct"), "developer_holder_pct")
        if top > 100 or dev > 100:
            raise ValueError("holder percentages cannot exceed 100")
        return cls(
            mint=mint, source=source,
            observed_at=timestamp(payload.get("observed_at"), "observed_at"),
            quote_at=timestamp(payload.get("quote_at"), "quote_at"),
            price_usd=decimal(payload.get("price_usd"), "price_usd", positive=True),
            liquidity_usd=decimal(payload.get("liquidity_usd"), "liquidity_usd"),
            top10_holder_pct=top, developer_holder_pct=dev,
            honeypot=strict_bool(security, "honeypot"),
            mint_authority_disabled=strict_bool(security, "mint_authority_disabled"),
            freeze_authority_disabled=strict_bool(security, "freeze_authority_disabled"),
            token_age_seconds=age,
        )
