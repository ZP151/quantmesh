# QuantMesh

> A local-first, evidence-driven workstation for cross-market quantitative
> research, real-time monitoring and deterministic paper trading.

**Status:** pre-release · local-only · paper-first · English / 简体中文 · no
autonomous execution

QuantMesh brings equities, crypto perpetuals and prediction markets into one
inspectable workflow. It is built for a solo quantitative researcher who needs
to see where a value came from, how fresh it is, test an idea, rehearse a
paper decision and reproduce the result later.

**[中文说明](README.zh-CN.md)** · **[Product strategy](docs/product-strategy.md)** ·
**[Roadmap](docs/roadmap/ROADMAP.md)** · **[Active delivery state](docs/goals/ACTIVE.md)**

## What works today

| Surface | Current capability | Truth boundary |
| --- | --- | --- |
| Local workstation | One-command, loopback-only React/FastAPI application | Never exposed as a hosted service |
| Demo | Deterministic seeded data, resettable paper account and provenance labels | Demo and synthetic data are visibly labelled |
| Markets | Equities, crypto and prediction-market views; watchlists and research screens | Venue/source/time/freshness remain visible |
| Paper workflow | Paper orders, positions, P&L, risk controls, kill switch and audit trail | The deterministic paper kernel remains the order authority |
| Live research | Read-only connectors, freshness states, smoke and replay drills where a local feed is available | Missing or stale feeds are unavailable, never fabricated |
| Preferences | Persistent English / Simplified Chinese and system / light / dark themes | Preference data stays in the local browser |

## Quick start

### Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev,research,e2e]"
quantmesh-workstation --demo
```

Open <http://127.0.0.1:8765/app/>. The first demo start seeds a labelled,
deterministic local scenario; it never sends an order or credential to an
external venue.

### Optional read-only live research

Use live mode only after configuring a bounded local watchlist. It remains
read-only and is intentionally separate from the deterministic demo:

```powershell
$env:QUANTMESH_LIVE_WATCHLIST = "BTC,ETH,SOL,HYPE"
quantmesh-workstation --live
```

See the [live-cockpit operator checklist](docs/runbooks/live-cockpit-operator-checklist.md)
before connecting optional Moomoo or prediction-market sources.

## The product loop

```text
Observe sourced market evidence
        ↓
Check venue · timestamp · sequence · age · freshness
        ↓
Research / forecast / compare a hypothesis
        ↓
Deterministic risk checks and paper-order decision
        ↓
Positions · P&L · risk · audit · replay
```

The interface is intentionally dense but not opaque: a synthetic, delayed,
stale, disconnected or replayed value must look different from a live value.

## Safety model

QuantMesh is a research and rehearsal environment, not an autonomous trading
bot.

- AI may summarize evidence, challenge a thesis and propose experiments; it
  cannot sign, place, cancel or resize orders.
- Paper trading is the default. Mainnet signing, real-money execution and
  wallet custody are outside the current product boundary.
- Every order path is governed by deterministic risk rules, quote fences,
  position limits, kill switches and audit records.
- Secrets stay local. Never put private keys, broker credentials or raw signed
  payloads in prompts, commits or issue descriptions.

Read the full [threat model](docs/threat-model.md) and
[release process](docs/release-process.md) before any execution-related work.

## Architecture

```text
React + TypeScript + Vite workstation
              │
              ▼
       FastAPI local API
              │
  ┌───────────┼────────────────┐
  ▼           ▼                ▼
Market    Research lake    Paper / risk / audit
adapters  DuckDB + Parquet deterministic kernel
  │
  ├─ Hyperliquid (read-only public data)
  ├─ Moomoo OpenD (optional local read-only / paper surface)
  ├─ Polymarket and Kalshi (read-only probability data)
  └─ Deterministic demo and replay fixtures
```

QuantMesh owns the normalized contracts, provenance/freshness semantics,
paper kernel, risk gates, replay evidence and operator workflow. It reuses
mature libraries and official SDKs behind adapters rather than rebuilding
commodity infrastructure.

## Delivery roadmap

| Horizon | Outcome |
| --- | --- |
| Now | Local demo-to-paper workflow, auditability, global preferences and full SPA localization |
| Next: iteration 0019 | Bounded live research board: quote/book/trade/probability metrics, honest freshness, compact charts and deterministic replay |
| Research lab | Features, backtests, walk-forward evaluation, model registry and lineage |
| Portfolio and risk | Cross-market exposure, correlations, limits, drawdown and reconciliation |
| AI advisory | Local evidence-backed analyst, critic and risk-assistant outputs with citations |
| Guarded execution | Only after separate approval, simulation/testnet gates, idempotency and reconciliation drills |

The current executable plan is [iteration 0019](docs/iterations/0019-live-research-surface.md).
The longer-term product boundary is recorded in
[the strategy document](docs/product-strategy.md).

## Open-source reuse

| Reuse target | Role in QuantMesh |
| --- | --- |
| Qlib / LightGBM / scikit-learn | Research, factor and model experimentation |
| Official venue SDKs | Isolated, reviewable market-data and paper/testnet adapters |
| DuckDB / Parquet | Local research lake and reproducible replay data |
| React / Vite / selected shadcn/ui | Local operator workstation |
| Hummingbot, Freqtrade, OpenBB, VeighNa, TradingAgents | Design references, not copied execution authority |

Licensing, ownership and adaptation decisions live in
[the reuse matrix](docs/REUSE_MATRIX.md) and
[reference-project notes](docs/REFERENCE_PROJECTS.md).

## Repository map

```text
src/quantmesh/       Python domain, API, data, research, risk and adapters
frontend/            React/TypeScript workstation source
tests/               Regression, integration and browser tests
docs/                ADRs, runbooks, roadmap, iterations and release evidence
tools/               Build, smoke, release and operational checks
vendor/              Pinned upstream components and reference projects
```

## Development and verification

```powershell
# Python checks
python -m pytest
ruff check .

# Frontend checks
Push-Location frontend
npm ci
npm run lint
npx vitest run
npm run build
Pop-Location

# Confirm the committed SPA bundle is current
python tools/build_frontend.py --check
```

For a release candidate, run the documented clean-checkout gate rather than
treating a local green test run as release evidence.

## Contributing with agents

Read [AGENTS.md](AGENTS.md) first. The durable handoff is
[ACTIVE.md](docs/goals/ACTIVE.md); implementation decisions and evidence live
in the relevant iteration record. Use one integration branch, preserve
protected `main`, and never force-push or mutate an existing release
candidate.

## Disclaimer

QuantMesh is software for quantitative research and engineering. It is not
investment, legal or tax advice. Backtests, forecasts and paper results do
not guarantee future performance. Real trading can result in partial or total
loss of capital.
