# Iteration 0034 — Deployed read-only live market data

- Status: completed and accepted on AWS, 2026-09-12
- Planned: 2026-09-12
- Issue: [#140](https://github.com/ZP151/quantmesh/issues/140)
- Planning branch: `codex/0034-live-data-delivery-plan`, from `origin/main@6ea9a13`
- Implementation branch: `codex/0034-deployed-live-market-data`
- Executable plan: `docs/superpowers/plans/2026-09-12-deployed-live-market-data.md`
- Dependency: reconcile private staging integration in [#135](https://github.com/ZP151/quantmesh/issues/135); do not overwrite its independent worktree

## User action and outcome

Open the AWS private workstation and inspect real Hyperliquid BTC/ETH/SOL
prices, source timestamps and connection/freshness state. The first bounded
slice succeeds when a five-minute observation records at least two distinct
upstream timestamps for each selected symbol, source data reaches the browser,
and a controlled disconnect/reconnect demonstrates stale/recovery behavior.
Record source-to-browser delay observations rather than claiming an exchange
latency SLA. No order is required for acceptance.

## Evidence and scope decision — 2026-09-12

- **Planner/Product:** the operator identified AWS as the deployment in question.
  Prioritize deployed data delivery before adding more models or research UI.
  Code completion, deployed build identity and live-provider acceptance are
  separate statuses. Iteration 0033 is merged through PR #139 at `6ea9a13`.
- **Read-only deployment audit:** iteration 0031's independent branch
  `codex/0031-aws-private-staging` at `9a177c6` records a 2026-09-09 activation of
  `402294248406fa865d601633f4e5ba3bd3521b5b`. Its health evidence is
  `runtime_mode=demo`, `paper_mode=true`, `live_trading=false`; its tracked
  `deploy/aws/lightsail/quantmesh-staging.service` explicitly uses `--demo`.
  These are recorded deployment facts, not a fresh server probe. The current
  server SHA and runtime must be observed before changing a deployment.
- **Implementer assessment:** main already has LiveFeed/LiveBuffer, venue
  supervisors, replay and local stream delivery. `--demo` and `--live` are
  exclusive. Reuse this path instead of constructing another market-data plane.
  The staging integration has private-origin/build-identity support absent from
  this main baseline; deploying main directly is not a sufficient update plan.
- **Quant Researcher:** live ticks are observations, not trusted daily history,
  qualified forecasts or calibrated confidence. Preserve upstream timestamps,
  venue/instrument identity, calendar and quality semantics. Delayed equity
  entitlements and closed sessions must remain visible. Stream connectivity
  alone cannot satisfy DecisionPacket evidence or paper promotion gates.

## Sequential delivery order

| Priority | Bounded delivery | Exit evidence |
| --- | --- | --- |
| 0 | Reconcile #135 deployment support with merged product code; read current private health and service mode | Exact candidate SHA, preserved private-origin checks, retained rollback target; no assumption that merging updates AWS |
| 1 — this iteration | Hyperliquid BTC/ETH/SOL public feed through the existing cockpit/watchlist and replay | Five-minute real-source/browser witness, stale/reconnect test, reload/replay and paper-only state |
| 2 — follow-up | Moomoo AAPL/NVDA with reachable OpenD and actual quote entitlements | Market-session witness, observed timestamp freshness, explicit delayed/unavailable states; current five-second polling labelled honestly |
| 3 — follow-up | Polymarket active contracts, then authenticated Kalshi streaming | Verified current subscription payloads, token/ticker and expiry mapping; authenticated Kalshi handshake or an explicit unavailable reason |
| 4 — follow-up | Trusted historical datasets feeding the Lab and outcome review | Pinned manifests, quality/calendar acceptance and replayable 7/30-session evidence from real data |

Do not run these as parallel market tracks. Finish and review each visible
user loop before widening venue coverage. The 0021 soak remains independent.

## Existing capability and gaps

- Hyperliquid: public WebSocket/recovery implementation exists. The first
  slice validates the actual deployment path and fixes only blockers to it.
- Moomoo: `src/quantmesh/live/moomoo.py` polls OpenD (default five seconds).
  This is not native tick push. An AWS process cannot assume the operator's
  Windows-local OpenD is reachable; choose a private supported placement first.
  Existing last-price rows lack bid/ask and must not be promoted to executable
  quotes by this work.
- Polymarket: public market feed and REST book adapters exist; validate current
  protocol against real active contracts before declaring deployment acceptance.
- Kalshi: current assembly reuses `LiveHyperliquidTransport`, whose WebSocket
  connection has no signing/authentication headers. The official
  [WebSocket quickstart](https://docs.kalshi.com/getting_started/quick_start_websockets)
  requires handshake authentication. This needs an adapter change and secure
  credential configuration, not merely a watchlist setting.
- `src/quantmesh/api/workstation.py` currently requires a nonempty
  `QUANTMESH_LIVE_WATCHLIST` for `--live`; independent non-crypto enablement is
  a later composition concern, not a reason to expand the first slice.

Protocol references checked 2026-09-12:
[Hyperliquid subscriptions](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket/subscriptions),
[Polymarket real-time data](https://docs.polymarket.com/market-data/realtime-data).

## Acceptance gates for the first implementation

- [x] Inspect the actual AWS build/mode and reconcile #135 ownership before
  preparing a deployment candidate; retain private HTTPS and rollback behavior.
- [x] Write the executable test-first implementation plan against that reconciled
  baseline, naming exact affected runtime/configuration/UI/test files. This
  document is a prioritized design, not an executable implementation plan.
- [x] Preserve source identity and freshness through existing APIs to the
  rendered prices. Demo, disconnected, stale and live states must be distinct.
- [x] Record the five-minute BTC/ETH/SOL witness with timestamps and build SHA;
  verify reload/replay and stale detection within the configured threshold.
- [x] Test disconnect/reconnect using a controlled harness; do not interrupt
  unrelated production or soak connections to manufacture evidence.
- [x] Run targeted regression checks while developing and required broad gates
  at the reviewed slice/PR boundary; attach exact commands/results to this ledger.
- [x] Verify `paper_mode=true`, `live_trading=false` and unchanged order/risk
  authority before and after the user loop.
- [x] Publish an exact-build deployment acceptance checkpoint separately from
  the merge checkpoint. A green CI run is not a live-provider witness.

## Non-goals and boundaries

No live trading, order placement, new forecasting framework, UI redesign,
unrelated soak repair, historical backfill or multi-market expansion in the
first slice. No credentials in prompts/logs/fixtures. This planning change
performs no server update, account subscription or infrastructure mutation.
Deployment execution follows the existing operator scope recorded in #135;
do not infer authority to purchase data or expose new public services.

## Planning verification

- **Reviewer:** one independent read-only review found no actionable issues.
  It checked scope, historical merge dates, issue links and the distinction
  between recorded AWS evidence and a fresh server probe.
- **Verifier:** controller re-read PR #139 merge state, issue #138 closure and
  exact CI run/head; checked all 25 relative Markdown link targets across the
  seven changed documents. `git diff --check` passed. Documentation only; no
  application behavior changed and no new runtime test pass is claimed.
- **Publication:** issue #140 tracks the proposed delivery; this planning PR
  references it without closing it. Implementation and live-provider acceptance
  remain outstanding.

## 2026-09-12 — Approved implementation checkpoint

- **Planner:** operator explicitly approved the subsequent iteration. Created
  the goal for the deployed BTC/ETH/SOL loop. #141's missing 0033 goal archive
  was added in `388645a`; the actual review thread is resolved, fresh CI pending.
  Its commits are present on this integration branch without bypassing CI.
- **Verifier / AWS:** fresh private HTTPS health confirmed exact `4022942`,
  demo, paper true/live false. Tailscale identifies the intended node online.
  SSH requires an operator identity check; no host-key bypass was used.
- **Integrator:** merged independent staging `9a177c6` into this worktree,
  retained current product/goal/index/roadmap records and rebuilt current assets.
  The original staging worktree and branch remain untouched. No local-main reset.
- **Quant Researcher:** found ACK/context/BBO protocol mismatches and receipt-only
  freshness masking old quotes. Actual public ACKs also include server-default
  fields, so literal request/response equality is invalid. Historical chart
  backfill is explicitly excluded; recorded MarketUpdate replay is acceptance.
- **Implementer / deployment:** canonical explicit live profile and mode/safety
  health validation, legacy environment compatibility and retained rollback.
  Agent recorded baseline 31 passed, RED 23 failed/18 passed plus CLI RED,
  then 63 staging/identity passed. Controller integration selection below
  independently includes these tests.
- **Implementer / protocol:** official nested BBO/context, ACK handling and
  socket cleanup. Null sides emit no quote/activity; malformed sides fail closed.
  RED 18 failed/76 passed; follow-up null/fixture RED observed. Agent's targeted
  140-test gate passed before the actual ACK default-echo correction.
- **Implementer / freshness:** three backend and three frontend RED assertions
  reproduced old-source/future-clock/cache-aging defects. Source-based quote
  age and a client timer fix them; receipt-timed metrics do not refresh quotes.
  The aggregate backend label preserves disconnected unavailability.
- **Verifier / controller:** 152 feed/router/replay/staging/identity tests passed
  in 15.53s with one existing Starlette warning. 74 frontend tests passed in
  10.11s. OpenAPI generation/check and actual TypeScript/build passed; current
  bundle is rebuilt. Initial default pytest cleanup hit an unrelated Windows
  temp permission error; subsequent runs use unique owned `--basetemp` paths.
  Protocol actual-source probe and browser fixture acceptance are still running.
- **Scope:** no order, server update, paid subscription, credentials or
  independent operational track change at this checkpoint. ADR-0022 records
  the bounded private read-only profile and timestamp semantics.

## Reviewed integration verification

- **Reviewer:** independent Standards/Spec review identified browser wall-clock
  skew and unverified automatic rollback. Both are corrected and the sole
  confirmation found no remaining issue. Cached age now adds monotonic browser
  elapsed time to initial server/source age and cannot recover on clock rollback.
  Failed activation validates and health-checks the retained release; failed
  restoration has a separate error. Correction RED: two clock cases and 14
  rollback cases; targeted GREEN evidence is included in controller checks.
- **Protocol actual-source correction:** live ACKs contain server-added defaults;
  match requested fields while tolerating additional response fields. Real
  candles use an inclusive end millisecond: accept exactly the interval or
  interval minus one millisecond; reject neighboring invalid durations. Captured
  public frames reproduced both failures before correction. A bounded public
  parser then consumed 932 frames over 45 seconds without errors, including
  78 candles and 578 BBO frames across BTC/ETH/SOL.
- **Verifier / controller:** final nine-file Python selection passed 311 tests
  in 32.96s, one existing Starlette warning. Full frontend passed 333 tests in
  21.50s. Initial fixture browser pass: 7 passed in 44.01s; final correction
  confirmation is tracked separately. Ruff all-source checks passed. No full
  local pytest/release/soak was launched; automatic final-head CI remains a gate.
- **Current limitation:** the built-in browser refused the local test port and
  Chrome automation is unavailable. Existing project browser E2E provides the
  packaged loopback fixture acceptance; actual-source API/persistence is being
  witnessed separately. Do not call this an AWS browser acceptance.

- **Final local boundary:** correction browser confirmation passed 7 tests in
  49.25s. Ruff, OpenAPI freshness, actual TypeScript and rebuilt bundle freshness
  passed. Submodule status was inspected (reference submodules uninitialized;
  none changed). Working-tree whitespace check passed.

## Publication and local real-source witness

- Integration commit `ed3900deeb949c0a291e5b43c9684d4db4120660` is published
  in [PR #142](https://github.com/ZP151/quantmesh/pull/142). #141 remains the
  prior documentation dependency. Required automatic CI is pending; neither
  final integration nor AWS deployment is claimed complete.
- Full local `--live` application, not an injected provider, observed public
  Hyperliquid from 2026-09-12 08:55:09 to 09:00:11 UTC: 302.13 seconds, 61
  samples, 61 distinct quote source timestamps for each BTC/ETH/SOL. Zero
  disconnected samples. Maximum sampled source/receipt quote ages were BTC
  2041ms, ETH 2641ms and SOL 4777ms; these are observations, not an SLA.
- Paper true/live trading false throughout; risk state and empty order list
  remained unchanged. Replay API reported 8560 stored updates at the witness
  boundary (includes earlier diagnostic runs). After stopping only the owned
  temporary app processes, the same lake reopened with at least that count.
- Detailed public-data evidence is in OS-temp
  `qm0034-live-9foa6m4c/witness-summary.json` and `witness-samples.json`.
  This is local source-to-API/persistence evidence, **not AWS browser acceptance**.
  Temporary app processes are stopped; the operator's real data roots and AWS
  service remain unchanged. Tailscale SSH still awaits operator authentication.


## Resume — AWS access and dependency integration

- Previous goal turn made implementation and verified local-source progress.
  SSH check session30832 now completed: operator authentication accepted,
  intended retained4022942 release active under quantmesh user/group.
- Remote read-only preflight: Ubuntu Python3.12.3, 54GB disk available,
  approximately1.3GB available memory, passwordless sudo and existing private
  Tailscale Serve ->127.0.0.1:8765. No deployment or infrastructure change yet.
- PR#141 merged as00a0ee0 at09:02:33UTC. Its final archive-head run34683518613
  remained in progress when rechecked; GitHub auto-merge did not wait for that
  optional check. No green claim is made. For#142 explicitly wait for final-head
  CI success before merge/deploy, regardless of repository auto-merge policy.
- Merged origin/main into the integration branch. Conflicts were only the
  already-carried planning documents; retained current implementation/evidence
  versions, without discarding new upstream source changes. Source code and
  generated bundle are unchanged from reviewed/tested ed3900d.
- Browser automation navigation to the private AWS hostname was refused by
  both in-app and Edge surfaces (ERR_BLOCKED_BY_CLIENT). HTTPS/SSH CLI access
  works; deployed browser acceptance remains a separate unresolved gate.

## Planner checkpoint — external review before activation

- Corrected the browser preflight: the deployed route is `/app/cockpit`.
  Edge renders staging4022942, the demo banner and "no live feed is attached".
  Earlier `/cockpit` navigation failures were not evidence of blocked private
  browser access. SSH authentication is complete; no activation has occurred.
- AWS-host direct public WebSocket probe at09:12:53UTC ran45.22seconds:
  3 subscription acknowledgments,397 BBO frames and182/83/132 distinct source
  timestamps for BTC/ETH/SOL. This proves venue reachability from AWS only;
  application/browser live acceptance still awaits deployment.
- New external PR review arrived after the bounded independent review and
  correction confirmation. Returned to Planner before further implementation:
  reduce the remaining work to four concrete acceptance defects, without
  another open-ended structural review or market expansion. Reuse the existing
  aging hook in the detail screen, preserve the disconnected-status veto in
  shared label derivation, constrain deployment to the audited dependency
  closure, and validate the official BBO order-count field. Each requires
  reproduced RED/GREEN evidence. Existing protocol/replay architecture stays.
- The source timestamp/freshness and deterministic deployment contracts make
  these corrections part of the current user loop. Final-head CI must rerun
  after the single correction checkpoint; old-head success cannot authorize
  activation. No deployment, order or independent soak changes are allowed
  during this correction step.

## External-review correction verification

- **Implementer / frontend:** regression RED reproduced both disconnect veto
  cases and frozen detail age:3 failed/61 passed. Shared label derivation now
  retains unavailable status; quotes cannot clear it until a connected status
  arrives. Detail uses the same monotonic aging hook. Targeted GREEN64 passed.
  Full-suite load exposed an existing wait race between connector text and the
  actual watchlist row; the test now waits for the BTC row link. Full frontend
  GREEN336 passed across27 files in21.72seconds.
- **Implementer / protocol:** required BBO `n` is a non-negative integer;
  missing/null/bool/negative/fraction/string fail closed. A null side cannot
  conceal a malformed counterpart. RED13 failed/1 passed; agent GREEN114
  wire/supervisor tests. Controller includes these in the combined gate below.
- **Implementer / deployment:** installation constrains the base package with
  the candidate's audited closure. Demo/live command assertions both failed
  before correction. Agent staging/identity GREEN78 passed. Read-only Linux
  CPython3.12 wheel resolution and marker/Requires-Python inspection verified
  all37 base runtime dependencies against the pinned closure; no dependency
  installation or shared-environment mutation occurred.
- **Reviewer / controller:** inspected the bounded corrections against each
  external finding; retained null-side behavior, explicit reconnect recovery,
  base-only dependency installation, old demo environment and checked rollback.
  No third broad architecture review or additional market work was launched.
- **Verifier / controller:** combined nine-file protocol/feed/router/replay/
  staging/identity gate:326 passed in26.67seconds, one existing Starlette
  warning. Packaged browser gate:7 passed in36.16seconds. Full frontend336
  passed; TypeScript build, generated API and frontend lint passed (existing
  four Fast Refresh warnings). Current bundle rebuilt. These supersede the
  earlier local counts; full final-head CI and AWS live acceptance remain open.

## CI fixture clock correction — 2026-09-12

- PR#141 archive-head run34683518613 completed successfully at09:25:16UTC:
  3321 Python passed/55 skipped and325 frontend passed. This closes its earlier
  pending-check uncertainty; it does not change the recorded merge ordering.
- PR#142 run34685627199 atf62630e failed after40m13s of full pytest:
  3441 passed/55 skipped/1 failed. All preceding frontend/audit/build/lint
  checks succeeded. The only failure was the prediction-pipeline test expecting
  `real` for a2025 source timestamp observed at its2026 clock. Local invocation
  of that exact test reproduced the same failure in3.59seconds.
- **Quant/Reviewer:** source-age behavior is correct. Do not weaken freshness or
  alter prediction-provider production code to satisfy an inconsistent fixture.
  Scope the correction to the pipeline's observation clock and stronger tests.
- **Implementer:** exercise both source age0 and60seconds; assert both venue
  labels, preserved source/receipt timestamps and exact source age. The quiet
  test now starts from proven fresh data before crossing the five-second lag.
- **Verifier:** prediction/feed selection passed102 tests in1.88seconds.
  Controller inspected the diff; only tests and checkpoint documents changed.
  Ruff and scoped formatting/whitespace checks passed. App source and built
  assets remain those already verified atf62630e. No AWS service update occurred.
  A new final-head CI run is required before merge and deployment.


## Final integration and AWS acceptance — 2026-09-12

This checkpoint supersedes the pending deployment/CI statements above, which
remain chronological evidence of the investigation and corrections.

- **Planner/Product:** the operator can open the private AWS cockpit and inspect
  real BTC/ETH/SOL source observations, aging and replay. This closes the bounded
  #140 user action and integrates #135; other markets remain subsequent slices.
- **Reviewer:** all four external review threads on [PR #142](https://github.com/ZP151/quantmesh/pull/142)
  were resolved after the bounded correction review. Final tested head
  `ee8b4644eb4ee70ec07168c1b3cea95c5de68b75` and merged main
  `e185c3b052ca0cdd3590b0d5d05fd7460d783fb7` have the identical Git tree
  `45cadd9613f39236ce81b96cb9c4a149c596e977`. Merge completed at 10:45:43 UTC,
  after [CI run 34687576761](https://github.com/ZP151/quantmesh/actions/runs/34687576761)
  succeeded at 10:44:20 UTC. Divergent local main and independent operational
  worktrees were preserved.
- **Verifier / code:** final-head CI passed 3443 Python tests / 55 skipped /
  9 warnings and 336 frontend tests. License/audit, generated API, typecheck,
  lint and committed-bundle checks passed. The preceding local gate passed
  326 targeted Python, 336 frontend and 7 packaged browser tests; the final
  fixture-only clock correction separately passed 102 prediction/feed tests.
- **Implementer / deployment:** activated exact merged build `e185c3b` through
  the reviewed deployment script and unit; service started at 10:47:11 UTC.
  Both private HTTPS and loopback health reported staging, `runtime_mode=live`,
  `paper_mode=true`, `live_trading=false` and the full merged build ref. Actual
  AWS `pip check` reported no broken requirements. The service remains under
  the quantmesh user, listening only on `127.0.0.1:8765`, behind existing private
  Tailscale Serve. No new AWS resource, public application ingress or credential.
  Retained rollback: `402294248406fa865d601633f4e5ba3bd3521b5b` with its demo
  profile. Existing unrelated firewall hardening remains in the #135 ledger.
- **Verifier / actual source:** private application API sampling from
  10:47:45.622964 to 10:52:50.354646 UTC ran 304.88 seconds: 60 samples and
  60 distinct upstream quote times for each BTC/ETH/SOL. All 180 quote samples
  were labelled real; zero disconnected samples. Risk state and the empty
  order list remained unchanged; initial and final health were identical.
  The replay lake held 5468 updates at this boundary, beginning at
  10:47:14.188289 UTC. See [summary](evidence/0034/aws-witness-summary.json)
  and [quote observations](evidence/0034/aws-quote-observations.jsonl).
- **Verifier / actual browser:** Edge rendered `/app/cockpit` with exact staging
  build, live read-only banner, connected WebSocket and advancing source times
  for all three instruments. Three observations span 323.567 seconds. Desktop
  1280x900 and mobile 390x844 had no document overflow; the mobile table has
  its own horizontal scroll. Keyboard Enter opened five-minute lake replay
  (2533 updates); live quotes continued. Clear replay restored the live view.
  Reload reconnected the WebSocket and retained the same earliest recorded
  minute (3501 updates then). Viewport override was reset. See
  [browser witness](evidence/0034/aws-browser-witness.json).
- **Quant Researcher:** source-to-server receipt medians were BTC 230.596ms,
  ETH 235.072ms and SOL 232.409ms; maximum sampled source ages were 2531ms,
  4507ms and 5248ms respectively. These finite observations are not an SLA or
  a measured continuous browser transport latency. Browser event/receipt times
  were inspected separately. Controlled quiet/disconnect/reconnect acceptance
  comes from feed/supervisor and browser regressions, not an induced AWS outage.
  No order authority, strategy qualification or trusted historical dataset is
  established by this live-data witness.

### Operator acceptance / 操作验收

Open [AWS private cockpit](https://quantmesh-staging.tail99d23c.ts.net/app/cockpit)
from the authorized tailnet. Verify staging `e185c3b`, live read-only session,
BTC/ETH/SOL real rows with advancing event times, then use Replay 5 min and
Clear replay. Paper remains enabled; live trading remains disabled.

在已授权的私有网络中打开上方地址，可查看 BTC、ETH、SOL 的真实行情、源时间、
新鲜度与五分钟回放。本轮仅验收这三个 Hyperliquid 标的；美股、预测市场和可信
历史数据尚未完成 AWS 实际数据验收。下一步先核对 Moomoo/OpenD 私有连接和
行情权限，再交付 AAPL/NVDA 页面观察闭环；详见迭代计划。

### Closeout evidence review

- Independent closeout reviewer: pass, no actionable findings in documentation,
  local links, source counts/statistics, build identity, scope or secret exposure.
  This was a document/evidence audit, not another architecture review.
- Controller validation recomputed 180 JSONL observations, 60 distinct source
  clocks per symbol, age and receipt-delay summaries, exact build/safety fields,
  browser duration/layout/replay flags and local evidence links: passed.
- Fresh AWS loopback health still reported exact `e185c3b`, live data, paper true
  and live trading false. `git diff --check` passed. Vendored submodule revisions
  were inspected and remain uninitialized/unchanged in this worktree.
