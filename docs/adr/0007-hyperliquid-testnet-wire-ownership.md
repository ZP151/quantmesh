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

- Phase B (#30), **recorded 2026-08-08**: testnet execution with the journal
  as the single source of truth, the M4 discipline extended to a venue with
  no order-status endpoint.
  - The `Exchange` boundary (`SdkExchangeTransport`) is explicit-
    construction-only with an injected in-memory signer: key material lives
    in memory only — never persisted, logged, or reported — with the env var
    as the operator path (`signer_from_env`, fail-closed on missing or
    malformed values) and construction-time refusal of any non-testnet base
    URL, mirroring decision 2.
  - Identity runs through the **cloid channel**, the venue's echo of the
    journal's `client_order_id` (exactly 32 lowercase hex → `"0x"` + 32 hex),
    replacing Moomoo's remark channel: ids are journal-first (recorded before
    the wire; an id already mapped refuses submission), a lost ack leaves the
    order PENDING unacknowledged, and reconciliation recovers the mapping
    from the venue's cloid echo and re-stamps the oid at adoption
    (MAPPING/WARNING note, non-blocking). Both channels mapping to different
    orders is ambiguous → divergent. Place-time "filled" acks only advance to
    ACCEPTED — fills enter through reconciliation, stamped with the venue's
    own fill identity (`tid`/`hash`) and fee.
  - Order status is **derived** because the venue has no order-status
    endpoint: "open" while the venue lists the order (its meaning is
    "remaining size", compatible with journal partial fills — fills are
    reported separately), "inactive" for fills-only rows interpreted with
    journal context (fills totalling the order quantity → FILLED; a journal
    already CANCELED/REJECTED → that status; otherwise the venue's silence
    means the order is no longer live → CANCELED). The explicit
    `HYPERLIQUID_STATUS_TO_DOMAIN` table declares the full venue vocabulary
    (surface + ack); anything outside it fails closed as a status finding.
    Ack-terminal journal orders the venue no longer lists are classified
    matched — a confirmed ack plus a silent surface is venue truth, not a
    lost order — with a MAPPING/WARNING note only when the order never
    received a venue order id.
  - Reconciliation keeps the M4 discipline on the shared contract types
    (`quantmesh.execution.reconciliation`): matched/pending clean pairs adopt
    broker-confirmed progress only (fills with venue identity + fee, derived
    terminal events, the recovered oid); divergent and missing pairs are
    refused, never adopted; fee-less fills are refused; the broker may be
    ahead (pending, adoptable) but never behind (drift); account positions
    compare as signed sizes.
  - Market orders cannot carry reduce-only (the pinned SDK's `market_open`
    hard-codes it False): the adapter refuses rather than silently re-typing
    the order; position closing goes through reduce-only LIMIT orders
    (Phase C's closing path).
- Phase C (#31), **recorded 2026-08-08**: a pre-submission risk gate sits
  between the adapter and the wire, and funding is accounted as a fee-like
  journal entry.
  - The gate is pure and deterministic (`evaluate_order` over
    `RiskLimits` + `RiskContext`) — fixture-testable without the SDK or the
    network — and it fails closed: a check whose inputs are incomplete is a
    typed `MISSING_DATA` refusal, never a guess. The four checks:
    - **Leverage bound** — the resulting signed position (venue position +
      the new order) at the entry estimate (limit price, else the l2Book
      mid) divided by account equity must stay within `max_leverage`
      (default 3.0x); a full close has nothing left to lever and skips the
      check; missing equity or entry fails closed.
    - **Liquidation-distance floor** — the resulting position's estimated
      distance to its liquidation price must stay above
      `min_liquidation_distance_bps` (default 500). The estimate scales the
      venue's own reported `liquidationPx` proportionally to the
      size-weighted entry of the resulting position (a direction flip
      rebases to the new entry), corrects the entry for cumulative funding
      (paid funding moves the effective entry toward the mark — a
      conservative shrink), and measures against the l2Book mid; a mark
      already at or beyond the estimate is a refusal. Orders that strictly
      decrease risk (reductions, full closes) skip the estimate; anything
      the estimate needs (position, entry, liquidation price, mark,
      funding) that is missing fails closed.
    - **Reduce-only posture** — with `reduce_only` limits configured, only
      reduce-only orders pass.
    - **Stale-data window** — the latest book timestamp must be within
      `stale_data_window_s` (default 30) of the context clock; a missing or
      future timestamp is a refusal — no order trades on stale data.
  - The adapter wires the gate paired: `risk_limits` and `risk_context`
    (a `RiskContextProvider` that assembles position, book, funding,
    equity, and clock at order time) are configured together or not at all
    — a half-configured gate is a construction error. The gate runs BEFORE
    the journal-first recording, and a refusal raises
    `HyperliquidRiskRefusalError` carrying the typed refusals: nothing is
    recorded, nothing is sent.
  - Funding is a fee-like journal entry: `FundingLedger` records the
    signed delta of each position's venue-reported cumulative funding
    (positive = the position paid) into `funding.jsonl` under the orders
    directory — append-only with atomic temp-file+replace writes and
    fail-closed reads with line attribution, per-coin series (each delta
    is against that coin's running cumulative, never the last row), the
    first record anchors, zero deltas are no-ops.
- Phase D (#32), **recorded 2026-08-08**: order-book imbalance and
  volatility baselines on the M5 report stack.
  - The imbalance signal is pure and depth-weighted over the full book:
    `book_imbalance = (Σbid − Σask)/(Σbid + Σask)`. A book with zero depth
    on both sides is an error, never a fabricated value; one-sided books
    are well-defined extremes (±1.0).
  - The canonical per-bar series `imbalance_by_bar` buckets snapshots into
    `[timestamp, timestamp + interval)` bar windows and returns the per-bar
    means, aligned 1:1 with the bar grid. Alignment fails closed: a
    snapshot outside every window, a bar without a snapshot, a
    non-monotonic snapshot series, a symbol mismatch, or mixed bar
    intervals all raise — a misaligned signal would silently shift the
    hypothesis, so it cannot exist silently.
  - Signal-driven baseline strategies (`book_imbalance`, and `low_
    volatility` over realized train volatility) consume caller-supplied
    per-bar signal series validated against the grid (universe equality +
    per-symbol length). Weights are computed from the train slice of each
    window only — no lookahead by construction, proven by test.
  - The signal inputs are part of the report's pinned setup: a digest
    over the canonical sorted signal JSON folds into `report_id` and is
    recorded on the report as `signals_digest`, so the identity covers
    the signal series and the recorded setup and the id cannot disagree;
    a run without signals keeps the pre-Phase-D identity. The strategy
    vocabulary is extended (`low_volatility`, `book_imbalance`) rather
    than opened up, so an unknown strategy stays a validation error.
- Phase E (#33), **recorded 2026-08-08**: key material is confined to
  memory by construction and by test.
  - Private keys enter only through an injected `InMemorySigner` or the
    `signer_from_env` env-var path; nothing ever persists, logs, or
    reports them. The signer's repr is redacted (`<InMemorySigner
    redacted (32 bytes)>` — the default dataclass repr would print the
    bytes into logs, exceptions, and process dumps), and env-parse
    errors describe the shape without echoing the value (a malformed
    secret is itself key material).
  - Construction without a key fails closed: the transport's signer is a
    required positional argument with no default and `None` is refused —
    there is no default-key path.
  - The wallet-isolation suite proves the invariant durably: a full
    scripted order/cancel/reconcile drill with a real 32-byte key leaves
    no key hex, key-bytes repr, or signer repr in the journal JSONL, the
    shipped drill script, captured DEBUG logs, or the entire scratch
    tree, and the wired risk-gate refusal path is clean and consumes
    nothing.
  - The operator drill (faucet → env → health/read-only checks → small
    order/cancel/reconcile drill → redacted evidence, exact steps in
    iteration 0007) is the sole external-state gate for M5; it is
    recorded and deferred until a human runs it, and no real-money,
    mainnet, or unredacted-key path exists anywhere.
