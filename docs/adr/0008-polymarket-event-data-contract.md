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

  Recorded specifics (`quantmesh.events.calibration` and
  `quantmesh.events.forecast`, 2026-08-08):

  - **Fee-aware mid, derived from break-even, not assumed.** The
    consensus price is the mid `(bid + ask) / 2`, else the venue's
    last trade, else fail closed — a quote with neither is no price.
    The linear-fee venue (Polymarket `taker_fee_bps` on notional)
    widens the no-arbitrage interval: buying YES at `a` breaks even
    at `a(1 + f)`, selling at `b` at `b(1 - f)`, whose center is
    `mid + f(a - b)/2 = mid + fee_rate * half_spread`; that shift is
    `spread_adjustment`. Kalshi's `taker_fee_bps = 0` (its fee is
    quadratic on profit and not linearizable into the quote surface —
    the adapter says so) yields a zero adjustment; the quadratic fee
    is absorbed by the confidence band, never fabricated.
  - **Liquidity confidence, documented constants.** Depth score =
    total contract depth saturating at 2000 (both sides), spread
    score = 1.0 at ≤ 2 ticks decaying linearly to a 0.2 floor at 10
    ticks; a one-sided book halves the product (the other side's
    level is unobserved, not absent). Confidence is rounded to 4
    decimals; below 0.5 the history fallback blends the quote toward
    the recent price series' mean (volatility surfaced in the basis),
    at or above 0.5 the quote stands undiluted.
  - **Brier is binary and point-in-time.** Per-pair `brier`,
    `brier_score`, reliability-curve `brier_by_bin` (half-open bins,
    `p == 1.0` in the last; empty bins stay `None`) and
    `liquidity_weighted_brier`. Forecast windows evaluate contiguous
    tails of each market's timestamp-sorted observation grid; an
    observation strictly older than `resolved_at` never sees the
    outcome (an observation exactly on the resolution instant does),
    so a resolution that flips after a window closed cannot leak into
    it — enforced in `_outcome_value`, proven by the flip test.
    Split (multi-outcome) resolutions are refused — a binary Brier
    needs a binary resolution (fractional-payoff is a documented
    future extension); a resolution without `resolved_at` fails
    closed (it cannot be replayed). Unresolved windows report
    `brier = None`, never a fabricated number.
  - **Forecast report stack mirrors M5 (ADR-0005) with no lake pin.**
    `ForecastReport.id` is a setup-only 16-hex hash over commit +
    sorted universe (venue, venue_market_id composite) + window spec
    + bin count; `ForecastReportRegistry` is JSONL with atomic
    temp+replace appends, fail-closed reads with line attribution and
    duplicate-id refusal; artifacts (`report.json` with `created_at`
    excluded, `windows.csv`, `calibration.csv`) are byte-stable
    across registry roots. The recorded universe of event markets
    *is* the pin — there is no lake manifest to reference.
- Phase D (issue #37): cross-platform event mapping is
  reconciliation-disciplined — explicit evidence (normalized title,
  outcome set, expiry, resolution-rule fingerprints) required for a
  match, outcomes matched/pending/ambiguous, never silent fuzzy
  matching.

  Recorded specifics (`quantmesh.events.mapping`, 2026-08-08):

  - **Four independent evidence kinds; a pair needs two.** TITLE:
    normalized question texts equal (NFKC, case folding, whitespace
    collapsing — the resolution-rule fingerprint normalization);
    OUTCOME_SET: the normalized outcome-name sets equal (order-
    insensitive); EXPIRY: both expiries present and within the
    tolerance (default 3600s — admits sub-minute clock skew without
    admitting adjacent meetings); RESOLUTION_RULE: the canonical rule
    fingerprints equal. Two or more satisfied kinds make a pair
    MATCHED; exactly one leaves it PENDING (more evidence — typically
    the resolution itself — is required); when one event is strongly
    matched by two candidates on the other venue the conflicting pairs
    are AMBIGUOUS with all their evidence recorded. Events with no
    candidate pair are listed unmatched, never guessed. `pair_key` is
    an order-invariant 16-hex hash over the sorted member ids; every
    verdict is a deterministic function of the evidence, never of
    list order.
  - **The generic binary outcome set never matches.** All fixture
    markets are binary Yes/No, so on the recorded fixture universes
    every candidate pair carries exactly one evidence item (the
    outcome set) and stays PENDING — including the Fed correspondence
    that is in fact real: the September 2026 Polymarket questions and
    the April 2027 Kalshi question differ in title, expiry and rule
    fingerprint, so the mapping refuses to claim them. The acceptance
    drill pins this honest verdict (18 pending pairs) and demonstrates
    the MATCHED path on a drill-only pair whose four evidence kinds
    align.
  - **Ledger discipline mirrors ADR-0006.** `MappingLedger` is an
    append-only JSONL record of every verdict with its evidence and
    the producing commit (`~/.quantmesh/mappings/mappings.jsonl`):
    atomic temp+replace appends, fail-closed reads with line
    attribution, duplicate refusal by (pair_key, status, evidence
    signature), and re-evaluation with *changed* evidence appends as
    history — a PENDING pair that later matches upgrades to MATCHED
    with the evidence to prove it (`by_pair` returns the history in
    order).
