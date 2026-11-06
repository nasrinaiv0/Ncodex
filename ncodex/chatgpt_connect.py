"""Owner-only, server-side ChatGPT subscription sign-in using TradingAgents.

The official TradingAgents flow generates a PKCE-protected authorization URL and
uses a loopback callback. A mobile browser cannot reach the remote server's
127.0.0.1, so the user pastes the final browser URL into the protected Ncodex
page. Only the trusted server submits it to TradingAgents' callback validator.
Never expose access tokens, refresh tokens, or ChatGPT passwords to the browser.
"""
from __future__ import annotations

import importlib
import importlib.util
from queue import Empty, Queue
import secrets
import threading
from urllib.parse import parse_qs, urlsplit


AUTH_ORIGIN = "https://auth.openai.com"
AUTH_PATH = "/api/accounts/authorize"
CALLBACK_PATH = "/auth/callback"


class TradingAgentsAuthAdapter:
    """Lazy import avoids installing the large trading framework for offline tests."""

    def _auth(self):
        return importlib.import_module("tradingagents.llm_clients.chatgpt_auth")

    def installed(self) -> bool:
        try:
            return importlib.util.find_spec("tradingagents") is not None
        except (ImportError, ValueError):
            return False

    def account(self) -> str | None:
        if not self.installed():
            return None
        try:
            return self._auth().signed_in_as()
        except (ImportError, OSError, ValueError, AttributeError):
            return None

    def sign_in(self, say, read_line) -> str:
        return self._auth().sign_in(say=say, read_line=read_line, timeout=300, port=0)

    def sign_out(self) -> str | None:
        return self._auth().sign_out()


class ChatGPTSignIn:
    """Single-operator, single-flight sign-in; never grants real trading rights."""

    def __init__(self, adapter=None):
        self.adapter = adapter if adapter is not None else TradingAgentsAuthAdapter()
        self._lock = threading.RLock()
        self._flow: dict | None = None
        self._answers: Queue | None = None
        self._done: threading.Event | None = None

    def status(self) -> dict:
        with self._lock:
            flow = self._flow
            flow_status = flow["status"] if flow else "idle"
            result = {
                "installed": bool(self.adapter.installed()),
                "session_saved": bool(self.adapter.account()),
                "account_email": self.adapter.account(),
                "session_verified_online": False,
                "flow_status": flow_status,
                "flow_id": flow["id"] if flow else None,
                "authorize_url": flow.get("url") if flow and flow_status == "awaiting_callback" else None,
                "error": flow.get("error") if flow and flow_status == "failed" else None,
                "trading_permissions": "research_only",
            }
            # Successful sign_in verified OpenAI ID token at that moment; do not
            # imply that the credential remains valid or that a plan is active.
            if flow_status == "connected":
                result["session_verified_at_sign_in"] = True
            return result

    def start(self) -> dict:
        if not self.adapter.installed():
            raise RuntimeError("TradingAgents must be installed on the server first")
        with self._lock:
            if self._flow and self._flow["status"] in ("starting", "awaiting_callback", "finishing"):
                raise RuntimeError("A ChatGPT sign-in is already running")
            attempt_id = secrets.token_urlsafe(24)
            self._flow = {"id": attempt_id, "status": "starting", "url": None,
                          "redirect_uri": None, "expected_state": None, "error": None}
            self._answers = Queue(maxsize=1)
            self._done = threading.Event()
            thread = threading.Thread(target=self._run, args=(attempt_id,),
                                      daemon=True, name="ncodex-chatgpt-auth")
            thread.start()
            return {"flow_id": attempt_id, "flow_status": "starting"}

    def _run(self, attempt_id: str) -> None:
        with self._lock:
            answers, done = self._answers, self._done

        def say(line: str) -> None:
            if not line.startswith(AUTH_ORIGIN + AUTH_PATH + "?"):
                return
            parsed = urlsplit(line)
            params = parse_qs(parsed.query, strict_parsing=True)
            redirect = params.get("redirect_uri", [""])[0]
            requested_state = params.get("state", [""])[0]
            callback = urlsplit(redirect)
            if (parsed.scheme != "https" or parsed.netloc != "auth.openai.com"
                or callback.scheme != "http" or callback.hostname != "127.0.0.1"
                or callback.path != CALLBACK_PATH or callback.port is None
                or not requested_state or callback.query or callback.fragment):
                raise ValueError("Unexpected ChatGPT authorization URL")
            with self._lock:
                if self._flow and self._flow["id"] == attempt_id:
                    self._flow.update(url=line, redirect_uri=redirect,
                                      expected_state=requested_state,
                                      status="awaiting_callback")

        def read_line() -> str:
            while not done.is_set():
                try:
                    return answers.get(timeout=0.25)
                except Empty:
                    continue
            raise EOFError

        try:
            self.adapter.sign_in(say, read_line)
        except Exception:
            # Never echo provider exceptions: some may include sensitive URLs.
            with self._lock:
                if self._flow and self._flow["id"] == attempt_id:
                    self._flow.update(status="failed",
                                      error="Sign-in failed or expired. Start a new connection.")
        else:
            with self._lock:
                if self._flow and self._flow["id"] == attempt_id:
                    self._flow.update(status="connected", url=None, error=None)
        finally:
            done.set()

    def complete(self, flow_id: object, callback_url: object) -> dict:
        if not isinstance(callback_url, str) or not (20 <= len(callback_url) <= 4096):
            raise ValueError("Paste the full URL displayed after ChatGPT authorization")
        if not isinstance(flow_id, str):
            raise ValueError("Invalid sign-in attempt")
        with self._lock:
            flow = self._flow
            if not flow or flow["id"] != flow_id or flow["status"] != "awaiting_callback":
                raise ValueError("Sign-in session is not awaiting a callback")
            final_url = urlsplit(callback_url.strip())
            redirect = urlsplit(flow["redirect_uri"])
            if (final_url.scheme, final_url.hostname, final_url.port, final_url.path) != (
                    redirect.scheme, redirect.hostname, redirect.port, redirect.path):
                raise ValueError("The final URL does not match this ChatGPT sign-in")
            if final_url.username or final_url.password or final_url.fragment:
                raise ValueError("Unexpected final URL format")
            params = parse_qs(final_url.query)
            if params.get("state") != [flow["expected_state"]]:
                raise ValueError("Sign-in security state mismatch")
            if not (params.get("code") or params.get("error")):
                raise ValueError("The final URL does not contain the authorization result")
            self._answers.put_nowait(callback_url.strip())
            flow["status"] = "finishing"
            flow["url"] = None
            return {"flow_status": "finishing"}

    def disconnect(self) -> dict:
        with self._lock:
            if self._flow and self._flow["status"] in ("starting", "awaiting_callback", "finishing"):
                raise RuntimeError("Finish the current sign-in before disconnecting")
        if not self.adapter.installed():
            raise RuntimeError("TradingAgents is not installed")
        result = self.adapter.sign_out()
        with self._lock:
            self._flow = None
        return {"disconnected": True, "token_revocation": result or "no_existing_session"}

