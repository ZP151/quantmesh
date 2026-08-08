# Iteration 0007 — M5 Hyperliquid testnet workflow

- Status: completed
- Started: 2026-08-08
- Completed: 2026-08-08
- Owner: Claude (solo delivery lane)
- GitHub issue: #29-#33 (Phases A-E)
- Pull request: [#66](https://github.com/ZP151/quantmesh/pull/66) (merged)
- Roadmap milestone: M5 (`DONE`)

## Outcome

Analyze spot/perpetual markets and execute safely on Hyperliquid **testnet**:
REST/WebSocket market data with reconnect and gap recovery, testnet
order/cancel/fill/position adapters reconciled against the order journal,
funding/leverage/liquidation-distance/reduce-only risk checks, order-book
imbalance and volatility baselines, and wallet-isolation secret-handling
tests. No mainnet URL, real key, or real-money path exists in the product
surface; the sole external-state gate is a human-provided testnet wallet for
the operator drill (Phase E).

## Scope and boundaries

- In scope: `quantmesh.hyperliquid` package (REST Info adapter, WS stream
  with reconnect + gap recovery, testnet Exchange adapter, risk pre-submission
  checks, wallet isolation), Hyperliquid fixture data extended through the M3
  lake path, order-book imbalance and volatility baselines on the M5 report
  stack, testnet reconciliation against the M4 `OrderJournal`.
- Out of scope: mainnet trading, real wallets/private keys in the product
  surface, AI order authority, funding-rate arbitrage, mobile/frontend work,
  and M6 prediction markets.
- Reuse: the pinned `hyperliquid-python-sdk` (submodule 0.24.0) for the wire
  protocol — `Info` (REST) and `Exchange` (testnet signing); Hummingbot
  Hyperliquid connectors are design references only, never copied (no
  GPL/AGPL code copying, per repo convention). The SDK's bundled
  `WebsocketManager` is basic; QuantMesh owns reconnect and gap-recovery
  logic on top of it (ADR-0007).
- Stacking: `feat/m5-hyperliquid-testnet-workflow` branches from the M4
  branch tip (`b6fd2ea`), because M5 reuses the M4 `OrderJournal`,
  `OrderStateMachine`, `Fill`, and reconciliation discipline. M4's final PR
  awaits the M4 Phase E human gate; M5's PR stacks on it until both gates
  are complete.

## Acceptance criteria

- [x] REST/WebSocket market data normalizes into the M3 lake with reconnect
      and gap recovery: after a scripted disconnect, candle coverage is
      clean and the order-book rebuilds without missed deltas (fixture
      drill). — DONE 2026-08-08 (issue #29, Phase A): 75 new tests; the
      acceptance drill (scripted frames → `DROP` → `RESUME` → REST re-sync)
      ends with a gap-free merged candle series, a fresh-snapshot book, and
      a typed trades-gap finding; the fixture provider registers in the M3
      registry and its bars round-trip through `Lake` gap-free (ADR-0007
      decision 3: Hyperliquid book updates are full level arrays, so a
      snapshot rebuild is the honest recovery — there are no deltas to
      miss).
- [x] Testnet execution survives disconnect/reconnect without duplicate
      orders: the journal is the single source of truth for
      client_order_id↔oid; after a reconnect the order state is re-derived
      from the broker's orders list, never re-submitted; a client id already
      mapped refuses submission (fixture drill). — DONE 2026-08-08 (issue
      #30, Phase B): 86 new tests; the acceptance drill (scripted phases:
      lost ack → cloid recovery with re-stamped oid → cancel by oid →
      ack-terminal match → fills + positions imported → second pass clean)
      converges to {matched: 2, pending: 0, missing: 0, divergent: 0} with
      0 findings and 0 refusals; the reused-cid refusal, the per-order ack
      error → REJECTED path, fee-less and overfill refusals, and the
      position drift findings are all fixture-covered (ADR-0007 Phase B:
      cloid channel, journal-first ids, re-derive-on-reconnect, derived
      statuses, ack-terminal classification).
- [x] Risk limits prevent excess leverage and stale-data execution: the
      pre-submission guard refuses orders that breach the leverage bound,
      liquidation-distance floor, reduce-only posture, or the stale-data
      window; funding is accounted in the journal (fixture tests). — DONE
      2026-08-08 (issue #31, Phase C): 40 new tests; the pure
      `evaluate_order` gate covers each check including the fail-closed
      MISSING_DATA paths (no equity, no entry, no liquidation price, no
      mark, no funding), the funding-corrected liquidation-distance
      estimate (paid funding shrinks the distance; direction flips rebase
      to the new entry; reductions and full closes skip the estimate),
      and the adapter wiring proves a refusal consumes nothing — no
      journal entry, no wire call; `FundingLedger` anchors, deltas,
      no-ops, per-coin series, and fail-closed reads are fixture-covered.
- [x] Order-book imbalance and volatility baselines each produce a
      reproducible walk-forward, cost-aware report from a pinned dataset
      (M5 report stack on the M4 `run_walk_forward`/`ReportRegistry`). —
      DONE 2026-08-08 (issue #32, Phase D): `book_imbalance` (depth-
      weighted (Σbid−Σask)/(Σbid+Σask), fail-closed on empty books) and
      `imbalance_by_bar` (snapshots bucketed into [timestamp, timestamp+
      interval) bar windows, per-bar means aligned 1:1 with the bar grid;
      outside-every-window, no-snapshot, non-monotonic, and symbol-
      mismatch inputs all fail closed); `low_volatility_weights` (bottom
      half by train realized vol, zero-vol symbols included) and
      `book_imbalance_weights` (top half by train mean signal) as
      `run_walk_forward` strategy branches; the signal series are caller-
      supplied per bar, validated against the grid (universe + length), a
      train-window-only proof guards against lookahead, and the signal
      digest folds into `report_id` (None keeps legacy identity) with
      `signals_digest` pinned on `StrategyReport` itself; end-to-end
      reports reproduce byte-identically and signal inputs differentiate
      the identity.
- [x] Wallet isolation: private-key material is accepted only through an
      injected in-memory signer or env var; never persisted, logged, or
      reported; adapter construction without a key fails closed; the
      Exchange adapter pins testnet and refuses any non-testnet base URL
      before the wire. — DONE 2026-08-08 (issue #33, Phase E safe work;
      the operator drill itself is the deferred human gate below):
      `InMemorySigner` repr/str redact the key bytes (the default
      dataclass repr would print them into logs and dumps),
      `signer_from_env` errors never echo the env value (a malformed
      secret is itself key material), `SdkExchangeTransport(None)` and
      missing-signer construction fail closed (no default-key path),
      and the wallet-isolation suite drives a full scripted drill
      (lost ack → cloid recovery → cancel → fills + positions → clean)
      with a real 32-byte key, then scans the journal JSONL, the drill
      script, captured DEBUG logs, and the entire scratch tree for the
      key's hex form, its bytes repr, and the signer repr — and proves a
      risk-refusal message carries no key material either; testnet pin +
      non-testnet refusal were already covered at Phase B construction.
- [ ] No real-money order path is implemented or enabled.

## Implementation plan

### Phase A — market-data surface with reconnect and gap recovery (issue #29)

REST `Info` adapter (candles, l2Book, meta/spot_meta, funding) and a WS
stream (trades, order-book deltas, funding) with heartbeats, resubscribe,
and REST re-sync over the disconnect window. Fixture-first: recorded
testnet frames as JSONL fixtures (extend the M3 Hyperliquid fixture
provider with l2Book snapshots/deltas, funding, and multi-session candles).
Gap detection reuses the M3 `coverage_gaps` discipline; lake writes go
through the existing `Lake`/`ManifestWriter` gates. A LIVE provider joins
the registry explicit-construction-only (M4 pattern).

### Phase B — testnet execution adapters (issue #30)

`Exchange` boundary with an injected in-memory signer; testnet base URL
pinned, mainnet refused. `place`/`cancel`/status/fill/position through the
M4 `OrderJournal`; a per-venue `HYPERLIQUID_STATUS_TO_DOMAIN` table
(SUBMITTED/OPEN/FILLED/CANCELED/REJECTED + partials) with unmappable
statuses as findings; a reconciliation service with the M4 discipline
(matched/pending/missing/divergent, adoption only for clean pairs, remark
channel replaced by the explicit oid mapping the SDK returns). Duplicate-
order safety: journal-first client ids, re-derive-on-reconnect.

### Phase C — risk pre-submission surface (issue #31)

Before any order reaches the wire: leverage bound, liquidation-distance
floor (from l2Book + funding + position), reduce-only posture, and a
stale-data window (latest quote/book timestamp age). Funding accounted as
a fee-like journal entry. Blocks on Phases A and B.

### Phase D — crypto baselines (issue #32)

Order-book imbalance (bid/ask depth weighted) and volatility (realized,
windowed) baselines feeding the M5 report stack via `run_walk_forward`
with the shared `CostModel`; book imbalance needs l2Book-derived signals
recorded as canonical series. Blocks on Phase A.

### Phase E — wallet isolation tests and operator drill gate (issue #33)

Secret-handling tests (no key material in journal, lake, logs, reports,
fixtures, or process dumps), testnet-only refusal tests, and the operator
drill: a human supplies a testnet wallet/private key via env var, runs
the health + read-only market-data checks, then a deliberately small
testnet order/cancel/reconcile drill; redacted evidence is recorded. This
is the sole external-state gate for M5 — same posture as M4 Phase E:
never request or log a real wallet, mainnet key, or real-trading
confirmation.

**Operator gate (recorded 2026-08-08; deferred — all safe Phase E work
is complete and committed, and the final M5 PR stays closed until a human
runs this drill and records redacted evidence):**

1. Fund a Hyperliquid *testnet* wallet via the testnet faucet/bridge
   (https://app.hyperliquid-testnet.xyz — testnet tokens have no value)
   and export its private key as 64 hex characters.
2. In a fresh terminal with shell history disabled, export
   `QUANTMESH_HYPERLIQUID_PRIVATE_KEY=<64-hex>`. Never write the key into
   a file, commit, issue, log, or chat; never use a mainnet wallet.
3. Health + read-only market-data check (no key needed):
   ```python
   from quantmesh.hyperliquid.rest import SdkRestTransport
   from quantmesh.hyperliquid.market_data import HyperliquidLiveProvider
   from quantmesh.domain.models import Instrument, InstrumentType, Venue
   info = SdkRestTransport()                      # testnet pinned; mainnet refused
   meta = info.meta()                             # sanity: venue reachable
   provider = HyperliquidLiveProvider(info)       # explicit-construction-only
   btc = Instrument("BTC", venue=Venue.HYPERLIQUID, instrument_type=InstrumentType.PERPETUAL)
   bars = provider.fetch_bars(btc, interval="1h", start=..., end=...)  # bounded range mandatory
   book = provider.fetch_order_books(btc)
   ```
   Expect: `meta` returns, bars/book return fresh testnet data, no key
   material printed anywhere.
4. Deliberately small order/cancel/reconcile drill (key needed):
   ```python
   from datetime import UTC, datetime
   from quantmesh.hyperliquid.exchange import (
       HyperliquidExecutionAdapter, SdkExchangeTransport, signer_from_env)
   from quantmesh.execution.journal import OrderJournal
   from quantmesh.domain.models import OrderRequest, Side, Instrument, InstrumentType, Venue
   from quantmesh.domain.orders import OrderStatus
   from quantmesh.hyperliquid.reconciliation import apply_reconciliation, run_reconciliation
   from quantmesh.settings import settings
   transport = SdkExchangeTransport(signer_from_env())
   journal = OrderJournal(settings.orders_dir)
   adapter = HyperliquidExecutionAdapter(transport, journal)
   order = adapter.place(
       OrderRequest(instrument=Instrument("BTC", venue=Venue.HYPERLIQUID,
                   instrument_type=InstrumentType.PERPETUAL),
                   side=Side.SELL, quantity=0.001, limit_price=<mid*1.02>),
       order_id="op-drill-1", created_at=datetime.now(UTC),
       client_order_id="<32-hex>")
   assert order.status is OrderStatus.ACCEPTED
   adapter.cancel(journal.get("op-drill-1"), at=datetime.now(UTC))
   report = run_reconciliation(transport.snapshot(), journal)
   apply_reconciliation(report, journal, transport.snapshot())
   ```
   Expect: ACCEPTED then CANCELED, reconciliation clean (matched 1,
   findings empty). The journal file holds no key material — the
   wallet-isolation suite proves the invariant; the operator just
   confirms the drill ran.
5. Record redacted evidence in this document and close the gate: date,
   venue response statuses, final reconciliation counts, and a journal
   excerpt with no key material. Then the M5 final PR opens, #33 closes,
   and M6 is unblocked.

## Delivery protocol

Solo fast lane: one branch `feat/m5-hyperliquid-testnet-workflow`, one
tested/reviewed/issue-linked commit per issue, push each checkpoint, one
final M5 PR after the acceptance criteria and operator-validation evidence
are complete, squash-merge under the standing merge authority when CI is
green, close #29-#33, checkpoint ACTIVE.md/0007/ROADMAP.md. The human gate
deferral rule of the goal directive applies: complete all safe work,
record the exact gate, proceed to M6.

## Durable decisions to record when reached

- ADR-0007 **recorded 2026-08-08** (issue #29 Phase A): Hyperliquid is
  reached only through the pinned SDK submodule (lazy, import-guarded REST
  `Info` boundary; the SDK's WS manager has no reconnect, so QuantMesh owns
  the stream); testnet pinned and mainnet refused before the wire; reconnect
  = heartbeat → resubscribe → REST re-sync (candles merged over the gap with
  the frame stream winning, the book replaced by a fresh snapshot —
  Hyperliquid pushes full level arrays, not deltas, so there is nothing to
  replay; trades are typed gap findings — no public trades REST endpoint);
  a clean socket close is a disconnect too (backoff, no reconnect storm);
  the 50 s ping anchors at the connection instant; fail-closed parsing from
  SDK-source contracts; fixture-first wire-shaped payloads through the real
  parsers; live provider explicit-construction-only.
- ADR-0007 extension **recorded 2026-08-08** (issue #30 Phase B): the
  testnet Exchange adapter is explicit-construction-only with an injected
  in-memory signer (env var the operator path, fail-closed; key material
  never persisted/logged/reported); testnet pinned and mainnet refused
  before the wire; the journal is the single source of truth for
  client_order_id↔oid with re-derive-on-reconnect (never re-submit), the
  cloid channel (client_order_id → "0x"+32-hex) replacing Moomoo's remark
  channel — a lost ack leaves PENDING unacknowledged, reconciliation
  recovers the mapping from the venue's cloid echo and re-stamps the oid at
  adoption (MAPPING/WARNING, non-blocking), ambiguous channels are
  divergent; place-time "filled" acks only advance to ACCEPTED (fills
  arrive through reconciliation with venue fill identity + fee); order
  status is derived from the surface (no order-status endpoint): open =
  remaining size (compatible with journal partial fills), inactive =
  fills-only rows with journal context (fill total → FILLED, journal
  terminal → that status, else venue silence → CANCELED); per-venue status
  table with unmappable statuses as findings; ack-terminal orders the venue
  no longer lists are matched (note only when no venue order id was ever
  received); adoption only for matched/pending clean pairs through the
  shared ADR-0006 contract types; fee-less fills refused; market orders
  cannot carry reduce_only (the pinned SDK hard-codes it) — refused, not
  silently re-typed; positions compare as signed sizes.
- ADR-0007 extension (issue #31 Phase C) **recorded 2026-08-08**: the
  pure, deterministic pre-submission gate (leverage bound, liquidation-
  distance floor from l2Book + funding + position, reduce-only posture,
  stale-data window) fails closed on missing inputs; the adapter wires
  `risk_limits` + `risk_context` paired or not at all, the gate runs
  before the journal-first recording, and a refusal raises
  `HyperliquidRiskRefusalError` consuming nothing; funding is a fee-like
  `FundingLedger` entry (signed deltas vs the running cumulative per
  coin, atomic writes, fail-closed reads).
- ADR-0007 extension (issue #32 Phase D) **recorded 2026-08-08**: the
  order-book imbalance signal is pure and depth-weighted over the full
  book (Σbid−Σask)/(Σbid+Σask), an empty book is an error; the per-bar
  canonical series buckets snapshots into [timestamp, timestamp+interval)
  windows aligned 1:1 with the bar grid and fails closed on any gap
  (snapshot outside every window, bar without snapshot, non-monotonic
  series, symbol mismatch, mixed intervals); signal-driven baseline
  strategies consume caller-supplied per-bar signal series validated
  against the grid, train-window-only by construction; the signal digest
  is part of the report setup (folds into `report_id`, pinned as
  `signals_digest` on the recorded report, None preserves the legacy
  identity); the baseline strategy vocabulary is extended
  (`low_volatility`, `book_imbalance`) rather than opened up.
- ADR-0007 extension (issue #33 Phase E) **recorded 2026-08-08**: private
  keys enter only via injected signer or env var, in memory, never
  persisted or logged; the signer's repr redacts the key bytes; env-parse
  errors never echo the value; construction without a key fails closed;
  the wallet-isolation suite scans every durable surface (journal, drill
  script, captured logs, scratch tree) and the refusal path for key
  material after a full scripted drill; the operator drill is the sole
  external-state gate — recorded verbatim above and deferred until a
  human runs it.

## Work log

- 2026-08-08: M5 planned and opened — iteration 0007 recorded; issues
  #29-#33 created; branch `feat/m5-hyperliquid-testnet-workflow` branched
  from the M4 tip `b6fd2ea` (stacked delivery). M4's final PR and M5's
  final PR both await their operator gates; all safe work proceeds.
- 2026-08-08: **Issue #29 (Phase A, REST/WS market data with reconnect and
  gap recovery) committed** — `quantmesh.hyperliquid` package: typed errors;
  `wire` parsers (candles/l2Book/trades/allMids/funding/meta/spotMeta) with
  contracts derived from the pinned SDK source and fail-closed shape
  checks; `SdkRestTransport` (lazy, import-guarded, testnet pinned, mainnet
  refused at construction) + `ScriptedRestTransport` drill stub; WS layer
  split into the deterministic `StreamSupervisor` state machine, the
  scripted `SimulatedStreamTransport`, and the `HyperliquidStream` asyncio
  pump with exponential backoff (SDK's `WebsocketManager` has no reconnect —
  ADR-0007); `HyperliquidDataAdapter`/`HyperliquidFixtureProvider`
  (wire-shaped fixtures through the real parsers, registry-registerable)/
  `HyperliquidLiveProvider` (explicit-construction-only, bounded ranges,
  trades fail closed); 6 wire-shape fixtures; settings for the pinned
  testnet URL and timeouts; ADR-0007 recorded (5 decisions + 3 extension
  hooks). 75 new tests. Review caught and fixed two real defects: the live
  pump used `async with` on a raw coroutine (`TypeError` on Python 3.13 —
  the SDK connection is awaited before entering the context manager, and a
  clean socket close now marks channels dark and backs off instead of
  spinning), and `parse_trades_frame` expected the frame envelope while the
  supervisor hands it the data payload (contract aligned to the data list).
  600 passed, 3 skipped; ruff clean; diff clean; submodules clean.
  Checkpoint pushed.
- 2026-08-08: **Issue #30 (Phase B, testnet execution adapters +
  reconciliation) committed** — the ADR-0006 contract types
  (`FindingKind`/`Severity`/`ReconcileTolerance`/`ReconciliationFinding`/
  `OrderOutcome`/`ReconciliationReport`/`AdoptionResult`) extracted to
  `quantmesh.execution.reconciliation` and re-exported by the Moomoo
  binding; `quantmesh.hyperliquid.exchange` — wire models (BrokerOrder/
  BrokerFill with venue fill identity + cloid/BrokerPosition/ExecutionSnapshot),
  signer boundary (32-byte in-memory signer; `signer_from_env` fail-closed),
  `ExchangeTransport` boundary, `ScriptedExchangeTransport` (JSONL phases,
  deterministic oids, `lost_acks` withholding the ack), `SdkExchangeTransport`
  (lazy + import-guarded, testnet pinned, mainnet refused, market orders
  refuse reduce_only because the pinned SDK's `market_open` hard-codes it —
  closing goes through reduce-only LIMIT orders), `HyperliquidExecutionAdapter`
  (journal-first client ids — recorded before the wire, reused ids refuse —
  per-order ack errors → REJECTED(reason), filled acks → ACCEPTED only,
  cancel by oid or cloid), fail-closed parsers for every wire shape
  (`tid`/`hash` fill identity, cloid echo mismatch, top-level err);
  `quantmesh.hyperliquid.reconciliation` — cloid channel recovery
  (recovered = MAPPING/WARNING non-blocking, re-stamps oid at adoption,
  ambiguous channels divergent), derived statuses for a surface with no
  order-status endpoint (open = remaining size tolerates journal partial
  fills; inactive = fills-only rows: fill total → FILLED, journal terminal
  → that status, else silence → CANCELED), ack-terminal unclaimed orders
  matched (note only when the order never received a venue order id),
  M4-discipline compares (quantity/price/fees/fill identity/positions with
  declared tolerances; fee-less fills MISSING_DATA; stamped fill the venue
  forgot → REVOKED_FILL), adoption only for matched/pending clean pairs
  (fee-less and overfill refusals, derived CANCELED/REJECTED applied with
  venue evidence timestamps, idempotent); 6-phase drill fixture
  `wire_exchange_script.jsonl` (lost ack → cloid recovery → cancel →
  ack-terminal match → fills + positions → clean); ADR-0007 Phase B
  extension recorded; acceptance criterion 2 checked off. 86 new tests
  (52 exchange, 34 reconciliation) including the acceptance drill
  converging to 0 findings / 0 refusals. Review caught and fixed four
  real defects before commit: `BrokerFill` lacked the cloid the snapshot
  merge reads (fills-only rows would crash), `parse_fill` rejected rows
  whose identity comes from `hash` when `tid` is absent, the
  `SdkExchangeTransport._call` helper swallowed keyword arguments (the
  `market_open` cloid route), and the drill fixture's second cloid was 33
  hex characters — caught by the venue's own 34-char cloid shape check
  and corrected in the fixture and tests. Shared contract types verified
  against the Moomoo binding (full suite green). 686 passed, 3 skipped;
  ruff clean; diff clean; submodules clean. Checkpoint pushed.
- 2026-08-08: **Issue #31 (Phase C, risk pre-submission surface)
  committed** — `quantmesh.hyperliquid.risk`: pure `evaluate_order` gate
  over `RiskLimits`/`RiskContext` with four fail-closed checks (stale-data
  window — missing, future, or over-age book timestamps refuse; reduce-only
  posture; leverage bound on the resulting signed position vs account
  equity — full closes skip, missing equity/entry MISSING_DATA; liquidation-
  distance floor — the venue's reported liquidationPx scaled to the
  size-weighted entry of the resulting position, funding-corrected toward
  the mark (conservative), measured against the l2Book mid, already-at-or-
  beyond a refusal, reductions/full closes skip the estimate, direction
  flips rebase to the new entry); typed `RiskKind`/`RiskRefusal`/
  `RiskDecision` (allowed only with zero refusals, checks recorded in gate
  order); `RiskContextProvider` Protocol; `FundingLedger` fee-like journal
  entry — signed deltas against each coin's running cumulative (never the
  last row's delta, which would compound the series — caught and fixed in
  review), `funding.jsonl` under the orders dir, atomic temp+replace
  writes, fail-closed reads with line attribution, first record anchors,
  zero deltas no-ops; adapter wiring — `risk_limits` + `risk_context`
  paired at construction or ValueError, the gate runs BEFORE the journal-
  first recording, a refusal raises `HyperliquidRiskRefusalError` with the
  typed refusals and consumes nothing (no journal entry, no wire call);
  ADR-0007 Phase C extension recorded; acceptance criterion 3 checked off.
  40 new tests (26 gate, 7 adapter wiring, 7 funding ledger). Review caught
  one real defect before commit: the ledger computed deltas against the
  previous row's delta instead of the running cumulative (a three-record
  series would compound to 3.6 instead of 1.1 — now fixed with a regression
  test), plus the adapter's TYPE_CHECKING annotations needed the module's
  `from __future__ import annotations`. 726 passed, 3 skipped; ruff clean;
  diff clean; submodules clean. Checkpoint pushed.
- 2026-08-08: **Issue #32 (Phase D, order-book imbalance and volatility
  baselines) committed** — `quantmesh.hyperliquid.signal`: pure
  depth-weighted `book_imbalance` over the full book (one-sided books are
  well-defined ±1.0, an empty book fails closed), `imbalance_by_bar`
  cursor-aligned bucketing into [timestamp, timestamp+interval) bar
  windows with per-bar means aligned 1:1 to the grid and every misalignment
  an error (outside every window, bar without snapshot, non-monotonic
  snapshots, symbol mismatch, mixed intervals, empty inputs);
  `quantmesh.research.baselines` — `low_volatility_weights` (bottom half
  by train realized vol, equal weight, zero-vol symbols included, sorted
  tie-break) and `book_imbalance_weights` (top half by train mean signal)
  as `run_walk_forward` strategy branches; `signals_by_symbol` validated
  against the bar grid (universe equality + per-symbol length), computed
  per window from the train slice only (no lookahead — proven by a test
  where the signal flips after window 1 and the weights hold); the signal
  digest (`_signals_digest`, sha256 over sorted signal JSON) folds into
  `report_id` and is pinned as `signals_digest` on `StrategyReport` so the
  recorded setup and the identity agree (None keeps the legacy id — the
  review caught that the report model recomputed the expected id without
  the digest, rejecting every signal-driven report; fixed by carrying the
  digest on the report itself); `STRATEGIES` extended with
  `low_volatility`/`book_imbalance` rather than opened up; exports in the
  hyperliquid and research package surfaces; acceptance criterion 4
  checked off. 55 new/updated tests (16 signal, 39 baseline) plus the
  corrected tie-break and train-window expectations. Review caught two
  real defects before commit: the identity/pin mismatch above, and the
  tie-break expectation (bottom half of a 3-way tie is the first two
  symbols sorted by name — the implementation was right, the test was
  wrong). 755 passed, 3 skipped; ruff check clean; diff clean; submodules
  clean. Checkpoint pushed.
- 2026-08-08: **Issue #33 (Phase E, wallet isolation + operator drill
  gate) committed** — two leak vectors fixed in `exchange.py`: the
  default dataclass repr of `InMemorySigner` printed the key bytes into
  logs/exceptions/dumps (now a redacted `<InMemorySigner redacted
  (32 bytes)>`), and `signer_from_env` echoed the malformed env value in
  its error message (a secret being parsed is itself key material — the
  message now states the shape without repeating the value);
  `SdkExchangeTransport(None)` fails closed at construction (no
  default-key path), matching the Phase B TypeError for a missing
  signer; `tests/test_hyperliquid_wallet_isolation.py` — the
  secret-handling suite: signer repr redaction; env-parse error
  redaction across malformed values; construction-without-key fail-closed;
  a full scripted drill (lost ack → cloid recovery → cancel → fills +
  positions → clean, same `wire_exchange_script.jsonl` drive as the
  Phase B acceptance drill) with a real 32-byte key, after which every
  durable surface — journal JSONL, the shipped drill script, captured
  DEBUG logs, and the whole scratch tree — is scanned for the key's hex
  form, its bytes repr, and the signer repr, and a wired risk-refusal
  path is scanned too (typed refusal message, empty journal, no wire
  calls). ADR-0007 Phase E extension recorded; acceptance criterion 5
  checked off; the operator drill gate is recorded verbatim in the Phase
  E section and deferred (testnet wallet + faucet + exact steps +
  redacted evidence requirement). 5 new tests. 760 passed, 3 skipped;
  ruff check clean; diff clean; submodules clean. Checkpoint pushed.

## Verification evidence

- Phase A slice (issue #29), after the #29 commit, 2026-08-08:
  `pytest -q` → 600 passed, 3 skipped (symlink creation not permitted);
  `ruff check src tests` → clean; `git diff --check` → clean;
  `git submodule status` → clean. Fixture drill result: scripted frames →
  `DROP` → `RESUME` → re-sync ends with `find_gaps == []` over the merged
  candle series, the book rebuilt from a fresh snapshot, resubscribes
  re-sent on the reconnected socket (8 total), and a typed trades gap
  finding ("cannot be REST re-synced; sequence resumes at tid 8").
- Phase B slice (issue #30), after the #30 commit, 2026-08-08:
  `pytest -q` → 686 passed, 3 skipped (symlink creation not permitted);
  `ruff check src tests` → clean; `git diff --check` → clean;
  `git submodule status` → clean. Drill result
  (`test_acceptance_drill_converges_to_a_clean_report`): lost ack on
  place (PENDING unacknowledged) → cloid channel recovers the mapping
  (MAPPING/WARNING note, oid re-stamped at adoption) → cancel by oid →
  ack-terminal match with a silent surface → fills 0.6 @ 107.4 + 0.4 @
  107.5 and a +1.0 BTC position imported on the first apply pass
  (venue-ahead progress) → final report {matched: 2, pending: 0,
  missing: 0, divergent: 0} with 0 findings and 0 refusals.
- Phase C slice (issue #31), after the #31 commit, 2026-08-08:
  `pytest -q` → 726 passed, 3 skipped (symlink creation not permitted);
  `ruff check src tests` → clean; `git diff --check` → clean;
  `git submodule status` → clean. Gate drill
  (`test_adapter_gate_refuses_before_anything_is_recorded_or_sent`): a
  leverage-violating order through the wired adapter raises
  `HyperliquidRiskRefusalError` (the message carries the typed `[leverage]`
  refusal) with an empty journal and zero wire calls — the refuse path
  consumes nothing; the funding ledger's three-record series proves the
  delta is against the running cumulative, not the last row
  (`test_ledger_records_deltas_since_the_last_cumulative`).
- Phase D slice (issue #32), after the #32 commit, 2026-08-08:
  `pytest -q` → 755 passed, 3 skipped (symlink creation not permitted);
  `ruff check src tests` → clean; `git diff --check` → clean;
  `git submodule status` → clean. Signal drill
  (`test_series_means_the_snapshots_inside_each_bar_window`): a snapshot
  at a bar boundary lands in the next bar, per-bar means align 1:1 with
  the bar grid, and every misalignment path (snapshot outside every
  window, bar without snapshot, non-monotonic series, symbol mismatch,
  mixed intervals, empty book/inputs) raises instead of fabricating a
  value. Baseline drills: `test_book_imbalance_weights_use_train_window_
  signals_only` proves no lookahead (the train signal flips after window
  1 yet the weights hold through window 2), `test_signal_reports_are_
  byte_reproducible` proves two registries under different roots produce
  byte-identical artifacts, and `test_signal_inputs_are_part_of_the_
  report_identity` proves the same setup with different signal inputs
  yields different report ids (and `report_id(..., signals_digest=None)`
  keeps the legacy id).
- Phase E slice (issue #33), after the #33 commit, 2026-08-08:
  `pytest -q` → 760 passed, 3 skipped (symlink creation not permitted);
  `ruff check src tests` → clean; `git diff --check` → clean;
  `git submodule status` → clean. Isolation drill
  (`test_full_drill_leaves_no_key_material_on_durable_surfaces`): a
  full scripted order/cancel/reconcile drill with a real 32-byte key
  leaves no key hex, key-bytes repr, or signer repr in the journal, the
  shipped drill script, captured DEBUG logs, or the entire scratch tree;
  `test_refusal_messages_carry_no_key_material` proves the wired risk
  gate's typed refusal message is clean and consumes nothing;
  `test_in_memory_signer_repr_redacts_key_material` and
  `test_signer_from_env_errors_never_echo_the_value` cover the two
  fixed leak vectors; `test_exchange_transport_construction_without_a_
  key_fails_closed` covers the missing-signer and None paths. Operator
  gate recorded and deferred: exact faucet → env → health/read-only →
  small order/cancel/reconcile drill → redacted-evidence steps are in
  the Phase E section; the final M5 PR stays closed until a human runs
  it.

## Risks and gates

- Testnet wallet/private key and testnet network access are external
  conditions (the sole human gate, Phase E); fixture development must not
  wait for them.
- Testnet order semantics can drift from mainnet (statuses, partial fills,
  funding schedule); fixtures pin observed behavior and reconcile against
  the journal rather than trusting SDK docs.
- The SDK's `WebsocketManager` lifecycle (start/stop/reconnect) is
  sync/callback-oriented; isolate it from async surfaces and test
  reconnect under scripted disconnects.
- `Info` REST rate limits on testnet; keep poll intervals configurable and
  bounded.
- Never render private-key material into errors, journal lines, reports,
  fixtures, or CI logs (wallet-isolation tests enforce this).
