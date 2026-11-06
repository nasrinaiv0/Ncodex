"""ChatGPT subscription connection tests — no OpenAI network calls."""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from urllib.parse import parse_qs, urlencode, urlsplit
from unittest.mock import patch

from ncodex.chatgpt_connect import ChatGPTSignIn
from ncodex.mobile import MobileServer


class FakeTradingAgents:
    redirect = "http://127.0.0.1:1455/auth/callback"
    expected_state = "TEST_STATE_8dBhyZ9LAnlvBr"
    def __init__(self):
        self.email = None
        self.last_callback = None
        self.fail = False

    def installed(self):
        return True

    def account(self):
        return self.email

    def sign_in(self, say, read_line):
        url = "https://auth.openai.com/api/accounts/authorize?" + urlencode({
            "client_id": "dynamic_agent_client", "state": self.expected_state,
            "redirect_uri": self.redirect, "code_challenge_method": "S256",
            "code_challenge": "test",
        })
        say("Continue with ChatGPT")
        say(url)
        callback = read_line()
        params = parse_qs(urlsplit(callback).query)
        if params.get("state") != [self.expected_state] or params.get("code") != ["TESTCODE"]:
            raise RuntimeError("Invalid fake callback")
        self.last_callback = callback
        self.email = "owner@example.com"
        return self.email

    def sign_out(self):
        self.email = None
        return "revoked"


def spin_until(func, timeout=3):
    until=time.monotonic()+timeout
    while time.monotonic()<until:
        value=func()
        if value:
            return value
        time.sleep(.015)
    raise AssertionError("Sign-in never reached expected state")


class SignInFlowTests(unittest.TestCase):
    def setUp(self):
        self.fake=FakeTradingAgents()
        self.flow=ChatGPTSignIn(self.fake)

    def test_correct_callback_signin_and_disconnect(self):
        flow_id=self.flow.start()["flow_id"]
        spin_until(lambda:self.flow.status()["authorize_url"])
        status=self.flow.status()
        self.assertFalse(status["session_saved"])
        self.assertNotIn("access_token",str(status))
        callback=self.fake.redirect+"?"+urlencode({"code":"TESTCODE","state":self.fake.expected_state})
        with self.assertRaisesRegex(ValueError,"state mismatch"):
            self.flow.complete(flow_id,self.fake.redirect+"?code=TESTCODE&state=WRONG")
        with self.assertRaisesRegex(ValueError,"does not match"):
            self.flow.complete(flow_id,"http://attacker.example.com/auth/callback?code=TESTCODE&state="+self.fake.expected_state)
        self.assertEqual(self.flow.complete(flow_id,callback)["flow_status"],"finishing")
        spin_until(lambda:self.flow.status()["flow_status"]=="connected")
        status=self.flow.status()
        self.assertTrue(status["session_saved"])
        self.assertEqual(status["account_email"],"owner@example.com")
        self.assertFalse(status["session_verified_online"])
        self.assertIsNone(status["authorize_url"])
        self.assertEqual(self.flow.disconnect()["token_revocation"],"revoked")
        self.assertFalse(self.flow.status()["session_saved"])

    def test_concurrent_signin_rejected(self):
        self.flow.start()
        with self.assertRaises(RuntimeError):
            self.flow.start()
        spin_until(lambda:self.flow.status()["authorize_url"])
        self.assertIn("auth.openai.com",self.flow.status()["authorize_url"])

    def test_no_dependency(self):
        class Missing:
            def installed(self): return False
            def account(self): return None
        flow=ChatGPTSignIn(Missing())
        with self.assertRaisesRegex(RuntimeError,"installed"):
            flow.start()

    def test_invalid_completion_is_rejected(self):
        f=self.flow.start()["flow_id"]
        spin_until(lambda:self.flow.status()["authorize_url"])
        invalids=[
            "http://127.0.0.1:9999/auth/callback?code=TESTCODE&state="+self.fake.expected_state,
            "http://127.0.0.1:1455/auth/callback?code=TESTCODE",
            "https://127.0.0.1:1455/auth/callback?code=TESTCODE&state="+self.fake.expected_state,
            "not-a-url",
        ]
        for value in invalids:
            with self.assertRaises(ValueError):
                self.flow.complete(f,value)


class ConnectAPITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{"NCODEX_ENABLE_CHATGPT_CONNECT":"1"})
        self.env.start()
        self.fake=FakeTradingAgents()
        self.server=MobileServer(("127.0.0.1",0),self.temp.name+"/paper.db",
                  "test-private-owner-token-1234567890",
                  chatgpt_signin=ChatGPTSignIn(self.fake))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close()
        self.thread.join(timeout=3)
        self.env.stop()
        self.temp.cleanup()

    def request(self,method,path,payload=None,authorized=True,origin=None):
        conn=HTTPConnection("127.0.0.1",self.server.server_port,timeout=5)
        headers={}
        if authorized: headers["Authorization"]="Bearer test-private-owner-token-1234567890"
        if origin: headers["Origin"]=origin
        body=None
        if payload is not None:
            body=json.dumps(payload)
            headers["Content-Type"]="application/json"
        conn.request(method,path,body=body,headers=headers)
        response=conn.getresponse()
        mime=response.getheader("Content-Type") or ""
        raw=response.read()
        status=response.status
        conn.close()
        return status,json.loads(raw) if mime.startswith("application/json") else raw

    def test_owner_only_and_mobile_assets(self):
        self.assertEqual(self.request("GET","/api/chatgpt/status",authorized=False)[0],401)
        self.assertEqual(self.request("POST","/api/chatgpt/start",{"approved":True},authorized=False)[0],401)
        self.assertEqual(self.request("GET","/connect.js")[0],200)
        self.assertEqual(self.request("GET","/connect.css")[0],200)
        html=self.request("GET","/")[1]
        self.assertIn(b'id="screen-connect"',html)
        self.assertIn(b"Continue with ChatGPT",html)
        self.assertNotIn(b'OPENAI_API_KEY=',html)

    def test_complete_signin_via_api(self):
        status,data=self.request("GET","/api/chatgpt/status")
        self.assertEqual(status,200)
        self.assertTrue(data["enabled"])
        self.assertFalse(data["session_saved"])
        self.assertEqual(self.request("POST","/api/chatgpt/start",{"approved":False})[0],400)
        code,data=self.request("POST","/api/chatgpt/start",{"approved":True})
        self.assertEqual(code,202)
        fid=data["flow_id"]
        spin_until(lambda:self.server.chatgpt_signin.status()["authorize_url"])
        code,data=self.request("GET","/api/chatgpt/status")
        self.assertEqual(data["flow_status"],"awaiting_callback")
        self.assertIn("https://auth.openai.com/",data["authorize_url"])
        callback=self.fake.redirect+"?"+urlencode({"code":"TESTCODE","state":self.fake.expected_state})
        code,_=self.request("POST","/api/chatgpt/complete",{"flow_id":fid,"callback_url":callback})
        self.assertEqual(code,202)
        spin_until(lambda:self.server.chatgpt_signin.status()["flow_status"]=="connected")
        code,data=self.request("GET","/api/chatgpt/status")
        self.assertTrue(data["session_saved"])
        self.assertEqual(data["account_email"],"owner@example.com")
        code,_=self.request("POST","/api/chatgpt/disconnect",{"approved":True})
        self.assertEqual(code,200)
        self.assertFalse(self.request("GET","/api/chatgpt/status")[1]["session_saved"])

    def test_uninstalled_provider_reports_actionable_error(self):
        self.fake.installed=lambda: False
        code,data=self.request("POST","/api/chatgpt/start",{"approved":True})
        self.assertEqual(code,503)
        self.assertIn("installed",data["error"])

    def test_cross_origin_is_blocked(self):
        code,data=self.request("POST","/api/chatgpt/start",
             {"approved":True},origin="https://evil.example.com")
        self.assertEqual(code,403)
        self.assertFalse(self.server.chatgpt_signin.status()["session_saved"])

    def test_remote_feature_flag_off(self):
        self.server.chatgpt_connect_enabled=False
        code,data=self.request("GET","/api/chatgpt/status")
        self.assertFalse(data["enabled"])
        self.assertNotIn("account_email",data)
        code,data=self.request("POST","/api/chatgpt/start",{"approved":True})
        self.assertEqual(code,403)


if __name__=="__main__":
    unittest.main()

