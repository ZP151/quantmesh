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

### Task 3 completion — pinned NautilusTrader replay/sandbox comparator

- Commits `25d5dc5`, `5fb9d4b`, `d7dede2` and `9d416d6` add the
  credential-free comparator at NautilusTrader `v1.231.0` / commit
  `27a8e54e7ac3c57d6cbf8891f0283dfbaee97317`. The controller independently
  verifies the fetched tag, detached HEAD, package version, LGPL-3.0 license
  hash, `pip check`, environment closure and two physically independent runs.
- The recorded Hyperliquid candle fixture is parsed through QuantMesh's wire
  contract. `n` remains trade count, replay order is explicitly labeled
  `replay_ordinal` / `quantmesh-fixture-order`, and any source `sequence_gap`,
  duplicate, descending timestamp or non-60-second interval fails closed.
- The real isolated run is deterministic with digest
  `cfa10c25c523cfbd2f13d639d95f7d6116e57ea6e213d7d5ef0f26cec8f64514`.
  Windows install, license, chronology, no-leakage and paper-only gates pass.
  Overall evidence remains honestly `status="failed"` because Nautilus MARGIN
  balance semantics differ from the QuantMesh cash account and pinned
  `SandboxExecutionClientConfig` has no standalone offline recorded-bar path;
  `contract_mapping=false` is retained rather than normalized away.
- Three fresh review rounds closed fixture provenance, fetched-tag identity,
  generic Windows reparse cleanup, portable HTTPS transcript and Windows
  UNC/device metadata findings. Final scoped review approved with no remaining
  Critical or Important issue. Verification includes the 111-test combined
  Nautilus/FinRL/risk/replay regression, 44/44 final Nautilus tests and Ruff.
- No Nautilus package or LGPL code entered the release runtime, no credential
  or live endpoint was read, and no execution authority changed. Task 4 now
  owns the generated scorecard and ADR disposition for both failed candidates.

### Task 4 complete — common scorecard and ADR gate

- The scorecard implementation was developed test-first. RED was collection
  failure for missing `tools.framework_bakeoff.score`; GREEN is 27 focused
  scorecard/CLI tests. The exact CLI generated
  `docs/evidence/0020/framework-scorecard.json` atomically from the two
  committed evidence files.
- Both evidence files contain `score_inputs={}`. Every soft category is
  therefore explicitly `0.0`, every missing category is machine-listed, and
  both totals are honestly `0.0`. No soft score was inferred from prose.
- FinRL-X is `reject`: the `bt`/MSVC installation failure leaves Windows,
  determinism, chronology, leakage, paper-only and contract-mapping gates
  unverified. NautilusTrader is `isolated-comparator`: all required comparator
  gates pass except contract mapping; LGPL/process isolation, its 565,969,715
  byte environment and unavailable standalone offline sandbox path remain
  explicit limitations.
- ADR-0015 keeps QuantMesh's contracts and deterministic paper kernel, records
  zero copied upstream files and zero runtime dependencies, and selects the
  native workspace implementation as the fallback. The release closure is
  unchanged.
- Fix round 1 now validates schema-v1 evidence and scorecards in strict mode,
  forbids extra or coerced/non-finite values, enforces the exact seven hard
  gates and seven soft categories, and rechecks score totals, admission and
  disposition when a scorecard is loaded. The aggregate binds each framework
  to its repo-logical source ID and the SHA-256 of the exact bytes validated;
  deterministic regeneration produced
  `b2cff147ea1145658db43107abd7d4016b2b07f4e6739c029162c6c6ae1c063b`.
- Fresh Task 1-4 plus security verification is 173/173 tests. A unique clean
  virtual environment installed `-e ".[dev,research,e2e]"` successfully, and
  its Python reviewed the 64-package release closure (58 packages installed on
  Windows) with every license allowed. The validated temporary root was then
  removed and verified absent; the shared `.venv` was not mutated.
- Independent review accepted Task 4 with zero Critical, Important or Minor
  findings. It independently reproduced 79/79 focused tests, 173/173 Task 1-4
  compatibility tests, byte-identical scorecard output and rejection of 13/13
  malformed evidence plus 15/15 tampered score objects. ADR-0015 is accepted.
  Task 5 (venue-aware historical data contracts and service) is now the active
  implementation frontier.

### Task 5 initial implementation

- Strict TDD began with a collection RED because `quantmesh.instruments` did
  not exist. The new focused suite is GREEN at 31/31 tests; the plan-prescribed
  history/lake/manifest compatibility run is 110 passed and 3 platform-skipped.
- `HistoryRange` now exposes the stable `1d`, `5d`, `1m`, `3m`, `6m` and `1y`
  wire values. `DatasetBinding` routes one exact venue/symbol/resolution to a
  dataset ID while retaining calendar and adjustment semantics; it does not
  duplicate `Dataset`, `Bar`, `Instrument` or `Venue` domain authority.
- `HistoryService` receives a narrow dataset loader and invokes it on every
  request, so reads pass through the current lake manifest gate instead of a
  cached `Dataset`. It selects `5m`, `30m`, `1h` or `1d` according to the
  requested range and only falls back to the nearest coarser bound interval,
  recording the transition explicitly.
- Returned series normalize aware timestamps to UTC and carry the manifest
  dataset ID, revision, source, license, generated time and coverage together
  with calendar, adjustment, gaps, duplicates, limitations and resolution
  fallback. Deterministic fixed windows are 1, 5, 31, 93, 186 and 366 calendar
  days ending inclusively at the injected `as_of` value.
- Empty windows, stale/missing/foreign manifest coverage, ambiguous bindings,
  finer fallback, mixed identity or interval, duplicate/non-monotonic rows,
  future leakage, and live-tail/forecast rows fail closed. Comparison series
  use only exact shared observed timestamps, never forward-fill, require two
  shared points and normalize each positive finite first close to 100 under
  the stable `venue:symbol` key.
- Focused Ruff and `git diff --check` are clean. No dependency, storage,
  frontend, execution-authority or upstream-code change was made. Independent
  Task 5 review remains pending; no tracked plan checkbox or `ACTIVE.md` state
  is advanced by this implementation checkpoint.

### Task 5 complete — fix round 1 and independent acceptance

- The first independent review found four Important issues: returned rows were
  not fully bound to manifest coverage, equal-duration interval aliases made
  selection order-dependent, fixed-grid gaps mislabeled session closures, and
  frozen top-level models still exposed mutable/aliased nested state. The
  review RED reproduced all four categories as 7 failures in 38 tests.
- Manifest coverage is now normalized to UTC before the read. Every returned
  timestamp must be inside both the inclusive request window and the declared
  coverage. A request containing the full declared coverage also requires the
  exact manifest row count and first/last timestamps. The loader is still
  invoked on every request, preserving the query-time stale-manifest gate.
- Binding identity now uses normalized interval duration per venue/symbol, so
  aliases such as `60m` and `1h` fail closed regardless of input order. A lone
  alias can satisfy the preferred duration while the exact raw interval remains
  bound to manifest lookup and lake reading. All six ranges cover preferred,
  nearest-coarser and never-finer behavior.
- Fixed-grid gap detection now runs only for the exact continuous-calendar
  spelling `24/7`. Session calendars such as `XNYS` return no calendar-blind
  gaps and carry the stable limitation that session-aware detection was not
  run; comparison responses preserve that limitation.
- Task 5-owned frozen strict subclasses snapshot the existing `Instrument` and
  `SeriesCoverage` schemas without changing those domain models. Tuple-backed
  collections and read-only mappings detach reader state and make the full
  historical/comparison response graph immutable while JSON output remains
  arrays and objects with strict stable round trips.
- Focused Task 5 verification is 54/54. The Task 5 + lake + manifest gate is
  133 passed and 3 platform-skipped in 7.25 seconds using a unique system-temp
  base, which was verified removed. Focused Ruff and `git diff --check` pass;
  no workspace temp artifact, dependency or out-of-scope source change remains.
- Independent fix-round review closed all four findings with zero Critical,
  Important or Minor issue. It reproduced 54/54 focused tests, 133 passed plus
  3 platform-skipped compatibility checks and 18/18 targeted probes, then
  verified Ruff, diff cleanliness, FastAPI encoding and strict JSON round trips.
  Task 6 (historical and continuity-safe live-tail API) is the active frontier.

### Task 6 initial implementation — changes requested

- Strict TDD began with 34 expected failures: the workstation did not accept a
  historical service, no instrument-history router existed, and Hyperliquid
  candle payloads omitted their interval. The new API suite now covers 34
  focused cases, including root/API parity, exact OpenAPI response identity,
  stable input and absence errors, bounded comparison parsing, and execution
  state immutability.
- `GET /instruments/{venue}/{symbol}/history` and its `/api` mount resolve one
  explicit aware request time, pass it to both primary history and normalized
  comparison reads, and return the strict `HistoricalPayload` envelope. A
  missing service returns the exact typed 404; invalid venue, range, symbol or
  comparison syntax returns 422; unavailable manifest-backed data returns a
  stable reason-bearing 404.
- Repeated and comma-separated comparison values retain first-seen order,
  deduplicate peers, refuse the primary instrument, and cap query-value count,
  token length, symbol length and unique peers. Comparisons remain Task 5
  observed-only output and never receive a live or forecast tail.
- The optional live join addresses the exact venue/symbol/candle cache key. It
  accepts only real or delayed provenance with a present sequence, no sequence
  gap, aware non-future timestamp, finite valid OHLCV and an explicit canonical
  payload interval exactly equal to the selected historical interval. It can
  replace only the final timestamp or append exactly one next interval; every
  matching refusal preserves the frozen Task 5 series and adds a stable
  limitation. Adjusted history refuses an unadjusted live candle.
- Hyperliquid stream and reconnect candles now carry the canonical `1m`
  interval with focused regressions. Task 5 currently selects no interval finer
  than `5m`; those candles therefore remain truthfully unjoined unless a future
  explicitly reviewed producer/range policy aligns the intervals. No interval
  is inferred and no browser-side aggregation is introduced.
- TypeScript now mirrors the immutable history, coverage, comparison and
  payload wire shapes, including exact venue and instrument-type unions. The
  client URL-encodes path values, sends the selected range, and omits an empty
  comparison query instead of emitting a misleading blank value.
- Verification is 148/148 across Task 6, SPA API, Task 5 history, live feed and
  Hyperliquid supervisor suites. TypeScript `--noEmit`, focused Ruff and
  `git diff --check` pass using a unique system-temp pytest base that was
  removed. No dependency, built frontend asset, execution route or order
  authority changed. Fresh independent review remains pending.

### Task 6 fix round 1 — changes requested

- The independent review of `ffd1ce1` requested five Important fixes and one
  local Minor: synchronized public feed access, positive continuity evidence,
  point-in-time freshness, immutable live lineage and historical-only coverage
  semantics, ADR-0013 OpenAPI generation, and a typed expected-unavailability
  exception. This round addresses every finding without changing execution
  authority and deliberately awaits a new independent review.
- `LiveFeed.snapshot_exact` now returns a detached exact venue/instrument/kind
  snapshot. One threading lock protects cache and continuity reads/writes and
  the detached `latest_state`/`statuses` snapshots. Continuity becomes proven
  only after a valid predecessor for the same stream: intervals match, neither
  update carries a gap, receipt/event times are monotonic, event time is the
  same bar or exactly the next interval, and sequence behavior is
  non-regressive for a same-bar update or advancing for a next-bar update.
  First observations and the first clean observation after a gap remain
  unproven.
- The history API consumes only that public snapshot at its one captured
  `as_of`. It rejects naive, post-snapshot and over-lag receipts and requires
  positive continuity before a tail can join. Accepted bars carry a strict,
  frozen `LiveTailLineage` with source/venue/instrument, real-or-delayed
  provenance, event and receipt times, exact interval, sequence and predecessor
  evidence, freshness label and age. `coverage_scope: historical-only` and a
  stable limitation explain why a live tail may lie beyond manifest coverage.
- `HistoryUnavailableError` is the sole expected absence/data-unavailability
  exception translated to the stable 404. Unrelated `ValueError` and Pydantic
  validation failures remain observable as 500 responses in the focused API
  regressions.
- ADR-0013 is now executable: deterministic cross-platform scripts export the
  workstation OpenAPI and generate committed `frontend/src/api/client.ts`.
  Task 6 DTOs are aliases of generated components and `api.history` uses the
  generated path through `openapi-fetch`; an empty comparison remains omitted.
  CI runs `check:api`. Exact additions are `openapi-fetch==0.17.0` (MIT) and
  `openapi-typescript==7.13.0` (MIT); generator peer compatibility pins
  `typescript==5.9.3` (Apache-2.0). The 644-entry lock closure is fully
  allowlisted and `npm audit` reports zero advisories.
- Fix-round verification is 168/168 across Task 5, Task 6, SPA API, live feed
  and supervisor suites, plus 73/73 Vitest tests. OpenAPI stale generation
  passed twice with byte-identical SHA-256
  `9f2d93cdf638d0de9ac84eca1c92e10c516cff6fa78b5bb0487ef8ba193b5693`;
  TypeScript no-emit, Ruff and `git diff --check` pass. Existing Vitest
  React `act(...)`/undefined-query warnings remain outside this Task 6 fix.

### Task 6 fix round 2 — changes requested

- The round-1 rereview found four remaining Important issues and one Minor:
  attached-lake writes were outside the feed lock, disconnects did not end the
  continuity session, strict lineage reload did not bind receipt age to the
  enclosing response, CI did not type-check the generated caller, and loader
  `ValueError` was still converted to expected absence. This round addresses
  all five findings; review acceptance remains deliberately pending.
- Each `LiveFeed` update is now one serialized transaction under the feed
  lock: detached update, continuity calculation, lake append, cache commit and
  disconnect barrier update. Persistence occurs before visible cache state.
  The 100-update/eight-writer regression captures every worker exception,
  proves exactly-once persistence and unique contiguous `local_seq`, exercises
  exact/latest/status snapshots concurrently, and confirms the final cache.
  A forced append failure leaves both displayed value and continuity proof
  unchanged.
- Exact `DISCONNECTED` and `UNAVAILABLE` status observations establish a
  venue/instrument session barrier for existing non-status stream keys without
  removing their last display value. The first later candle is unproven and a
  second valid predecessor relationship can restore proof. `CONNECTED` and
  `LAGGING` do not fabricate proof; venue and symbol boundaries remain
  isolated, including a disconnect before any candle.
- `HistoricalSeries` now permits at most one live bar and only as the final
  bar. Every historical bar must remain inside manifest coverage, while that
  final live tail alone may extend beyond historical coverage. Live receipt
  cannot follow the response `as_of`, and `age_ms` must exactly equal the
  nonnegative integer millisecond difference. Strict JSON tampering
  regressions reject forged age, future receipt, middle/multiple live bars and
  historical coverage escape while preserving exact round trips.
- The frontend defines the exact `typecheck: tsc --noEmit` package script and
  CI runs it immediately after `check:api`; a repository regression fixes both
  the command and ordering. `HistoryService` now lets plain loader
  `ValueError`/Pydantic faults reach FastAPI's sanitized 500 boundary, while a
  loader-raised `HistoryUnavailableError` remains the explicit stable 404.
- RED evidence reproduced the prior defects: concurrent lake ingestion raised
  77 worker errors, post-disconnect proof remained true, forged lineage and
  out-of-coverage history validated, CI lacked `typecheck`, and both loader
  faults returned 404. GREEN verification is 187/187 across the round-1 matrix
  plus 21/21 `LiveBuffer` tests (208 total), and 73/73 Vitest tests. OpenAPI
  stale checks passed twice at byte-identical SHA-256
  `9f2d93cdf638d0de9ac84eca1c92e10c516cff6fa78b5bb0487ef8ba193b5693`;
  `npm run typecheck`, frontend lint, focused Ruff and diff checks pass. The
  npm closure is unchanged at 644 allowlisted entries and `npm audit` reports
  zero advisories. Existing frontend warning debt is unchanged; no execution
  authority, dependency, generated client or built asset changed.

### Task 6 fix round 3 — accepted

- The round-2 rereview closed every prior finding but identified one remaining
  atomicity defect: a STATUS append used separate DuckDB auto-committed
  statements, so failure of the `source_status` upsert could leave a replay
  event without a status row. This round addresses only that finding.
- `LiveBuffer.append` now starts one explicit DuckDB transaction before
  allocating `local_seq`. The allocation, `market_updates` insert and
  conditional `source_status` upsert all complete before COMMIT. Any exception
  attempts ROLLBACK and re-raises the original failure; rollback failure cannot
  mask the initiating exception. The existing long-lived connection remains
  open and supports an immediate retry after rollback.
- The fault-injection regression delegates the replay insert to DuckDB and
  raises at the following status write. RED reproduced one partial replay row.
  GREEN proves both tables remain empty, retry returns `local_seq=1`, and only
  one replay row plus one status row persists. A reopened-lake regression
  proves ordinary non-status commits remain durable, while existing status
  upsert behavior remains covered.
- The attached-feed regression starts from proven candle continuity, injects
  the same partial STATUS failure, and proves the public cache/status/proof are
  unchanged. The next candle still proves uninterrupted continuity, while a
  successful retry persists exactly one STATUS event and only then establishes
  the disconnect barrier.
- Verification is 23/23 `LiveBuffer` plus 38/38 `LiveFeed` tests (61 total),
  and 211/211 across the complete Task 6 focused matrix. Focused Ruff and
  `git diff --check` pass. Frontend, generated OpenAPI client, dependencies and
  execution authority are untouched.
- The final narrow independent review of `7f051b8..629d3c8` closed the sole
  remaining finding with zero Critical, Important or Minor issue. Independent
  RuntimeError, `BaseException`, failed-BEGIN, rollback-failure and nested-
  transaction recovery probes preserved the original failure and found no
  partial row or supported-path connection poisoning. The 100-update/eight-
  writer exactly-once drill and four focused atomicity cases passed without a
  duplicate, sequence hole or deadlock. Task 6 is complete; Task 7 (truthful
  multi-horizon forecast artifacts) is the active frontier.

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
