# Active Goal

Status: iteration0035 recovery ACTIVE, 2026-09-13 10:14 UTC. Actual acceptance
failed on5332a19; the bounded Task3a frontend correction is now tested/reviewed,
awaiting its new exact-head PR/CI, merge, deployment and actual AWS witness. Prior GitHub merge blocker is
resolved by operator merge; it is not the current blocker.

PR148 merged manually at09:39:11UTC as5332a19cb0458170ca8b3a6d69fa95157aac3aab.
Exact tree2549e8df6a4c8c674ceb20fec88f0e558254e109 equals tested candidate
7f8065357946b399c0cc75983af1d8b92b4f49e9. Required CI34747168953 passed3524 Python
and359 frontend tests; do not repeat that completed source gate.

Exact5332a19 deployed successfully through reviewed private helper; release
command exit0, PID44749 started09:43:53UTC, private loopback8765,
papertrue/livefalse. Original retained lake and rollback releases preserved.
Stable copied lake09:56:58UTC:896780 rows/sequence, index present, four old
quarantines unchanged; /tmp/quantmesh-0035-recovered-lake-778zbzvd.

Actual API witness attempt1 exited1 after16 completed rounds across~10min:
all source/workspace samples real/fresh, ten tail minutes each, but BTC had
only2 distinct closes within one sampled minute (required3). ETH4/SOL3.
Per-request latency list and final orders/risk comparison were not emitted
because final assertion failed; do not infer those gates. Browser attempt2
exited1 waiting20s for SOL chart in initial navigation; BTC/ETH paths passed,
sustained/reload phase never started. Sessions84521/72652 are terminal.
Artifacts: output/playwright/0035-aws-5332a19/attempt-{1,2}, partial-summary.json
and failure.json. User IAB BTC1DLine visibly showed real changing full chart;
that one page is not complete six-path acceptance.

Task3a bounds live Hyperliquid full-workspace refresh to5s after request
success/failure, refuses in-flight invalidation and targets exact query scope.
Other markets retain existing behavior. Six new RED/GREEN regressions,
107targeted and365full frontend tests pass; independent spec/standards reviews
have no findings. Typecheck/lint/API-client/production build and packaged chart
E2E1test17.41s pass. Prior PR148 CI must not substitute for this new change.
Paired actual AWS helper is being reviewed; it will capture API source checks
alongside three chart pages, preserve20s gates and always save failed evidence.
No new deployment or successful final acceptance at this checkpoint.

Current branch: codex/0035-sustained-chart-closeout, from origin/main5332a19.
Keep reviewed docs plus new failure checkpoints. Continue the active plan;
do not close144 or expand markets while full actual acceptance is unmet.
Historical9cfe1bc short acceptance below is not current AWS health.

## Accepted user outcome

Markets and Watchlist on private AWS open BTC/ETH/SOL in the full chart with
1D/line defaults and real Hyperliquid minute observations. Current candles
revise, new minutes append and reload retains recorded coverage. Actual source,
time, freshness and the explicit 5m-to-1m fallback remain visible.

- Issue: https://github.com/ZP151/quantmesh/issues/144
- Code PRs: #145 merged as `90fe577`; corrective #146 merged as
  `9cfe1bc8ff910792b3f8cb6928763b667ba2442a`.
- Exact deployed build: `9cfe1bc`; live market data, paper true/live false,
  service PID41909, loopback8765/private HTTPS. Deployment completed exit0.
- Corrective CI34704029214 passed: 3517 Python tests, 56 skipped, 9 warnings;
  frontend359 and install/audit/API/typecheck/lint/bundle gates passed. Reviewed
  candidate6dc6ec3 and merge9cfe1bc share tree
  `bafcff7e3ba027d2cb329f2e3bc239b8fe0a30e8`.
- Actual API witness passed313.748s/21samples: three real, fresh quote streams
  and available workspace evidence throughout sampling; orders/risk unchanged.
- Actual browser witness passed301.968s: all six entry paths, six tail minutes
  per coin,41/20/21 BTC/ETH/SOL DOM changes matched their own received frames,
  API point comparison, reload, keyboard,1440/390px and no page errors.
- Artifacts: ignored `output/playwright/0035-aws-9cfe1bc/attempt-1` (API) and
  `attempt-2` (browser). A first browser attempt hit the assertion default5s;
  the helper's intended20s assertion timeout was applied for attempt2. No
  product change or network substitution. These witness sessions are terminal;
  do not poll old handles or rerun deployment/CI to recover session output.
- Stable DB/WAL copy `/tmp/quantmesh-0035-stalled-lake-l3zrnx3z` contains270555
  accepted updates through17:07:32 UTC and the unchanged four old quarantines.
  Independent17:12:53–56 UTC health/workspaces remained real/fresh/available.
- Iteration: `docs/iterations/0035-live-instrument-charts.md`.
- Plan: `docs/superpowers/plans/2026-09-12-live-instrument-charts.md`.
- Closeout branch: `codex/0035-chart-closeout`, from `origin/main@9cfe1bc`.
  Review and integrate its evidence-only docs; close #144 after that gate.
  AWS already runs the accepted source tree; a docs-only merge needs no deploy.

## Evidence and boundaries to preserve

The first chart build90fe577 failed sustained acceptance after a metrics ID
collision despite moving charts. The correction qualifies local-observation
identities with full UTC time/content and captures workspace clock/quote/proof
together. Earlier failed witnesses and four quarantine rows remain intact.
Do not treat old failures as current state or HTTP health as source acceptance.
Controlled disconnect/gap/future tests are separate from actual source witnesses.

0034 completed via #142/#143; #140 closed. Retain e185c3b (prior live build with
the diagnosed identity limitations) and4022942 demo rollback. #135 remains open
for operator-deferred firewall acceptance. Preserve0021 soak, independent
worktrees and divergent local main. No new public access, paid subscriptions,
credentials, order tests, execution enablement or strategy promotion.

## Next bounded slice

Moomoo/OpenD readiness for AAPL/NVDA: identify the existing licensed host,
verify the approved private AWS route and inspect quote entitlement. Current
five-second polling is not native tick push. Open-session real observations,
delayed/closed/unavailable semantics and an actual page witness are required.
Local Windows default-port/process probes alone cannot establish remote OpenD
absence or entitlement. Await the existing operator readiness information;
do not infer credentials or expose OpenD publicly. Write the exact-file plan
and issue only once readiness is established. Prediction venues and qualified
history follow sequentially in `docs/ITERATION_PLAN.md`.

Standing reviewed merge/private-deployment authority remains in the user request
and `.codex/prompts/goal.md`; no further confirmation for this approved scope.
