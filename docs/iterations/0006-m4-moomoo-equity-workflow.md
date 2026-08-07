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

- [ ] Local OpenD health and capability status are observable without logging
      secrets.
- [ ] Historical, daily, and intraday Moomoo-shaped data normalize into the
      M3 lake with manifests and quality gates.
- [ ] Momentum, mean-reversion, and risk-parity baselines each produce a
      reproducible walk-forward, cost-aware report from a pinned dataset.
- [ ] A Moomoo simulated-order reconciliation identifies every matched,
      pending, missing, or divergent order/fill without silently accepting
      drift.
- [ ] No real-money order path is implemented or enabled.

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

### Phase E — operator validation and milestone gate

Only after all fixture tests pass, request one human-provided local OpenD plus
Moomoo **simulated-account** validation. Run health, read-only quote/history,
then a deliberately small simulated-order reconciliation drill. Record
redacted evidence. This is the sole external-state gate for M4; never request
or log a password, secret, or real-trading confirmation.

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
- ADR: walk-forward/report schema and cost-model ownership. — pending Phase C.
- ADR: broker-paper reconciliation identity and tolerance policy. — pending Phase D.

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

## Verification evidence

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

## Risks and gates

- OpenD availability, market-data entitlements, and simulated-account access
  are external conditions; fixture development must not wait for them.
- SDK transport is synchronous/callback-oriented; isolate it from async API
  surfaces and test lifecycle/reconnect behavior.
- Moomoo symbols, timezone/session rules, corporate actions, and fee details
  must remain provider metadata and be represented in manifests/reports.
