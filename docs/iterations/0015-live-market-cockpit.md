# Iteration 0015 — Live Market Cockpit

- Status: active
- Started: 2026-08-09
- Completed:
- Owner: solo fast lane; primary agent acts as Tech Lead, Product
  Designer, Implementer, Reviewer and Verifier
- GitHub issue: create a small milestone issue set only when
  implementation begins; do not create a PR per checkbox
- Pull request: one integration PR per phase, CI green, squash-merge
- Roadmap target: live multi-venue read-only research terminal over the
  v0.1.0 RC line

## Outcome

Turn the deterministic RC line (v0.1.0-rc4) into a *Live Market
Cockpit*: opening the local app shows a bounded watchlist of real,
sourced, freshness-labeled stock, crypto-perp and prediction-market
quotes in one workspace — replayable, comparable, and safely usable by
paper trading through a deterministic quote fence. All venues stay
read-only; AI may summarize and challenge signals but cannot submit
orders; no credentials are requested, stored or printed.

## Why this iteration exists

The operator's product read (2026-08-09): the engineering base is
~75% complete, but a "real-time trading research terminal you can open
every day" is ~35% — the core gap is live-data productization. Current
state: deterministic demo data dominates; Hyperliquid has only a
manual public L2 snapshot path. The next prototype is named Live
Market Cockpit; its only acceptance result is: open the local app and
see a bounded watchlist of real, sourced, freshness-marked quotes
across stocks, perps and prediction markets in the same workspace;
replay, compare and safely paper-trade on them.

## Product scope (first wave — no "all symbols")

- **Hyperliquid**: BTC, ETH, SOL, HYPE + 2–4 more perps — mid, BBO,
  L2 depth, trades, candles, funding, open interest, mark/index,
  disconnect state. Reuse the existing `HyperliquidStream`; official
  WS supports candle/l2Book/trades/allMids/BBO/assetCtx subscriptions.
- **Polymarket / Kalshi**: read-only. Implied probability, bid/ask,
  spread, depth, liquidity, expiry, cross-platform probability
  difference and calibration. Both have public real-time WS paths.
- **Moomoo**: AAPL, NVDA, MSFT, TSLA + 2–4 more watchlist stocks via
  the local OpenD realtime subscription; with insufficient account
  rights or subscriptions, the UI shows delayed/unavailable explicitly
  — never fabricated real-time.
- **Unified display parameters**: last, bid/ask, mid, spread bps,
  volume, 24h/intraday change, OHLCV, book depth/imbalance, trade
  tape, data time, receive time, latency, sequence gaps, connection
  state. Perps add funding/OI/mark-index/leverage/liquidation
  distance; prediction markets add probability, liquidity confidence,
  expiry/settlement rules and cross-platform spread.

## Architecture (operator-prescribed shape)

```text
Venue REST/WS feeds → provider-specific parser → normalized MarketUpdate
+ sequence/freshness checks → local event buffer + DuckDB/Parquet replay
→ latest-state cache → FastAPI WebSocket/SSE → React Live Market Cockpit
→ paper-order quote fence
```

Key principles: the browser never connects to exchanges directly;
orders may only read locally validated latest quotes (source + age +
sequence continuity); any disconnected or expired source shows
stale/degraded and blocks paper orders on its instruments.

## Delivery phases

### Phase A — ADR-0014, MarketUpdate contract, replay buffer, fixture server

- [x] Record ADR-0014 and open iteration 0015; branch
      `0015-live-market-cockpit` from the released main.
- [x] `quantmesh/live/contract.py`: the owned `MarketUpdate` model
      (venue, instrument, kind, typed payload, data_time, received_at,
      sequence, provenance, gap flags) and the source status model.
- [x] `quantmesh/live/buffer.py`: append-only DuckDB replay lake
      (day/venue partitions, provenance persisted, bounded retention,
      range and point-in-time queries).
- [x] Fixture-first WebSocket test server (asyncio fake venue playing
      scripted frames incl. DROP/RESUME/reorder/gap) in the test tree.
- [x] Tests: contract validation, buffer round-trip/replay/retention,
      fixture server determinism. (53/53, merged via PR #85, f48d4fd.)

### Phase B — supervisor protocol and Hyperliquid live supervisor

- [x] `quantmesh/live/supervisor.py`: reconnect/backoff, snapshot
      resync, sequence/gap detection, freshness monitor, bounded
      backpressure with explicit gap marking (generalizing the M5
      HyperliquidStream pattern).
- [x] Hyperliquid supervisor for the 4–8 perp watchlist: candles,
      l2Book, trades, allMids/BBO, assetCtx subscriptions; REST
      resync on reconnect; normalized MarketUpdates.
- [x] Fixture-driven tests: disconnect/resume, resync, gap marking,
      freshness transitions, backpressure. (31/31 in
      `tests/test_live_supervisor.py`, 84/84 on the live surface.)

> **Checkpoint B1 (2026-08-09)** — Phase B landed on branch
> `0015-phase-b` (based on post-#85 main), PR pending. The generic
> protocol (ADR-0014 decision 2) is a deterministic state machine:
> every transition takes an explicit clock, `SourceStatusTracker`
> emits STATUS only on freshness transitions
> (connected → lagging → stale → disconnected), `BackpressureGate`
> drops oldest on overflow with explicit gap marking carried by the
> first surviving update of the dropped stream (never silent loss),
> and the asyncio pump is the only wall-clock path — drills drive the
> scripted transport (`ScriptedHyperliquidTransport`, mirroring the
> M5 stream drills) and never touch the network. The Hyperliquid
> supervisor subscribes candle/l2Book/trades/bbo per watchlist coin
> plus allMids/activeAssetCtx, normalizes every frame into
> `MarketUpdate`s (fail-closed: unsubscribed identifiers, unknown
> channels, unknown coins and malformed frames raise
> `HyperliquidProtocolError`), detects per-coin trade-sequence
> continuity (first trade after subscribe/reconnect is never a gap),
> and heals on reconnect via REST candle backfill over the dark
> window + book snapshot replace, reporting unhealable trades gaps as
> findings. Review fixes folded in before commit: the gate's drop
> path was dead code in draft form (eager auto-flush could never
> overflow) — emission is now explicit; the freshness tracker keys
> off the watchlist, not subscription identifiers (which embed
> interval text); and `datetime.UTC` was replaced with the module
> `UTC` import (it is not a class attribute). Phase A merged to main
> first (PR #85), so Phase B sits on the full live surface.

### Phase C — feed surface and cockpit screens

- [ ] `/api/live/*` router (double-mounted): WebSocket stream + SSE
      fallback + latest-state + status endpoints.
- [ ] React: Market Cockpit watchlist (real/delayed/stale/synthetic/
      unavailable states), instrument detail (chart, order book, trade
      tape), connector-health panel.
- [ ] Browser E2E + accessibility/mobile checks for the cockpit.

### Phase D — deterministic quote fence

- [ ] Quote fence: provenance + age + sequence continuity gate over
      paper-order consumption; explicit rejection reasons; demo mode
      unchanged.
- [ ] Unit + E2E drills: stale/gapped/unprovenanced quotes blocked,
      healthy quotes flow.

### Phase E — prediction markets (read-only)

- [ ] Polymarket public WS (market channel): implied probability,
      bid/ask, spread, depth, liquidity, expiry.
- [ ] Kalshi public WS: same normalized surface.
- [ ] Prediction comparison screen: cross-platform probability diff +
      calibration; distinct states.

### Phase F — Moomoo OpenD streaming

- [ ] OpenD realtime subscription when locally available (AAPL, NVDA,
      MSFT, TSLA + watchlist); honest delayed/unavailable otherwise.
- [ ] Never fabricated real-time; label and block per the status model.

### Phase G — verification, gate, acceptance

- [ ] Replay determinism tests, periodic live read-only smoke drill
      (opt-in), full E2E/a11y.
- [ ] Clean-checkout release gate, isolated demo/live-read-only
      acceptance environment, operator checklist, checkpoint record.

## Safety (unchanged invariants)

All external venues read-only; no credentials; no mainnet, real-money
trading or autonomous execution; AI summarize/challenge only; demo and
live data labeled and isolated; paper orders gated by the quote fence.
