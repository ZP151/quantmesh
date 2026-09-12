# Active Goal

Status: iteration 0035 product acceptance passed; documentation closeout awaiting
review/integration, 2026-09-13 (local date).

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
