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
      `tests/test_live_supervisor.py`, 84/84 on the live surface.
      Merged via PR #86, 641f3c6.)

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
> first (PR #85), so Phase B sits on the full live surface. Phase B
> merged via PR #86 (641f3c6); Phase C starts from post-B main.

### Phase C — feed surface and cockpit screens

- [x] `/api/live/*` router (double-mounted): WebSocket stream + SSE
      fallback + latest-state + status endpoints.
- [x] React: Market Cockpit watchlist (real/delayed/stale/synthetic/
      unavailable states), instrument detail (chart, order book, trade
      tape), connector-health panel.
- [x] Browser E2E + accessibility/mobile checks for the cockpit.

> **Checkpoint C3 (2026-08-09)** — Phase C landed on main via PR #87
> (`553e944`). The cockpit E2E (`tests/test_live_e2e.py`) runs the
> whole stack for real, loopback-only: uvicorn serves the workstation
> with the live feed attached (the `--live` assembly), the Hyperliquid
> supervisor talks through `LiveHyperliquidTransport` to the scripted
> fixture venue on its own asyncio loop (burst at connect, 4 s
> keep-alive cycles for ~40 s, then an hour of silence with the socket
> still open — the deterministic quiet-venue condition), and Playwright
> walks the watchlist streaming (Real badge, quote numbers, connector
> health, live banner), the instrument detail (hand-drawn SVG chart
> once two closes arrive, per-side book, trade tape, back link), the
> stale transition (badge flips to Stale while the transport and banner
> stay live, no sequence-gap flag), the keyboard-only walk (Tab →
> Enter → detail → Back link) and the 390×844 viewport (the quote
> table scrolls inside its overflow container, the body never
> overflows). Skips cleanly without playwright/chromium or with the
> pinned port taken. Two real defects found by the E2E, both fixed
> with drills: the order book never rendered — the frontend
> `bookSide()` parsed levels as `{price, size}` objects while the
> ADR-0014 contract (`_validate_l2`) emits `[price, size]` pairs, so
> every level failed silently (the parse now lives in `lib/live.ts`
> matching the contract — finite-checked, malformed levels dropped —
> and is unit-drilled on the real wire shape, closing the client-side
> gap that had zero l2 coverage; vitest 43/43); and reconnect findings
> keyed on the venue name fabricated a phantom watchlist row via
> STATUS — `_surface_findings` now surfaces only watchlist-symbol
> findings as LAGGING, with a dedicated drill. Green: E2E 5/5, full
> backend suite 1983/1983, vitest 43/43, `tsc -b` clean, oxlint only
> pre-existing warnings, ruff clean, bundle repackaged via
> `tools/build_frontend.py`. Phase D (quote fence) starts from this
> checkpoint.

> **Checkpoint C2 (2026-08-09)** — Phase C-2 landed on branch
> `0015-phase-c` atop C1. `src/lib/live.ts` owns the client side: the
> connection ladder (`openLiveConnection` — WebSocket first, SSE
> fallback on socket error, 2 s backoff retry of the whole chain;
> injectable transports keep the ladder unit-drilled, since jsdom has
> neither WebSocket nor EventSource), the pure reconciliation helpers
> (mergeUpdate writes a streamed update into the snapshot and
> recomputes the instrument badge; the badge is the worst of the
> *data* kinds — status is connector health, never part of the
> instrument label; mid/spread-bps/age-text/candle-close helpers), and
> the `useLiveConnection` hook (ref-held callback so re-renders never
> re-arm the socket). `src/screens/Cockpit.tsx` is the watchlist
> (`/app/cockpit`): snapshot from `/api/live/state` every 10 s merged
> with streamed updates, badge per instrument, bid/ask/mid/spread bps/
> age + ⚠ gap marker, stream banner naming the active transport, and
> the connector-health panel from `/api/live/status` below the board.
> `CockpitDetail.tsx` (`/app/cockpit/:symbol`) subscribes to the same
> stream filtered to the instrument: header badge + mid/spread/gap,
> hand-drawn SVG close chart (no chart dependency), per-side L2 book
> from the latest bid/ask snapshots (kept separately — the wire emits
> one side per l2_snapshot), and the recent trade tape. Nav entry
> "Live cockpit" (Radio icon) under Markets; `useSurface` untouched —
> the cockpit uses react-query directly for its custom refetch cadence.
> Green: vitest 40/40 (ladder fallback/retry/close, reconciliation,
> label rank, watchlist rendering incl. mixed labels, panel states,
> stream merge, 404 message), oxlint clean (only pre-existing
> warnings), `tsc -b` clean, production build clean. Phase C-3
> (browser E2E + a11y/mobile) starts from this checkpoint.

> **Checkpoint C1 (2026-08-09)** — Phase C-1 landed on branch
> `0015-phase-c` (based on post-#86 main). The feed hub
> (`quantmesh/live/feed.py`) is the deterministic middle: `ingest` is a
> pure function (latest-per-venue+instrument+kind cache + lake append
> + status upsert), `label` derives the five watchlist states from
> provenance and receipt age (real/delayed/stale/synthetic/
> unavailable), fan-out is a bounded per-client queue with drop-oldest
> overflow, and `publish_threadsafe` lets any thread (a TestClient, the
> E2E harness) inject updates into the running pump. The router
> (`quantmesh/live/api.py`) double-mounts like the demo router:
> `/live/*` and `/api/live/*` serve the same feed (state snapshot,
> connector statuses, WS stream, SSE fallback with 15 s heartbeat);
> subscriptions are eager (registered in the handler before the
> response streams) so a publish after connect is never lost — the
> determinism the drills rely on. `create_workstation_app` gained the
> `live_feed=` handle and a lifespan factory that runs the pump only
> when a feed is attached (unconfigured servers answer 404 "no live
> feed is attached" and are unchanged); `--live` is the opt-in CLI
> path (mutually exclusive with `--demo`, watchlist from
> `QUANTMESH_LIVE_WATCHLIST`), and the live transport adapts the sync
> VenueTransport protocol to the real websockets client with a deferred
> open + outbox flush. Two real findings from the drills: starlette's
> current TestClient buffers the whole response body before returning,
> so an infinite SSE stream cannot be driven through it — the SSE drill
> runs a real uvicorn server on pinned loopback port 8644 (exactly the
> shape the SPA fallback will talk to); and OpenAPI never lists
> WebSocket routes, so the openapi drill asserts the HTTP surface only.
> Green: 112/112 on the live surface (`test_live_contract`,
> `test_live_buffer`, `test_live_supervisor`, `test_live_feed`,
> `test_live_router`), ruff clean, full backend suite 1956/1956.
> Phase C-2 (cockpit screens) starts from this checkpoint.

### Phase D — deterministic quote fence

- [x] Quote fence: provenance + age + sequence continuity gate over
      paper-order consumption; explicit rejection reasons; demo mode
      unchanged.
- [x] Unit + E2E drills: stale/gapped/unprovenanced quotes blocked,
      healthy quotes flow.

> **Checkpoint D1 (2026-08-09)** — Phase D landed on branch
> `0015-phase-d` via PR #89. The deterministic quote fence
> (`quantmesh/live/fence.py`) is the pure gate between the live feed
> and paper-order consumption: `evaluate(view, instrument, now)` is
> wall-clock-free, and `resolve(snapshot, instrument, now)` binds it
> to the same `latest_state` JSON the watchlist renders. Rejection
> reasons are explicit and priority-ordered (the first defect wins):
> `no-quote` ("no locally validated quote for {symbol}"), `not-real`
> (provenance delayed/synthetic/unavailable — "only locally validated
> real quotes may feed paper orders"), `gap` (sequence discontinuity —
> the venue dropped updates), `stale` (quote is N s old; the fence
> horizon is H s, default 30 s — the matcher's max-quote-age family),
> `no-depth` (no usable bid/ask/sizes). A blessed quote carries the
> local receipt anchor (timestamp=received_at), mid as last, and
> bid+ask size as volume — the demo route's depth convention.
> `PaperAccount.submit` gained `quote_fence=` + `snapshot=` kwargs:
> the fence resolves and blesses before the risk gate; a rejection
> lands as a REJECTED order with the explicit reason; a fence without
> a snapshot fails closed (ValueError); the blessed quote replaces
> any caller quote; and idempotency-key replays return the original
> order before any gate — fence included (M10 Phase B semantics
> preserved). Demo callers pass no fence, so demo mode is unchanged
> by construction. Drills 20/20 in `tests/test_live_fence.py`: every
> pure verdict + the priority order, snapshot-resolution shapes, the
> consumption path (healthy quotes fill at the blessed ask, rejections
> recorded with exact reasons, caller quote ignored, replay bypass,
> fail-closed ValueErrors, no-fence demo path untouched), and the
> real-stack drill — ScriptedVenue burst → HyperliquidVenueSupervisor
> → LiveFeed pump on one daemon loop: a fresh quote flows to a fill
> at 100.5, and the same venue going quiet ages the quote out
> ("quote is 6 s old; the fence horizon is 5 s") with no fills. The
> fence's E2E is this live-stack drill: the cockpit has no order-entry
> surface (AI may not submit orders), so the gate's end-to-end path
> is venue → supervisor → feed → fence → paper kernel. Green: full
> backend suite 2003/2003 (1983 prior + 20 new), ruff clean (incl.
> UP035 `typing.Mapping` → `collections.abc.Mapping`). Phase E
> (prediction markets, read-only) starts from this checkpoint.

### Phase E — prediction markets (read-only)

- [x] Polymarket public WS (market channel): implied probability,
      bid/ask, spread, depth, liquidity, expiry.
- [x] Kalshi public WS: same normalized surface.
- [x] Prediction comparison screen: cross-platform probability diff +
      calibration; distinct states.

> **Checkpoint E1 (2026-08-09)** — Phase E landed on branch
> `0015-phase-e` via PR #90. Both prediction venues are read-only
> supervisors over the same supervisor protocol as the cockpit:
> `PolymarketVenueSupervisor` drives the public CLOB market channel
> (book snapshots → L2 both sides + touch QUOTE with sizes;
> documented `price_change` single-sided frames are no-ops until a
> complete touch, sizes composed from the last book; `tick_size_change`
> benign; REST `ClobBookSource` → `SdkPolyTransport` re-seeds depth
> on reconnect, keyless), and `KalshiVenueSupervisor` drives the
> trade-api WS v2 three channels (market/orderbook_delta/trades) with
> two cents-keyed bid ladders: QUOTE = (best YES bid, 1 − best NO
> bid), the ask L2 is the NO ladder mirrored ascending, a crossed
> book skips the QUOTE, and every open seeds the book from REST
> (`KalshiOrderbookSource` → `HttpxKalshiTransport`, pinned host) —
> deltas without the seed fail closed (KalshiProtocolError → reconnect
> heals), ladders parsed ascending worst-first per the recorded wire.
> The comparison board (`PredictionBoard` + `parse_prediction_watchlist`
> "key[:title[:pm_symbol[:kalshi_symbol[:expiry_date]]]]") folds the
> feed's latest state into per-pair venue rows — implied probability
> (mid × 100), bid/ask, spread bps, touch depth, book liquidity, the
> freshness label (real/stale/unavailable) and the signed cross-venue
> diff in percentage points; a pair with only one venue renders the
> absent side honestly (no fabricated number, no diff). Wiring is
> explicit and keyless: `QUANTMESH_PREDICTION_WATCHLIST` +
> `QUANTMESH_POLYMARKET_WS_URL` + `QUANTMESH_KALSHI_WS_URL` settings,
> `GET /api/live/prediction`, and the `--live` assembly attaching the
> board's per-venue watchlists — no registry, no credentials (ADR-0014
> pinning holds). Frontend: Prediction markets screen (per-pair cards,
> diff chip with tone at |Δ| ≥ 1 pp, calibration link to the existing
> forecast surface — never re-fabricated), routed + nav'd under /app.
> Gates: 71/71 router+board drills, 226/226 regression, 47/47 vitest,
> lint/tsc/build clean, and the port-8646 browser E2E 5/5 — comparison
> (62.5%/65.0%/−2.5 pp/+3.0 pp over two scripted venues + canned
> Kalshi REST books), honest unavailable (solo pair), the stale
> transition after the plans' quiet tail, keyboard walk into
> "Forecasts", 390 px no body overflow.

### Phase F — Moomoo OpenD streaming

- [x] OpenD realtime subscription when locally available (AAPL, NVDA,
      MSFT, TSLA + watchlist); honest delayed/unavailable otherwise.
- [x] Never fabricated real-time; label and block per the status model.

> **Checkpoint F1 (2026-08-09)** — Phase F landed on branch
> `0015-phase-f`. The Moomoo surface is a poll-driven read-only venue
> over the same supervisor protocol: `MoomooVenueTransport` turns the
> request/response OpenD boundary into the venue wire — `probe()` at
> connect (a missing daemon, or a quote capability that is off, raises
> and the pump's disconnect path surfaces the honest state), `send()`
> collects the subscription specs, and a poll task on the pump's loop
> calls the sync M4 client off-thread, queueing one frame per payload
> (the stock-quote batch / one rt_ticker per code); a failed poll call
> is queued as a `poll_error` frame → dispatch raises → the pump
> disconnects and the backoff loop retries, so the surface recovers on
> its own when the local daemon returns. `MoomooVenueSupervisor`
> subscribes bare symbols (`AAPL,NVDA,MSFT,TSLA` + watchlist) and
> derives market-qualified SDK codes via `sdk_code` (an instrument
> without a known market fails closed at subscribe); OpenD has no wire
> envelope, so the subscription spec itself is the message. Dispatch:
> the quote batch is split per row → METRICS (last + volume) with the
> venue's own data_date/data_time as the honest timestamp — no bid/ask
> exists on the wire, so no QUOTE is ever emitted and paper orders are
> impossible for Moomoo instruments by construction; `rt_ticker` rows
> → TRADE ticks with the venue-reported aggressor side and sequence,
> deduped over the overlapping poll windows (a tick is never replayed)
> and neutral-direction rows accepted-but-skipped (no invented side).
> Fail-closed dispatch: unsubscribed symbols, unknown frame kinds and
> poll errors raise. The venue-clock gate blocks any answer whose own
> timestamp is outside the realtime window (`lag`) — a closed market
> or delayed feed is never labeled real: the last real numbers age to
> Stale through the feed's freshness machine and the tracker walks
> LAGGING → STALE; on disconnect the poll task is stopped (no
> double-poll behind a reconnect) and the dedup set reset. Wiring is
> explicit and keyless: `QUANTMESH_MOOMOO_WATCHLIST` +
> `QUANTMESH_MOOMOO_MARKET` + `QUANTMESH_MOOMOO_POLL_INTERVAL_S`
> settings, and the `--live` assembly attaches the supervisor when the
> watchlist is set — the cockpit renders the surface generically (zero
> frontend changes). Gates: 13/13 F drills (normalized surface,
> fail-closed dispatch, transport probe/poll contracts, and the live
> honest-availability ladder — real labels from a fresh daemon, Stale
> when the venue clock stops, DISCONNECTED after a mid-stream poll
> failure with the last real numbers visible, UNAVAILABLE with no
> metrics/trade surface when the daemon never answers), 2066/2066
> backend regression, ruff clean.

### Phase G — verification, gate, acceptance

- [ ] Replay determinism tests, periodic live read-only smoke drill
      (opt-in), full E2E/a11y.
- [ ] Clean-checkout release gate, isolated demo/live-read-only
      acceptance environment, operator checklist, checkpoint record.

## Safety (unchanged invariants)

All external venues read-only; no credentials; no mainnet, real-money
trading or autonomous execution; AI summarize/challenge only; demo and
live data labeled and isolated; paper orders gated by the quote fence.
