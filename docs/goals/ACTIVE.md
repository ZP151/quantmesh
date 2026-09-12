# Active Goal

Status: iteration 0035 locally tested/reviewed; final PR CI and AWS acceptance pending, 2026-09-12.

## Current user outcome

Open BTC/ETH/SOL from Markets or Watchlist on AWS and see the existing full-size
chart update from real venue observations. Default to 1D/line, preserve candle
switching and explicit range choices, and show actual source/time/coverage.

- Issue: https://github.com/ZP151/quantmesh/issues/144
- PR: https://github.com/ZP151/quantmesh/pull/145 (open; final-head CI required).
- Iteration: `docs/iterations/0035-live-instrument-charts.md`
- Plan: `docs/superpowers/plans/2026-09-12-live-instrument-charts.md`
- Branch: `codex/0035-live-instrument-charts`, from `origin/main@2a50565`.
- User explicitly approved continued development and requested these real
  streaming charts; existing private AWS update follows reviewed/tested scope.
- Diagnosis: actual Hyperliquid candles are 1m; replay history currently rejects
  finer than 5m even for 1D. Default workspace 6M falls back to small detail chart.
  Markets has demo wording/empty marks and live decision-Watchlist is empty.
- Local gate: 143 backend/packaged browser tests, 359 full frontend tests, actual
  production build and API freshness passed. Local race and four external review
  boundaries corrected; independent reduced-batch review has no findings.
  Old CI 34697814465 / `940a74b` was cancelled as superseded, never a merge gate.
- Backend owns bounded resolution fallback and tests; controller owns shared
  live list, entry/default behavior, frontend tests and integration. Record
  actual RED/GREEN in iteration before declaring implementation complete.

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
