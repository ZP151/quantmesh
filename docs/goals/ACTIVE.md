# Active Goal

Status: iteration 0034 implementation and AWS acceptance complete, 2026-09-12.
Repository closeout is tracked by the acceptance PR linked to #140/#135.
On resume, verify its merge and issue closure before marking the goal tool complete.

## Completed checkpoint

- PR #142 merged as `e185c3b052ca0cdd3590b0d5d05fd7460d783fb7`; final-head
  CI34687576761 passed 3443 Python / 55 skipped and 336 frontend tests.
- Exact merged build is active at the private AWS `/app/cockpit` route.
  BTC/ETH/SOL actual-source API witness ran 304.88 seconds, 60 distinct source
  times each; browser witness spans 323.567 seconds with replay/reload accepted.
- Paper mode true, live trading false; risk/orders unchanged. Retained demo
  rollback `402294248406fa865d601633f4e5ba3bd3521b5b` remains available.
- Evidence: `docs/iterations/0034-live-data-delivery.md` and its tracked JSON/JSONL.
- Goal archive: `docs/goals/archive/2026-09-12-deployed-live-market-data.md`.

## Next frontier

- Follow `docs/ITERATION_PLAN.md`: Moomoo/OpenD private reachability and actual
  quote entitlement first, then one AAPL/NVDA API-to-page observation slice.
- Identify the existing licensed OpenD host and approved private AWS route;
  Windows-local OpenD is not implicitly reachable by AWS. Preserve explicit
  five-second polling, closed/delayed/unavailable states and research-only
  last prices without bid/ask. No purchase, public OpenD or order test.
- Create the next issue/iteration and exact-file test-first plan after readiness
  evidence. Do not claim equities or prediction markets are accepted on AWS.
- Preserve the independent 0021 soak and operational worktrees. New branches
  start from `origin/main`; do not reset divergent local main. Standing reviewed
  merge authority remains in `.codex/prompts/goal.md`.
