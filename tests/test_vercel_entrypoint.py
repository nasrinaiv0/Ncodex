"""Smoke and security tests for Vercel's stateless WSGI entrypoint."""
import io
import json
import os
import unittest
from unittest.mock import patch
from wsgiref.util import setup_testing_defaults

import app as vercel_app


class HTTPResult:
    def __init__(self, status=200, mime="application/json", data=b'{"mode":"paper"}'):
        self.status = status
        self.headers = {"Content-Type": mime}
        self.data = data
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, n=-1): return self.data[:n]


class FakeOpener:
    def __init__(self, calls):
        self.calls = calls
    def open(self, request, timeout=None):
        self.calls.append(request)
        return HTTPResult()


class VercelEntrypointTests(unittest.TestCase):
    def request(self, path, method="GET", data=None, headers=None):
        env = {}
        setup_testing_defaults(env)
        env["REQUEST_METHOD"] = method
        env["PATH_INFO"] = path
        env["HTTP_HOST"] = "ncodex.example.com"
        env["wsgi.url_scheme"] = "https"
        if data is not None:
            body = json.dumps(data).encode()
            env["CONTENT_LENGTH"] = str(len(body))
            env["wsgi.input"] = io.BytesIO(body)
        if headers:
            env.update(headers)
        info={}
        def start(status, hs):
            info["status"] = int(status[:3])
            info["headers"] = dict(hs)
        with patch.dict(os.environ, {"NCODEX_BACKEND_URL": ""}):
            info["body"] = b"".join(vercel_app.app(env, start))
        return info

    def test_app_entrypoint_is_callable(self):
        self.assertTrue(callable(vercel_app.app))
        self.assertIn("/index.html", vercel_app.STATIC)

    def test_home_and_two_humanoids_are_served(self):
        info=self.request("/")
        self.assertEqual(info["status"],200)
        self.assertIn(b'data-humanoid="dirk"',info["body"])
        self.assertIn(b'data-humanoid="ej"',info["body"])
        self.assertIn(b'href="/humanoids.css"',info["body"])
        self.assertIn("media-src 'self' blob:",info["headers"]["Content-Security-Policy"])

    def test_static_assets_and_no_directory_browsing(self):
        for path in ("/app.js","/styles.css","/humanoids.css","/sw.js","/manifest.webmanifest","/icon.svg"):
            with self.subTest(path=path):
                self.assertEqual(self.request(path)["status"],200)
        self.assertEqual(self.request("/.env.example")["status"],404)
        self.assertEqual(self.request("/upstream/OpenAlice/LICENSE")["status"],404)
        self.assertEqual(self.request("/api/swagger")["status"],503)
        self.assertEqual(self.request("/app.js","POST")["status"],405)

    def test_health_and_api_fail_closed_without_persistent_backend(self):
        r=self.request("/api/health")
        self.assertEqual(r["status"],503)
        data=json.loads(r["body"])
        self.assertEqual(data["status"],"persistent_backend_not_configured")
        self.assertFalse(data["live_trading_enabled"])
        for p in ("/api/paper","/api/voice","/api/chatgpt/start"):
            with self.subTest(path=p):
                method="POST" if p != "/api/paper" else "GET"
                r=self.request(p,method=method,data={} if method=="POST" else None)
                self.assertEqual(r["status"],503)
        self.assertEqual(self.request("/api/health")["headers"]["Cache-Control"],"no-store")

    def test_origin_restriction_and_owner_token(self):
        with patch.dict(os.environ,{"NCODEX_BACKEND_URL":"https://private.example.com"}):
            env = {}
            setup_testing_defaults(env)
            env.update({"REQUEST_METHOD":"GET","PATH_INFO":"/api/paper","CONTENT_LENGTH":"0",
                        "HTTP_HOST":"ncodex.example.com","wsgi.url_scheme":"https"})
            def invoke():
                captured={}
                def start(status,hs):captured["status"]=int(status[:3]);captured["headers"]=dict(hs)
                captured["body"]=b"".join(vercel_app.app(env,start))
                return captured
            self.assertEqual(invoke()["status"],401)
            env["HTTP_AUTHORIZATION"]="Bearer secure-owner-token-for-proxy-1234567"
            env["HTTP_ORIGIN"]="https://evil.example.com"
            self.assertEqual(invoke()["status"],403)

            env["HTTP_ORIGIN"]="https://ncodex.example.com"
            calls=[]
            with patch.object(vercel_app,"build_opener",return_value=FakeOpener(calls)):
                r=invoke()
            self.assertEqual(r["status"],200)
            self.assertEqual(len(calls),1)
            self.assertEqual(calls[0].full_url,"https://private.example.com/api/paper")
            self.assertEqual(calls[0].get_header("Authorization"),
                             "Bearer secure-owner-token-for-proxy-1234567")
            self.assertEqual(r["headers"]["Cache-Control"],"no-store")
            self.assertNotIn("Set-Cookie",r["headers"])

    def test_backend_url_rejects_untrusted_scheme_and_credentials(self):
        for url in ("http://private.example.com","https://user:secret@example.com",
                    "file:///root/.env","https://example.com/api",
                    "https://example.com?token=private"):
            with self.subTest(url=url),patch.dict(os.environ,{"NCODEX_BACKEND_URL":url}):
                self.assertIsNone(vercel_app.backend_origin())

    def test_build_manifest_keeps_web_assets(self):
        from pathlib import Path
        spec=json.loads(Path("vercel.json").read_text())
        self.assertEqual(spec["functions"]["app.py"]["includeFiles"],"web/**")
        self.assertEqual(spec["functions"]["app.py"]["maxDuration"],30)


if __name__ == "__main__":
    unittest.main()

