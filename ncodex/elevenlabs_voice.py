"""Read-only, server-side ElevenLabs speech adapter for Ncodex humanoids.

This adapter can only synthesize speech. It never accesses wallets or market
execution, never receives API credentials from the browser and never logs text.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

VOICE_NAME = "Ncodex"
# Saved "Ncodex" cloned voice in the connected ElevenLabs workspace.
VOICE_ID = "wk8ShXIdIRizcgWBCs4y"
MODEL_ID = "eleven_flash_v2_5"
API_URL = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}?output_format=mp3_44100_128"
MAX_TEXT_CHARS = 700
MAX_AUDIO_BYTES = 1_500_000


class VoiceUnavailable(RuntimeError):
    """Configured voice service failed without exposing private details."""


class ElevenLabsVoice:
    def __init__(self, key: str | None = None):
        self._key = key if key is not None else os.environ.get("ELEVENLABS_API_KEY", "")

    def configured(self) -> bool:
        return bool(self._key)

    def synthesize(self, text: str, humanoid: str) -> bytes:
        if not self.configured():
            raise VoiceUnavailable("ElevenLabs voice is not configured")
        if humanoid not in ("dirk", "ej"):
            raise ValueError("Unknown humanoid voice profile")
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_CHARS:
            raise ValueError(f"Speech text must be 1–{MAX_TEXT_CHARS} characters")
        # Same saved voice, slightly different speaking pace — no cloned voice is
        # constructed or exposed for each character.
        speed = 0.95 if humanoid == "dirk" else 1.07
        payload = json.dumps({
            "text": text.strip(),
            "model_id": MODEL_ID,
            "voice_settings": {
                "stability": 0.55,
                "similarity_boost": 0.8,
                "speed": speed,
            },
        }).encode()
        request = urllib.request.Request(
            API_URL, payload, method="POST",
            headers={
                "xi-api-key": self._key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                if "audio/" not in (response.headers.get("Content-Type") or "").lower():
                    raise VoiceUnavailable("Unexpected audio response from ElevenLabs")
                audio = response.read(MAX_AUDIO_BYTES + 1)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            # Do not leak provider responses, key, request text or auth details.
            raise VoiceUnavailable("ElevenLabs speech unavailable") from exc
        if not audio or len(audio) > MAX_AUDIO_BYTES:
            raise VoiceUnavailable("ElevenLabs audio response out of bounds")
        return audio

