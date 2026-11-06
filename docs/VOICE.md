# Ncodex humanoid voice — ElevenLabs

The connected ElevenLabs workspace has one saved cloned voice named **Ncodex**.
Voice ID \`wk8ShXIdIRizcgWBCs4y\` is not a secret; API credentials are.

Dirk and EJ use the same voice model and cloned voice ID. Dirk speaks at
0.95× generation speed, EJ at 1.07×, with a small client playback distinction.
This preserves a recognizable shared Ncodex voice while giving each humanoid
a slightly different cadence.

## Setup

Run Ncodex on a trusted persistent server behind HTTPS, with a private owner
token and these variables:

\`\`\`env
NCODEX_ACCESS_TOKEN=<a-long-random-owner-secret>
ELEVENLABS_API_KEY=<ElevenLabs-workspace-API-key>
NCODEX_ENABLE_ELEVENLABS_VOICE=1
\`\`\`

\`ELEVENLABS_API_KEY\` is distinct from the ChatGPT subscription and OpenAI API
key. The connected ChatGPT ElevenLabs plugin can inspect your saved voice but
does not automatically export a runtime API credential into Vercel or the app.

Open Ncodex → Chat → tap the speaker icon to opt in. A tap on the speaker
button after a reply can play the latest answer. Text replies work normally
if the voice backend is disabled or inaccessible. Mobile browsers require
user interaction before autoplay or audio playback; the app cannot override
device privacy settings. Microphone input is a separate, optional
SpeechRecognition browser feature.

The Ncodex server sends short assistant response text to ElevenLabs over
HTTPS. **Do not use private account information as speech text.** It is
processed by ElevenLabs. The server returns MP3 audio; no credentials reach
the browser. Do not copy ElevenLabs secrets into localStorage, JS, logs,
GitHub or third-party telemetry.

## Safeguards

- Owner-token authentication mandatory for paid voice; disabled by default.
- Max 700 characters per request, 1.5 MB response, fixed API hostname.
- At most one synthesis at a time and a 3-second gap, 100 requests per server
  day; this is an in-memory best-effort limit, not production-grade billing
  protection.
- No caching of generated voice or raw text on disk; media URL is revoked
  after playback. Requests can still appear in ElevenLabs provider history.
- No live trading is performed or authorized by voice playback.

Real multiuser deployment needs per-account quotas and billing, authentication,
cloud provider spending limits, persistent distributed rate limiting,
privacy disclosures, consent, monitoring and abuse controls.
