# ADR-0008 — Prediction-market data contract: fixture-first, fail-closed, keyless

- Status: accepted
- Date: 2026-08-08
- Deciders: solo delivery (iteration 0008, M6 Phase A, issue #34)
- Related: ADR-0004 (adapter boundary and wire contracts — this ADR
  extends the same "contracts derived from pinned sources, never docs"
  discipline to event markets), ADR-0007 (testnet wire ownership — the
  keyless/explicit-construction and fixture-first disciplines are
  carried over), ADR-0006 (reconciliation discipline — Phase D
  extension builds on it), `docs/iterations/0008-m6-prediction-market-intelligence.md`

## Context

M6 normalizes prediction-market data into calibrated probability
signals. The data surfaces are Polymarket (Gamma discovery REST API +
CLOB REST API) and Kalshi (trade-api v2 REST). Both are public,
read-only, and reachable without credentials — so unlike M4/M5 there
is no order path and no signing surface anywhere in the milestone. The
wire contracts must be pinned as versioned authority, parsing must
fail closed, live access must be explicit-construction-only, and
fixtures must record the observed wire so CI never depends on the
network.

## Decisions

### 1. Event-market data enters only through fixture-first adapters with fail-closed parsers pinned to a versioned contract authority

`quantmesh.events` carries the canonical venue-neutral models
(`EventVenue`/`EventMarket`/`Outcome`/`ResolutionRule`/`MarketQuote`/
`ImpliedProbability`); `quantmesh.polymarket` carries wire models and
fail-closed parsers; `PolyFixtureProvider` serves recorded wire
payloads through the real parsers (a fixture failure is a parser
failure) and registers in the M3 registry; `PolyLiveProvider` is
explicit-construction-only. A missing key, non-numeric price, price
outside [0, 1], count mismatch between outcomes and token ids, naive
timestamp, or out-of-order history raises `PolymarketProtocolError` —
never a silently wrong model.

### 2. Contract authority: the vendored `py-clob-client-v2` source plus wire shapes recorded from the live public API on 2026-08-08

The CLOB endpoints and the book/market shapes are pinned to the
vendored SDK source (`endpoints.py`, `clob_types.py`,
`parse_raw_orderbook_summary`). Live probing on 2026-08-08 recorded
the following and the parsers pin *observed behavior* where the
vendored source is stale or silent:

- **The live `/book` omits the SDK's `last_trade_price`/
  `min_order_size`/`neg_risk`/`tick_size` summary fields** — the SDK's
  `parse_raw_orderbook_summary` would crash on the live payload.
  QuantMesh parses the live shape and reads those values from the
  market object instead (which carries `minimum_tick_size`,
  `minimum_order_size`, `maker_base_fee`, `taker_base_fee`).
- **Level ordering is worst-first** (bids ascending, asks descending —
  confirmed on two live books). Best levels are extracted
  order-agnostically (max bid / min ask); the canonical M3
  `OrderBook` is re-ordered to best-first.
- **`/prices-history` rows are objects `{"t": unix seconds, "p":
  price}`**, not `[ts, price]` arrays; long ranges without an interval
  are refused server-side ("invalid filters", a recorded 400) — the
  live provider always sends the bounded range plus the 1m interval.
- **Fee rate lives at `/fee-rate` → `{"base_fee": bps}`** (the SDK's
  own endpoint; `/fee-rate-bps` is a 404). The SDK's `or 0` fallback
  on a missing fee is fail-open and is deliberately not replicated —
  a missing `base_fee` is a protocol error. Per-market fees come from
  the market object's `maker/taker_base_fee` (observed 1000 bps on
  both the endpoint and the market object).
- **Every error response is `{"error": "..."}`** (recorded from live
  400/404s including retired markets and over-long ranges) and raises
  a typed error carrying the server message — never a silent empty.
- **Retired markets 404** on `/markets/{condition_id}` ("market not
  found") — so resolution capture through the CLOB winner flags is
  only possible while the market object exists; the Gamma
  closed/`outcomePrices` inference path is a Phase C decision.

For Kalshi (Phase B) there is no vendorable SDK at all (the legacy
`kalshi-python` repo is removed; modern SDKs are PyPI-generated from
an unpublishable spec), so its contract authority is recorded wire
fixtures plus the docs.kalshi.com endpoint/field contract — the same
rule, with the fixtures themselves as the versioned authority.

### 3. Live providers are explicit-construction-only and keyless; no order path exists

`PolyLiveProvider` is `ProviderMode.LIVE` with an injected
`PolyRestTransport`; the M3 registry refuses it. The SDK's `ClobClient`
is constructed with `key=None` (the pinned constructor's `signer` is
None then — proven by test with a faked import), reached only lazily
and import-guarded; missing SDK and SDK failures are typed errors.
Gamma is reached through httpx against the settings-pinned base URL.
There is no credential, no signer, no order method anywhere in the
package — the adapters cannot even construct a trading surface.

### 4. Polymarket has no public bar surface and no public trades-history surface on the pinned contract — the provider fails closed instead of fabricating

`fetch_bars`/`fetch_trades` raise `PolymarketProtocolError` (the
Hyperliquid-trades precedent). The CLOB `/prices-history` is a price
series, not trades; deriving OHLC bars from it would invent a volume
the venue never reports (Kalshi candlesticks do report volume, so
Kalshi will serve bars in Phase B). Consequently the canonical fixture
set is `polymarket_events.json` + `polymarket_books.json`; the
`polymarket_trades.json` named in the Phase A plan is deliberately
omitted for this reason.

### 5. Discovery returns deployed markets only; resolution enters only through the CLOB winner flags

A Gamma market whose `clobTokenIds` are empty is pre-deployment (no
quoteable tokens) and is skipped by the adapter (the parser still
surfaces it). Gamma carries no winner flag, so Gamma-discovered
`EventMarket`s are unresolved by design; resolution is `[]` until the
CLOB market object's `tokens[].winner` flags say otherwise (multiple
winners is a genuine split resolution and stays a list). Retired
markets' resolution and the timing of resolution entry are Phase C
decisions (point-in-time replay).

## Consequences

- Positive: every Polymarket surface is fixture-covered; CI never
  touches the network; a future wire drift shows up as a loud parser
  failure with the server's own message.
- Positive: keyless construction is proven by test, so the milestone
  cannot silently grow a signing surface.
- Positive: the canonical event models are venue-neutral — Phase B
  (Kalshi) normalizes into the same contracts, and Phase D maps
  across them on fingerprints.
- Negative: resolved/retired markets are not CLOB-fetchable, so
  resolution capture for old markets must wait for the Phase C
  inference decision.
- Negative: Polymarket bars and trades cannot be served — consumers
  that want a bar surface must use venues that report one.

## Extensions (recorded when their phases land)

- Phase A (issue #34), **recorded 2026-08-08**: this document.
- Phase B (issue #35), **recorded 2026-08-08**: Kalshi contract
  authority — recorded wire fixtures plus docs.kalshi.com (no
  vendorable SDK exists); the live base URL
  `https://api.elections.kalshi.com` pinned; the migration host
  refused at construction; the adapter cannot hold credentials. Live
  probing pinned the following to the recorded wire (the docs were
  stale on each):
  - **Routes**: executed trades live at `GET /markets/trades?ticker=`
    (not `/markets/{ticker}/trades`, which 404s even on liquid
    markets); candlesticks live at
    `GET /series/{series}/markets/{ticker}/candlesticks` with
    `period_interval` one of 1/60/1440 (not
    `/markets/{ticker}/candlesticks`, which 404s). `/markets` rejects
    `status=active` with a recorded 400 — the filter set is
    {open, settled, unopened}, even though the market object's own
    `status` field reports `active`.
  - **Orderbook**: the response is `orderbook_fp` with `yes_dollars`
    and `no_dollars` ladders, both ascending worst-first resting bids
    (the docs' "best to worst" claim is contradicted by the wire). The
    best YES bid is the max of the yes ladder; the best YES ask is
    derived as `1 − max(no ladder)` (the docs' own rule, verified
    exact against the market object's `yes_bid_dollars`/`yes_ask_dollars`
    captured at the same instant: derived 0.42/0.69 matched the
    market object, sizes 6.00/4.00 cross-checked too). A NO bid at
    $1.00 mirrors to a $0 ask and is skipped — it carries no tradeable
    depth.
  - **Bars are genuine**: candlesticks report `volume_fp`, so Kalshi
    serves an honest bar surface (contrast Polymarket, decision 4).
    Zero-volume rows carry only `price.previous_dollars` (no period
    OHLC) and produce no bar — nothing is fabricated; a traded row
    missing its trade OHLC is a fail-closed error. `end_period_ts` is
    the period END; bars are re-based to the M3 bar-open convention.
  - **Resolution is inline**: a settled/finalized market carries its
    `result` ("yes"/"no") and `settlement_ts` on the market object, so
    Kalshi `EventMarket`s resolve from the venue report (unlike
    Polymarket's winner-flag-only path); non-binary markets are
    refused at the adapter.
  - **Error shapes**: `{"error": {"code", "message"}}` on 404s (typed
    refusal with the server's message) and `{"msg": "Parameter
    validation failed ..."}` on 400s; the migration host
    `trading-api.kalshi.com` answers everything with a plain-text 401
    "API has been moved to https://api.elections.kalshi.com/" —
    refused at construction, parity with the M5 testnet-pin discipline.
  - **Series identity**: the `/series/{ticker}` object carries its
    ticker in `ticker`, not `series_ticker` (the docs' schema field is
    absent on the wire).
- Phase C (issue #36): implied probabilities are pure and
  fee/spread/liquidity-aware with venue-pinned payoff structures;
  forecast reports reuse the M5 report-stack discipline and enforce
  point-in-time replay by construction — resolution data participates
  only from its resolution timestamp (including the Gamma inference
  path for markets whose CLOB object has been retired).
- Phase D (issue #37): cross-platform event mapping is
  reconciliation-disciplined — explicit evidence (normalized title,
  outcome set, expiry, resolution-rule fingerprints) required for a
  match, outcomes matched/pending/ambiguous, never silent fuzzy
  matching.
