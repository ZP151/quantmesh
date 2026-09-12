# Active Goal

Status: iteration 0034 approved and implementing; final integration, AWS activation
and real-source acceptance pending, 2026-09-12.

## Completed checkpoint

- PR #139 merged as `6ea9a1305b2b3eea28795ccb0059d6ebba82b769`; issue #138 closed.
- Final-head CI run 34628077408 succeeded: 3321 Python passed /55 skipped,
  325 frontend passed. Independent reviews and real frozen save/replay evidence
  are recorded in `docs/iterations/0033-forecast-outcome-scorecard.md`.
- This merge does not update AWS or establish live-provider acceptance.

## Next frontier

- Issue: https://github.com/ZP151/quantmesh/issues/140
- Design: `docs/iterations/0034-live-data-delivery.md`
- Delivery order: `docs/ITERATION_PLAN.md`
- Implementation branch: `codex/0034-deployed-live-market-data`.
- Integration PR: https://github.com/ZP151/quantmesh/pull/142 (CI pending).
- Executable plan: `docs/superpowers/plans/2026-09-12-deployed-live-market-data.md`.
- Authority: operator approved the proposed subsequent iteration, including the
  bounded existing AWS deployment update and public read-only Hyperliquid feed.
  No new AWS resources, paid subscriptions, credentials or public access.
- AWS fresh HTTPS/SSH probes confirm exact `4022942`, runtime demo, paper true/live
  false. Tailscale SSH identity check completed; approved server access works.
- Integrated staging9a177c6 locally; preserved original independent worktree.
  Explicit live profile/verified rollback and Hyperliquid protocol/freshness
  corrections are implemented. See ledger for test counts and RED/GREEN.
- #141 merged as `00a0ee0` at 2026-09-12 09:02:33 UTC. Its archive-head CI
  was still running when inspected; do not claim that run passed. GitHub auto
  merge permitted integration before that optional check completed. Wait for
  #142 final-head CI explicitly before its integration/deployment.
- Review: Standards/Spec correction confirmation passed for monotonic browser
  aging and checked automatic rollback. Inclusive candle end milliseconds are
  corrected; 45-second public parser smoke passed. Controller final gates: 311
  Python/333 frontend/7 fixture browser passed; full CI and AWS acceptance pending.
- Later external review produced four bounded corrections, scoped by Planner
  and verified: detail timer aging, disconnect veto, audited install constraints
  and strict BBO order count. Latest controller gate:326 Python/336 frontend/
  7 browser passed. See iteration ledger for RED/GREEN and dependency evidence.
- Local real-source witness passed: 302.13 seconds, 61 distinct source quote
  timestamps per BTC/ETH/SOL, zero disconnected samples, risk/orders unchanged;
  replay persisted after the temporary app stopped. This is not AWS acceptance.
- Next: inspect final-head CI/review for #141 then #142, integrate in order,
  finish approved AWS exact-build update after SSH authentication, and record
  the separate five-minute AWS source/browser witness. Temporary local app is
  stopped. SSH check session30832 completed successfully. AWS preflight: Python
  3.12.3, 54GB free disk, ~1.3GB available RAM, passwordless sudo, retained
  demo release and private Serve route intact. No AWS service change yet.
- Correct browser route `/app/cockpit` works in Edge and confirms the deployed
  demo/no-feed state. Earlier wrong-route errors are superseded. AWS-host public
  WebSocket probe received397 BBO frames in45.22seconds acrossBTC/ETH/SOL;
  this is host reachability, not deployed-app acceptance. Reuse the open Edge
  tab for the eventual exact-build browser/replay witness.
- Preserve paper mode and disabled live trading. Separate further Moomoo,
  Polymarket/Kalshi and trusted-history work into subsequent bounded slices.
- Continue from `origin/main`, preserve divergent local main and independent
  operational worktrees. Routine reviewed integration remains governed by
  `.codex/prompts/goal.md`; deployment authority is tracked separately in #135.
