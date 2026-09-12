# Active Goal

Status: iteration 0035 chart PR merged/deployed; actual-source acceptance failed,
bounded follow-up correction in progress, 2026-09-12.

## Current user outcome

Open BTC/ETH/SOL from Markets or Watchlist on AWS and see the existing full-size
chart update from real venue observations. Default to 1D/line, preserve candle
switching and explicit range choices, and show actual source/time/coverage.

- Issue: https://github.com/ZP151/quantmesh/issues/144
- PR: https://github.com/ZP151/quantmesh/pull/145 (merged as `90fe577`).
- Iteration: `docs/iterations/0035-live-instrument-charts.md`
- Plan: `docs/superpowers/plans/2026-09-12-live-instrument-charts.md`
- Follow-up branch: `codex/0035-chart-acceptance`, from `origin/main@90fe577`.
- Final CI 34700259858 passed exact candidate `7230c68`: Python 3486 passed /
  56 skipped, frontend 359 passed. Merged tree is identical to the tested tree.
  Exact `90fe577` is deployed; independent health/profile/pip/service checks
  passed, loopback/private access and paper true/live false preserved.
- Actual browser attempt 1 passed six entry paths, three moving full charts,
  matching received candles, reload, keyboard and desktop/mobile checks. The
  parallel continuous API gate FAILED after the collector stopped at
  15:45:47 UTC from a different BTC metrics identity collision. Early chart
  movement and HTTP health are insufficient. Current build remains unaccepted.
- Preserve **four** quarantine entries: three prior final-candle collisions
  and the new metrics collision. Stable evidence copy is
  `/tmp/quantmesh-0035-stalled-lake-821r_gz_`; do not restart repeatedly or erase
  evidence. Actual browser/API artifacts: ignored
  `output/playwright/0035-aws-90fe577/attempt-1`.
- Planner reduced follow-up: Task 3a corrects full-precision, content-qualified
  local-observation identities for Hyperliquid activeAssetCtx/allMids; Task 3b
  captures workspace clock and detached quote/proof together before assembly.
  The latter has a public API RED reproducing false future-receipt degradation
  for a 329ms quote. Both need tracked RED/GREEN, independent review, final CI
  and a new deployed API/browser witness. Issue #144 stays open.
- Task 3a/3b implementation and fresh round-one spec/standards reviews are
  complete with no findings. Controller combined source/packaged-browser gate
  passed 342 tests in 49.14s; Ruff/diff/submodule checks passed. The next gate is
  the follow-up PR's full final-head CI, then exact merge/deploy and actual
  five-minute API/browser acceptance. Frontend assets/dependencies unchanged.
- User explicitly approved continued development and requested these real
  streaming charts; existing private AWS update follows reviewed/tested scope.
- Merged chart work includes exact 1m replay fallback, configured live entries,
  1D/line defaults, live following and closed-candle revision identity. Combined
  local 306 backend/packaged browser tests passed before the final green CI.
  Superseded cancelled CI runs are recorded in the iteration, never acceptance.
- Root owns docs/integration; separate bounded owners handle Task 3a and 3b
  files from the tracked plan. No UI redesign, watchdog, general time model,
  provider expansion, conflict suppression or execution change.

## Preserved completion and boundaries

0034 is complete: PR #142 / AWS `e185c3b`, acceptance PR #143 merged as
`2a50565`, issue #140 closed. Paper true/live false and private/loopback access.
Retain `e185c3b` live rollback and older `4022942` demo. #135 stays open for
operator-deferred firewall acceptance; do not change its rules. Preserve 0021
soak and independent worktrees; never reset divergent local main.

Next after this user-requested chart slice: existing licensed Moomoo/OpenD
host, approved private AWS route and quote entitlement, then AAPL/NVDA witness.
No new paid data, public OpenD, credentials or order tests. Standing reviewed
merge authority: `.codex/prompts/goal.md`.
