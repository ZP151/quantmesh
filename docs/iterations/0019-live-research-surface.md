# Iteration 0019 — Live Research Surface

Status: active
Started: 2026-08-10
Branch: `0019-live-research-surface`
Baseline: `origin/main` at `5069d1b` (PR #100, after `v0.1.0-rc6`)

## Outcome

Turn the existing read-only multi-venue cockpit into the first genuinely
useful real-time research surface. The operator should be able to watch a
bounded cross-market list, understand what changed, compare venue conditions,
and replay the same evidence later without confusing live, stale, delayed or
synthetic data.

## Baseline audit and first slice

The initial audit confirmed that iteration 0015 already supplies the normalized
`MarketUpdate` contract, venue supervisors, DuckDB replay lake, stream
fan-out, freshness/sequence labels, compact SVG candle chart, L2 depth and
trade tape. Iteration 0019 must extend those owned seams rather than recreate
them.

The first remaining product gap is visible metrics and evidence: Hyperliquid
already emits funding rate, mark price, index price and open interest in a
normalized `metrics` frame, but the cockpit did not render them or show the
frame's event/receive/sequence/age boundary. Slice 1 exposes those values in
the instrument detail with reviewed en/zh-CN copy. Missing data renders as
unavailable; no UI estimate is introduced.

### Checkpoint 1 — research evidence and documentation

- Rewrote the English-first README and Chinese companion as concise developer
  product pages: one-line hero, direct navigation, early demo start, product
  loop, short capability/safety sections and links to detailed documentation.
  No screenshot or badge is invented; a focused, tagged-build product capture
  can be added later when it is reproducible.
- Added a reviewed market-context card to cockpit instrument detail for the
  normalized Hyperliquid funding rate, mark price, index price and open
  interest fields. The card only renders finite venue-provided values.
- Added an evidence card for venue, freshness label, event time, local receive
  time, sequence and age. It intentionally uses the normalized local view,
  not an inferred wall-clock or provider-specific client calculation.
- Verification: Cockpit screen drill 9/9; complete frontend suite 59/59;
  `npm run lint` passes with four existing Fast Refresh warnings;
  production TypeScript/Vite build passes; packaged SPA bundle rebuilt and
  `python tools/build_frontend.py --check` passes.

### Checkpoint 2 — recorded replay workflow (slice 4)

- Backend: `GET /api/live/replay/windows` returns the lake's recorded extent
  (count, earliest/latest `received_at`, distinct venues); `GET /api/live/replay`
  replays a bounded window in append order with provenance, sequence and gap
  marks. Both fail closed with typed 404 details when no lake is attached or
  the lake is empty; window bounds are required, ordered and UTC-pinned.
  (Slice 1 already established the ingestion path into the lake.)
- Frontend: a `Recorded replay` card on the cockpit renders the recorded
  extent, offers 5 min / 15 min / all window actions, and shows the replayed
  rows under an unmistakable violet `Replay mode` banner with window bounds,
  update count and `source: lake`, plus a clear action. Replay is strictly
  read-only: it never folds into the live cache or the paper surface.
- Replay drills were already covered by iteration 0015's `test_live_replay.py`
  (rebuild equivalence, append-order determinism, byte-identical replays
  across connections, gap marks and provenance labels surviving the round
  trip, age not resurrecting old data as fresh); slice 4 added endpoint-level
  drills in `test_live_router.py` (`TestReplayEndpoint`).
- Operator-drill coverage was audited against scope item 4: healthy and
  dead-station live in `test_live_smoke.py`; delayed/provenance in the
  supervisor and replay ladder drills; dropped frames in the backpressure
  gate and sequence-gap drills; reconnect in `TestDisconnectDrill` and the
  replay fold (the reconnect/backfill equivalence); browser acceptance at
  desktop and 390 px was extended with a tablet (768 px) no-overflow walk
  and a replay-card honesty drill — the E2E workstation runs without a
  lake, so the card must fail closed over the real wire (`Replay 5 min`
  never renders, honest no-lake copy shows).
- Verification: Cockpit screen drill 14/14; complete frontend suite 71/71;
  `tsc --noEmit` clean; `npm run lint` passes with the same four existing
  Fast Refresh warnings; backend `tests/` full run 2124 passed (includes
  `test_live_router.py` 49 passed with `test_live_replay.py` and
  `test_live_feed.py`); live browser E2E 7/7; committed SPA bundle rebuilt
  and `python tools/build_frontend.py --check` passes.

## Scope

### 1. Unified live board

- Extend the existing `MarketUpdate`, venue supervisor, sequence, age and
  replay contracts instead of adding provider-specific UI models.
- Show venue, instrument, source, event time, receive time, sequence, age and
  freshness state on every live row.
- Keep Hyperliquid perps, Moomoo equities, Polymarket and Kalshi event markets
  visibly distinct while allowing a single watchlist and filter model.

### 2. Research-grade metrics

- Equities/crypto: last, bid, ask, mid, spread, trade size, volume, depth,
  short-window return, realized volatility and gap/reconnect markers.
- Hyperliquid where the public feed provides them: funding, open interest,
  mark/index divergence and liquidation-distance context; absent values stay
  unavailable rather than estimated in the UI.
- Prediction markets: implied probability, bid/ask, spread, touch depth,
  liquidity, cross-venue difference, expiry and calibration link.
- Every metric carries a source and time boundary suitable for replay.

### 3. Charts and density

- Reuse the current SVG/canvas-friendly frontend boundary and existing design
  tokens; introduce a chart dependency only after a small spike proves it
  handles local packaging, 390 px layouts, keyboard/a11y and deterministic
  snapshots.
- Add a compact price/probability sparkline, trade tape and depth view before
  adding advanced indicators.
- Preserve readable empty, stale, delayed, unavailable and reconnect states.

### 4. Replay and operator drills

- Persist the same live frames to the DuckDB lake with deterministic local
  sequence boundaries.
- Add “replay this window” from a recorded interval, with a visible replay
  mode and provenance banner.
- Add healthy, delayed, dropped-frame, reconnect and dead-station drills.
- Run browser acceptance at desktop, tablet and 390 px widths.

## Reuse-first implementation order

1. Existing live contracts, supervisors, DuckDB lake and `/api/live/*` routes.
2. Existing cockpit components, labels, source chips and SVG primitives.
3. Existing `tools/live_smoke.py`, replay drills and browser fixtures.
4. Mature charting library only if the spike passes packaging and a11y gates.
5. New backend models only when the existing normalized contract cannot express
   a required metric; record that decision in an ADR.

## Exit criteria

- A fresh demo station has deterministic values and an unmistakable synthetic
  label; a live station never fabricates a value when a venue is unavailable.
- A bounded watchlist updates without page reload, reconnects after a dropped
  stream, and shows a truthful age/sequence state.
- The operator can inspect quote/book/trade/probability context, replay it and
  reproduce the displayed state from the lake.
- Browser, accessibility, frontend, backend, smoke and clean-checkout gates
  pass; no real-money or autonomous execution path is added.

## Explicitly out of scope

- Mainnet wallet signing or live order submission.
- AI placing, cancelling or resizing orders.
- Unbounded symbol discovery, paid data feeds or cloud deployment.
- Claims of predictive accuracy before walk-forward evidence exists.

## Handoff

Use one vertical integration branch and one PR. Update `ACTIVE.md` only after
PR #100 is merged; record all metric-contract, chart-library and replay-boundary
decisions in this iteration and the relevant ADRs.
