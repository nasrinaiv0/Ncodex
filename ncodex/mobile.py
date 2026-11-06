"""Mobile-first local PWA and authenticated paper-only API.

Run: python -m ncodex.mobile --port 3000
Default interface is loopback only. Binding a public interface requires a
separately configured access token and HTTPS reverse proxy for real deployment.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import threading
import time
import uuid
from urllib.parse import urlsplit

from .ledger import PaperLedger
from .pipeline import PaperDesk
from .research import TradingAgentsBridge, normalize_research_request
from .freqtrade_bridge import FreqtradeBridge
from .chatgpt_connect import ChatGPTSignIn
from .elevenlabs_voice import ElevenLabsVoice, VoiceUnavailable, VOICE_NAME, MAX_TEXT_CHARS
from .schema import Candidate, decimal

ASSETS = Path(__file__).resolve().parent.parent / "web"
DEMO_MINT = "So11111111111111111111111111111111111111112"
FILE_MIMES = {"/": ("index.html", "text/html; charset=utf-8"),
              "/index.html": ("index.html", "text/html; charset=utf-8"),
              "/styles.css": ("styles.css", "text/css; charset=utf-8"),
              "/connect.css": ("connect.css", "text/css; charset=utf-8"),
              "/humanoids.css": ("humanoids.css", "text/css; charset=utf-8"),
              "/connect.js": ("connect.js", "text/javascript; charset=utf-8"),
              "/app.js": ("app.js", "text/javascript; charset=utf-8"),
              "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json"),
              "/sw.js": ("sw.js", "text/javascript; charset=utf-8"),
              "/icon.svg": ("icon.svg", "image/svg+xml")}


def sample_candidate(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    stamp = now.isoformat()
    return {
        "chain": "solana", "mint": DEMO_MINT,
        "source": "manual-reviewed",
        "observed_at": stamp, "quote_at": stamp,
        "price_usd": "1.25", "liquidity_usd": "100000",
        "token_age_seconds": 3600,
        "security": {
            "top10_holder_pct": "25", "developer_holder_pct": "2",
            "honeypot": False, "mint_authority_disabled": True,
            "freeze_authority_disabled": True,
        },
        "synthetic": True,
        "note": "Synthetic paper-only data. No price or safety check was fetched.",
    }


class ResearchJobs:
    """One research job at a time; no implicit execution of trades."""
    def __init__(self, runner=None):
        self.runner = runner or TradingAgentsBridge()
        self.lock = threading.Lock()
        self.jobs: dict[str, dict] = {}
        self.busy = False

    def start(self, ticker: str, day: str, asset_type: str) -> str:
        with self.lock:
            if self.busy:
                raise RuntimeError("A research run is already in progress")
            self.busy = True
            job_id = uuid.uuid4().hex
            self.jobs[job_id] = {"status": "running", "ticker": ticker, "date": day}
        def perform():
            try:
                output = self.runner.run(ticker, day, asset_type)
                result = {"status": "completed", "result": output}
            except Exception as exc:
                # No stacktrace, environment, credentials or third-party response to mobile.
                result = {"status": "failed", "error": type(exc).__name__ +
                          ": see secure server logs for details"}
            finally:
                with self.lock:
                    self.jobs[job_id].update(result)
                    self.busy = False
        threading.Thread(target=perform, daemon=True).start()
        return job_id

    def lookup(self, job_id: str) -> dict | None:
        with self.lock:
            job = self.jobs.get(job_id)
            return dict(job) if job is not None else None


class MobileServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, db_path: str, token: str,
                 research: ResearchJobs | None = None,
                 chatgpt_signin: ChatGPTSignIn | None = None,
                 voice: ElevenLabsVoice | None = None):
        super().__init__(address, MobileHandler)
        self.db_path = db_path
        self.token = token
        self.paper_lock = threading.Lock()
        self.research = research or ResearchJobs()
        self.chatgpt_signin = chatgpt_signin or ChatGPTSignIn()
        self.voice = voice or ElevenLabsVoice()
        self.voice_enabled = (
            len(token) >= 20 and bool(self.voice.configured())
            and os.environ.get("NCODEX_ENABLE_ELEVENLABS_VOICE") == "1"
        )
        self.voice_lock = threading.Lock()
        self.voice_request_day = ""
        self.voice_request_count = 0
        self.voice_last_call = 0.0
        # Owner-only feature. A paid plan never authorizes live trades.
        self.chatgpt_connect_enabled = (
            bool(token) and len(token) >= 20
            and os.environ.get("NCODEX_ENABLE_CHATGPT_CONNECT") == "1"
        )


class MobileHandler(BaseHTTPRequestHandler):
    server: MobileServer
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        # Avoid logging bearer tokens or contents.
        return

    def _json(self, status: int, data: dict | list):
        body = json.dumps(data, ensure_ascii=False, default=str).encode()
        self.send_response(status)
        self._headers("application/json; charset=utf-8", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _headers(self, content_type: str, size: int):
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cache-Control", "no-store" if (content_type.startswith("application/json") or content_type.startswith("audio/")) else "public, max-age=120")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; connect-src 'self'; img-src 'self' data:; "
                         "style-src 'self'; script-src 'self'; object-src 'none'; "
                         "base-uri 'none'; frame-ancestors 'none'; form-action 'self'")

    def _authorized(self) -> bool:
        expected = self.server.token
        # Loopback server may have no token. Public interface requires one.
        if not expected:
            return True
        value = self.headers.get("Authorization", "")
        return secrets.compare_digest(value, "Bearer " + expected)

    def _route(self) -> str:
        return urlsplit(self.path).path

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        host = self.headers.get("Host", "")
        return origin in ("http://" + host, "https://" + host)

    def do_GET(self):
        path = self._route()
        if path in FILE_MIMES:
            name, mime = FILE_MIMES[path]
            asset = ASSETS / name
            if not asset.is_file():
                self._json(404, {"error": "asset missing"})
                return
            body = asset.read_bytes()
            self.send_response(200)
            self._headers(mime, len(body))
            self.end_headers()
            self.wfile.write(body)
            return
        if not path.startswith("/api/"):
            self._json(404, {"error": "not found"})
            return
        if not self._authorized():
            self._json(401, {"error": "access token required"})
            return
        if path == "/api/voice/status":
            self._json(200, {"provider": "ElevenLabs", "voice": VOICE_NAME,
                             "enabled": self.server.voice_enabled,
                             "humanoids": ["dirk", "ej"],
                             "requires_owner_token": True,
                             "browser_fallback_available": True})
        elif path == "/api/chatgpt/status":
            result = {"enabled": self.server.chatgpt_connect_enabled}
            if self.server.chatgpt_connect_enabled:
                result.update(self.server.chatgpt_signin.status())
            else:
                result.update({"flow_status": "unavailable", "session_saved": False,
                               "installed": self.server.chatgpt_signin.adapter.installed(),
                               "trading_permissions": "research_only"})
            self._json(200, result)
        elif path == "/api/health":
            self._json(200, {"status": "ok", "mode": "paper", "live_trading_enabled": False})
        elif path == "/api/paper":
            with self.server.paper_lock:
                db = PaperLedger(self.server.db_path)
                try:
                    self._json(200, db.summary())
                finally:
                    db.close()
        elif path == "/api/integrations":
            self._json(200, {
                "tradingagents": self.server.research.runner.status(),
                "freqtrade": FreqtradeBridge().snapshot(),
                "watchers": "source pinned; no live feed connected",
                "execution": "disabled",
            })
        elif path == "/api/sample":
            self._json(200, sample_candidate())
        elif path.startswith("/api/research/"):
            job = self.server.research.lookup(path.removeprefix("/api/research/"))
            self._json(200 if job else 404, job or {"error": "unknown research job"})
        else:
            self._json(404, {"error": "unknown endpoint"})

    def _body(self) -> dict:
        size_str = self.headers.get("Content-Length", "")
        if not size_str.isdigit() or int(size_str) > 16_384:
            raise ValueError("JSON body missing or too large (16 KiB max)")
        data = json.loads(self.rfile.read(int(size_str)).decode("utf-8"),
                          parse_float=Decimal)
        if not isinstance(data, dict):
            raise ValueError("body must be an object")
        return data

    @staticmethod
    def _id(body: dict) -> str:
        event_id = body.get("id")
        if (not isinstance(event_id, str) or not 1 <= len(event_id) <= 128
                or not event_id.isascii() or not event_id.isprintable()):
            raise ValueError("valid idempotency id required")
        return event_id

    def do_POST(self):
        path = self._route()
        if not self._authorized():
            self._json(401, {"error": "access token required"})
            return
        if not self._origin_ok():
            self._json(403, {"error": "origin rejected"})
            return
        try:
            body = self._body()
            if path == "/api/voice":
                if not self.server.voice_enabled:
                    self._json(503, {"error": "ElevenLabs voice is not configured on the server"})
                    return
                spoken = body.get("text")
                humanoid = body.get("humanoid")
                if humanoid not in ("dirk", "ej"):
                    raise ValueError("Choose Dirk or EJ")
                if not isinstance(spoken, str) or not 1 <= len(spoken.strip()) <= MAX_TEXT_CHARS:
                    raise ValueError("Voice reply text is missing or too long")
                if not self.server.voice_lock.acquire(blocking=False):
                    self._json(429, {"error": "Voice generation already in progress"})
                    return
                try:
                    today = datetime.now(timezone.utc).date().isoformat()
                    if today != self.server.voice_request_day:
                        self.server.voice_request_day = today
                        self.server.voice_request_count = 0
                    clock = time.monotonic()
                    if clock - self.server.voice_last_call < 3 or self.server.voice_request_count >= 100:
                        self._json(429, {"error": "Voice request limit reached; try again later"})
                        return
                    self.server.voice_last_call = clock
                    self.server.voice_request_count += 1
                    try:
                        audio = self.server.voice.synthesize(spoken, humanoid)
                    except VoiceUnavailable:
                        self._json(502, {"error": "ElevenLabs voice unavailable; use device speech"})
                        return
                    self.send_response(200)
                    self._headers("audio/mpeg", len(audio))
                    self.end_headers()
                    self.wfile.write(audio)
                finally:
                    self.server.voice_lock.release()
                return
            if path.startswith("/api/chatgpt/"):
                if not self.server.chatgpt_connect_enabled:
                    self._json(403, {"error": "ChatGPT connection disabled. Configure owner token and enable the service."})
                    return
                if path == "/api/chatgpt/start":
                    if body.get("approved") is not True:
                        raise PermissionError("Explicit authorization is required")
                    self._json(202, self.server.chatgpt_signin.start())
                    return
                if path == "/api/chatgpt/complete":
                    self._json(202, self.server.chatgpt_signin.complete(
                        body.get("flow_id"), body.get("callback_url")))
                    return
                if path == "/api/chatgpt/disconnect":
                    if body.get("approved") is not True:
                        raise PermissionError("Confirm account disconnection")
                    self._json(200, self.server.chatgpt_signin.disconnect())
                    return
                self._json(404, {"error": "Unknown ChatGPT action"})
                return
            if path == "/api/research":
                ticker, day, asset_type = normalize_research_request(body)
                if not self.server.research.runner.status()["ready_to_attempt"]:
                    self._json(503, {"error": "TradingAgents / ChatGPT is not yet authorized on the server"})
                    return
                job_id = self.server.research.start(ticker, day, asset_type)
                self._json(202, {"job_id": job_id, "status": "running", "mode": "research only"})
                return
            if path not in ("/api/paper/fund", "/api/paper/buy", "/api/paper/sell"):
                self._json(404, {"error": "unknown endpoint"})
                return
            event_id = self._id(body)
            if body.get("approved") is not True:
                raise PermissionError("explicit paper-only approval is required")
            with self.server.paper_lock:
                ledger = PaperLedger(self.server.db_path)
                try:
                    if path == "/api/paper/fund":
                        amount = decimal(body.get("usd"), "usd", positive=True)
                        if amount > Decimal("1000000"):
                            raise ValueError("maximum single paper deposit is $1,000,000")
                        inserted = ledger.fund(event_id, amount)
                        output = {"mode": "paper", "inserted": inserted, "summary": ledger.summary()}
                    elif path == "/api/paper/buy":
                        # Only synthetic candidate is available in this mobile MVP;
                        # no client-supplied data is trusted as a market quote.
                        if body.get("candidate_id") != "demo-sol":
                            raise ValueError("only synthetic demo candidate is supported")
                        candidate = Candidate.from_mapping(sample_candidate())
                        result = PaperDesk(ledger).buy(
                            event_id, candidate, body.get("usd"),
                            approved=True, fee_usd=body.get("fee_usd", "0"))
                        output = {**result, "synthetic": True, "summary": ledger.summary()}
                    else:
                        if body.get("candidate_id") != "demo-sol":
                            raise ValueError("only synthetic demo candidate is supported")
                        result = ledger.sell(
                            event_id, DEMO_MINT, body.get("qty"),
                            body.get("price_usd"), body.get("fee_usd", "0"),
                            source="manual-reviewed")
                        output = {"mode": "paper", "synthetic": True,
                                  "realized_pnl_usd": str(result), "summary": ledger.summary()}
                finally:
                    ledger.close()
            self._json(200, output)
        except (ValueError, PermissionError, TypeError, json.JSONDecodeError) as exc:
            self._json(400, {"error": str(exc)})
        except RuntimeError as exc:
            if path.startswith("/api/chatgpt/"):
                message = str(exc)
                if "installed" in message:
                    self._json(503, {"error": "TradingAgents must be installed on the server first"})
                else:
                    self._json(409, {"error": "A ChatGPT sign-in is active or the connection is unavailable"})
            else:
                self._json(409, {"error": "research is already in progress"})


def main(argv=None):
    parser = argparse.ArgumentParser(description="Ncodex mobile paper-only PWA")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3000)
    parser.add_argument("--db", default=os.environ.get("NCODEX_DB", "paper.db"))
    args = parser.parse_args(argv)
    token = os.environ.get("NCODEX_ACCESS_TOKEN", "")
    if args.host not in ("127.0.0.1", "localhost", "::1") and len(token) < 20:
        parser.error("public binds require NCODEX_ACCESS_TOKEN of at least 20 characters")
    with MobileServer((args.host, args.port), args.db, token) as server:
        print(f"Ncodex PAPER mobile UI at http://{args.host}:{server.server_port} "
              "(run behind TLS + authentication for remote access)", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
