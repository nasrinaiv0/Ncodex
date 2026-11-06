# Security, risk, and licensing

**Default: paper-only. Live execution is not implemented.** This is experimental software, not investment advice.

- No private keys or signing logic are included. Never enter seed phrases or wallet private keys into an AI prompt, skill document, repository, CI job, or Vercel sandbox.
- Do not grant a crawler/LLM agent direct swap or withdrawal permission.
- Inputs from GMGN, Telegram, RPC, token metadata, launch watchers, and GitHub repositories are untrusted data. Sanitize and validate before display or action.
- Trading risk gates use verified metadata, liquidity/holder thresholds, a new-token cooldown, fresh timestamps, per-order caps and daily budget. These do not eliminate losses.
- No arbitrary upstream install scripts or dependency hooks run in the Ncodex test job. Clone/inspect first; audit release changes before enabling code.
- Third-party repos are tracked as gitlinks with exact commit SHAs, not vendored into Ncodex's Python import path. Independently review transitive dependencies and vulnerability disclosures.
- Do not blindly mix runtime ecosystems: Python 3.11+ (Chainstack), Rust (sol-trade-sdk), Bun/Node (Eliza), pnpm (OpenAlice), Node skills (GMGN and Matt Pocock).
- Chainstack warns its bot is for educational purposes and **not for production**; OpenAlice describes execution as **beta**.
- OpenAlice is **AGPL-3.0**, which has network-use/source-disclosure obligations. Consult counsel before redistributing a modified or hosted integrated service. The other pinned roots currently indicate MIT or Apache-2.0; verify individual bundled dependencies and notices.
- License identification is not legal advice. Respect API terms, exchange rules, market-manipulation restrictions, and local financial licensing rules.
- A user's approval for PAPER trading never grants LIVE trading authority.

- TradingAgents is Apache-2.0. It can use ChatGPT subscription sign-in if installed and authorized by the user on the server; token material must remain server-side and should never be logged or committed.
- Freqtrade is GPL-3.0; consult licensing counsel for redistributing modified code. Ncodex pins Freqtrade as an independent repository.
- The mobile server is a **local reference server**. It has a single shared paper ledger, optional shared bearer token and no per-user accounts. It must NOT be publicly deployed as a multitenant trading service without adding user-scoped database access, roles and permissions, TLS termination, CSRF protections, rate limiting, audit logs, hardened authentication and secret management.
- Public binding requires an access token but is still not a production deployment recommendation. The reference server never has wallet keys; live order submission is not implemented.
- The browser PWA cache includes only static files. API responses, secret tokens and chat contents are not cached in a service worker.
- Don't put any real exchange API passwords into the mobile browser; Freqtrade's basic credentials are read from server environment.
