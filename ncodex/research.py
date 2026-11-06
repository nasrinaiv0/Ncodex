"""Optional TradingAgents -> ChatGPT subscription bridge.

Uses TradingAgents' documented ChatGPT provider, not an OpenAI API key.
No execution or trading endpoint is exposed. Provider sign-in is performed
separately on the host with "tradingagents login chatgpt".
"""
from __future__ import annotations
from datetime import date, datetime
import importlib.util
import re
from pathlib import Path
from typing import Any

TICKER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,23}$")
ANALYSTS = ("market", "social", "news", "fundamentals")


def normalize_research_request(body: dict) -> tuple[str, str, str]:
    if not isinstance(body, dict):
        raise ValueError("request must be an object")
    ticker = body.get("ticker")
    if not isinstance(ticker, str) or not TICKER.fullmatch(ticker):
        raise ValueError("invalid ticker (max 24 letters/numbers/symbols)")
    ticker = ticker.upper()
    date_str = body.get("date", date.today().isoformat())
    if not isinstance(date_str, str):
        raise ValueError("date must be a YYYY-MM-DD string")
    try:
        run_date = date.fromisoformat(date_str)
    except ValueError as exc:
        raise ValueError("date must be YYYY-MM-DD") from exc
    if run_date.isoformat() != date_str or run_date > date.today():
        raise ValueError("research date cannot be in the future")
    asset_type = body.get("asset_type", "stock")
    if asset_type not in ("stock", "crypto"):
        raise ValueError("asset_type must be stock or crypto")
    return ticker, date_str, asset_type


class TradingAgentsBridge:
    def __init__(self, auth_path: str | None = None):
        self.auth_path = Path(auth_path or "~/.tradingagents/chatgpt-auth.json").expanduser()

    def status(self) -> dict:
        installed = importlib.util.find_spec("tradingagents") is not None
        auth_file = self.auth_path.is_file()
        return {
            "installed": installed,
            "chatgpt_login_file_present": auth_file,
            "ready_to_attempt": installed and auth_file,
            "authentication_verified": False,  # file presence is not a validity check
            "provider": "chatgpt",
            "live_order_permissions": False,
            "login_command": "tradingagents login chatgpt",
        }

    def run(self, ticker: str, date_str: str, asset_type: str = "stock") -> dict:
        # Import lazily to keep Ncodex core dependency-free and sandbox testable.
        if not self.status()["ready_to_attempt"]:
            raise RuntimeError(
                "TradingAgents package and ChatGPT authorization are required on the server. "
                "Install upstream/TradingAgents then run: tradingagents login chatgpt"
            )
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        from tradingagents.default_config import build_default_config
        config = build_default_config()
        config["llm_provider"] = "chatgpt"
        config["quick_think_provider"] = "chatgpt"
        config["deep_think_provider"] = "chatgpt"
        # This is solely research. No order execution path exists here.
        graph = TradingAgentsGraph(selected_analysts=ANALYSTS, config=config)
        state, signal = graph.propagate(ticker, date_str, asset_type=asset_type)
        # Limit size and disclose model output is unverified opinion.
        report_keys = (
            "market_report", "sentiment_report", "news_report",
            "fundamentals_report", "investment_debate_state",
            "risk_debate_state", "final_trade_decision",
        )
        reports: dict[str, str] = {}
        if isinstance(state, dict):
            for key in report_keys:
                value = state.get(key)
                if value is not None:
                    reports[key] = str(value)[:4000]
        return {
            "ticker": ticker, "date": date_str, "asset_type": asset_type,
            "signal": str(signal)[:200], "reports": reports,
            "source": "TradingAgents / ChatGPT subscription",
            "disclaimer": "AI research only. No trade placed or approved.",
        }
