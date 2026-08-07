# QuantMesh Product Roadmap

Last updated: 2026-08-07

## Status legend

- `DONE`: exit criteria are met and evidence is recorded.
- `ACTIVE`: current iteration target.
- `NEXT`: committed near-term scope.
- `LATER`: sequenced but not committed to the next iteration.

## Delivery principles

1. Paper-first: no live execution before deterministic simulation and paper evidence.
2. Vertical slices: each iteration joins data, domain logic, API and verification where practical.
3. Reuse-first: integrate maintained SDKs and frameworks behind adapters.
4. Evidence-first: backtests include costs, time ordering and out-of-sample validation.
5. Local-first: data, credentials, models and audit logs remain under user control.

## Baseline completed

### M0 — Repository foundation (`DONE`)

Delivered:

- Python/FastAPI package skeleton and health endpoint
- Shared instrument, quote, signal and order-request models
- Minimal internal paper connector
- Pinned direct components and reference projects as Git submodules
- English primary README and Chinese companion README
- GitHub remote and Apache-2.0 repository license

### M1 — Agent collaboration environment (`DONE`)

Delivered:

- Codex and Claude project environments
- Curated project-scoped engineering skills
- Shared agent contract, role prompts and safety defaults
- GitHub issue/triage conventions
- Domain context, ADRs, roadmap and writable iteration ledger

Exit criteria:

- A new agent can identify the current goal, domain terms, safety boundaries and verification commands without conversation history.
- A new iteration can be created with `quantmesh-iteration`.

## Product milestones

### M2 — Deterministic paper-trading kernel (`DONE`, merged to main 2026-08-07)

Outcome: run a complete order lifecycle locally with reproducible cash, positions, fills and P&L.

Deliverables:

- Account, cash, position, order, fill and fee models
- Explicit order-state machine
- Deterministic market/limit order matching
- Spread, fee and slippage models
- Pre-trade limits and kill switch
- SQLite event/audit persistence
- Replay and reconciliation tests

Reuse targets: Freqtrade dry-run behavior, Hummingbot order tracking, NautilusTrader event semantics as references.

Exit criteria:

- Identical replay input produces identical fills and portfolio state.
- Invalid state transitions and stale quotes fail closed.
- Paper account survives restart and reconciles from persisted events.

### M3 — Data foundation and experiment registry (`DONE`, merged to main 2026-08-07 as squash `bcfb0b1` via PR #23)

Outcome: ingest, normalize and version research data without coupling strategies to providers.

Deliverables:

- Provider registry and normalized bar/order-book/event schemas
- Parquet/DuckDB local lake and data-quality checks
- Dataset manifests with source, timezone, revision and license metadata
- Experiment IDs linking data, code, parameters and metrics
- Scheduled ingestion and gap detection

Reuse targets: OpenBB provider patterns, Qlib datasets, DuckDB and Parquet.

Exit criteria:

- A pinned dataset can reproduce an experiment on a clean checkout.
- Missing, duplicated and out-of-order observations are detected.

### M4 — Equity workflow with Moomoo (`NEXT`, start per frontier item 9 in `docs/goals/ACTIVE.md`)

Outcome: research and paper-trade a small US/HK equity universe through one workflow.

Deliverables:

- Moomoo OpenD health, quote and paper-order adapters
- Historical/daily/intraday ingestion
- Momentum, mean-reversion and risk-parity baselines
- VectorBT/Qlib experiment adapters
- Broker-paper versus internal-paper reconciliation

Exit criteria:

- At least three baseline strategies have walk-forward, cost-aware reports.
- Moomoo paper orders reconcile with internal order state.

### M5 — Hyperliquid crypto workflow (`LATER`)

Outcome: analyze spot/perpetual markets and execute safely on testnet.

Deliverables:

- REST/WebSocket market data with reconnect and gap recovery
- Testnet order, cancel, fill and position adapters
- Funding, leverage, liquidation-distance and reduce-only checks
- Order-book imbalance and volatility baselines
- Wallet isolation and secret-handling tests

Reuse targets: official Hyperliquid SDK and Hummingbot Hyperliquid connectors.

Exit criteria:

- Testnet execution survives disconnect/reconnect without duplicate orders.
- Risk limits prevent excess leverage and stale-data execution.

### M6 — Prediction-market intelligence (`LATER`)

Outcome: normalize event markets into calibrated probability signals.

Deliverables:

- Polymarket discovery, CLOB and history adapters
- Kalshi market-data adapter
- Canonical event, outcome, resolution-rule and expiry models
- Fee/spread/liquidity-aware implied probabilities
- Calibration metrics and cross-platform event mapping

Exit criteria:

- Point-in-time replay prevents look-ahead from market resolution data.
- Forecast reports include Brier score, calibration and liquidity confidence.

### M7 — Unified research and portfolio engine (`LATER`)

Outcome: combine equity, crypto and event signals under one risk budget.

Deliverables:

- Feature registry and model registry
- LightGBM/logistic/HMM/GARCH baseline pipelines
- Ensemble and uncertainty calibration
- Portfolio constraints, exposure decomposition and scenario tests
- Model drift and failure detection

Exit criteria:

- Every promoted signal has benchmark, ablation and out-of-sample evidence.
- Portfolio construction respects venue, asset and event-risk constraints.

### M8 — Local AI research layer (`LATER`)

Outcome: use AI to accelerate research while preserving deterministic execution authority.

Deliverables:

- Local/OpenAI-compatible model gateway
- Structured analyst, critic, risk and portfolio research roles
- Retrieval over filings, news, experiments and audit logs
- Tool permissions and prompt-data redaction
- Decision logs with citations and model metadata

Reuse targets: TradingAgents role orchestration and OpenBB AI/data boundaries.

Exit criteria:

- AI output is schema-validated and cannot bypass risk APIs.
- Research claims link to source data and reproducible experiments.

### M9 — Local frontend workstation (`LATER`)

Outcome: operate research, paper portfolios and risk from a local web interface.

Deliverables:

- Market overview, watchlists and cross-venue instruments
- Experiment comparison and strategy promotion screens
- Positions, orders, fills and P&L
- Prediction probability and calibration views
- Risk alerts, audit explorer and global kill switch
- Playwright end-to-end coverage

Exit criteria:

- Core paper workflow is usable without direct database or CLI access.
- Critical controls pass keyboard, accessibility and end-to-end tests.

### M10 — Guarded live execution and hardening (`LATER`)

Outcome: permit limited live trading with explicit user control and production-grade observability.

Deliverables:

- Per-venue live enablement and approval workflow
- Idempotency, reconciliation and disaster recovery
- Secret store integration and signed audit exports
- Metrics, structured logs, alerts and incident runbooks
- Security threat model, dependency/license scanning and release process

Exit criteria:

- Shadow/paper operation meets defined reliability and drawdown limits.
- Live execution can be disabled globally and per venue without model cooperation.
- Recovery drills demonstrate no duplicate or orphaned orders.

## Current next slice

M3 (data foundation and experiment registry) is planned in `docs/iterations/0005-m3-data-foundation.md` as a six-slice chain: normalized market-data schemas, Parquet/DuckDB lake with quality checks, dataset manifests, provider registry (fixture-only adapters), experiment registry, then scheduled ingestion and gap detection. M2's slice chain (PRs #7-#11) merged to main 2026-08-07; start M3 with issue #14 (normalized market-data schemas).

