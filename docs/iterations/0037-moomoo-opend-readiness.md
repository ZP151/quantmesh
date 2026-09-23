# Iteration 0037 — Private Moomoo/OpenD AAPL/NVDA readiness

- Status: ACTIVE, 2026-09-23. The local readiness repair is implemented,
  reviewed and verified. Live polling follow-up and real equity acceptance
  remain open; 8 GB observation stays in later operational acceptance.
- Linked issue: [#156 — Private Moomoo/OpenD AAPL/NVDA readiness](https://github.com/ZP151/quantmesh/issues/156).
- Plan: [Moomoo readiness probe plan](../superpowers/plans/2026-09-23-moomoo-readiness-probe.md).
- Operator steps: [private readiness runbook](../runbooks/moomoo-readiness.md).
- Later operational acceptance: [iteration 0036](0036-staging-recovery.md).
  The user explicitly deferred observation/drills so development can proceed.
  CI remains paused; no remote integration or deployment occurs in this slice.

## User action and measurable outcome

An operator runs `quantmesh-moomoo readiness --json` and receives a redacted,
machine-readable report for the private OpenD endpoint and `US.AAPL`/
`US.NVDA`. The command checks the TCP route before SDK use, probes only quote
and daily history, records each symbol independently and exits non-zero for a
missing route, provider, entitlement or malformed payload. It never checks or
unlocks an order session.

The code slice is complete when the report boundary and CLI tests pass, Ruff
and diff checks are clean, and the report distinguishes `route_unavailable`,
`sdk_missing`, `auth_required`, `unavailable`, `protocol_error`, `timeout`,
`partial` and `ready` without persisting credentials or quote rows. `ready`
means readable, valid payloads, not freshness, licensed real-time entitlement,
market-session progression or trading approval.

## Implementation checkpoint — 2026-09-23

Commits `50b2ddb` through `3ff91d2` add `ReadinessReport`,
`SymbolReadiness` and `run_readiness(...)`. The boundary validates quote and
history payloads through the existing Moomoo adapter, requires at least one
daily history row, rejects cross-market responses and preserves per-symbol
failures. A later review found that the original use of the general `probe()`
indirectly opened a trade context. The earlier no-order-context claim was
incorrect; the repair below replaces that call chain.

The follow-up CLI changes add the private TCP preflight plus stable text/JSON
output. The latest focused suite passes `96 passed, 1 skipped` including the
existing live-smoke checks; Ruff and `git diff --check` pass. A full 3,601-test
run was attempted but interrupted before the latest fixes; its slowdown was
not diagnosed at that point, so it is not claimed as green. CI is intentionally paused,
so no remote check, push, merge or deploy is claimed.

## Current operator evidence and blocker

The new AWS host is healthy for the accepted Hyperliquid BTC/ETH/SOL path, but
the read-only route from AWS `100.86.41.64` to the Windows OpenD host
`100.91.234.68:11111` currently returns `CLOSED`. This is recorded as
`route_unavailable`; no public OpenD port is opened and no quote is treated as
real. Local Windows OpenD capability and the existing Basic-data rejection for
AAPL/NVDA remain separate evidence. This AWS route observation is historical,
not repeated by the latest local CLI run. On this resume the Windows host has
no listener on `127.0.0.1:11111`; the real local command returns
`route_unavailable`, `order_checked=false`, exit 1.

The original Basic-data rejection cannot establish a paid-rights blocker:
`get_stock_quote` was called without the SDK-required QUOTE subscription.
Official [quote](https://openapi.moomoo.com/moomoo-api-doc/en/quote/get-stock-quote.html)
and [subscription](https://openapi.moomoo.com/moomoo-api-doc/en/quote/sub.html)
documentation confirms the required registration. The repaired adapter uses
`subscribe_push=False` and does not purchase or change account permissions.
Actual rights remain unknown until a real subscription succeeds.

## Repair roles and review — 2026-09-23

- **Planner/Product:** complete the local preflight operator loop for #156.
  Do not couple it to capacity observation, add a provider UI, or claim AWS
  equities work before the private route and real witness exist.
- **Quant researcher:** readability is not freshness or entitlement certification.
  Preserve symbol, requested interval and raw adjustment identity; no stale
  payload may be presented as a live-session witness by this report.
- **Implementer:** dedicated `probe_market_data()` creates only a quote
  context. Quote reads subscribe to QUOTE first, reject malformed status/tuple
  envelopes and always close the context. The existing general `probe()` is
  preserved for its separate operator command. Typed errors survive aggregate
  classification; only allowlisted messages reach reports.
- **Implementer:** the CLI uses the existing bounded JSON subprocess runner,
  with exact-checkout worker imports and only non-secret endpoint settings.
  Default `--timeout-seconds 30` is the whole SDK worker deadline (maximum
  300 seconds), excluding TCP preflight and bounded process cleanup. Worker
  output is discarded; temporary request/report metadata is removed. Quote
  rows/account data are never written to those files.
- **Reviewer, round 1:** identified indirect trade context, ineffective SDK
  timeout, lost failure types and raw vendor-text leaks. All fixed.
- **Reviewer, round 2:** independent Spec axis found no remaining defect in
  this local slice. Standards axis found non-integer subscription statuses
  accepted as success. Added four red regressions, reused `_sdk_result`, and
  verified all four green. No third structural review/refactor loop.
- **Verifier:** real client/transport tests use a fake SDK that rejects trade
  context construction and refuses an unsubscribed quote. The initial three
  failures became green. Error/symbol/history identity tests were red then
  green. A real stalled subprocess is terminated and its scratch directory
  is emptied; worker-main tests check typed protocol output and secret
  sentinel removal. Final focused suite: **121 passed, 1 skipped**.
  Full verification after documented corrective reruns covers **148 files,
  3,628 cases: 3,567 passed, 61 skipped**. Skips remain skips, not acceptance
  evidence. Full-scope Ruff and diff checks pass. The reconciliation script
  checks every collected file, its case count and all 14 changed Python
  source/test hashes. Artifacts: `output/pytest-0037-shards/`,
  `output/pytest-retention-clock-final.log`, `output/pytest-router-serial.log`,
  `output/0037-verification-final.json` and `output/0037-source-sha256.json`.
- **Verifier, real process boundary:** the shipped CLI against a local TCP
  listener that accepts connections but never speaks OpenD returned a single
  JSON `timeout`, exit 1, in **2.862 seconds** for a 2-second worker limit.
  `order_checked=false`, stderr empty; this is a fault-injection check, not
  a real-market-data result.
- **Verifier, deployment separation:** a read-only new-origin `/health`
  check on 2026-09-23 still reports `status=ok`, merged build `33aa0521`,
  runtime live, paper true and live trading false. No candidate deployment
  occurred; this point sample does not close the 24-hour observation.
- **Verification runtime finding:** the initial serial run again slowed in
  demo-based tests. Profiling one Decision Inbox test produced a passing
  58.25-second run, with demo seeding, filesystem operations and forecast
  validation in the profile. A later faulthandler sample shows the existing
  `write_bars` Parquet copy path; that 234.84-second file run passed. The
  complete suite is scheduled by independent file with six local workers,
  separate temporary roots, and single-thread BLAS/OpenMP limits. No test is
  removed, no production performance change or security setting is made.
- **Verification blocker repair:** broad checks reproduced nine failures in
  fixed-September-12/13 replay fixtures across four files after the real clock
  moved beyond the default seven-day retention window. The scoped
  `tests/live_clock.py` helper pins only the buffer clock in affected tests,
  preserving actual retention and preventing wall-clock drift. The combined
  history/buffer/lookup/candle/identity rerun passes **110 tests**. Independent
  test-repair review confirms all assertions, default expiry, index queries,
  migration, continuity and quarantine behavior remain intact. No production
  retention behavior changed. The SSE file
  encountered a local bind race during parallel checks; its isolated rerun
  passed **35 tests** without changing the application or test assertions.

## Remaining sequence

1. Local readiness repair and broad verification are complete at this checkpoint.
2. Next execute the [live-polling follow-up](../superpowers/plans/2026-09-23-moomoo-live-polling-repair.md):
   its connect still uses the general probe, and ticker reads lack SDK
   registration. These are not repaired by the readiness-only command.
3. Establish the licensed OpenD private quote route; the local process is not
   currently listening. Do not solve this by opening public ingress.
4. Collect real AAPL/NVDA source-time progression and session/delay evidence,
   then validate the Markets/Watchlist chart loop on the new AWS host.
5. Review the deferred 8 GB observation/drills and staged release evidence.
   CI resumption, remote merge and deployment are not claimed in this record.

After an approved private route or AWS-side licensed OpenD placement is
available, run the JSON probe during an open US session. Acceptance requires
at least two distinct source timestamps for both AAPL and NVDA, explicit
delayed/closed/unavailable labels, the existing five-second polling contract,
paper mode unchanged and live execution disabled. A last-price-only response
remains research data; it cannot bless a paper order.

## Explicit non-goals

Do not open public ingress, install credentials in the repository, enable live
trading, place an order as a connectivity test, fabricate bid/ask values, or
claim AWS equity acceptance before the route and entitlement witness exists.
The 8 GB 24-hour capacity/freshness, rollback and reboot work remains in
iteration 0036 for later operational acceptance, without blocking development.
