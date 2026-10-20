# Controlled-stop lease handoff — issue198

Issue: https://github.com/ZP151/quantmesh/issues/198
Plan: ../superpowers/plans/2026-10-20-controlled-stop-lease.md

Planner: actual human approved the concrete first-cause signal/owned-cleanup/
transaction-fenced lease-only exception on2026-10-20. Original failed pair and
90-second target remain unchanged. Design authority is consumed, not pending.

Quant researcher: this slice concerns synthetic operational recovery only.
No strategy promotion, new data, model call, accounting or order authority.

Implementer: source/tests are bounded by the tracked plan. A separate branch
from origin/main avoids changing PR199's reviewed inventory-only head. No
unmerged source is deployed; current Demo and original OpenD stay untouched.

Implementer evidence: store regressions observed7failed before the extension
and7passed afterward. Runner first failed because the stop token was absent;
with the token present, the expected handoff assertion failed1/7 before runner
wiring. Bootstrap signal-first regression failed1/2 before wiring. A further
observed-child-failure-before-signal regression failed as intended, then passed
after preserving that failure indication.

Verifier: final affected WSL Python3.12 run passed123tests, skipped8 opt-in
PostgreSQL cases, one existing exchange_calendars/NumPy warning,78.39seconds.
This covers stores, actual runner/owned-process interfaces with fake Engine,
daemon, deadlines, snapshot serialization, bootstrap and service store tests.
Actual PostgreSQL integration and actual Engine cleanup are not newly certified.
An isolated native self-signal probe passed real SIGTERM/SIGINT while the main
thread held the reentrant stop condition; signal-first/failure-first remained
immutable. No services, provider calls or Engine access occurred in that probe.

Full Ruff src/tests/tools/service source/tests, all10 changed Python files'
format checks and git whitespace checks passed. Submodule pins are unchanged
and uninitialized in this worktree. An initial combined pytest invocation failed
conftest import of test_research_jobs; adding the explicit existing tests path
fixed the harness, without installation or dependency changes. Missing local
Windows venv Ruff path and two initial formatting findings were corrected by
using the existing WSL runtime and formatting the changed tests. Raw evidence:
output/0038-controlled-stop/{runner-red,runner-behavior-red,signal-red,
poll-failure-red,affected-final,native-signal}.txt.

Reviewer: fresh independent read-only complete-diff review returned READY with
no actionable findings in round1. It explicitly checked signal reentry,
first-cause freezing, cleanup-before-handoff, failure exclusions, transactional
fences, both PostgreSQL inheritance paths and unchanged protocol. It did not
claim native Engine or PostgreSQL acceptance. No second or third review loop.

Required full CI is owned by the existing release owner, not duplicated locally.
New exact-diff ClassB human review and CI green remain merge gates. Source
implementation is reviewable; production pair recovery is still not accepted.
