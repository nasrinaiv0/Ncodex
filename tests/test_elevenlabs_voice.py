from __future__ import annotations

import io
import json
import os
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from unittest.mock import patch

from ncodex.elevenlabs_voice import ElevenLabsVoice, VoiceUnavailable, VOICE_ID, VOICE_NAME
from ncodex.mobile import MobileServer


class FakeResponse:
    headers = {"Content-Type": "audio/mpeg"}
    def __init__(self, contents=b"ID3fake-mp3-payload"):
        self.content = contents
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def read(self, size=-1): return self.content[:size]


class ClonedVoiceTests(unittest.TestCase):
    def test_saved_voice_is_ncodex(self):
        self.assertEqual(VOICE_NAME,"Ncodex")
        self.assertEqual(VOICE_ID,"wk8ShXIdIRizcgWBCs4y")

    def test_clone_synthesizes_both_humanoids_with_same_voice(self):
        voice=ElevenLabsVoice("fake-key-never-sent-to-network")
        captures=[]
        def fake_send(req,timeout):
            self.assertIn(VOICE_ID,req.full_url)
            self.assertNotIn("fake-key",req.full_url)
            self.assertEqual(req.get_header("Xi-api-key"),"fake-key-never-sent-to-network")
            captures.append(json.loads(req.data))
            return FakeResponse()
        with patch("urllib.request.urlopen",side_effect=fake_send):
            a=voice.synthesize("Capital protection matters.","dirk")
            b=voice.synthesize("Compare your signals.","ej")
        self.assertEqual(a,b)
        self.assertEqual(captures[0]["model_id"],"eleven_flash_v2_5")
        self.assertLess(captures[0]["voice_settings"]["speed"],
                        captures[1]["voice_settings"]["speed"])
        self.assertEqual(captures[0]["text"],"Capital protection matters.")

    def test_bad_input_never_calls_provider(self):
        voice=ElevenLabsVoice("fake-key")
        with patch("urllib.request.urlopen") as send:
            for text,bot in [("", "dirk"),("Hi","unknown"),("z"*701,"ej")]:
                with self.assertRaises(ValueError):voice.synthesize(text,bot)
            send.assert_not_called()
        with self.assertRaises(VoiceUnavailable):
            ElevenLabsVoice("").synthesize("Hi","dirk")

    def test_upstream_errors_do_not_expose_credential(self):
        voice=ElevenLabsVoice("secret-key")
        from urllib.error import HTTPError
        with patch("urllib.request.urlopen",side_effect=HTTPError(
                "https://api.elevenlabs.io",401,"Bad key",{},None)):
            with self.assertRaises(VoiceUnavailable) as err:
                voice.synthesize("Hello","ej")
        self.assertNotIn("secret-key",str(err.exception))


class FakeVoice:
    def __init__(self):
        self.calls=[]
        self.enabled=True
    def configured(self):return self.enabled
    def synthesize(self,text,bot):
        self.calls.append((text,bot))
        return b"ID3mock-mp3-data"


class VoiceAPITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{"NCODEX_ENABLE_ELEVENLABS_VOICE":"1"})
        self.env.start()
        self.fake=FakeVoice()
        self.server=MobileServer(("127.0.0.1",0),self.temp.name+"/trades.db",
            "owner-secret-voice-test-123456789",voice=self.fake)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close()
        self.thread.join(timeout=3)
        self.env.stop();self.temp.cleanup()

    def request(self,method,path,payload=None,token=True,origin=None):
        connection=HTTPConnection("127.0.0.1",self.server.server_port,timeout=5)
        hdr={}
        if token:hdr["Authorization"]="Bearer owner-secret-voice-test-123456789"
        if origin:hdr["Origin"]=origin
        data=None
        if payload is not None:
            data=json.dumps(payload)
            hdr["Content-Type"]="application/json"
        connection.request(method,path,body=data,headers=hdr)
        resp=connection.getresponse()
        raw=resp.read()
        mime=resp.getheader("Content-Type") or ""
        status=resp.status
        cache=resp.getheader("Cache-Control")
        connection.close()
        return status,(json.loads(raw) if "json" in mime else raw),cache,mime

    def test_voice_status_and_auth(self):
        self.assertEqual(self.request("GET","/api/voice/status",token=False)[0],401)
        status,body,_,_=self.request("GET","/api/voice/status")
        self.assertEqual(status,200)
        self.assertTrue(body["enabled"])
        self.assertEqual(body["voice"],"Ncodex")
        self.assertEqual(body["humanoids"],["dirk","ej"])
        self.assertEqual(self.request("POST","/api/voice",{"text":"Hi","humanoid":"ej"},token=False)[0],401)

    def test_both_personas_and_rate_limits(self):
        status,data,cache,mime=self.request("POST","/api/voice",{"text":"Hello Dirk.","humanoid":"dirk"})
        self.assertEqual(status,200)
        self.assertEqual(data,b"ID3mock-mp3-data")
        self.assertEqual(cache,"no-store")
        self.assertIn("audio/mpeg",mime)
        self.assertEqual(self.fake.calls[-1],("Hello Dirk.","dirk"))
        status,_,_,_=self.request("POST","/api/voice",{"text":"Spam","humanoid":"ej"})
        self.assertEqual(status,429)
        self.server.voice_last_call=0
        status,_,_,_=self.request("POST","/api/voice",{"text":"Hello EJ.","humanoid":"ej"})
        self.assertEqual(status,200)
        self.assertEqual(self.fake.calls[-1],("Hello EJ.","ej"))
        self.server.voice_request_count=100
        self.server.voice_last_call=0
        self.assertEqual(self.request("POST","/api/voice",{"text":"Beyond quota","humanoid":"dirk"})[0],429)

    def test_invalid_character_and_spoofed_origin_denied(self):
        self.assertEqual(self.request("POST","/api/voice",{"text":"Hi","humanoid":"admin"})[0],400)
        self.assertEqual(self.request("POST","/api/voice",{"text":"z"*701,"humanoid":"dirk"})[0],400)
        self.assertEqual(self.request("POST","/api/voice",{"text":"Hi","humanoid":"dirk"},origin="https://evil.test")[0],403)
        self.assertFalse(self.fake.calls)

    def test_disabled_flag_prevents_all_synthesis(self):
        self.server.voice_enabled=False
        code,body,_,_=self.request("POST","/api/voice",{"text":"Hello","humanoid":"dirk"})
        self.assertEqual(code,503)
        self.assertEqual(self.fake.calls,[])


if __name__=="__main__":
    unittest.main()

