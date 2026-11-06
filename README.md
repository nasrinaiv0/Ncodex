# Ncodex

An experimental, **paper-trading-first** integration workspace for Solana token research, launch monitoring, risk assessment, and precision accounting.

Eight upstream projects are pinned as **Git submodules**, rather than flattened into one unsafe dependency tree. This allows Ncodex to reference each project's original code, version and license while maintaining its own security boundary.

> **Not a production trading bot.** No real funds are traded. No wallet keys, broker credentials, paid APIs or network requests are used by the Ncodex Python core. Historical patterns are observational, not financial advice or evidence of predictive performance.

## Modules

| Role | Upstream project | Ncodex usage |
|---|---|---|
| Token scanner, security and wallet research | [GMGN Skills](https://github.com/GMGNAI/gmgn-skills) | External research data source; normalize and verify before assessing |
| Launch watcher and strategy reference | [Chainstack pumpfun-bonkfun-bot](https://github.com/chainstacklabs/pumpfun-bonkfun-bot) | Separate monitoring process; feed alerts into Ncodex |
| Solana trade execution | [sol-trade-sdk](https://github.com/0xfnzero/sol-trade-sdk) | Future isolated Rust execution service; not enabled |
| Brain and persistent agent memory | [Eliza](https://github.com/elizaOS/eliza) | Future optional agent runtime; approvals remain outside agent |
| Research manager and human approvals | [OpenAlice](https://github.com/TraderAlice/OpenAlice) | Optional, separately licensed manager (AGPL-3.0) |
| Development process and code review | [Matt Pocock's skills](https://github.com/mattpocock/skills) | Optional engineering-agent skills |
| LLM research, debate, ratings, report memory | [Tauric TradingAgents](https://github.com/TauricResearch/TradingAgents) | Optional ChatGPT-subscription research bridge; human-reviewed |
| Dry-run crypto strategies, backtesting and FreqAI | [Freqtrade](https://github.com/freqtrade/freqtrade) | Read-only dry-run status connector, no order-control API |

## Clone all eight pinned upstreams

```bash
git clone https://github.com/nasrinaiv0/Ncodex.git
cd Ncodex
git submodule update --init --recursive
# Or use: bash scripts/sync_sources.sh
```

Git submodules are stored as pinned gitlinks, **not automatically executed**. The Eliza monorepo is large; cloning the complete working tree may require substantial disk space.

## Core: offline risk and paper accounting

Requires Python 3.11+; has no third-party Python dependencies.

```bash
python -m unittest discover -s tests -v
python -m ncodex.cli analyze --candidate examples/solana-candidate.json --usd 20 --now 2026-11-06T02:00:00+00:00
python -m ncodex.cli fund --db paper.db --usd 1000 --id initial-capital
python -m ncodex.cli paper-buy --db paper.db --candidate examples/solana-candidate.json --usd 20 --id paper-buy-1 --approve --now 2026-11-06T02:00:00+00:00
python -m ncodex.cli summary --db paper.db
# Analyze an append-only normalized watcher feed (no automatic trading):
python -m ncodex.cli watch --source-file examples/solana-candidate.jsonl --memory-db patterns.db --usd 10 --now 2026-11-06T02:00:00+00:00
python -m ncodex.cli patterns --memory-db patterns.db
```

The example candidate is synthetic, never live market data. Never use the example's token or price to place a real trade.

The evaluator requires verified security attributes (liquidity, concentration, honeypot status, mint and freeze authority) and rejects missing or stale data. Even a favorable risk verdict is **not an automatic order**. Paper buys require explicit `--approve`. The SQLite ledger is append-only for journal entries and uses decimal arithmetic plus FIFO lots for partial sales, fees and realized P&L.

## Design principles

1. **Fail closed.** Unknown security status, stale data, missing wallet balance, or failed approval means no trade.
2. **Live trading disabled.** Submodules may contain live-trade features, but Ncodex never calls them.
3. **Audit all money movements.** Double-entry journal, idempotency keys, FIFO cost basis and fees in USD.
4. **Keep agent memory separate from execution authority.** AI may summarize evidence; it cannot sign transactions.
5. **Pin and review upstream versions.** Never auto-update dependencies or silently run their setup scripts.

See [Integration Architecture](docs/INTEGRATION.md), [Security & Licensing](docs/SECURITY.md), and [Sources](docs/SOURCES.md).

## Mobile humanoid assistants (DIRK and EJ)

**Ncodex is a mobile-first progressive web app**, not eight complete desktop frameworks running on the phone. It provides an animated humanoid trading-research companion, voice input where supported by the browser, optional spoken replies, market research, paper-trading accounting, and an integrations dashboard. It uses plain HTML/CSS/JavaScript; no build tool is required for the mobile interface.

The workspaces, optional ChatGPT research process, scanners and trading engines operate as separate backend processes. Mobile clients never receive credentials to exchanges, ChatGPT sign-in files, or wallet keys.


### Two humanoid assistant versions

Users can switch between **DIRK** (charcoal armor, red optical accents, measured risk-and-strategy style) and **EJ** (silver/white shell, graphite details, responsive market-research style) on the Home, Chat or Settings screens. Each version changes the animated humanoid styling, chat labels, introductory guidance and browser text-to-speech rate/pitch. The choice is retained in localStorage as a **non-sensitive UI preference** only. Neither version has special wallet permissions: both share the existing paper-only safety rules and TradingAgents research backend. Colors are solid black, grey, charcoal, red and white (no gradients).

### Launch the local mobile server

```bash
python -m unittest discover -s tests -v
python -m ncodex.mobile --host 127.0.0.1 --port 3000 --db paper.db
# Open http://127.0.0.1:3000 on the same machine
```

For install-on-home-screen, host the PWA behind an HTTPS origin. On iOS, use Safari > Share > Add to Home Screen. Android browsers support Install app/Add to Home Screen. Remote hosting requires authenticating users, HTTPS reverse proxy, persistence and CSRF/security review; **the local reference server is not production-ready**. Never expose its Python server directly to the public internet.

### Connect TradingAgents to ChatGPT

The mobile app now includes a dedicated owner-only **Connect ChatGPT** screen under **Settings** and **Research**, with an official OpenAI sign-in link and a mobile callback-paste step. See [ChatGPT subscription authorization](docs/CHATGPT_CONNECT.md) for setup and security requirements.


At the host (not in the phone browser), install TradingAgents and authorize the supported ChatGPT subscription provider:

```bash
cd upstream/TradingAgents
python -m venv .venv
# activate .venv and install the upstream package per its README
pip install .
tradingagents login chatgpt
```

Then run the Ncodex mobile server in the same authorized environment, so it can import TradingAgents and access the local `~/.tradingagents/chatgpt-auth.json` credentials. This is optional and requires **explicit sign-in**. The bridge sets `llm_provider=chatgpt` and disables any live order capability. Your ChatGPT subscription and API key billing are separate authentication options; Ncodex does not collect your ChatGPT password.

### Connect Freqtrade for status only

Configure a Freqtrade instance in **dry-run mode** on the host and add:

```bash
export FREQTRADE_API_URL=http://127.0.0.1:8080
export FREQTRADE_API_USER=your-readonly-proxy-username
export FREQTRADE_API_PASSWORD=your-secret
```

Ncodex only queries `show_config` and `status` and refuses to report a LIVE Freqtrade bot as safe. Use dedicated least-privilege proxying in a real deployment; Freqtrade's native REST user may have more privileges than this read-only Ncodex integration.

### Interfaces

- **Home:** premium compact portfolio summary and animated DIRK/EJ humanoid selector.
- **Research:** ChatGPT-connected TradingAgents research requests with analyst reports, no orders.
- **DIRK/EJ chat:** guided local conversation with research handoff, speech-to-text (browser support dependent) and optional TTS.
- **Paper trading:** synthetic demo asset, human approval, decimal-precision double-entry ledger, FIFO positions and realized P&L.
- **Agents:** 8 source repositories and honest real-time connection statuses.
- **Settings:** local session token and diagnostics.

All demo prices and balances are labeled simulated, and live trading is disabled. This is an **early mobile prototype**, not a finished mobile App Store product.
