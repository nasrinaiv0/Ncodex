# Connect ChatGPT Plus / Pro to TradingAgents from Ncodex mobile

Ncodex provides an **owner-only subscription sign-in page** for TradingAgents. The
feature is based on TradingAgents' own documented Sign in with ChatGPT OAuth
flow. It is not an OpenAI API-key setup, not a hosted ChatGPT web login clone,
and not an Ncodex-managed ChatGPT username/password form.

## Prerequisites

- Install TradingAgents in an isolated Python environment on a persistent
  trusted host where Ncodex mobile's Python server is running.
- The host needs outbound HTTPS access to auth.openai.com and api.openai.com.
- The account owner needs a ChatGPT Plus or Pro subscription that can authorize
  TradingAgents' requested plan usage scope.
- Set NCODEX_ACCESS_TOKEN to a long random owner token (minimum 20 characters).
  Do not commit the value, put it in the mobile app source, or share it.
- Set NCODEX_ENABLE_CHATGPT_CONNECT=1 on the **same persistent server**.
- Serve Ncodex behind HTTPS and a private reverse proxy/access boundary.
  Do not expose the reference Python HTTP server directly to the internet.

Example locally, with your chosen virtual environment active:

    pip install ./upstream/TradingAgents
    export NCODEX_ACCESS_TOKEN="<generate a random secret>"
    export NCODEX_ENABLE_CHATGPT_CONNECT=1
    python -m ncodex.mobile --host 127.0.0.1 --port 3000 --db paper.db

## Mobile steps

1. Open Ncodex → Settings → enter your owner access token for this page session.
2. Select **Open ChatGPT connection**.
3. Tap **Continue with ChatGPT** and then **Open official ChatGPT sign-in**.
4. Sign in at OpenAI and grant TradingAgents permission to use your ChatGPT plan.
5. TradingAgents' upstream OAuth redirects to a loopback address on
   127.0.0.1, belonging to the server where it runs. On an iPhone or other
   separate device this loopback address may not load. **Copy the full final
   return URL from your browser address bar** and paste it into Ncodex's
   callback form. Do not paste it into a public chat, email, analytics service,
   or support ticket.
6. Ncodex checks the returned host, path, port and one-time state against
   the sign-in it created. TradingAgents exchanges the code using PKCE,
   verifies the signed OpenAI ID token and saves credentials in its
   server-local file (owner-readable only).
7. Visit Research and run a report to confirm the subscription can be used.
   A saved credential file is not proof the session is still valid.

## What the mobile sign-in page does not do

- It never collects ChatGPT passwords or receives subscription access tokens.
- It does not automatically connect the ChatGPT website's conversation history.
- It does not make an OpenAI API key out of a ChatGPT subscription.
- It does not link multiple Ncodex users to separate ChatGPT plans.
- It does not allow live trades, account transfers, or wallet signing.
- It does not confirm trading performance or pricing data.

## Server security and future production changes

This first version supports **one authorized operator per trusted server**, with
one in-memory OAuth attempt at a time. It requires the owner token and
NCODEX_ENABLE_CHATGPT_CONNECT=1 before starting a sign-in or disconnect.

This reference server has no commercial multiuser account system. A public
product must implement individual user authentication, per-user isolated
TradingAgents auth credentials and storage, encrypted backups, CSRF and
authorization review, rate limiting, auditing without auth-code logging,
persistent distributed OAuth session storage, and a registered HTTPS callback
mechanism approved for the product's OAuth client. Do **not** use a single
server's ChatGPT subscription as a shared multiuser credential.

The ability to revoke depends on OpenAI connectivity. TradingAgents'
sign_out() first attempts revocation then removes the local tokens, reporting
whether network revocation succeeded. If the service is unreachable, review
authorized applications in your ChatGPT account as well.

### CLI fallback

If browser callback copying is inconvenient, sign in directly on the host with

    tradingagents login chatgpt

TradingAgents provides the same paste-back fallback and stores the sign-in in
~/.tradingagents/chatgpt-auth.json. The mobile page then detects the saved
account on the next refresh. To revoke from the host, run

    tradingagents logout chatgpt

Never commit the auth file, transfer it to a mobile device, or reuse another
person's account. ChatGPT subscription usage limits still apply.
