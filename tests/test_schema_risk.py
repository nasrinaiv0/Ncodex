import copy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import unittest

from ncodex.risk import RiskPolicy, evaluate
from ncodex.schema import Candidate


NOW = datetime(2026, 11, 6, 2, 0, tzinfo=timezone.utc)
MINT = "So11111111111111111111111111111111111111112"


def valid_candidate():
    return {
        "chain": "solana", "mint": MINT, "source": "gmgn",
        "observed_at": (NOW - timedelta(seconds=5)).isoformat(),
        "quote_at": (NOW - timedelta(seconds=4)).isoformat(),
        "price_usd": "0.00000000015", "liquidity_usd": "20000",
        "token_age_seconds": 180,
        "security": {"top10_holder_pct": "30", "developer_holder_pct": "3",
                     "honeypot": False, "mint_authority_disabled": True,
                     "freeze_authority_disabled": True}
    }


class SchemaRiskTests(unittest.TestCase):
    def test_clean_candidate_paper_only(self):
        result = evaluate(Candidate.from_mapping(valid_candidate()), "20", "0", NOW)
        self.assertTrue(result.allowed_for_paper)
        self.assertFalse(result.as_dict()["live_trading_allowed"])

    def test_missing_security_fails_closed(self):
        payload = valid_candidate()
        del payload["security"]["honeypot"]
        with self.assertRaises(ValueError):
            Candidate.from_mapping(payload)

    def test_missing_price_fails_closed(self):
        payload = valid_candidate()
        del payload["price_usd"]
        with self.assertRaises(ValueError):
            Candidate.from_mapping(payload)

    def test_future_quote_rejected(self):
        payload = valid_candidate()
        payload["quote_at"] = (NOW + timedelta(seconds=1)).isoformat()
        reasons = evaluate(Candidate.from_mapping(payload), "1", "0", NOW).reasons
        self.assertIn("stale_or_future_quote", reasons)

    def test_stale_quote_rejected(self):
        payload = valid_candidate()
        payload["quote_at"] = (NOW - timedelta(minutes=2)).isoformat()
        reasons = evaluate(Candidate.from_mapping(payload), "1", "0", NOW).reasons
        self.assertIn("stale_or_future_quote", reasons)

    def test_fiat_limits(self):
        candidate = Candidate.from_mapping(valid_candidate())
        self.assertIn("trade_notional_exceeds_limit", evaluate(candidate, "51", "0", NOW).reasons)
        self.assertIn("daily_buy_budget_exceeded", evaluate(candidate, "20", "90", NOW).reasons)

    def test_honeypot_and_permissions(self):
        payload = valid_candidate()
        payload["security"]["honeypot"] = True
        payload["security"]["freeze_authority_disabled"] = False
        reasons = evaluate(Candidate.from_mapping(payload), "10", "0", NOW).reasons
        self.assertIn("honeypot_flag", reasons)
        self.assertIn("freeze_authority_enabled", reasons)

    def test_invalid_numbers_and_mint(self):
        for value in ["NaN", "Infinity", "-1", None, True]:
            payload = valid_candidate()
            payload["liquidity_usd"] = value
            with self.assertRaises(ValueError):
                Candidate.from_mapping(payload)
        payload = valid_candidate()
        payload["mint"] = "not-a-mint!"
        with self.assertRaises(ValueError):
            Candidate.from_mapping(payload)

    def test_concentration(self):
        payload = valid_candidate()
        payload["security"]["top10_holder_pct"] = "80"
        payload["security"]["developer_holder_pct"] = "30"
        reasons = evaluate(Candidate.from_mapping(payload), "10", "0", NOW).reasons
        self.assertIn("concentrated_holders", reasons)
        self.assertIn("developer_concentration", reasons)
