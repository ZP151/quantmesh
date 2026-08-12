# ADR-0014 — Live Market Stream Runtime (Live Market Cockpit)

- Status: accepted (iteration 0015, Phase A evidence to follow)
- Date: 2026-08-09
- Supersedes: none; extends ADR-0013 (SPA/API boundary) and the
  M5-era Hyperliquid stream decision (ADR-0007) from one venue to a
  multi-venue stream runtime.

## Context

The RC line (v0.1.0-rc4) ships a deterministic labeled demo runtime, a
one-shot credential-free snapshot path (`datalink`/connectors), and a
read-only Hyperliquid WebSocket pump
(`hyperliquid/stream.py`: `HyperliquidStream` + `StreamSupervisor` +
`SimulatedStreamTransport`, drill-tested for reconnect/gap recovery).
The next prototype, Live Market Cockpit, must turn a bounded watchlist
(4–8 perps, 4–8 stocks, prediction markets) into a local, read-only,
replayable real-time workstation: multi-venue live quotes with
provenance and freshness, an instrument workspace (chart, order book,
trade tape), cross-platform prediction comparison, and paper trading
that may consume live data only through a deterministic quote fence.

## Decisions

1. **One owned `MarketUpdate` contract** (`quantmesh/live/contract.py`).
   Every venue stream normalizes into the same event shape: venue,
   instrument id, kind (`quote`, `trade`, `candle`, `l2_snapshot`,
   `l2_delta`, `metrics`, `status`), typed payload per kind, `data_time`
   (venue time), `received_at` (local), sequence info (venue sequence
   where the venue provides one, else supervisor-assigned), provenance
   (`real` / `delayed` / `synthetic` / `unavailable`) and gap flags.
   Downstream consumers (UI, replay, quote fence) never need venue
   knowledge.

2. **Venue supervisor protocol** generalizing the HyperliquidStream
   pattern: subscribe(watchlist), reconnect with backoff, snapshot
   resync on reconnect (L2 snapshot + candle backfill, trades reported
   as gap findings where no REST backfill exists — exactly the M5
   behavior), sequence/gap detection, per-subscription freshness
   monitor (connected → lagging → stale → disconnected), bounded
   backpressure (bounded queue, drop-oldest *with explicit gap
   marking*, never silent loss).

3. **Append-only replay lake** over DuckDB (already a core dependency)
   partitioned by day/venue: every `MarketUpdate` persisted with
   provenance; replay (range) and point-in-time queries; bounded
   retention. The demo seed path is untouched and stays isolated;
   live data is labeled `real` and never mixed into the deterministic
   seed state.

4. **Local feed surface**: FastAPI WebSocket `/api/live/stream` (+ SSE
   fallback) publishing normalized updates and per-venue status
   transitions. The browser connects only to the local server; venue
   URLs and clients live server-side only (enforced by construction —
   no venue endpoints in the frontend).

5. **Deterministic quote fence**: paper orders may consume a quote
   only if provenance is `real`, age ≤ the venue's maximum
   freshness, and sequence continuity holds; otherwise the order is
   rejected with an explicit reason (stale / gapped / unprovenanced).
   `delayed` remains visible for analysis but is deliberately excluded
   from execution authority; iteration 0020 tightened this rule so an
   operator can never mistake delayed display data for an executable quote.
   In demo mode the fence consumes the seeded synthetic quotes exactly
   as today (no behavior change). Fully unit-tested, no wall-clock
   dependence in the checks' core.

6. **Status model per source**: connected / lagging / stale /
   disconnected × real / delayed / synthetic / unavailable; the UI
   renders distinct, labeled states; a degraded venue blocks paper
   orders on its instruments.

7. **Scope gates (unchanged invariants)**: all external venues
   read-only; no credentials requested, stored or printed; Moomoo OpenD
   streams only when locally available, otherwise an honest
   delayed/unavailable state; AI may summarize and challenge signals
   but never submits orders.

## Consequences

- New module `quantmesh/live/` (contract, buffer, fence, supervisors),
  an `/api/live/*` router (double-mounted like the demo router), and
  cockpit screens in the SPA (Cockpit watchlist, instrument detail,
  prediction comparison, connector health).
- Fixture-first WebSocket tests: a fake venue WS server (asyncio)
  drives canned frames, disconnects, reorders and gaps; replay
  determinism tests; browser E2E; accessibility/mobile checks; an
  opt-in periodic live read-only smoke drill.
- The M5-era Hyperliquid machinery is generalized, not rewritten: the
  existing wire parsers, backoff and gap-finding helpers are reused.
- Rollback: live streaming is additive; the workstation runs unchanged
  when no live watchlist is configured (demo mode is the default).
