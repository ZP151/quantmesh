# Iteration0038 continuation: bounded BTC market-data-only application

Issue: https://github.com/ZP151/quantmesh/issues/218 (existing continuation).
Plan: docs/superpowers/plans/2026-10-26-market-data-only.md.
Base: origin/main7c49d341a40eb000ffd95cac0e4a56e06fc9d336.
Branch: codex/market-data-only. No push, PR, CI or server operation by this leaf.

## Planner / product handoff

One action: open the existing BTC chart in a separate default-off loopback mode,
observe advancing minute snapshots, then stop the application cleanly.
Success: at least two distinct newly completed target timestamps via the existing
formal history/workspace API, read-only HTTP/WS access and budgeted owned-cache
publication followed by exact handle close and cold read. Controlled engineering
evidence is not native provider/server acceptance.

Non-goals: no new collector/engine/platform, no feed.py/buffer.py edits, math,
PG/worker/keys, frontend/static/client, dependencies, provider/network/host actions,
or repairs to PR227/other tracks. Sole publisher integrates the separately frozen
UI; operator alone controls merged native run and capacity admission.

Actual ACK2026-10-25T16:13:30Z; interface frozen16:26:49Z before15-minute limit;
first targeted result before17:13:30Z; hard final18:13:30Z is unchanged.
Frozen interface output/market-data-only/INTERFACE.json SHA256:
f7278698f20f676801058395044bdea4ca7f8e4ce855d9d0c7543ccd4ce628c0.

## Quant researcher handoff / rulings

- Root chose post-close REST snapshot sampling after rejecting the intermediate
  feed batching proposal. Filter WS interims before normalized/durable events;
  zero initial REST; exact previous full-minute window and real request/receipt
  ordering. Bounded reconnect1..5; no retry of failed slots in the same process.
- Provider finality and historical PIT remain unknown. Payload annotations and
  history limitations state these are partial public REST observations. Existing
  final=True admits completed-interval replay, not provider finality or a qualified
  research dataset. No trading or statistical performance conclusion follows.
- No new wire-byte ceiling or global HTTP latency guarantee is claimed. Public
  REST remains synchronous in the owned supervisor task; cancellation joins that
  request before closing the same cache. Per-phase timeout is not a total deadline.
- Root terminated Stooq cashbook qualification; no real SPY run or fixture
  substitute. Existing sample evidence and all math remain untouched.

## Implementer handoff

Four source files only: early factory/CLI opt-in in api/workstation.py; optional
health fields in api/app.py; new api/market_data_only.py assembling existing app,
routers, workspace/history and SPA with an outer ASGI allowlist; mode-only
sampling/recovery in live/hyperliquid.py. Ordinary default/live path is preserved.

HTTP mutators/legacy aliases and unrelated GETs refuse before body/handler;
only exact BTC range1d/chart/health/market/live reads and outbound live WS remain.
Finite HEAD, scoped OPTIONS and WS1008 refusal tested. No unrelated store/model/
catalog/account-file constructors run. Mode accepts only bounded cache admission,
paper configuration and loopback. Failed pre-lifespan bind disposes owned cache.

Lifecycle owns the feed task, source transport, exact replay_buffer and public
HTTP client. Shutdown joins task and close through repeated cancellation; safe
fixed failure reasons replace raw exceptions. Capacity stop keeps reads available
until application shutdown. Existing COMMIT acknowledgement remains authoritative.

## Verifier evidence (targeted only, in output/market-data-only/)

- 01-boundary-red:19 failures missing factory opt-in; 03-clock-red:1 failure from
  workspace clock mismatch; 04-boundary-green:19 PASS.
- 05-observation-red:19 failures missing candle-only args; 06:19 PASS.
- 07-receipt-order-red rejected missing causal receipt check; 08-cli-red rejected
  missing CLI option; 09-cli-observation-green:45 PASS.
- 10/11-lifecycle failed extra healthy status note churn and actual socket close;
  mode-only corrections in12-lifecycle-green:2 PASS. Actual4 intents including
  startup/STATUS/two different candle writes; normal close once and cold read2.
- 13-recovery-shutdown-red:3 failures for hidden task failure, lost cancellation
  and truncated known reconnect gap; 14-delta-green:50 PASS.
- 15-inflight-rest:2 PASS (boundary/recovery). Real owned synchronous request
  returns before cache close; no abandoned worker, no write after close.
- 16-targeted:52 PASS/1 failure, 17 diagnostic:1 PASS, 18-targeted-compat:58 PASS/
  1 failure exposed test observation race. DB rows become visible before feed
  applies receipt and acknowledges. Test now waits actual durable acknowledgement
  before comparing full HTTP DTOs, plus terminal state before capacity-stop reads;
  source/feed semantics unchanged. All failed logs preserved.
- 19-targeted-compat:58 PASS/1 failure exposed an overstrong shutdown oracle:
  cancellation can follow COMMIT but precede admission/ack. Test now records
  actual on_persisted callbacks; only acknowledged eligible COMMIT rows advance
  the cursor, while conservative cursor omission is safe. Production unchanged.
- 20 initial scoped Ruff findings corrected by21; 21-ruff:PASS. Scoped formatter
  changed only the four allowed source paths and three new test paths.
- 22-targeted-compat:59 PASS,6 existing deprecations,11.75s:54 new cases plus five
  named existing checks (ordinary live CLI wiring/bind, base health, default
  subscriptions and ordinary reconnect recovery). No broad suite run.

Windows substitutes only unavailable directory fsync primitive. Actual DuckDB,
budget-intent/stop/close receipts, async task ownership and API execute. Existing
Starlette/NumPy deprecations are recorded, no new dependency added. No old/full
suites, CI, native filesystem quota or external provider tests run by this leaf.

## Reviewer / final status

Initial source freeze c9622c5da4581413e53838dae8e7bc4d00cf2b16, tree
ee93f06377155200c23c7280d239518e358384c5 after59-case GREEN. One fresh independent
R1 returned NOT_READY with two Important/P2 findings;54 new cases independently
PASS in9.86s. Immutable reports:output/market-data-only/review-r1.md and.json.
Review covers sampling clocks/finite attempts, guard scope, durable cursor and
normal/capacity/in-flight shutdown, default compatibility and source ownership.
Native chart/server acceptance remains with main/operator after sole publication.

### One aggregate correction / known round2

R1: over-limit refusal advanced attempted-through, allowing a second reconnect to
request a truncated tail. R2: disconnect before first REST discarded the known
observed baseline, permitting pre-session or truncated initial recovery.
Both accepted by root as bounded P2 defects, not architecture expansion.

-26-review-corrections-red:all5 new cases failed against frozen c9622c5, covering
  durable/failed initial target then two consecutive long reconnects, plus first
  disconnect in same minute/within one completed minute/beyond horizon.
- Fix in hyperliquid.py only: retain initial observed baseline independently of
  resettable WS/current and actual-attempt watermark; screen entire known range
  before attempted-slot filtering, and do not mark refused ranges attempted.
  Future ordinary snapshots remain possible and explicitly KNOWN_GAP.
-27 retained two test-only enum-string mistakes after three behavior cases passed;
  use actual ContinuityState enum in new assertions and existing in-flight oracle.
 28-review-corrections-green:5 PASS/21deselected0.30s.
-29-final-targeted-compat:64 PASS (59new+5named existing),6 existing warnings11.93s.
 30-final-ruff/31-final-format/32-final-diffcheck:PASS;7 files already formatted.
- Root requested the original R1 reviewer to check only these known corrections,
  added regressions and final delta as round2; no new fresh review or third round.
  Round2 result pending before integration release. No feed/buffer changes.

### Review judgments / deferred gates

No deferred Minor findings. Each declined behavior remains a gate owned by main:

1. Native quota, peak, fsync and prepared mount: controlled Windows evidence only;
   physical containment remains unproved until operator acceptance (risk: disk).
2. Actual provider rate, availability/finality: no external calls; display partial
   observations with unknown finality (risk: incomplete or later revised bars).
3. Wire-byte and total shutdown bound: no new guarantee; synchronous request is
   joined before close (risk: request/loop delay until transport returns).
4. UI/client/bundle/native two-minute chart: separate frozen UI and sole publisher/
   operator acceptance (risk: source works but merged UI/native route may fail).
5. Rights/redistribution: no new copied source/dependency; data/source qualification
   separate (risk: unapproved redistribution; no such promotion by this leaf).
6. PIT/OOS/SPY/paper/live promotion: observations do not qualify research or trading
   (risk: biased research if someone ignores these explicit limitations).
7. Broad CI/default native runtime: targeted checks only under root's leaf scope;
   release gates still required (risk: untested broader integration regression).

Commits bypass broad local hooks with core.hooksPath=NUL under root's targeted-only
instruction. This is a scoped candidate handoff, not release/native acceptance.
