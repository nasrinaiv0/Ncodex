import json
import os
import tempfile
import threading
from http.client import HTTPConnection
from pathlib import Path
import unittest
from decimal import Decimal
from unittest.mock import patch

from ncodex.mobile import MobileServer, ResearchJobs, sample_candidate
from ncodex.research import normalize_research_request, TradingAgentsBridge
from ncodex.freqtrade_bridge import FreqtradeBridge


class MockRunner:
    def status(self):
        return {"ready_to_attempt": True, "provider": "chatgpt"}

    def run(self, ticker, date_str, asset_type):
        return {"ticker": ticker, "signal": "HOLD", "source": "mock", "asset_type": asset_type}


class MobileAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.path = os.path.join(cls.temp.name, "trades.db")
        cls.httpd = MobileServer(("127.0.0.1", 0), cls.path, "secret-test-token-1234567890",
                                 research=ResearchJobs(MockRunner()))
        cls.port = cls.httpd.server_port
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=3)
        cls.temp.cleanup()

    def request(self, method, path, body=None, token=True, origin=None):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer secret-test-token-1234567890"
        if origin:
            headers["Origin"] = origin
        conn.request(method, path, body=json.dumps(body).encode() if body is not None else None,
                     headers=headers)
        response = conn.getresponse()
        content = response.read()
        ctype = response.getheader("Content-Type") or ""
        conn.close()
        return response.status, json.loads(content) if ctype.startswith("application/json") else content

    def test_auth_and_source(self):
        self.assertEqual(self.request("GET", "/api/paper", token=False)[0], 401)
        self.assertEqual(self.request("GET", "/")[0], 200)
        self.assertEqual(self.request("GET", "/styles.css")[0], 200)
        self.assertEqual(self.request("GET", "/app.js")[0], 200)
        self.assertEqual(self.request("GET", "/not-found")[0], 404)

    def test_no_cross_origin_mutation(self):
        status, data = self.request("POST", "/api/paper/fund",
            {"id": "bad", "usd": "100", "approved": True}, origin="https://attacker.invalid")
        self.assertEqual(status, 403)

    def test_paper_fund_and_round_trip(self):
        body = {"id": "fund-mobile", "usd": "100", "approved": True}
        self.assertEqual(self.request("POST", "/api/paper/fund", body)[0], 200)
        self.assertFalse(self.request("POST", "/api/paper/fund", body)[1]["inserted"])
        status, data = self.request("POST", "/api/paper/buy",
            {"id": "buy-mobile", "usd": "20", "fee_usd": "0.01",
             "candidate_id": "demo-sol", "approved": True})
        self.assertEqual(status, 200)
        self.assertEqual(Decimal(data["summary"]["cash_usd"]), Decimal("80.00"))
        qty = data["quantity"]
        status, data = self.request("POST", "/api/paper/sell",
            {"id": "sell-mobile", "qty": qty, "price_usd": "1.5",
             "candidate_id": "demo-sol", "approved": True, "fee_usd": "0.02"})
        self.assertEqual(status, 200)
        self.assertTrue(data["summary"]["journal_balanced"])
        self.assertEqual(data["summary"]["positions"], {})

    def test_human_approval_and_not_real_order(self):
        status, data = self.request("POST", "/api/paper/buy",
            {"id": "denied", "candidate_id": "demo-sol", "usd": "20", "approved": False})
        self.assertEqual(status, 400)
        self.assertIn("approval", data["error"])
        status, data = self.request("GET", "/api/health")
        self.assertFalse(data["live_trading_enabled"])

    def test_research_async(self):
        status, body = self.request("POST", "/api/research",
            {"ticker": "AAPL", "asset_type": "stock"})
        self.assertEqual(status, 202)
        import time
        for _ in range(20):
            status, data = self.request("GET", "/api/research/" + body["job_id"])
            if data.get("status") == "completed":
                break
            time.sleep(0.01)
        self.assertEqual(data.get("status"), "completed")
        self.assertEqual(data["result"]["signal"], "HOLD")

    def test_invalid_body_and_routes(self):
        self.assertEqual(self.request("POST", "/api/paper/sell", {"approved": True})[0], 400)
        self.assertEqual(self.request("GET", "/api/research/unknown")[0], 404)
        self.assertEqual(self.request("GET", "/api/unknown")[0], 404)

    def test_static_security_headers(self):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=3)
        conn.request("GET", "/")
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        self.assertIn("script-src 'self'", response.getheader("Content-Security-Policy"))
        self.assertEqual(response.getheader("X-Frame-Options"), "DENY")
        response.read()
        conn.close()


class BridgeTests(unittest.TestCase):
    def test_ticker_validation(self):
        self.assertEqual(normalize_research_request({"ticker": "AAPL"})[0], "AAPL")
        for ticker in ["../../etc/passwd", "AAPL;echo", "", "a" * 100]:
            with self.assertRaises(ValueError):
                normalize_research_request({"ticker": ticker})
        with self.assertRaises(ValueError):
            normalize_research_request({"ticker": "AAPL", "date": "2999-01-01"})

    def test_auth_status_is_not_claiming_validation(self):
        with tempfile.TemporaryDirectory() as dir:
            path = Path(dir) / "auth.json"
            path.write_text("{}", encoding="utf8")
            status = TradingAgentsBridge(str(path)).status()
            self.assertFalse(status["authentication_verified"])
            self.assertTrue(status["chatgpt_login_file_present"])

    def test_freqtrade_gates(self):
        with self.assertRaises(ValueError):
            FreqtradeBridge("http://untrusted.example.com", "bob", "password")
        bridge = FreqtradeBridge("http://127.0.0.1:8080", "bob", "password")
        with self.assertRaises(ValueError):
            bridge.get("forcebuy")
        with patch.object(bridge, "get", side_effect=[
            {"dry_run": False}]):
            self.assertEqual(bridge.snapshot()["mode"], "blocked")
        with patch.object(bridge, "get", side_effect=[
            {"dry_run": True}, [{"trade_id": 1}]]):
            self.assertEqual(bridge.snapshot()["open_trade_count"], 1)
