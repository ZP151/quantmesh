# Iteration 0006 — M4 Moomoo Equity Workflow

- Status: active
- Started: 2026-08-07
- Completed:
- Owner: solo delivery fast lane
- GitHub issue: to be split from this plan before implementation
- Pull request: one final M4 integration PR from `feat/m4-moomoo-equity-workflow`
- Roadmap milestone: M4

## Outcome

Deliver a local US/HK equity workflow that ingests Moomoo-compatible market
data, produces reproducible cost-aware research reports, and reconciles
Moomoo simulated orders against QuantMesh's deterministic paper-account
semantics. Live trading is not part of this iteration.

## Scope and boundaries

- In scope: OpenD connectivity diagnostics, fixture-first Moomoo adapters,
  historical/daily/intraday normalization into the M3 lake, three baseline
  strategies, walk-forward reports, and simulated-order reconciliation.
- Out of scope: real-money orders, account unlock passwords, credentials in
  source control, AI order authority, mobile/frontend work, and Hyperliquid
  or prediction-market execution.
- Reuse: consume the pinned `py-moomoo-api` SDK through a thin adapter;
  borrow Qlib/VectorBT through optional research adapters rather than copying
  their engines. Do not copy GPL/AGPL reference-project code.

## Acceptance criteria

- [x] Local OpenD health and capability status are observable without logging
      secrets. — issue #25 (`quantmesh-moomoo probe`, redacted, exit 3 gated).
- [x] Historical, daily, and intraday Moomoo-shaped data normalize into the
      M3 lake with manifests and quality gates. — issue #26 (fixture path).
- [x] Momentum, mean-reversion, and risk-parity baselines each produce a
      reproducible walk-forward, cost-aware report from a pinned dataset.
      — issue #27.
- [x] A Moomoo simulated-order reconciliation identifies every matched,
      pending, missing, or divergent order/fill without silently accepting
      drift. — issue #28 (fixture drills, 0-blocking-findings convergence).
- [x] No real-money order path is implemented or enabled. — pinned
      `TrdEnv.SIMULATE`; fixture-only CLI surface; REAL refused before the wire.

## Implementation plan

### Phase A — contract and diagnostics

Create issue(s) for a fixture-first `MoomooOpenDClient` boundary, settings for
host/port/timeouts, capability reporting, and typed unavailable/auth-required
errors. Unit tests must run without OpenD. Probe a real local OpenD instance
only through an explicit operator command; never persist its response if it
contains account data.

### Phase B — market-data adapter

Map SDK historical-kline, quote, and ticker responses to canonical M3 `Bar`
and `TradeEvent` models. Ingest fixture data through `Lake`, manifests, and
quality checks before any live OpenD read. Add integration tests using fixtures
for US and HK symbols and daily/intraday intervals.

### Phase C — research baselines

Add a strategy-report contract with pinned dataset reference, universe,
walk-forward windows, fee/spread/slippage assumptions, metrics, and generated
artifacts. Implement momentum, mean-reversion, and risk-parity as transparent
baselines. VectorBT/Qlib adapters are optional accelerators; QuantMesh owns
the report schema and reproducibility test.

### Phase D — simulated execution reconciliation

Add a simulated-only Moomoo order/status/fill adapter and a reconciliation
service that maps broker identifiers to QuantMesh client/order IDs. Reconcile
quantities, prices, fees, status transitions, timestamps, and positions; fail
closed on missing or ambiguous mappings. Fixture replay is mandatory.

### Phase E — operator validation and milestone gate (PENDING HUMAN GATE)

Only after all fixture tests pass, request one human-provided local OpenD plus
Moomoo **simulated-account** validation. Run health, read-only quote/history,
then a deliberately small simulated-order reconciliation drill. Record
redacted evidence. This is the sole external-state gate for M4; never request
or log a password, secret, or real-trading confirmation.

**Gate status 2026-08-08 — deferred by the autonomous lane.** All safe work
is complete: issues #25-#28 are committed on `feat/m4-moomoo-equity-workflow`
(checkpoint `5fbeb6c`, pushed), the fixture suite is green (525 passed), and
the live surface is deliberately locked — `probe` is read-only, writes
nothing, reads no credentials; `paper-order`/`reconcile` refuse any
invocation without `--fixture` (exit 3). No code, credential material, or
safe task is waiting on this gate.

**Exact operator drill (human, local OpenD running + Moomoo simulated
account):**

1. `quantmesh-moomoo probe` — expect quote=True history_kline=True
   order=True order_query=True, auth_required=False. A locked session is
   *reported* in the capability line, never unlocked by QuantMesh.
2. Read-only market-data check against the simulated account (explicit
   operator action only; the live path otherwise stays fixture-first):
   one kline and one quote request, verifying the ADR-0004 payload
   contract and UTC conversion against a real OpenD.
3. Simulated-order drill: place one small simulated order via the operator
   surface, reconcile it (`--apply`), confirm the mapping, status
   transitions, and fill adoption match the fixture-drill semantics, then
   cancel it. Expect the same exit-code contract (0 clean / 1 blocking
   findings).
4. Record redacted evidence in the Verification evidence section: command,
   exit code, counts line, and findings summary. No account data, no
   secrets, no ids beyond the drill order's own broker id.

Until a human runs the drill, the final M4 PR stays closed: the delivery
protocol requires operator-validation evidence before opening it. The
branch remains the live checkpoint; CI runs on each push.

## Delivery protocol

Use `feat/m4-moomoo-equity-workflow` as the solo integration branch. Before
coding, split Phases A-D into GitHub issues with acceptance criteria and
blocking edges. Keep one tested, reviewed, issue-linked commit and iteration
checkpoint per issue; push each checkpoint. Do not open per-slice PRs. Open
one final M4 PR only after the acceptance criteria and operator-validation
evidence are complete; CI plus the standing merge authority controls merge.

## Durable decisions to record when reached

- ADR: OpenD adapter lifecycle, error classification, and credential boundary.
  — recorded as ADR-0004 (2026-08-08), extended 2026-08-08 with the
  market-data payload contract (issue #26 Phase B): pandas stops at the
  transport; kline/ticker/quote payload contracts; venue-local wall-clock
  times converted to UTC via market-prefix timezone metadata (US
  America/New_York, HK Asia/Hong_Kong, CN Asia/Shanghai — DST-aware via
  zoneinfo/tzdata); raw ``"None"`` autype default; `MoomooOpenDProvider`
  is explicit-construction-only (LIVE mode, registry refuses it); lake
  persists bars, trades/quotes are canonical models only.
- ADR: walk-forward/report schema and cost-model ownership.
  — recorded as ADR-0005 (2026-08-08, issue #27 Phase C): a `StrategyReport`
  is identified by its pinned setup only — dataset, manifest revision, code
  commit, strategy, interval, universe, window spec, cost model — hashed to
  a deterministic 16-hex `report_id` (setup hashed with sorted universe, so
  member order never changes identity). Walk-forward windows are count-based
  over the observed bar grid (`train_bars >= 2`, `step_bars >= test_bars`,
  so evaluation segments never overlap and the equity curve concatenates
  without double counting); calendar-free, so a pinned dataset pins the
  windows. One QuantMesh-owned `CostModel` (fee + half-spread + slippage
  bps / 10_000) is applied uniformly to every baseline, charged once per
  window on one-way turnover. Metrics schema is fixed with documented
  units (`sharpe`/`annualized_return` are `None` when undefined, never
  fabricated). Baselines are pure, no-RNG functions (momentum top half,
  mean-reversion bottom half, risk-parity inverse vol with zero-vol
  excluded; ties break on symbol) and fail closed on undefined inputs.
  Artifacts are deterministic functions of the ID at
  `reports_root/<id>/{report.json,equity_curve.csv,trades.csv}`;
  `report.json` excludes `created_at` so regeneration is byte-identical.
  `ReportRegistry` persists JSONL with the experiment-registry discipline:
  atomic appends, fail-closed reads with line attribution and duplicate-ID
  detection, every recorded pin validated through the lake's manifest gate
  (a report that exists is one whose data still exists at the pinned
  revision). VectorBT/Qlib remain optional future accelerators; the
  baselines stay dependency-free so pinning stays honest.
- ADR: broker-paper reconciliation identity and tolerance policy.
  — recorded as ADR-0006 (2026-08-08, issue #28 Phase D): the journal is
  the single source of truth for the broker_order_id↔order_id mapping;
  the remark channel recovers lost acknowledgements and ambiguous
  mappings fail closed; an explicit `BROKER_STATUS_TO_DOMAIN` table maps
  broker statuses (TIMEOUT/DISABLED/DELETED/FILL_CANCELLED unmappable →
  status findings); `ReconcileTolerance` is declared per run with exact
  (0) simulator defaults; fills are identified by the broker deal_id
  stamped as `broker_fill_id` and unhealthy deals are revoked-fill
  findings; adoption applies only to matched/pending clean pairs through
  the `OrderStateMachine` (divergence/missing/ambiguous refused); the
  execution adapter is explicit-construction-only with `TrdEnv.SIMULATE`
  pinned and REAL refused before the wire.

## Work log

- 2026-08-08: Issue #25 (Phase A, OpenD contract and diagnostics)
  implemented with TDD on `feat/m4-moomoo-equity-workflow`:
  - `quantmesh.moomoo` package: `MoomooOpenDClient` fixture-first boundary
    with injected `OpenDTransport`; typed errors
    (`OpenDUnavailableError` / `OpenDAuthRequiredError` /
    `OpenDSdkMissingError` / `OpenDProtocolError` under `OpenDError`);
    `OpenDCapabilities` probe report with the locked-session rule
    (auth_required forces order/order_query False); lazy-SDK `SdkTransport`
    whose error classifier is keyword-based pending Phase E validation.
  - Settings: `moomoo_opend_host/port/connect_timeout_s/request_timeout_s`
    (env `QUANTMESH_MOOMOO_*`, validated: port 1-65535, timeouts > 0).
  - `quantmesh-moomoo probe` operator command: the only path to a real
    OpenD; redacted stdout report, writes nothing, reads no credentials,
    typed exit codes (0 ok / 1 unavailable / 2 auth-required / 3 sdk
    missing).
  - 26 tests (24 initial + 2 classifier tests from review); full suite 321
    passed, 3 skipped. Review fixes: auth-on-order-context is reported
    state, not a raised probe failure; `_classify` unit-tested without the
    SDK; CLI client construction decoupled for injection; malformed payload
    fail-closed with extra vendor keys tolerated.
  - ADR-0004 recorded.
- 2026-08-08: Issue #26 (Phase B, market-data adapter) implemented with
  TDD on `feat/m4-moomoo-equity-workflow`:
  - Wire-shape contract derived from the vendored `py-moomoo-api` source
    (not docs): `request_history_kline` always returns a 3-tuple
    `(ret, table, page_req_key)` on every path; `get_stock_quote` /
    `get_rt_ticker` return 2-tuples; venue-local wall-clock time strings
    (US Eastern, HK/CN Beijing) with no zone marker; `AuType` keys
    `"None"/"qfq"/"hfq"`; error strings carried in the data slot when
    `ret != 0`.
  - `SdkTransport` extended with `history_kline` / `rt_ticker` /
    `stock_quote`, each returning pandas-free dict payloads (pandas stops
    at the transport, ADR-0004 extension decisions 8-13) with per-request
    context open/close and typed classification of `ret != 0` failures.
  - `MoomooDataAdapter`: pure payload→model mapping, fail closed
    (missing/mistyped keys, unknown market/autype/direction, unparseable
    times, code-symbol mismatch, multi-row quotes), venue-local times
    converted to aware UTC via market-prefix IANA zones (zoneinfo +
    tzdata, declared core dependency for Windows).
  - `MoomooOpenDProvider`: explicit-construction-only LIVE provider
    (registry refuses, tested); venue-local date bounds with UTC range
    filtering; interval/autype echo cross-checks; order books out of
    scope (Phase D); fixture payloads through the full M3 lake path
    (write → ManifestWriter → freshness gate → read back → clean
    coverage) for US/HK daily and 5m intraday.
  - 92 Moomoo tests; full suite 389 passed, 3 skipped; ruff clean;
    `git diff --check` clean; submodules pinned. Review fixes: the lake
    round trip is asserted on the canonical field surface (metadata is
    request-side identity, ADR-0003 boundary, pinned by test) instead of
    full Bar equality; `_assert_same_series` currency comparison fixed
    to compare the expected set, not the ternary; 12 long lines reflowed;
    provider fail-closed on a non-mapping transport payload (no untyped
    AttributeError leak).
  - ADR-0004 extended with the market-data payload contract (decisions
    8-13) and its consequences.
- 2026-08-08: Issue #28 (Phase D, simulated execution reconciliation)
  implemented with TDD on `feat/m4-moomoo-equity-workflow`:
  - Domain: `OrderEvent`/`OrderEventType` with `reason` for rejections,
    `Fill(broker_fill_id, fee)` stamped from broker deals,
    `OrderStateMachine` transitions incl. ACCEPTED and
    CANCELED/REJECTED with the broker message; `Order.fills` re-derived
    from FILL events.
  - `OrderJournal` (ADR-0006 decision 1): JSONL journal under
    `settings.orders_dir`; single source of truth for the
    broker_order_id↔order_id mapping; atomic temp+replace appends;
    duplicate ids refused; corrupt lines fail closed with line
    attribution; in-place snapshot replacement preserves history; fill
    round-trip persisted.
  - `SimulatedFixtureTransport`: deterministic JSONL phase script
    (`{"now", "orders", "deals", "positions", "lost_acks"}`) — the state
    at time *t* is the latest phase with `now <= t`, pure declaration,
    never mutated; `place` assigns B-1, B-2… deterministically and
    withholds the acknowledgement (`OpenDUnavailableError`) for ids in
    `lost_acks` — the disconnect gap the remark channel recovers.
  - Wire models `BrokerOrder`/`BrokerDeal`/`BrokerPosition` with
    venue-local wall-clock→UTC conversion by market prefix (ADR-0004
    zones); unknown markets, unparseable times, and unknown sides fail
    closed at the wire boundary (model validators, not lazy properties).
  - `MoomooExecutionAdapter` (explicit-construction-only, ADR-0006
    decision 6): stamps the broker order id, derives LIMIT/MARKET order
    type, enforces the 64-byte remark limit, requires market metadata
    fail-closed; `SdkTradeTransport` pins `TrdEnv.SIMULATE` and refuses a
    non-simulated environment before anything reaches the wire; SDK
    import guarded in tests via a monkeypatched `__import__`.
  - Reconciliation service: `ReconcileTolerance` (declared per run,
    deterministic simulator defaults exact), `run_reconciliation` pairs
    by broker_order_id or the remark channel (recovered mappings are
    WARNING and non-blocking), explicit `BROKER_STATUS_TO_DOMAIN` table
    with unmappable statuses reported as findings, `_is_progress`
    broker-ahead classification (broker terminal vs live journal is
    pending progress), position reconciliation with tolerance flags;
    `apply_reconciliation` adopts only matched/pending clean pairs
    through the state machine — ACCEPTED re-stamp, fills→FILLED, CANCELED,
    REJECTED with reason — and refuses divergence/missing/ambiguous/
    fee-less pairs and FILLED without complete fills; the second run on a
    matched pair changes nothing.
  - CLI: `quantmesh-moomoo paper-order` (--fixture, --symbol, --market,
    --side, --qty, --price, --currency, --client-order-id) and
    `reconcile` (report-only by default, --apply explicit, --at replay
    instant defaulting to the script's end, tolerance flags
    --qty-bps/--price-bps/--fee-abs/--time-skew-s/--position-qty-bps);
    both commands are Phase E-gated (exit 3) without `--fixture`; a
    lost-ack paper-order records the unacknowledged order with a warning
    (exit 0); reconcile exits 1 on blocking findings.
  - 87 new tests (13 journal + 22 execution + 37 reconciliation + 15
    CLI); full suite 525 passed, 3 skipped; ruff clean; `git diff --check`
    clean; submodules pinned. Review: adversarial pass — the missing
    `Severity.ERROR` in `_compare_positions` (TypeError) fixed; the
    remark-recovery WARNING no longer classifies a recovered pair as
    divergent (non-blocking by kind); ACCEPTED became adoptable so a
    broker-ahead pair converges; the smoke drill converges lost-ack →
    remark recovery → adoption → matched with 0 findings.
  - ADR-0006 recorded (6 decisions).

Per slice: `pytest -q`, `ruff check src tests`, `git diff --check`,
`git submodule status`.

Issue #25 (Phase A, committed on `feat/m4-moomoo-equity-workflow`):

```text
.\.venv\Scripts\python.exe -m pytest -q: 321 passed, 3 skipped (symlink creation not permitted), 1 warning
.\.venv\Scripts\python.exe -m ruff check src tests: All checks passed
git diff --check: passed
git submodule status: clean
```

Review gate: self-review adversarial pass — auth-on-order-context is
reportable state (capabilities) rather than a raised probe failure,
`_classify` covered by unit tests without the SDK, CLI client
construction decoupled for injection, malformed probe payloads fail
closed while extra vendor keys are tolerated. The live SDK path stays
gated on Phase E operator validation.

Issue #26 (Phase B, committed on `feat/m4-moomoo-equity-workflow`):

```text
.\.venv\Scripts\python.exe -m pytest -q: 389 passed, 3 skipped (symlink creation not permitted), 1 warning
.\.venv\Scripts\python.exe -m ruff check src tests: All checks passed
git diff --check: passed
git submodule status: clean
```

Review gate: self-review adversarial pass — wire arities verified
against the vendored SDK source (3-tuple kline on every path, 2-tuple
quote/ticker; `dict_data` appears only in the unused `get_cur_kline`
surface), lake round trip pinned to the ADR-0003 field surface,
provider fail-closed on non-mapping transport payloads, SdkTransport
error-string classification path exercised by unit tests without the
SDK. Likely Phase E adjustment (ADR-0004): time-format drift between
SDK versions.

- 2026-08-08: Issue #27 (Phase C, research baselines) implemented with
  TDD on `feat/m4-moomoo-equity-workflow`:
  - `quantmesh.research`: `StrategyReport` (pinned setup + results,
    id-consistency validator, tz-aware `created_at` normalized to UTC,
    finite metrics), `WalkForwardSpec` (count-based windows, never-overlap
    validator), `UniverseMember`, `CostModel` (bps components, finite at
    the boundary), `WindowResult`; `report_id` (16-hex setup hash over
    canonical sorted-universe JSON, "baseline-report\0" domain prefix);
    `ReportRegistry` (JSONL, atomic mkstemp+os.replace appends, duplicate
    IDs refused, fail-closed reads with line attribution, `resolve_pin`
    through the lake manifest gate refusing moved manifests); `Baseline`
    module: `momentum_weights` / `mean_reversion_weights` /
    `risk_parity_weights` (pure, no RNG, ties break on symbol, zero-vol
    excluded, all-zero fails closed), `run_walk_forward` (aligned-grid
    fail-closed, no lookahead, cost charged once per window on one-way
    turnover, equity curve concatenates disjoint test segments),
    `run_baseline_report` (universe validation incl. cross-venue symbol
    collision fail-closed, pin-before-compute, byte-stable artifacts,
    registry record). Settings: `reports_dir` default
    `~/.quantmesh/reports`. ADR-0005 recorded (9 decisions).
  - Verification: full suite `443 passed, 3 skipped` (54 new Phase C
    tests), `ruff check` clean, `git diff --check` passed, submodules
    clean. Review: adversarial pass — window boundary math cross-checked
    against `test_starts` (60 bars → [30, 40, 50]; 59 → [30, 40];
    35 fails closed), lookahead audit (weights from bars strictly before
    each test start; vol from `[train_start+1, test_start)`), trades
    journal computed before the weight-state update (n_trades [2, 0, 0]
    across windows), reproducibility test as the acceptance criterion
    (two fresh roots → identical ID/metrics/windows and byte-identical
    artifacts; `created_at` excluded from `report.json`), and the new
    cross-venue symbol guard found in review (the backtester keys bars by
    symbol, so a symbol on two venues would silently overwrite — now
    refused with a regression test). Next: #28 (Phase D, simulated
    execution reconciliation) — implemented and verified below; next:
    Phase E gate.

Issue #28 (Phase D, committed on `feat/m4-moomoo-equity-workflow`):

```text
.\.venv\Scripts\python.exe -m pytest -q: 525 passed, 3 skipped (symlink creation not permitted), 1 warning
.\.venv\Scripts\python.exe -m ruff check src tests: All checks passed
git diff --check: passed
git submodule status: clean
```

Review gate: self-review adversarial pass — the smoke drill is the
acceptance criterion: a lost acknowledgement places an order the
journal records unacknowledged; the remark channel recovers the
mapping (WARNING, non-blocking); `--apply` adopts ACCEPTED and
re-stamps the broker id; the fill (D-1 @ fee 0.5) adopts to FILLED;
the final run reports 1 matched, 0 findings. Classification semantics:
recovered mappings are non-blocking, broker-ahead is pending progress,
and only terminal agreement on both sides is "matched". The live
simulated account stays behind the Phase E gate; `paper-order` and
`reconcile` refuse any invocation without `--fixture` (exit 3).

## Risks and gates

- OpenD availability, market-data entitlements, and simulated-account access
  are external conditions; fixture development must not wait for them.
- SDK transport is synchronous/callback-oriented; isolate it from async API
  surfaces and test lifecycle/reconnect behavior.
- Moomoo symbols, timezone/session rules, corporate actions, and fee details
  must remain provider metadata and be represented in manifests/reports.
