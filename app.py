"""Ncodex Vercel frontend entrypoint (WSGI, Python standard library).

Vercel Functions are ephemeral. This module deliberately DOES NOT start the
long-running trading server, store paper funds in local SQLite, or perform OAuth
inside a function. It serves the mobile UI and proxies authenticated API calls
to an explicitly configured persistent backend. Without that backend it fails
closed for financial/research actions.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

WEB_ROOT = Path(__file__).resolve().parent / "web"
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/connect.js": ("connect.js", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/connect.css": ("connect.css", "text/css; charset=utf-8"),
    "/humanoids.css": ("humanoids.css", "text/css; charset=utf-8"),
    "/sw.js": ("sw.js", "text/javascript; charset=utf-8"),
    "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json"),
    "/icon.svg": ("icon.svg", "image/svg+xml"),
}
STATUS = {200: "OK", 400: "Bad Request", 401: "Unauthorized", 403: "Forbidden",
          404: "Not Found", 405: "Method Not Allowed", 413: "Payload Too Large",
          502: "Bad Gateway", 503: "Service Unavailable"}
CSP = ("default-src 'self'; connect-src 'self'; img-src 'self' data:; "
       "media-src 'self' blob:; style-src 'self'; script-src 'self'; "
       "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
MAX_REQUEST_BYTES = 16_384
MAX_RESPONSE_BYTES = 2_000_000


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not forward a bearer token to an unexpected redirect target.
        return None


def response(start_response, status, data, content_type, *, dynamic=False):
    headers = [
        ("Content-Type", content_type),
        ("Content-Length", str(len(data))),
        ("X-Content-Type-Options", "nosniff"),
        ("X-Frame-Options", "DENY"),
        ("Referrer-Policy", "no-referrer"),
        ("Content-Security-Policy", CSP),
        ("Cache-Control", "no-store" if dynamic else "public, max-age=120"),
    ]
    start_response(f"{status} {STATUS.get(status, 'Unknown')}", headers)
    return [data]


def json_response(start_response, status, info):
    data = json.dumps(info, separators=(",", ":"), ensure_ascii=False).encode()
    return response(start_response, status, data, "application/json; charset=utf-8", dynamic=True)


def backend_origin():
    url = os.environ.get("NCODEX_BACKEND_URL", "").strip()
    if not url:
        return None
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                or parsed.password or parsed.path not in ("", "/")
                or parsed.query or parsed.fragment or parsed.port == 0):
            return None
        return parsed.scheme + "://" + parsed.netloc
    except ValueError:
        return None


def proxy(environ, start_response, path, method):
    origin = backend_origin()
    if not origin:
        if method == "GET" and path == "/api/health":
            return json_response(start_response, 503, {
                "status": "persistent_backend_not_configured",
                "live_trading_enabled": False,
                "mode": "paper",
            })
        return json_response(start_response, 503, {
            "error": "Persistent Ncodex backend not configured. Set NCODEX_BACKEND_URL on Vercel.",
            "live_trading_enabled": False,
        })

    auth = environ.get("HTTP_AUTHORIZATION", "")
    if not (isinstance(auth, str) and auth.startswith("Bearer ") and len(auth) > 20
            and len(auth) <= 4096):
        return json_response(start_response, 401, {"error": "owner access token required"})

    request_origin = environ.get("HTTP_ORIGIN")
    if request_origin:
        host = environ.get("HTTP_HOST", "")
        scheme = environ.get("wsgi.url_scheme", "https")
        if request_origin != f"{scheme}://{host}":
            return json_response(start_response, 403, {"error": "cross-origin request rejected"})

    size_str = environ.get("CONTENT_LENGTH", "0")
    if not size_str or not size_str.isascii() or not size_str.isdecimal():
        return json_response(start_response, 400, {"error": "invalid request size"})
    size = int(size_str)
    if size > MAX_REQUEST_BYTES:
        return json_response(start_response, 413, {"error": "request too large"})
    body = environ["wsgi.input"].read(size) if size else None

    qs = environ.get("QUERY_STRING", "")
    target = origin + path + (("?" + qs) if qs else "")
    hdrs = {"Authorization": auth, "Accept": "application/json, audio/mpeg"}
    if method == "POST":
        hdrs["Content-Type"] = "application/json"
    upstream = Request(target, data=body if method == "POST" else None,
                       headers=hdrs, method=method)
    try:
        with build_opener(NoRedirect()).open(upstream, timeout=25) as r:
            status = r.status
            mime = r.headers.get("Content-Type", "application/octet-stream")
            data = r.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as err:
        status = err.code
        mime = err.headers.get("Content-Type", "application/json") if err.headers else "application/json"
        data = err.read(MAX_RESPONSE_BYTES + 1)
    except (OSError, URLError, TimeoutError, ValueError):
        return json_response(start_response, 502, {"error": "Ncodex backend unavailable"})

    if len(data) > MAX_RESPONSE_BYTES:
        return json_response(start_response, 502, {"error": "backend response too large"})
    if not 200 <= status <= 599:
        return json_response(start_response, 502, {"error": "invalid backend status"})
    if not (mime.startswith("application/json") or mime.startswith("audio/mpeg")):
        return json_response(start_response, 502, {"error": "invalid backend content type"})
    return response(start_response, status, data, mime, dynamic=True)


def app(environ, start_response):
    """Vercel discovers this WSGI callable at app.py:app."""
    method = environ.get("REQUEST_METHOD", "GET")
    path = environ.get("PATH_INFO", "/")
    if path in STATIC:
        if method != "GET" and method != "HEAD":
            return json_response(start_response, 405, {"error": "method not allowed"})
        filename, mime = STATIC[path]
        file_path = WEB_ROOT / filename
        if not file_path.is_file():
            return json_response(start_response, 404, {"error": "static asset unavailable"})
        data = file_path.read_bytes()
        return response(start_response, 200, data if method != "HEAD" else b"", mime)
    if path.startswith("/api/"):
        if method not in ("GET", "POST"):
            return json_response(start_response, 405, {"error": "method not allowed"})
        return proxy(environ, start_response, path, method)
    return json_response(start_response, 404, {"error": "not found"})

