# Integration architecture

## Data flow (stage 1 implemented / stage 2 future)

```text
Chainstack listener (separate process) -----+
                                             +--> Normalization/validation (contract)
GMGN research and security snapshot --------+             |
                                                           v
                                              Ncodex RiskPolicy (implemented)
                                                           |
                                  +------------------------+------------------------+
                                  |                                                 |
                               rejected                                    human paper approval
                                                                                   |
                                                                                PaperDesk
                                                                                   |
                                                                SQLite double-entry FIFO ledger
                                                                                   |
                                                             PatternMemory observations/outcomes
```

OpenAlice can be an **external** research/workflow UI; Eliza can be an **external** context agent. Neither receives signing permission or database write access. sol-trade-sdk stays an isolated future executor, not loaded by the Ncodex core. Matt Pocock's engineering skills are optional developer tooling.

## Upstream adapter contract

External crawlers/watchers are untrusted. A trusted mapping process must verify and normalize data into the exact keys consumed by `Candidate.from_mapping`:

```json
{
  "chain": "solana",
  "mint": "valid-base58-address",
  "source": "chainstack+gmgn",
  "observed_at": "ISO-8601-with-zone",
  "quote_at": "ISO-8601-with-zone",
  "price_usd": "decimal-string",
  "liquidity_usd": "decimal-string",
  "token_age_seconds": 60,
  "security": {
    "top10_holder_pct": "decimal-string",
    "developer_holder_pct": "decimal-string",
    "honeypot": false,
    "mint_authority_disabled": true,
    "freeze_authority_disabled": true
  }
}
```

The offline `watch` command reads newline-delimited normalized candidate JSON and stores deduplicated evaluations in SQLite pattern memory. It never sends orders. Use `--source-file -` to accept JSONL on standard input from a separate, reviewed listener process.

The contract is NOT a claim that raw GMGN or Chainstack payloads already match the schema. A future adapter must verify exact upstream fields and confidence before passing verified data. Missing or malformed data raises and blocks. Token scanners cannot establish safety by themselves.

## Proposed service boundaries

- `scanner`: GMGN API client with quotas, retries, timestamping, verified token addresses. No signing keys.
- `watcher`: Chainstack event listener with deduplication, rate limits, replay/catchup and backpressure. No signing keys.
- `brain`: Eliza external summarizer. No trading permission or self-modifying safety policy.
- `manager`: OpenAlice as separate AGPL-licensed application, optional human review and schedules.
- `executor`: Separate Rust `sol-trade-sdk` process **not enabled**, with HSM/signing boundary, authenticated requests, chain-id and quote checks.
- `accountant`: Ncodex ledger, independent of agent-generated prose. FIFO, per-event idempotency and balanced journal.

## Accounting design

Paper buy: debit inventory cost (including fee), credit cash. Paper sell: debit net cash, credit FIFO inventory cost and credit realized gain (or debit realized loss). Deposits: debit cash, credit owner equity. Sub-cent amounts are retained as exact Decimals; display-layer currency formatting must occur only after totals are computed. Real-world reporting later needs actual token decimals, swap receipts, fee assets, network fees, chain reorg handling and tax-lot policies per jurisdiction.

## What is NOT built yet

No API credentials, GMGN HTTP adapter, Chainstack realtime feed, agent hosting, OpenAlice process wiring, live Solana transaction signing, market data freshness provider, dashboard, replay/backtesting, true predictive learning or production deployment. These need separate, reviewable implementation work; **submodule inclusion is not functional interoperability**.

## Safe acceptance gates before production

1. Real upstream payload contract tests, market-data provenance, anti-sybil/honeypot assessments.
2. End-to-end devnet/testnet replay and simulator with fees/slippage, network faults and duplicate orders.
3. Signing segregation, hardware-backed keys, manual approvals, kill switch and spending ceilings.
4. OpenAlice AGPL compliance, data rights, jurisdictional regulatory and tax reviews.
5. Operations: uptime, alerting, trace IDs, reconciliation to on-chain receipts, rollback and incident response.


## Mobile DIRK/EJ prototype and two new sources

```text
iPhone / Android / tablet / desktop browser (mobile PWA)
     | HTTPS and per-user auth REQUIRED for production (not yet included)
     v
Ncodex /api endpoint
     |-- /paper --> Decimal-safe SQLite simulation; no real trades
     |-- /research --> TradingAgents Python library
     |                     |-- ChatGPT subscription login on HOST only
     |                     |-- multi-agent debate/report
     |                     +-- signal and reports shown as UNVERIFIED research
     |-- /integrations --> read-only Freqtrade (dry_run=true verified first)
     +-- local guided DIRK/EJ chat / TTS / browser STT
```

TradingAgents v0.7.0+ documents ChatGPT Plus/Pro subscription sign-in with `tradingagents login chatgpt` and `llm_provider="chatgpt"`. This access is held by the server user; **Ncodex does not fetch or transfer ChatGPT sign-in tokens**. The adapter uses a background thread and in-memory job state; production needs a durable job queue, per-user authentication and authorization, execution timeouts, per-user isolation, rate limits and cost limits, cancellation and retries.

Freqtrade is a separate Python bot using exchange APIs; its read-only control-plane adapter is intentionally locked to allowlisted GET endpoints. A production gateway must restrict Freqtrade native API credentials, avoid SSRF, bind localhost or HTTPS, and not expose live-trading endpoints.

**Humanoid** refers to the DIRK/EJ selectable interface: animated face, speaking expression, accessible text chat, browser speech recognition when available, and optional speech synthesis. It does not imply physical robotics or human-level autonomous trading.

Mobile PWA shell can be offline-cached, but live research and authoritative ledger operations require the server. The service worker deliberately never caches API responses.

DIRK and EJ's guided text replies run locally and use explicitly scripted intent paths; they are not a generative model. Genuine TradingAgents research requires the separate host sign-in. No direct ChatGPT conversation access is claimed.
