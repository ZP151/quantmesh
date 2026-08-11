# Iteration 0020 — Integrated Instrument Decision Workspace

Status: active
Target release: `v0.1.1-rc1`
Baseline: released `v0.1.0` at `5a7f660`
Branch: `0020-research-to-paper-loop`
GitHub issue: [#107](https://github.com/ZP151/quantmesh/issues/107)

## Outcome

Enable a solo researcher to understand one instrument and make a traceable
paper decision without assembling evidence across separate screens.

The primary product surface becomes an integrated instrument workspace that
joins historical and live market data, chart overlays, probabilistic forecast
evidence, current position and risk, and a paper-order ticket. Existing
specialist screens remain available for deeper experiment, forecast, risk and
audit inspection; the workspace links to them with the current instrument and
run context preserved.

This iteration does not promise a profitable price prediction. It presents
model output as a dated distribution with uncertainty, benchmark and
out-of-sample evidence. Missing or failed evidence blocks promotion and renders
an explicit unavailable state.

## Product diagnosis

Iteration 0019 delivered a useful live instrument detail, but the current
surface is still fragmented:

- `/app/cockpit/:symbol` has a close-price sparkline, live metrics, book depth
  and trade tape, but no historical interval selector or candlesticks.
- watchlists, experiments, forecasts, risk, positions, orders and audit are
  separate routes and do not carry one shared instrument/run context.
- the existing Forecasts surface evaluates prediction-market probabilities;
  it does not forecast an equity or crypto price path.
- the chart is a hand-drawn single SVG line over at most 120 streamed candle
  closes. It has no volume pane, overlays, comparison series or forecast band.

## Phase 0 — framework adoption bake-off (hard gate)

Before expanding production chart, forecast or portfolio-engine code, test
whether a coherent upstream framework can replace a meaningful subsystem. The
evidence and candidate rationale are recorded in
`docs/architecture/framework-adoption-review-2026-08-11.md`.

1. Pin FinRL-X/FinRL-Trading in an isolated checkout and run one complete NVDA
   path from the existing QuantMesh historical manifest through target weights,
   cost-aware backtest metrics and a paper proposal.
2. Map those outputs to existing QuantMesh dataset, experiment, risk, proposal
   and audit identities. The candidate must not introduce provider-specific UI
   objects or bypass the deterministic paper kernel.
3. Prove clean Windows installation, deterministic reruns, chronological data
   splits, leakage checks, dependency/license closure and bounded resource use.
4. Run a narrower NautilusTrader comparator using recorded Hyperliquid replay
   through sandbox-fill semantics. Keep it outside the release closure because
   LGPL adoption and the Rust/Python process boundary are not approved.
5. Score both paths against the current native baseline for product fit, market
   coverage, provenance, safety, determinism, maintenance and migration cost.
6. Record an ADR selecting or rejecting each integration boundary. A failed
   candidate is retained as evidence and iteration 0020 continues on the
   smallest native path; a successful candidate is used only behind a stable
   QuantMesh adapter.

The gate is complete only when another clean checkout can reproduce the
scorecard. “Example runs successfully” is not sufficient evidence for runtime
adoption.

## Primary workflow

1. Select an instrument from search, watchlist, market board or position.
2. Inspect live quote state and a historical 1D/5D/1M/3M/6M/1Y chart.
3. Switch line/candlestick mode; optionally add volume, moving averages, VWAP,
   Bollinger bands and up to three normalized comparison instruments.
4. Select a 7-trading-day, 30-trading-day or 6-month forecast horizon.
5. Inspect the median forecast path, uncertainty bands, forecast vintage,
   dataset/model identity, benchmark and out-of-sample calibration.
6. Accept or reject a strategy-generated paper proposal, or create a manual
   paper order while viewing current position, buying power, exposure and risk.
7. Follow the resulting lineage to the research run, paper order, fill, P&L
   and audit record.

## Information architecture

Adopt one canonical route keyed by venue and instrument, for example
`/app/instruments/:venue/:symbol`. Keep the existing cockpit detail URL as a
compatibility redirect once venue resolution is unambiguous.

### Persistent instrument header

- symbol, venue, asset type, session state and current price/change;
- source, event time, receive time, age, sequence and freshness status;
- watchlist action, interval selector and line/candlestick selector;
- unmistakable live, delayed, stale, synthetic, unavailable or replay state.

### Main evidence canvas

- historical OHLCV plus streamed updates, joined without duplicate bars;
- price and volume panes with pan, zoom, crosshair and keyboard-safe controls;
- single-series and normalized multi-series comparison modes;
- optional technical overlays whose parameters and source are visible;
- forecast median and 50/80/95 percent intervals extending from the forecast
  vintage, visually separated from observed history;
- markers for data gaps, reconnects, corporate actions and paper fills.

### Decision rail

- forecast horizon, direction distribution and calibration summary;
- model card, dataset manifest, code/config version and latest validation time;
- current paper position, P&L, exposure, risk budget and blocking warnings;
- paper proposal/manual ticket with quantity, order type, estimated costs and
  operator confirmation;
- global kill-switch state and links to full research/risk/audit evidence.

At compact widths the rail becomes ordered sections below the chart; paper
controls never obscure provenance or forecast limitations.

## Data and API slices

1. Add a venue-aware instrument identity and a bounded historical-series API
   over the existing DuckDB/Parquet lake. The response includes OHLCV,
   adjustment policy, calendar/session, manifest identity, coverage and gaps.
2. Add an aggregated decision-workspace API/BFF that references existing live,
   research, portfolio, risk and audit records rather than copying their
   domain models.
3. Define a `PriceForecastArtifact` with instrument, horizon, target,
   forecast vintage, train/validation/test boundaries, quantile paths,
   benchmark, metrics, limitations, manifest, model and configuration IDs.
4. Store forecast artifacts append-only and make historical forecasts
   replayable as they were known at their original vintage.
5. Link only an accepted research run to a paper proposal. The deterministic
   paper kernel and existing risk/quote fences remain the only order authority.

## Forecast baseline and truthfulness gates

Start with transparent baselines before neural or reinforcement-learning
models:

- naive last-value/random-walk and drift benchmarks;
- one statistical model supported by the existing Python closure, such as
  exponential smoothing or ARIMA;
- one existing QuantMesh feature/LightGBM candidate only after its target and
  time ordering are suitable for return/quantile prediction;
- residual bootstrap or conformal-style intervals evaluated on chronological
  out-of-sample windows.

Use trading sessions, not calendar days: 7D means seven trading sessions, 30D
means thirty, and 6M defaults to approximately 126 sessions. Every model is
compared with the naive benchmark at each horizon. Do not render a directional
claim when coverage, history length, calibration, staleness or leakage gates
fail. A six-month path may legitimately be unavailable or very wide.

## Reuse decisions and spikes

- **Evaluate first as a coherent engine:** FinRL-X/FinRL-Trading for the
  offline data-to-selection-to-allocation-to-timing-to-risk workflow. It is the
  preferred permissive framework candidate, but it is not a release dependency
  until Phase 0 passes and an ADR defines its boundary.
- **Execution-semantics comparator:** NautilusTrader for one recorded
  Hyperliquid replay-to-sandbox path. Its multi-venue event model and official
  Hyperliquid/Polymarket/IB adapters are relevant, but LGPL-3.0 prevents direct
  admission under the current release-license policy.
- **Adopt candidate:** TradingView Lightweight Charts behind a QuantMesh chart
  adapter for candlesticks, lines, volume and forecast bands. Apache-2.0;
  preserve the upstream NOTICE and visible attribution requirement.
- **Evaluate first:** Microsoft Qlib behind an offline research adapter for
  model/dataset workflow and alpha-model comparisons. MIT; do not replace
  QuantMesh provenance, paper, risk or audit contracts.
- **Evaluate first:** Darts in an isolated spike for probabilistic forecasts,
  backtesting and quantile paths. Apache-2.0; admit it to the release closure
  only if install size, Windows support, determinism and license gates pass.
- **Defer RL promotion:** FinRL-X may supply workflow and portfolio machinery,
  but reinforcement-learning policies remain behind transparent
  supervised/statistical baselines and cannot receive paper or live authority.
- **External comparator only:** QuantConnect LEAN for event-driven simulation
  parity; avoid embedding its C#/Docker runtime in this local Python slice.
- **Rejected from runtime:** VectorBT (Commons Clause) and OpenBB (AGPLv3)
  conflict with the current release-license policy. Patterns may be studied;
  their code is not copied into the permissive core.

Prefer a pinned package or process adapter over copying whole repositories.
Vendor only small, reviewed modules when the license is permitted, the source
commit and notice are recorded, and tests prove why an adapter is insufficient.

## Cross-agent execution and checkpoints

This iteration is executable by either Codex or Claude Code through
`docs/agents/cross-agent-execution.md`. The approved design is this iteration
record. The first implementation action is to generate a tool-neutral tracked
plan under `docs/superpowers/plans/` with exact files, interfaces, red/green
tests, review gates and commits.

Claude Code should use the installed Superpowers workflow, preferring
`writing-plans` followed by `subagent-driven-development`; Codex must enforce
the equivalent test-first and independent-review gates. Commit each coherent
green phase and push at every durable checkpoint (at least once per 60 minutes
when a green boundary exists). Mirror task completion, commit IDs and exact
verification results here and in `docs/goals/ACTIVE.md`; a local SDD ledger is
not sufficient for cross-agent recovery.

## Checkpoint 1 — executable plan activated (2026-08-11)

- Planning and upstream-review checkpoint `af62da2` is pushed on
  `0020-research-to-paper-loop`; issue #107 is the single milestone tracker.
- The task-level, test-first implementation plan is
  `docs/superpowers/plans/2026-08-11-integrated-instrument-workspace.md`.
- The plan contains 16 ordered tasks: framework evidence and two isolated
  bake-offs; the scorecard/ADR admission gate; owned history, forecast,
  proposal and workspace services; the chart adapter and instrument UI; then
  browser, release, merge and isolated-RC acceptance gates.
- Exact upstream pins are FinRL-X
  `e65d6f0483ead7d2ef4a5fc940cdf960392a25c1` and NautilusTrader
  `v1.231.0` / `27a8e54e7ac3c57d6cbf8891f0283dfbaee97317`.
  Lightweight Charts is proposed at `5.2.0` and is not admitted until its
  license, bundle and UI checks pass.
- No runtime framework has been admitted yet. The immediate executable task is
  Task 1, the QuantMesh-owned evidence contract and deterministic 420-session
  NVDA manifest.

### Task 1 completion — owned bake-off contract

- Commit `e251d8c` adds `FrameworkRunEvidence`, the data-only
  `FrameworkScore`, typed immutable upstream pins, and the explicitly labeled
  420-session NVDA lake fixture.
- TDD RED was the missing `quantmesh.research.frameworks` module. GREEN was
  14 focused contract cases plus the Lake/Manifest regression set; Ruff passed.
- A fresh task review approved spec and quality with no Critical or Important
  finding. One deferred Minor asks the final review to compare manifest bytes
  directly in addition to parsed deterministic values.
- No framework dependency entered the package and no execution authority
  changed. The next task is the pinned, child-process FinRL-X run.

### Task 2 completion — pinned FinRL-X NVDA bake-off

- Commits `e6e3c7d`, `f7482f1`, `e890a50`, `e23d2cf` and `5bdf32d`
  implement and harden the isolated FinRL-X controller, driver, evidence and
  process boundary. The fake adapter proves deterministic export, chronological
  `[0,252) / [252,315) / [315,420)` boundaries, no leakage, 17-bps cost
  semantics, target weights and a paper-only proposal without changing the
  QuantMesh order authority.
- The real pinned Windows run checked out
  `e65d6f0483ead7d2ef4a5fc940cdf960392a25c1`, verified Apache-2.0 license
  hash `afae3377fdbd0537635360e91585f3c5b478ffe8eb5308f1ddcb37b76a7325d2`,
  then failed honestly while building upstream dependency `bt`: this CPython
  3.13 host lacks Microsoft Visual C++ 14.0+. The evidence therefore remains
  `status="failed"`, deterministic/output claims remain false/null, and
  FinRL-X is not admitted to the release runtime.
- Four review rounds closed seven Important boundary findings: owned-root
  deletion, subprocess tree containment, proxy/credential isolation, exact
  output chronology, portable fail-closed evidence, Windows namespace aliases,
  and physical hard-link artifact uniqueness. Final focused verification is
  50/50 tests in 359.80 seconds plus Ruff and `git diff --check`; fresh review
  found no remaining Critical or Important issue. The pre-existing manifest
  byte-comparison Minor and test-runtime/module-split Minors remain parked for
  final review.
- No product dependency, execution route, credential surface or release
  evidence was changed. Task 3 is the separate pinned NautilusTrader
  Hyperliquid recorded-replay/sandbox comparator.

## Acceptance criteria

- From Markets, Watchlist, Cockpit or Positions, opening NVDA (or another
  seeded instrument) reaches one workspace with no context re-entry.
- The deterministic demo shows historical candles, volume, one overlay, one
  comparison line and clearly synthetic forecast intervals for all three
  horizons; a live station never substitutes synthetic history or forecasts.
- The same manifest, model and configuration reproduce the forecast artifact
  identity and values from a clean checkout.
- Forecast bands are visually and semantically distinct from observed prices;
  hover details expose quantile, vintage and provenance.
- Failed coverage, leakage, calibration or freshness gates remove the proposal
  action and show the exact reason.
- A confirmed paper proposal links forecast/run evidence through risk decision,
  order, fill, position/P&L and audit. Kill switch and stale quote drills block
  it deterministically.
- English and Simplified Chinese, light/dark/system themes, keyboard navigation,
  screen-reader labels and 390/768/desktop layouts pass browser acceptance.
- Frontend typecheck/lint/build/tests, backend tests, replay drills, security,
  bundle check and clean-checkout release gate pass before `v0.1.1-rc1`.

## Explicitly out of scope

- guaranteed price targets or an unlabeled single “AI prediction” line;
- real-money orders, mainnet signing or autonomous AI execution;
- unlimited indicators, models, providers or symbol discovery;
- copying an entire upstream research platform into the QuantMesh core;
- news/fundamental sentiment unless its point-in-time source rights and
  historical availability are proven.

## Later review queue

### Iteration 0021 — Trusted data fabric

Outcome: enable the operator to add reliable sources without changing product
logic. Build provider registry, symbol mapping, calendars, corporate actions,
raw/normalized/feature layers, manifests, quality SLAs and source-terms records.
Prioritize official Moomoo data for the user's equity workflow, official public
macro/filing sources, existing venue feeds and optional read-only CCXT crypto
coverage. Treat yfinance and AKShare as replaceable personal-research adapters,
not canonical reliability anchors.

### Iteration 0022 — Algorithm evaluation lab

Outcome: compare imported and native algorithms under one evidence contract.
Run Qlib and Darts spikes first; compare every candidate with transparent
baselines using walk-forward evaluation, costs, leakage tests, calibration,
stability and compute budget. Promote a model because it wins evidence gates,
not because its repository is popular.

### Iteration 0023 — Grounded research copilot

Outcome: explain chart changes, forecast disagreement and risk using citations
to local data, model cards and replay windows. AI remains advisory and cannot
create or approve an order.

### Iteration 0024 — Paper shadow portfolio

Outcome: schedule accepted strategies, generate proposals, simulate fills and
measure live-vs-forecast drift, costs and portfolio outcomes over time. Require
operator-configurable approval and preserve kill-switch authority.

### Later — Guarded venue execution

Only after a separate operator decision: broker/testnet credentials, venue
reconciliation, idempotency, exposure caps, incident drills and explicit
per-venue enablement. No paper release implicitly authorizes this phase.
