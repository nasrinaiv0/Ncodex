# Ncodex deployments: Vercel frontend + persistent backend

## Why the first deployment failed

The first build failed with \`PYTHON_ENTRYPOINT_NOT_FOUND\`. The repository
contained a long-running Python HTTP server (\`ncodex.mobile\`) and many
upstream Python projects, but no Python WSGI/ASGI app in a supported entry
module. Vercel cannot infer which server to run.

The root-level \`app.py:app\` is now explicitly selected in \`pyproject.toml\`
and serves Ncodex's mobile UI as a Vercel Python Function.
\`vercel.json\` bundles the \`web/\` assets and excludes large upstream samples.

## A necessary architectural distinction

Vercel Functions are **not a drop-in persistent replacement** for a server
that stores paper transactions in local SQLite and holds an in-memory
TradingAgents ChatGPT OAuth session. They may start and stop at any time.

Do **not** point them at a temporary \`/tmp/paper.db\` or expect multiple
functions to share one OAuth session. This frontend intentionally fails
closed with HTTP 503 for stateful trading, research, and paid voice until
a dedicated backend has been configured.

## Setup

1. Deploy this branch to the linked Vercel \`ncodex\` project. The Vercel
   production URL will serve the Ncodex home, Dirk/EJ selector, chat shell,
   CSS and JS, without needing Python server startup.
2. Deploy a persistent, private Ncodex Python server (e.g. on a secured
   container/VM service) using
   \`python -m ncodex.mobile --host 127.0.0.1 --port 3000 --db paper.db\`
   behind a trusted HTTPS reverse proxy. Use persistent storage, TLS,
   authentication and secret management. For commercial multiuser trading,
   replace local SQLite and in-memory OAuth with proper isolated durable
   services; the reference server remains owner-only.
3. In Vercel **Production** environment variables, set
   \`NCODEX_BACKEND_URL\` to the HTTPS **origin only** for that private
   server, e.g. \`https://backend.example.com\` (not \`/api\`).
4. Configure the same owner-only \`NCODEX_ACCESS_TOKEN\` in Vercel and on
   the backend. Users enter that token on the mobile Settings page for
   the current browsing session. Vercel **does not inject** the token into
   public clients or forward it to arbitrary destinations.
5. On the persistent backend, configure \`ELEVENLABS_API_KEY\`,
   \`NCODEX_ENABLE_ELEVENLABS_VOICE=1\`, and
   \`NCODEX_ENABLE_CHATGPT_CONNECT=1\` only when ready for real tests.
   Complete ChatGPT authorization on the trusted backend.
6. Validate \`/api/health\`, \`/api/paper\`, account isolation, voice,
   mobile browser playback and research workflow before advertising the
   product as live. All trading remains paper-only.

## Security

The Vercel frontend enforces same-origin requests, checks the presence of
an owner bearer token before proxying, refuses URL redirects, limits payload
sizes, forwards only JSON/MP3, and sets Content Security Policy and
no-store on API responses. The backend must still enforce its own token,
permissions, input validation and transaction idempotency. **Do not** make
the backend public without authentication and network protections.

If \`NCODEX_BACKEND_URL\` is absent, a 503 response for backend APIs is
**expected and safer than pretending a trade or paid service worked**.
The presence of a saved Vercel environment variable does not prove the
provider connection or subscription is authorized. Real ElevenLabs audio
generation may incur charges and requires explicit testing.

