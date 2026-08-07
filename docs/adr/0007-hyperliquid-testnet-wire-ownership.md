# ADR-0007 — Hyperliquid testnet wire ownership and fail-closed posture

- Status: accepted
- Date: 2026-08-08
- Deciders: solo delivery (iteration 0007, M5 Phase A, issue #29)
- Related: ADR-0004 (adapter boundary and wire contracts — the same
  "contracts derived from pinned sources, never docs" discipline), ADR-0006
  (journal-first execution identity — the Phase B extension builds on it),
  `docs/iterations/0007-m5-hyperliquid-testnet-workflow.md`

## Context

M5 brings Hyperliquid **testnet** market data and (later phases) execution
into QuantMesh. The wire contract is the pinned `hyperliquid-python-sdk`
submodule (0.24.0); the SDK's `Info` class offers a complete REST surface,
but its bundled `WebsocketManager` is a sync, callback-oriented thread whose
`run_forever` **exits on a dropped connection and never resubscribes**
(verified in the pinned submodule source). A market-data surface that
silently goes dark through a disconnect is exactly the failure this
workstation must not have. QuantMesh therefore owns the stream lifecycle.

## Decisions

### 1. The SDK is reached only through a lazy, import-guarded REST boundary

The REST transport wraps the SDK's `Info` (`skip_ws=True` — QuantMesh owns
the WS layer), constructed lazily on first use and import-guarded: unit
tests never import the SDK, mirroring the M4 OpenD discipline. Any SDK
exception other than QuantMesh's own typed errors becomes
`HyperliquidUnavailableError`; a missing SDK becomes
`HyperliquidSDKMissingError`. Nothing in the product surface constructs
`Info` implicitly.

### 2. Testnet is pinned; mainnet is refused before the wire

`SdkRestTransport` accepts only the SDK's own testnet base URL
(`https://api.hyperliquid-testnet.xyz`); any other URL raises a protocol
error at construction. The live provider is explicit-construction-only and
the M3 provider registry refuses LIVE venues, so no code path reaches
mainnet — the product surface cannot trade or quote a real market.

### 3. QuantMesh owns the WebSocket lifecycle: heartbeat → resubscribe → REST re-sync

The stream is a deterministic state machine (`StreamSupervisor`) with a
live asyncio pump (`HyperliquidStream`) layered over `websockets` (already a
core dependency). On a disconnect the supervisor records per-channel gap
windows; on reconnect it resubscribes and REST re-syncs every channel that
went dark:

- **Candles** are merged from `candleSnapshot` over `[last_data, now]`; the
  frame stream wins on conflict, and any window the REST answer leaves
  unhealed is reported as a typed gap finding.
- **The order book is replaced by a fresh `l2Book` snapshot, never
  delta-replayed**: Hyperliquid book updates are full level arrays (verified
  in the SDK source), so a snapshot fetch is the honest rebuild — there are
  no deltas to replay and nothing to merge.
- **Trades are reported as a gap finding**: Hyperliquid exposes no public
  trades REST endpoint, so a reconnect window's trades cannot be recovered;
  the finding carries the last seen `tid` so the operator knows where the
  sequence resumes.
- A **clean socket close is a disconnect too**: the pump marks channels dark
  and applies the exponential backoff, so a server-initiated close does not
  produce a reconnect storm or a silently missing recovery.

The ping cadence (50 s, the SDK's own interval) is anchored at the
connection instant, matching the SDK's timer semantics.

### 4. Parsing fails closed, from contracts pinned to the SDK source

Every payload contract in `quantmesh.hyperliquid.wire` is derived from the
pinned SDK source: `candleSnapshot` rows (float-string OHLCV, ms open/close
`t`/`T`), `l2Book` (`levels[0]` bids / `levels[1]` asks, exactly 2 arrays,
`n` an int), trades (`A`/`B` sides, `tid` as venue sequence), `allMids`,
`fundingHistory`, `meta`/`spotMeta`. A missing key, non-numeric price,
NaN/Infinity, symbol or interval mismatch, a candle whose close is not
exactly one interval after its open, an unknown frame channel, a frame for
an unsubscribed identifier, or a duplicate candle raises
`HyperliquidProtocolError` — a stream that silently drops frames is worse
than one that stops. The one deliberate exception is an empty trades frame,
which the SDK itself skips.

### 5. Fixture-first: wire-shaped payloads through the real parsers

Fixtures are the SDK's native wire shapes (not hand-canonicalized rows),
served by `HyperliquidFixtureProvider` through the real parsers, so a
fixture failure is a parser failure. Drills script the wire: frames,
`DROP`, `RESUME`, and scripted REST answers drive the reconnect acceptance
criterion deterministically — no network, no sleeps.

## Consequences

- Positive: disconnect/reconnect is a first-class, fixture-covered scenario
  (the acceptance drill proves clean candle coverage, a rebuilt book, and a
  reported trades gap); a live pump never enters unit tests, so CI cannot
  flake on the network.
- Positive: fail-closed parsing means an unknown future wire shape stops the
  stream loudly instead of corrupting the lake; the drift is visible in CI.
- Negative: trades lost across a disconnect window are genuinely lost — the
  finding is the honest contract (a future venue with a trades REST
  endpoint can heal them).
- Negative: book and candle recovery costs one REST round-trip per dark
  channel per reconnect; acceptable at testnet scale and bounded by the
  backoff.

## Extensions (recorded when their phases land)

- Phase B (#30): the testnet Exchange adapter is explicit-construction-only
  with an injected in-memory signer; the journal is the single source of
  truth for client_order_id↔oid with re-derive-on-reconnect (never
  re-submit); per-venue status table with unmappable statuses as findings.
- Phase C (#31): risk checks run before the wire (leverage, liquidation
  distance, reduce-only, stale-data window); funding is a fee-like journal
  entry.
- Phase E (#33): private keys enter only via injected signer or env var, in
  memory, never persisted or logged; wallet-isolation tests are part of the
  secret-handling suite.
