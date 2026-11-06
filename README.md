# Ncodex

An experimental, **paper-trading-first** integration workspace for Solana token research, launch monitoring, risk assessment, and precision accounting.

Six upstream projects are pinned as **Git submodules**, rather than flattened into one unsafe dependency tree. This allows Ncodex to reference each project's original code, version and license while maintaining its own security boundary.

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

## Clone all six pinned upstreams

\`\`\`bash
git clone https://github.com/nasrinaiv0/Ncodex.git
cd Ncodex
git submodule update --init --recursive
# Or use: bash scripts/sync_sources.sh
\`\`\`

Git submodules are stored as pinned gitlinks, **not automatically executed**. The Eliza monorepo is large; cloning the complete working tree may require substantial disk space.

## Core: offline risk and paper accounting

Requires Python 3.11+; has no third-party Python dependencies.

\`\`\`bash
python -m unittest discover -s tests -v
python -m ncodex.cli analyze --candidate examples/solana-candidate.json --usd 20 --now 2026-11-06T02:00:00+00:00
python -m ncodex.cli fund --db paper.db --usd 1000 --id initial-capital
python -m ncodex.cli paper-buy --db paper.db --candidate examples/solana-candidate.json --usd 20 --id paper-buy-1 --approve --now 2026-11-06T02:00:00+00:00
python -m ncodex.cli summary --db paper.db
\`\`\`

The example candidate is synthetic, never live market data. Never use the example's token or price to place a real trade.

The evaluator requires verified security attributes (liquidity, concentration, honeypot status, mint and freeze authority) and rejects missing or stale data. Even a favorable risk verdict is **not an automatic order**. Paper buys require explicit \`--approve\`. The SQLite ledger is append-only for journal entries and uses decimal arithmetic plus FIFO lots for partial sales, fees and realized P&L.

## Design principles

1. **Fail closed.** Unknown security status, stale data, missing wallet balance, or failed approval means no trade.
2. **Live trading disabled.** Submodules may contain live-trade features, but Ncodex never calls them.
3. **Audit all money movements.** Double-entry journal, idempotency keys, FIFO cost basis and fees in USD.
4. **Keep agent memory separate from execution authority.** AI may summarize evidence; it cannot sign transactions.
5. **Pin and review upstream versions.** Never auto-update dependencies or silently run their setup scripts.

See [Integration Architecture](docs/INTEGRATION.md), [Security & Licensing](docs/SECURITY.md), and [Sources](docs/SOURCES.md).