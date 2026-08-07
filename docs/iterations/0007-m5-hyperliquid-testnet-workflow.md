# Iteration 0007 — M5 Hyperliquid testnet workflow

- Status: active
- Started: 2026-08-08
- Completed:
- Owner: Claude (solo delivery lane)
- GitHub issue: #29-#33 (Phases A-E)
- Pull request: pending (opened after acceptance criteria and operator evidence)
- Roadmap milestone: M5 (`LATER` → `ACTIVE`)

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
- [ ] Testnet execution survives disconnect/reconnect without duplicate
      orders: the journal is the single source of truth for
      client_order_id↔oid; after a reconnect the order state is re-derived
      from the broker's orders list, never re-submitted; a client id already
      mapped refuses submission (fixture drill).
- [ ] Risk limits prevent excess leverage and stale-data execution: the
      pre-submission guard refuses orders that breach the leverage bound,
      liquidation-distance floor, reduce-only posture, or the stale-data
      window; funding is accounted in the journal (fixture tests).
- [ ] Order-book imbalance and volatility baselines each produce a
      reproducible walk-forward, cost-aware report from a pinned dataset
      (M5 report stack on the M4 `run_walk_forward`/`ReportRegistry`).
- [ ] Wallet isolation: private-key material is accepted only through an
      injected in-memory signer or env var; never persisted, logged, or
      reported; adapter construction without a key fails closed; the
      Exchange adapter pins testnet and refuses any non-testnet base URL
      before the wire.
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
- ADR-0007 extension (issue #30 Phase B): the testnet Exchange adapter is
  explicit-construction-only with an injected in-memory signer; testnet
  pinned and mainnet refused before the wire; the journal is the single
  source of truth for client_order_id↔oid with re-derive-on-reconnect
  (never re-submit); per-venue status table with unmappable statuses as
  findings.
- ADR-0007 extension (issue #31 Phase C): risk checks run before the wire
  (leverage, liquidation distance, reduce-only, stale-data window);
  funding is a fee-like journal entry.
- ADR-0007 extension (issue #33 Phase E): private keys enter only via
  injected signer or env var, in memory, never persisted or logged;
  wallet-isolation tests are part of the secret-handling suite.

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

## Verification evidence

- Phase A slice (issue #29), after the #29 commit, 2026-08-08:
  `pytest -q` → 600 passed, 3 skipped (symlink creation not permitted);
  `ruff check src tests` → clean; `git diff --check` → clean;
  `git submodule status` → clean. Fixture drill result: scripted frames →
  `DROP` → `RESUME` → re-sync ends with `find_gaps == []` over the merged
  candle series, the book rebuilt from a fresh snapshot, resubscribes
  re-sent on the reconnected socket (8 total), and a typed trades gap
  finding ("cannot be REST re-synced; sequence resumes at tid 8").

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
