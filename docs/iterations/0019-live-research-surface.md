# Iteration 0019 — Live Research Surface

Status: planned
Depends on: iteration 0018 / PR #100 merged
Baseline: the next replacement RC after `v0.1.0-rc6`

## Outcome

Turn the existing read-only multi-venue cockpit into the first genuinely
useful real-time research surface. The operator should be able to watch a
bounded cross-market list, understand what changed, compare venue conditions,
and replay the same evidence later without confusing live, stale, delayed or
synthetic data.

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
