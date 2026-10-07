# Active Goal

Status: iteration0037 ACTIVE, 2026-10-08 Singapore. The 0035 AWS real-chart acceptance
and the 8 GB migration's short acceptance are complete; this goal remains
active until the new host's sustained capacity gate is closed and the separate
Moomoo/OpenD route is ready. PR #161 is now merged and deployed; its live API acceptance passes.
PR #162 also passed CI and is deployed as `c8e1813`; API and list-page
acceptance pass. Source-backed equity minute charts are implemented on
`codex/0037-equity-minute-charts`, checked through PR #163 and deployed at
`69515b79d2bc67303bfef9dee660dbca9bef41e3`. Four AWS equity entry paths and
reload pass with supplier-matching closed bars; actual open-session revisions
and two new minute boundaries remain pending after the market closed. The user explicitly prioritized development and deferred observation
to later acceptance. On 2026-09-23 UTC (September 24 Singapore), the user
explicitly restored CI and authorized merge/private deployment after all checks pass.

PR #164 is checked and merged as `c4ebee4d80c7c3cd162a1f5b3d17ba5553f21f2d`.
The exact reviewed Windows startup helper is installed for the current user;
hidden helper PID53020 holds the singleton and duplicate launch exits0.
OpenD PID28036 and original tunnel session75590 remain alive. AWS continues
to serve `69515b7`, paper=true/live=false; Windows changes need no app redeploy.
Next actual Windows login/outage and open-session equity minute witnesses remain
pending. The evidence branch `codex/0037-release-acceptance` starts from
origin/main c4ebee4, preserving divergent local main.

## 8 GB capacity handoff — later acceptance work

The authoritative private origin is now
`https://quantmesh-staging-8gb.tail99d23c.ts.net`, serving exact merged build
`69515b79d2bc67303bfef9dee660dbca9bef41e3` after PR #163.
Previous `c8e1813` and `db3d18f` remain retained for rollback. The original
migration checkpoint used retained rollback build `33aa0521`. The restored dataset passed archive
hash, WAL recovery, JSON payload validation, 13-check read-only smoke, chart
entry-path, and controlled restart checks. The host currently reports about
6.0 GiB available RAM, no swap, an active service and zero automatic restarts.
These are the completed migration facts recorded in [PR #159](https://github.com/ZP151/quantmesh/pull/159);
the PR remains open after its earlier CI cancellation. Resuming CI for the
equity repair does not itself merge this separate migration-evidence PR.

The migration did not fill the old collection gap (the stopped source ends on
2026-09-17 and the new collector resumes on 2026-09-22), and it did not prove
the old 90-second shutdown behavior. A local, read-only observer started on
2026-09-22 16:21:42 UTC records five-minute smoke, quote/candle freshness,
health safety flags, service restarts, memory, swap, disk and recent journal
lines for 24 hours. The observation gate remains open until the complete log
is reviewed. No later provider or UI acceptance may treat this short sample as
indefinite availability.

The later operational acceptance checklist retains the following; these are
not prerequisites to developing the next provider slice:

- every sample keeps build `33aa0521`, `paper_mode=true` and
  `live_trading=false`;
- BTC, ETH and SOL quote/candle observations remain real and under the
  observer's 60-second freshness limit;
- the service stays active with no automatic restarts, OOM evidence or swap
  activity, and capacity/disk trends are reviewed;
- an operator-approved old-host rollback rehearsal and a new-host reboot test
  are separately completed or explicitly deferred with a recorded reason;
- the evidence is mirrored into iteration 0036 before its closeout.

The old origin is retained as a rollback resource and is not deleted. The
historical gap remains an explicit limitation; any backfill must use a
source-backed, lineage-preserving dataset and cannot be inferred from the
live replay.

## Iteration 0037 development checkpoint — private Moomoo/OpenD readiness

The current feature branch repairs and extends `quantmesh-moomoo readiness
--json` command for issue [#156](https://github.com/ZP151/quantmesh/issues/156).
It checks the private TCP route before SDK use, uses dedicated quote-only
capability discovery, subscribes to SDK QUOTE data before snapshot reads,
and validates daily history for `US.AAPL` and `US.NVDA`. A hard worker deadline
and allowlisted typed diagnostics protect the operator command. It never
opens an order context or persists quote/account rows. Plan and acceptance
details are in [iteration 0037](../iterations/0037-moomoo-opend-readiness.md).

The direct AWS-to-Windows OpenD port was closed. On 2026-09-23 the user
completed SSH revalidation and OpenD login. A reverse Tailscale SSH tunnel now
connects AWS `127.0.0.1:11111` to Windows `127.0.0.1:11111`; both listeners
remain loopback-only. Isolated AWS readiness and actual polling pass, with
AAPL/NVDA source clocks advancing at 15:46 UTC. PR #161 subsequently enabled
the reviewed SDK/watchlist profile on AWS at 17:17 UTC; 18 smoke checks and
four samples of five progressing real source clocks passed at 17:18 UTC. The tunnel requires
the Windows machine, OpenD and SSH process to remain running; it is not yet
a reboot-persistent service. Previous readiness-only local verification is
green (`121 passed, 1 skipped`); complete file coverage after corrective
reruns totals `3567 passed, 61 skipped`. Ruff, diff checks and independent
review pass, as recorded in iteration 0037. This earlier code checkpoint was not a
deployment, merge or real-equity acceptance claim.

The [live-polling follow-up](../superpowers/plans/2026-09-23-moomoo-live-polling-repair.md)
now fixes quote-only connect, TICKER subscription, Linux worker HOME restoration
and an opt-in, constrained SDK deployment profile. Its two independent review
rounds have no actionable findings; final broad verification covers all 149
files with 3582 passed and 61 skipped. Ruff and diff checks pass.
Release checkpoint: PR #161 / CI35887627930 passed 3591 Python tests
(56 skipped), 365 frontend tests and all preceding gates, then merged as
`db3d18fdb5a241826c7276760af59a49c2fc679d`; merge and candidate trees match.
Do not redeploy that completed release. Browser inspection confirmed the real
BTC chart, but equity list cells omitted metrics.last. The bounded follow-up
uses Last trade plus its own clock/age in Markets and Watchlist, retaining
truthful stale/disconnected labels and all order gates. It passed 379 frontend
tests, type/lint/build consistency, 27 Python asset/identity checks and an
independent review with no actionable findings. Local browser preview against
the actual private AWS feed shows both prices and progressing source times;
this is candidate evidence, not a follow-up production-deployment claim.
Release follow-up: PR #162 / CI35896206023 passed 3591 Python tests
(56 skipped) and 379 frontend tests. Normal squash merge at 18:27:52 UTC
produced `c8e1813c15d4837d8b0a7480ea376bbca5839161`, with the same tree
`b96aae511fa48b15a62ee6bfaf1559b0cac26e2e` as candidate `8229a7e`.
The exact release was deployed and passed 18 API checks plus five advancing
real sources. Markets/Watchlist now show Last trade, Real and moving source
clocks for AAPL/NVDA. Do not redeploy either completed release.
Next implement source-backed equity minute candles (existing poller emits
metrics/trades only). Review the deferred capacity/drill evidence later.
The prior Basic-data error is not proof of a paid entitlement requirement:
the old transport omitted the SDK subscription call. Actual subscription
acceptance is now proven for these two symbols in the recorded open-session
sample. It is not evidence of broader rights, every session or all markets.

## Accepted user loop

Markets and Watchlist open BTC/ETH/SOL full charts with1D/Line defaults and
actual Hyperliquid observations. The current minute revises, new minutes append,
and reload retains recorded coverage. Source, time, age and5m->1m fallback stay
visible. This is bounded observed history, not qualified full-day history or
tick-by-tick rendering. Automatic workspace reads wait5s after completion.

- Issue: https://github.com/ZP151/quantmesh/issues/144
- PR149 merged11:20:26UTC as76203e03476b120e149a0c06d9932849bb4d8e14.
- Candidatee23ab82, CI checkoutb4b6adc and squash merge share fulltree
  6e43a7754040bd35b2cef5b8094922fd90157e14. CI34751913362 passed3524Python
  tests/56skipped/9warnings,365frontend tests and all preceding gates.
- Exact private AWS deployment exited0. PID45254 started11:24:24UTC,
  loopback8765/runtime live/papertrue/live executionfalse. User's two existing
  QuantMesh IAB tabs were reloaded. Session59488 is terminal; do not redeploy it.
- Actual paired witness passed601.662s/175samples per page, six entry paths,
  11tailminutes per coin,62/55/53 BTC/ETH/SOL DOM changes matched to earlier
  own-page real frames. Reload/settled API history, keyboard/1440/390px passed.
- 296native workspace requests completed, no errors/timeouts/pending/censored
  requests. Max latency BTC5.743/ETH6.278/SOL5.737s; p95 2.579/3.450/3.000s.
  All21health observations had exact build/papertrue/livefalse. Orders/risk
  unchanged. Independent offline raw-evidence audit has no findings.
- Longest-lived sampling document loaders show minimum response-end-to-next-read
  spacing5.002073/5.002328/5.002287s, independently recomputed by root.
- Actual session97072 exited0 at12:07:43UTC; do not poll or rerun it.
  Artifacts: output/playwright/0035-aws-76203e0/attempt-2, verifier-audit.json,
  refresh-spacing.json and screenshots. HelperSHA256:
  9a3a26014624a33855824f3ae1d29990bd70c78f827b95b159390ee51a88dcff.

## Current recovery checkpoint

- Local Tailscale is healthy: backend Running, UDP/IPv4 available, Singapore
  DERP latency 6 ms.
- `quantmesh-staging.tail99d23c.ts.net` resolves to `100.90.189.16`; after a
  cold stop/start of the existing Lightsail instance, the peer is online and
  accepts private TCP 443.
- HTTPS `/health` reports build
  `76203e03476b120e149a0c06d9932849bb4d8e14`, runtime `live`, `paper_mode=true`
  and `live_trading=false`.
- The earlier Tailscale Machines snapshot and public-address checks captured the
  pre-recovery outage: the console showed **Machine not connected** and TCP
  22/443 timed out. After the cold start, local `tailscale status` shows the
  peer `active` with a direct IPv6 path; no public ingress was added.
- The instance initially looped on startup because its 1.9 GiB host had no swap
  while the 2.4 GiB live DuckDB lake held about 3.7M rows. Kernel OOM logs
  identified `quantmesh-workstation` as the killed process. A persistent 2 GiB
  swapfile on the existing disk restored startup; this is an operational
  mitigation pending a source-level retention guard.
- `tools/live_smoke.py --watchlist BTC,ETH,SOL` passed 13 read-only checks in
  0.9s. `/live/state` contains current real Hyperliquid quote/trade/metrics/L2
  and candle observations for all three instruments, and `/live/status` reports
  each source connected.
- Browser acceptance at the deployed BTC 1D/Line path showed `Live proven`,
  source `hyperliquid`, `real · real`, WebSocket stream and about 3s age while
  current-minute OHLC rows advanced.
- Recovery issue: [#135](https://github.com/ZP151/quantmesh/issues/135).
- Active iteration: [0036 staging recovery](../iterations/0036-staging-recovery.md).
- Plan: [2026-09-17 staging recovery plan](../superpowers/plans/2026-09-17-staging-recovery.md).

The recovery gate is now superseded operationally by the 8 GB host, but the
capacity observation above is still open. The agent must not treat a short
smoke, extra RAM or the former swap mitigation as a permanent stability claim.

Local OpenD and the reverse SSH route are now proven by the PR #161 deployed
five-instrument witness. The earlier Basic-subscription rejection below was
resolved by registering the SDK subscription; it did not establish that a paid
subscription was necessary. The tunnel remains dependent on this Windows host,
OpenD and SSH process; persistent recovery is still later operational work.

## Retention evidence and limits

Existing replay-window API reports1074523rows through12:11:55UTC, with earliest
receipt2026-09-12 10:47:14UTC; previous direct snapshot896780rows is preserved.
Chart reload retained covered observations from09:44 through12:07UTC. A new
stable file-copy attempt exhausted10tries while the lake was being written;
session90210 exited1, primary unchanged. No pause, truncation, unverified copy
read or retry followed. Current growth is proven through the existing in-process
read-only API. Last direct quarantine/index check remains09:56UTC: four old
quarantines and lookup index present; do not claim a new direct count.

Earlier failures remain in the iteration ledger. In particular76203e0 attempt1
was inconclusive for an old-document request, not a proven backend20s timeout.
Planner reset the measurement slice; native document identities,18pure controls
and two review rounds resolved it. The passing actual run censored zero requests.
A ten-minute witness does not certify indefinite availability.

The recovery found the production failure mode behind that limit: the running
service opened the full DuckDB lake before any production prune call, and the
old host had no swap. The retention setting, bounded latest-state lookup and
startup deadline are now in merged `33aa0521`; the new host's sustained
observation is the remaining evidence gate. The old swapfile remains a
reversible host mitigation and is not part of the new-host acceptance.

## Next frontier after migration

Proceed with the current product development slice while observation, rollback
and reboot work stays in later acceptance. Preserve the old release and
verified backups. The existing licensed host, private AWS route and two-symbol open-session
source progression are now established; finish the visible list-price repair
and then the separate real-minute-chart slice. No
credentials are needed in chat. Windows localhost probes cannot establish remote absence. An
open-session real-data witness and truthful delayed/closed/unavailable labels
are required; existing five-second polling is not native tick push. Then
prediction venues and qualified historical evidence follow sequentially in
docs/ITERATION_PLAN.md.

Keep0021soak and issues135/132/127 independent. No public OpenD exposure, paid
subscriptions, orders, strategy promotion or opportunistic maintenance changes.
Standing reviewed merge/private-deployment authority remains in the user's
request and .codex/prompts/goal.md; no further confirmation for this scope.


## October 8 continuation

Execute the tracked `2026-10-08-moomoo-minute-charts.md` plan. SDK, polling,
private replay and metrics-only workspace display are implemented, with source
samples across two real minute boundaries. Independent review resolved the
one mixed-watchlist compatibility finding; no trading authority changed.
Full Python run completed (output/0037-minute-full-suite.log and .exit), with
17 failures diagnosed and final affected reruns recorded separately. Never repeat the full run without a
new failure/changed boundary. Existing reverse Tailscale SSH tunnel is running;
keep it and user OpenD alive. AWS still serves c8e1813, not the candidate.
After checked release and four-entry/reload acceptance, proceed to the user's
requested OpenD self-start and private tunnel recovery. Account authentication
remains handled in the vendor UI, no password storage or disclosure. The
old capacity/shutdown and migration PR159 remain outside the product slice.

PR #163 first-head CI37655740964 failed the frontend dependency audit before
tests. The release gate is retained. Bounded dependency remediation now passes
the high/critical audit and isolated frontend checks; two automated correctness
findings were reproduced and fixed (reconnect dedupe, atomic metrics capture),
with 123 affected tests green. The completed broad Python job started before
these corrective changes and reads this mutable worktree; its result must be
reported with that limitation. Final new-head CI must verify the complete
candidate. AWS remains c8e1813 until checked merge and exact deployment.

The broad run finished with 3649 passed / 61 skipped / 17 failed. One failure
is the old in-memory 646-entry assertion against the corrected 362-entry lock.
The other 16 exposed a real scope regression: the private 1m freshness clock
also affected existing daily/other-interval Moomoo candles. Restrict the rule
to interval=1m, preserving the previous receipt clock elsewhere. The six-file
affected suite now passes 162 tests, including every failed file and two new
nonminute controls. Treat this as consolidated coverage plus targeted recovery,
not a clean exact-head local full run. Await final new-head CI before release.

Exact-head CI37664362155 completed with 3674 passed / 56 skipped / 2 failed;
the historical regressions are resolved. Both remaining failures concern the
installed simplejson 4.2.0 text license, previously inspected only at 4.1.x.
The official tag license and Linux/Windows wheels were verified against registry
hashes; add only the exact 4.2.0 MIT-choice text exception. Safety/license
regressions pass 29 tests, including unknown-version/changed-license refusals.
No dependency pin, generic parser, threshold or CI gate changes. Await the next
complete head CI before merge/deployment; AWS still serves c8e1813.

## Checked minute-chart release — October 8 Singapore

PR #163 is merged at 69515b79d2bc67303bfef9dee660dbca9bef41e3 (20:08:37 UTC
October 7). Final CI37672213223 passed 3677 Python tests / 56 skipped and
380 frontend tests; both automated review threads are resolved. Candidate
260571e and merged release share tree fa470ee5d8737f6822af30df79f85cdfb3f05e37.
Reviewed exact deployment succeeded; c8e1813 is retained for rollback. Do not
merge or deploy #163 again. Local main remains preserved; subsequent work
starts on codex/0037-opend-startup from origin/main.

Exact build, paper=true/live=false and 18 smoke checks pass. BTC/ETH/SOL
source clocks advance. Both stocks are closed/stale with source time near
20:00 UTC; the five-symbol progression helper exits nonzero for those two
stocks only. The minute witness has six source-bracketed samples: both
390-row histories match recent closed provider OHLCV. It exits nonzero because
two appends are unproven. This is a pending open-session acceptance gate,
not a full live-chart success or a reason to roll back a healthy closed session.
All four actual AWS Markets/Watchlist AAPL/NVDA entries, both stock reloads, disabled
paper proposal and BTC/ETH/SOL chart regressions pass. Keep real-time revisions
and two minute boundaries pending until the next regular session.

Evidence: output/0037-minute-ci37672213223-success.log,
0037-minute-deploy-69515b7.log/.exit, 0037-deployed-market-witness.json,
0037-aws-minute-witness/witness.json, 0037-aws-minute-browser.json and
0037-aws-aapl-minute-chart*.png. The ignored acceptance helper's initial
strict-Python-vs-JSON and missing adapter metadata errors were corrected;
retain their logs without treating them as product regressions.

Continue the authorized OpenD self-start/private tunnel recovery slice while
closed-session real-time acceptance waits. The installed vendor-signed GUI
is 10.10.7008 at C:/Users/15492/AppData/Roaming/moomoo_OpenD/moomoo_OpenD.exe.
No existing OpenD startup task or Run entry was found; only ChatGPT is in the
current-user Startup folder. Keep OpenD and reverse tunnel session75590 alive.
Do not read vendor credential files, change remembered-login settings, restart
Windows, open public ingress or enable trading.

The startup plan is tracked at `docs/superpowers/plans/2026-10-08-opend-startup.md`.
Fresh implementer `opend_startup` owns only Task1 scripts/native tests; root
owns docs/verification. Independent review precedes persistent installation.
Current-user execution policy remains RemoteSigned through LocalMachine, with
no Process/User override; local generated files need no policy weakening.
Actual next-logon/reconnect witness remains separate from installing files.

Startup Task1 now has recovery/provisioning scripts plus 26 native Windows
PowerShell 5.1 behavior tests. Root's isolated final run passes 26 in 27.23s,
with whole-tree Ruff/diff clean. Default pytest temp cleanup hit an existing
pytest-current permission error after the 26 test bodies; original log retained,
then a fresh workspace-owned --basetemp run exits0. Do not delete global temp
trees to work around it. Actual ObserveOnly exits0/existing_private_tunnel after
repairing the Tailscale host-first argument order. Independent review and final
CI remain ahead of installation; no startup configuration is installed yet.

Startup PR #164 is open at 2348d76, with first CI37684316455 in progress.
Independent Spec and Standards round1 each reports one P2 (the same defect):
an established owned tunnel can be killed after a subsequent unknown probe,
because startup timeout only remembers start time. The fresh implementer is
reproducing and fixing it with ChildEstablished lifetime state, retaining
established children on unknown/absent probes and resetting on a new child.
Installation stays blocked on this finding and final new-head CI. No changes
to the existing actual OpenD or tunnel have been made. After targeted green,
push the corrected head and cancel the superseded first CI; second independent
review is the final structural round. No repeated full local Python suite.

The P2 is reproduced with two failing native transitions (unknown/absent).
ChildEstablished now preserves an established child and resets after exit/new
launch; uncertain probes never trigger termination. The native affected suite
passes29, root's targeted reset/transitions pass3, Ruff/diff pass, and actual
ObserveOnly still returns existing_private_tunnel. Second review remains ahead
of installation. Corrected CI must complete on the final pushed head.

Final independent Spec/Standards round2 for c416513 has no P1/P2. GitHub's
automated comments on old2348d76 reiterate the fixed lifecycle issue and add
auxiliary status-file IO failure escaping recovery. Planner keeps this within
the existing narrow boundary: status persistence is best effort and never a
connection-control dependency. Missing-directory and locked-status native
cases reproduce escape/child stop; catch only auxiliary persistence failures,
without changing process/route authority. No third structural review or
architecture expansion is opened; final CI/review-thread gates still apply.

Final native suite after status-IO isolation passes31/31.88s, Ruff/diff green
(output/0037-opend-startup/status-green.log/.exit). Two automated findings are
covered by established-child and status-write regressions. Keep actual Startup
installation pending final head CI. Windows-only changes need no AWS redeploy.

Startup CI37685852546 completed at 21:49:39 UTC with 3676 passed, 87 skipped,
one failure in the existing valid-30m replay fixture. The isolated case and
34-test history file pass without a tick, but an explicit retention sweep
reproduces deletion of all four September fixture rows and the same 404.
Planner narrows this CI correction to test clock isolation: reuse the existing
freeze_buffer_clock helper and explicitly run the actual retention sweep in
all eight preferred/fallback cases. Retention and application code remain
unchanged. The forced-sweep test first fails (retention-test-red.log/.exit);
final targeted history/native verification and new-head CI precede installation.

Verifier: corrected history/native two-file run passes65 / 40.31s, exit0
(retention-and-native-green.log/.exit); whole-tree Ruff and diff checks pass.
All eight replay candidates now run real retention at their fixture clock.
Await the new exact-head full CI; no Startup files have been installed.

## Windows startup release and configuration acceptance — 2026-10-07 UTC

Final CI37692512030 completes successfully at 22:47:02 UTC: 3677 Python
passed/87 skipped/8 warnings, 3113.60s, and380 frontend passed. Linux skips
31 native Windows cases; the actual Windows run above passed31 and final
history/native run passed65. Normal match-head squash merges PR #164 at
22:50:18 UTC as c4ebee4. Candidate00be634 and merged trees both equal
47407bc9ad88f300e8a57f2a56865dbc6d5ad462; no force/admin merge.

Only exact committed scripts are extracted to an ignored reviewed directory.
Installation verifies signed existing GUI and writes current-user
LocalAppData/QuantMesh/OpenDRecovery plus the fixed Startup shortcut.
Installed supervisor SHA256:
9D9E19F735096EF32A3BA28B816ED348CC20D127029CCC97ECE24DF9CD20DE9B.
Shortcut executable/arguments/working directory match the owned manifest.
The hidden helper stays alive with mutex held; a second launch returns
duplicate_helper/exit0. Initial Start-Process witness could not observe the
exit code; direct owned .NET Process observation corrects the fixture without
changing runtime scripts or launching another long-running helper.

Actual OpenD PID28036 and all pre-existing CLI processes are preserved;
session75590 remains running. ObserveOnly confirms AWS loopback11111 and
health confirms exact69515b7/paper=true/live=false after installation.
An isolated real-shortcut install/uninstall/reinstall/removal witness passes,
mocking only its lack of a helper; actual current-user Startup stays installed.
Vendor auto-login is unchanged; a future human login may still be required.
No Windows logoff/reboot or true network outage is manufactured.

Evidence under output/0037-opend-startup/: ci37692512030-success.log,
reviewed-merge.json, actual-installed.json, actual-launch.json,
actual-startup-witness.json, actual-aws-after.json and
isolated-reinstall-witness.json. Configuration acceptance is complete;
actual next-login/outage and equity open-session revisions/two new minute
boundaries are pending. Do not repeat merge/install/deploy while waiting.
