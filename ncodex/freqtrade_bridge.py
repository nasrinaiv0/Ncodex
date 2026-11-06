"""Read-only Freqtrade REST integration.

No remote hostname is ever accepted from mobile-client input; credentials stay
in server environment. No endpoint here places, cancels, or changes an order.
"""
from __future__ import annotations
import base64
import json
import os
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Freqtrade redirects are forbidden")


class FreqtradeBridge:
    def __init__(self, base_url: str | None = None,
                 username: str | None = None, password: str | None = None):
        self.base = (base_url if base_url is not None
                     else os.environ.get("FREQTRADE_API_URL", "")).rstrip("/")
        self.username = username if username is not None else os.environ.get("FREQTRADE_API_USER", "")
        self.password = password if password is not None else os.environ.get("FREQTRADE_API_PASSWORD", "")
        if self.base:
            u = urlsplit(self.base)
            if u.scheme not in ("http", "https") or not u.hostname or u.username or u.password or u.query or u.fragment or u.path not in ("", "/"):
                raise ValueError("invalid Freqtrade base URL")
            if u.scheme == "http" and u.hostname not in ("127.0.0.1", "localhost", "::1"):
                raise ValueError("remote Freqtrade must use HTTPS")

    def configured(self) -> bool:
        return bool(self.base and self.username and self.password)

    def get(self, endpoint: str) -> dict | list:
        if endpoint not in ("ping", "status", "profit", "show_config"):
            raise ValueError("read-only endpoint not allowed")
        if not self.configured():
            raise RuntimeError("Freqtrade read-only connector is not configured")
        token = base64.b64encode((self.username + ":" + self.password).encode()).decode()
        req = Request(self.base + "/api/v1/" + endpoint,
                      headers={"Authorization": "Basic " + token,
                               "Accept": "application/json"}, method="GET")
        with build_opener(NoRedirect()).open(req, timeout=5) as resp:
            data = resp.read(262_145)
        if len(data) > 262_144:
            raise ValueError("Freqtrade response too large")
        parsed = json.loads(data.decode("utf-8"))
        if not isinstance(parsed, (dict, list)):
            raise ValueError("unexpected Freqtrade response")
        return parsed

    def snapshot(self) -> dict:
        if not self.configured():
            return {"configured": False, "connected": False, "mode": "read-only"}
        try:
            conf = self.get("show_config")
            # Fail closed if remote bot might be LIVE.
            dry = conf.get("dry_run") is True if isinstance(conf, dict) else False
            if not dry:
                return {"configured": True, "connected": True,
                        "mode": "blocked", "reason": "Freqtrade not in dry-run mode"}
            statuses = self.get("status")
            return {"configured": True, "connected": True, "mode": "read-only dry-run",
                    "open_trade_count": len(statuses) if isinstance(statuses, list) else 0}
        except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
            return {"configured": True, "connected": False, "mode": "read-only",
                    "error": type(exc).__name__}
