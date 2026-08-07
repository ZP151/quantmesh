# Iteration 0008 — M6 prediction-market intelligence

- Status: active
- Started: 2026-08-08
- Completed:
- Owner: Claude (solo delivery lane)
- GitHub issue: #34-#37 (Phases A-D)
- Pull request: pending (opened after acceptance criteria complete; stacks on the M5 PR)
- Roadmap milestone: M6 (`LATER` → `ACTIVE`)

## Outcome

Normalize event markets into calibrated probability signals: canonical
event/outcome/resolution-rule models, fixture-first Polymarket and Kalshi
market-data adapters (read-only, keyless, public endpoints only),
fee/spread/liquidity-aware implied probabilities, calibration metrics
(Brier score, reliability curves, liquidity confidence), forecast reports
on the M5 report stack with point-in-time replay (no look-ahead from
market resolution data), and reconciliation-disciplined cross-platform
event mapping.

## Scope and boundaries

- In scope: `quantmesh.events` canonical domain (venue-neutral event,
  outcome, resolution-rule, expiry, quote, implied-probability models);
  `quantmesh.polymarket` (discovery via the Gamma REST API, CLOB book +
  price history via the pinned `py-clob-client-v2` keyless public-data
  surface, fixture provider registry-registerable, live provider
  explicit-construction-only, fail-closed parsers pinned to the vendored
  SDK source); `quantmesh.kalshi` (thin public REST client over the
  live keyless trade-api v2 at `api.elections.kalshi.com`, wire shapes
  pinned by recorded fixtures — see the contract decision below —
  fixture provider + live provider, same discipline); fee/spread/
  liquidity-aware implied probabilities; Brier score, calibration curves
  and liquidity confidence; `ForecastReport` on the M5 report stack
  (`ReportRegistry`/`report_id`/artifact discipline) with point-in-time
  replay; cross-platform event mapping (matched/pending/ambiguous with
  evidence).
- Out of scope: any order path on Polymarket or Kalshi (no signer, no
  credentials, no trading surface exists anywhere in M6 — the adapters
  cannot even construct one); mainnet/real-money anything; M5's operator
  drill (already recorded and deferred); M7-M10.
- Reuse: the pinned `py-clob-client-v2` submodule (v1.1.0) for the
  Polymarket CLOB contract (order book, midpoints, tick size, fee
  rate/exponent, price history — all public, keyless methods); the
  public Gamma API for Polymarket discovery; the live Kalshi trade-api v2
  public endpoints; the M3 provider/lake/registry discipline; the M5
  report stack for forecast reports.
- Contract authority: Polymarket shapes are pinned to the vendored
  `py-clob-client-v2` source (same rule as M4/M5 SDK-source pinning).
  For Kalshi there is no vendorable SDK authority: the legacy
  `kalshi-python` repo is removed (404 on GitHub API; PyPI-only modern
  SDKs are generated from an unpublishable spec), so the contract is
  pinned by wire-shape fixtures recorded from the live public API on
  2026-08-08 plus the endpoint/field contract at docs.kalshi.com —
  exactly the "fixtures pin observed behavior" rule, with the fixtures
  themselves as the versioned authority and fail-closed parsers
  enforcing it. Recorded as ADR-0008 decision 2.
- Stacking: `feat/m6-prediction-market-intelligence` branches from the
  M5 branch tip (`f1a4b84`), because M6 reuses the M5 report stack and
  the M3 lake/provider discipline. M5's final PR awaits its human drill
  gate; M6's PR stacks on it until both are merged.

## Acceptance criteria

1. [x] Polymarket discovery/CLOB/history and Kalshi market data normalize
      through fixture-first adapters into the M3 lake (fixture path
      registry-registered; live providers explicit-construction-only,
      keyless, read-only). — Phase A (issue #34) 2026-08-08 + Phase B
      (issue #35) 2026-08-08.
2. [ ] Canonical event/outcome/resolution-rule/expiry models carry
      fee/spread/liquidity-aware implied probabilities computed by pure,
      fixture-tested functions (binary payoff structure per venue,
      spread-adjusted mid, liquidity confidence from book depth and tick
      size).
3. [ ] Point-in-time replay prevents look-ahead from market resolution
      data: every train window uses only observations timestamped at or
      before its end, enforced by construction and proven by a test
      where a resolution flips the outcome after window close.
4. [ ] Forecast reports (M5 report-stack discipline: deterministic
      setup-only `report_id`, `ReportRegistry`, byte-stable artifacts)
      include Brier score, calibration (reliability) curves and
      liquidity confidence.
5. [ ] Cross-platform event mapping is reconciliation-disciplined: the
      same real-world event on Polymarket and Kalshi maps only through
      explicit evidence (normalized title, outcome set, expiry, and
      resolution-rule fingerprints), reported as matched/pending/
      ambiguous — never silent fuzzy matching.

## Plan and role assignments

- Planner: Claude
- Quant researcher: Claude
- Implementer: Claude
- Reviewer: Claude (adversarial self-review before every commit)
- Verifier: Claude (fixture drills, full suite, ruff, diff, submodules)

### Phase A — canonical event models + Polymarket adapters (issue #34)

`quantmesh.events`: `EventVenue` (POLYMARKET/KALSHI), `EventMarket`
(venue, venue_id, event_ticker, title, category, expiry, outcomes,
resolution_rule, resolution), `Outcome` (name, venue_outcome_id, token_id
for Polymarket), `ResolutionRule` (canonical rule text + normalized
fingerprint), `MarketQuote` (bid/ask/ltp, book depth, liquidity, tick
size, fee rate), `ImpliedProbability` (probability, spread_adjustment,
liquidity_confidence, basis). `quantmesh.polymarket`: wire models +
fail-closed parsers pinned to the vendored `py-clob-client-v2` source
(clob_types/endpoints); `PolyMarketDataAdapter` (Gamma discovery →
events/markets/outcomes/volumes/liquidity; CLOB book by token id;
midpoints; tick size; fee rate/exponent; prices history);
`PolyFixtureProvider` (wire-shaped fixtures through the real parsers,
registry-registerable, M3 gate respected) + `PolyLiveProvider`
(explicit-construction-only; the CLOB client is constructed keyless —
`key=None` — and the signing surface is never reached); settings
(`QUANTMESH_POLYMARKET_*`); wire fixtures under
`src/quantmesh/polymarket/fixtures/` and canonical-shaped
`data/providers/fixtures/polymarket_{events,books,trades}.json` for the
M3 lake path. ADR-0008 recorded (5 decisions + extension hooks).
Tests: fixtures through the real parsers; fail-closed shape violations;
keyless construction proven; registry refusal for LIVE.

### Phase B — Kalshi market-data adapter (issue #35)

`quantmesh.kalshi`: thin public REST client over trade-api v2
(events, markets, series, orderbook, trades, candlesticks) with typed
errors and fail-closed parsers pinned to the recorded wire fixtures;
`KalshiFixtureProvider` (registry-registerable) + `KalshiLiveProvider`
(explicit-construction-only); the public base URL
`https://api.elections.kalshi.com` pinned and any non-public host
refused (the migration notice host `trading-api.kalshi.com` refuses at
construction — parity with the M5 testnet-pin discipline); no auth
surface exists — the adapter cannot hold credentials;
`QUANTMESH_KALSHI_*` settings; wire fixtures + canonical-shaped
`kalshi_{events,markets,books,trades}.json`; ADR-0008 Phase B extension
(contract-authority decision recorded).

### Phase C — implied probabilities + calibration + forecast reports (issue #36)

`quantmesh.events.calibration`: pure probability transforms — binary
payoff structure per venue (Polymarket YES/NO token payout at
resolution, fee rate/exponent from the pinned CLOB contract; Kalshi $1
per contract with the documented fee structure), spread-adjusted mid
with half-spread band, liquidity confidence from book depth and tick
size (thin books → wide confidence bands), price-history vol fallback;
Brier score (per-event and bucketed), reliability curves (confidence
bins vs observed frequency), liquidity-weighted confidence;
`ForecastReport` on the M5 report stack (`report_id` setup-only
determinism, `ReportRegistry` JSONL, byte-stable artifacts,
`created_at` excluded) with point-in-time replay: windows consume only
observations timestamped ≤ window end, resolution events participate
only from their resolution timestamp onward — enforced by construction
and proven by test; the report carries Brier score, calibration and
liquidity confidence (exit criteria 3-4). ADR-0008 Phase C extension.

### Phase D — cross-platform event mapping + point-in-time replay acceptance (issue #37)

`quantmesh.events.mapping`: canonical event identity via normalized
title + outcome set + expiry + resolution-rule fingerprints; explicit
evidence required for a match; outcomes are matched/pending/ambiguous
with the evidence recorded (JSONL mapping ledger, atomic appends,
fail-closed reads — the ADR-0006 reconciliation discipline applied to
events); point-in-time replay tests (resolution flips the outcome after
window close; the train never sees it); acceptance drill: fixture
Polymarket + Kalshi datasets → mapped events → implied probabilities →
calibration `ForecastReport` end-to-end with Brier + calibration +
liquidity confidence; final M6 PR (stacks on the M5 PR).

## Delivery protocol

Solo fast lane: one branch `feat/m6-prediction-market-intelligence`,
one tested/reviewed/issue-linked commit per issue, push each checkpoint,
one final M6 PR after acceptance criteria complete, squash-merge under
the standing merge authority when CI is green, close #34-#37, checkpoint
ACTIVE.md/0008/ROADMAP.md. There is no human gate in M6: all surfaces
are public read-only market data with no credentials and no order path,
so the milestone completes fully autonomously. The only stacking
constraint: the M6 PR merges after the M5 PR (which waits for the M5
operator drill).

## Durable decisions to record when reached

- ADR-0008 **recorded 2026-08-08** (issue #34 Phase A): event-market
  data enters only through fixture-first adapters with fail-closed
  parsers pinned to a versioned contract authority — for Polymarket the
  vendored `py-clob-client-v2` source; discovery goes through the public
  Gamma REST API; live providers are explicit-construction-only and
  keyless (the CLOB client is built with `key=None`; signing is never
  reachable because no order path exists); M6 surfaces are read-only
  market data by construction — there is no credential, no order, no
  real-money path.
- ADR-0008 extension (issue #35 Phase B), **recorded 2026-08-08**: the
  Kalshi contract authority is the recorded wire fixtures plus the
  docs.kalshi.com endpoint/field contract, because no vendorable SDK
  exists (legacy `kalshi-python` repo removed; modern SDKs are
  PyPI-generated from an unpublishable spec); the live base URL
  `https://api.elections.kalshi.com` is pinned and the migration host
  is refused at construction; the adapter cannot hold credentials. The
  recorded specifics: trades at `/markets/trades?ticker=` and
  candlesticks at `/series/{series}/markets/{ticker}/candlesticks`
  (both other routes 404); `/markets` rejects the `status=active`
  filter; both orderbook ladders ascend worst-first resting bids with
  YES asks derived as 1 − NO bid (verified exact against the market
  object at the same instant); bars are genuine (volume reported),
  zero-volume rows produce no bar; resolution is inline on
  settled/finalized market objects; error shapes are
  `{"error": {code, message}}` and `{"msg": ...}`; the migration host
  answers plain-text 401; the series object carries its ticker in
  `ticker`.
- ADR-0008 extension (issue #36 Phase C): implied probabilities are
  pure and fee/spread/liquidity-aware with venue-pinned payoff
  structures; forecast reports reuse the M5 report-stack discipline
  (setup-only identity, registry, byte-stable artifacts) and enforce
  point-in-time replay by construction — resolution data participates
  only from its resolution timestamp.
- ADR-0008 extension (issue #37 Phase D): cross-platform event mapping
  is reconciliation-disciplined — explicit evidence (normalized title,
  outcome set, expiry, resolution-rule fingerprints) required for a
  match, outcomes matched/pending/ambiguous, never silent fuzzy
  matching.

## Work log

- 2026-08-08: M6 planned and opened — iteration 0008 recorded; issues
  #34-#37 created; branch `feat/m6-prediction-market-intelligence`
  branched from the M5 tip `f1a4b84` (stacked delivery). Reuse survey
  done: `py-clob-client-v2` (v1.1.0) already pinned and keyless-capable;
  Kalshi has no vendorable SDK (legacy repo removed, GitHub API 404;
  modern SDKs PyPI-only) and the live public API was probed and
  confirmed keyless at `api.elections.kalshi.com` (the old
  `trading-api.kalshi.com` host serves a migration notice);
  docs.kalshi.com serves no downloadable OpenAPI spec. No external
  gates: M6 is public read-only market data end to end.
- 2026-08-08: **Phase A (issue #34) implemented** — canonical
  `quantmesh.events` models (`EventVenue` with `to_domain_venue()`,
  `ResolutionRule` with NFKC/casefold/whitespace-collapse fingerprint
  revalidation, `EventMarket`/`Outcome`/`MarketQuote`/`ImpliedProbability`
  with aware-timestamp and bounds validators) + `quantmesh.polymarket`
  (typed errors; wire models and fail-closed parsers pinned to the
  vendored `py-clob-client-v2` source and wire shapes recorded live
  2026-08-08; `SdkPolyTransport` keyless — `ClobClient(host, chain_id,
  key=None)`, proven by a faked-import test; `PolyMarketDataAdapter`
  pure wire→domain mapping; `PolyFixtureProvider` registry-registered /
  `PolyLiveProvider` explicit-construction-only). Live contract probing
  recorded the divergences that became ADR-0008 decision 2: the live
  `/book` omits the SDK's `last_trade_price`/`min_order_size`/`neg_risk`/
  `tick_size` fields (read from the market object instead); level order
  is worst-first (best levels extracted order-agnostically); `/prices-
  history` rows are objects `{"t", "p"}` with long ranges refused
  server-side; fees live at `/fee-rate` → `{"base_fee": bps}` (the SDK's
  `or 0` fallback deliberately not replicated — fail-closed); errors are
  `{"error": str}`; retired markets 404 "market not found". Polymarket
  has no public bar surface and no public trades surface on the pinned
  contract → `fetch_bars`/`fetch_trades` fail closed, and the canonical
  fixture set is `polymarket_events.json` + `polymarket_books.json`
  (`polymarket_trades.json` deliberately omitted — ADR-0008 decision 4).
  10 wire fixtures under `src/quantmesh/polymarket/fixtures/`; 2
  canonical-shaped fixtures under `data/providers/fixtures/` derived
  through the real parsers; `QUANTMESH_POLYMARKET_*` settings; ADR-0008
  recorded (5 decisions + Phase B/C/D extension hooks). 64 new tests;
  adversarial review fixed a per-market `_rule_text` cross-assignment
  bug (first market's description was applied to every market of an
  event) and removed an unused connect-timeout setting. 822 passed,
  3 skipped; ruff/diff/submodules clean.
- 2026-08-08: **Phase B (issue #35) implemented** — `quantmesh.kalshi`
  (typed errors; wire models and fail-closed parsers pinned to shapes
  recorded live 2026-08-08 at `api.elections.kalshi.com`;
  `HttpxKalshiTransport` httpx-based against the settings-pinned base
  URL, migration host refused at construction; `KalshiMarketDataAdapter`
  pure wire→domain mapping; `KalshiFixtureProvider` registry-registered /
  `KalshiLiveProvider` explicit-construction-only; no auth surface
  exists anywhere). Live contract probing recorded the divergences that
  became the ADR-0008 Phase B extension: trades live at
  `/markets/trades?ticker=` and candlesticks at
  `/series/{series}/markets/{ticker}/candlesticks` (the docs' routes
  404 even on liquid markets); `/markets` rejects `status=active` with
  a recorded 400; both orderbook ladders ascend worst-first resting
  bids (docs claim best-to-worst) — best YES ask derived as 1 − best
  NO bid per the docs' own rule, verified exact (0.42/0.69 with sizes
  6.00/4.00) against the market object captured at the same instant;
  candlesticks report `volume_fp` so Kalshi serves a genuine bar
  surface, zero-volume rows (only `price.previous_dollars`) produce no
  bar, `end_period_ts` is the period end and bars re-base to M3
  bar-open; resolution is inline on settled/finalized market objects
  (`result` + `settlement_ts`); error shapes are
  `{"error": {code, message}}` (404s) and `{"msg": ...}` (400s) plus
  the plain-text "API has been moved" 401 from the migration host;
  `/series/{ticker}` carries identity in `ticker`, not `series_ticker`.
  16 wire fixtures under `src/quantmesh/kalshi/fixtures/` (including
  the recorded error payloads and the migration-host 401); 4
  canonical-shaped fixtures under `data/providers/fixtures/`
  (`kalshi_{events,markets,books,trades}.json`) derived through the
  real parsers; `QUANTMESH_KALSHI_*` settings; ADR-0008 Phase B
  extension recorded. 57 new tests (881 passed, 3 skipped); the tests
  exposed and fixed two fail-closed gaps — `parse_market` leaked raw
  `KeyError`s (now wrapped like `parse_markets`) and `parse_series`
  read the docs' `series_ticker` field the recorded wire doesn't
  carry (identity is in `ticker`). Adversarial review also fixed 10
  over-long lines (E501) the earlier session left in the package;
  ruff/diff/submodules clean.

## Verification evidence

- Phase A slice (issue #34): **822 passed, 3 skipped** (symlink
  creation not permitted on Windows); ruff clean; `git diff --check`
  clean; submodules clean. Fixture drill: recorded Gamma/CLOB wire
  shapes (1 resolved NBA event + 5 active Fed markets + 99-level book +
  707-row prices-history) through the real parsers; keyless
  construction proven (faked `builtins.__import__` asserting
  `key=None`); registry refuses LIVE; bars/trades fail closed;
  canonical fixture consistency tests pin the M3-shape derivations.
- Phase B slice (issue #35): **881 passed, 3 skipped** (57 new tests);
  ruff clean; `git diff --check` clean; submodules clean. Fixture
  drill: recorded Kalshi wire shapes (3-event discovery page, Mars
  bundle, Fed + settled market objects with the 0.42/0.69/0.77 quote
  and 6.00/4.00 sizes, worst-first ladders, 5 complementary trades,
  230-row candlestick series with 10 traded bars, series object)
  through the real parsers; malformed variants fail closed (non-pair
  levels, out-of-order ladders, prices outside [0, 1], non-
  complementary trades, unknown status/market_type/result/taker_side,
  traded row missing OHLC, missing expiration, naive anything); typed
  error payloads (`{"error": ...}` and `{"msg": ...}`) and non-JSON
  bodies (`KalshiUnavailableError`); migration-host and unpinned-host
  construction refusal; registry refuses LIVE; derived-ask skip at
  $1.00; canonical fixture consistency tests pin the four
  `kalshi_*.json` derivations against the adapters.
- Phase C slice (issue #36): same gates; calibration fixture drills;
  point-in-time replay test (resolution after window close never seen
  in train); forecast report byte-reproducibility across registry roots.
- Phase D slice (issue #37): same gates; mapping ledger drill
  (matched/pending/ambiguous with evidence); acceptance drill converges
  to calibrated forecast reports with Brier + calibration + liquidity
  confidence.

## Risks and gates

- Public API drift (Gamma, CLOB, Kalshi) — fixtures pin observed
  behavior; parsers fail closed; recorded fixtures are the versioned
  authority for Kalshi.
- Polymarket CLOB fee structure changes — fee rate/exponent are read
  per market from the live contract; fixtures pin the parsing, never the
  values.
- Kalshi host migration — the base URL is pinned and non-public hosts
  refused; a future move needs one settings change and a fixture re-record.
- Event identity across platforms is fuzzy (titles differ per venue) —
  mapping requires explicit evidence and reports ambiguity instead of
  guessing.
- Rate limits on public endpoints — bounded poll intervals, configurable
  timeouts (settings), fixture-first development never depends on the
  network.
- No external gates: M6 carries no human gate (public read-only data,
  no credentials, no order path). The only dependency is the stacked
  M5 PR merge.
