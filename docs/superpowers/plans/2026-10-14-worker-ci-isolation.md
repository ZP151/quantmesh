# Worker Linux CI fixture isolation

> For agentic workers: use executing-plans inline and one bounded independent review. This closes PR #175's actual release-gate failure without changing runtime semantics.

**Goal:** Restore independent Worker queue/publication/cancellation checks on Linux.

**Architecture:** Cache only the deterministic lake and direct baseline report at module scope. Give each test its own SQLite queue, artifact root and fake Engine files. Keep production lease/claim/admission code unchanged.

**Tech stack:** Existing Python, pytest and SQLite; borrowed existing WSL environment, no installation.

Issue #172 / PR #175 exact failed candidate `de06066`; CI `38574294649` failed with 4924 passed / 4 failed / 141 skipped. The missing-binding test queues a job but intentionally never starts it; the shared module store lets later cases claim that old job. Three outcome failures and the cancellation failure cascade from this same queue.

Planner ruling: preserve the original 8,876,772-byte baseline, previous conservative resource ceilings and failures. Allocate a new 6,000,000-byte CI-diagnostic/focused-test phase, cumulative ceiling 46,000,000 bytes from the previous 40MB ceiling. This includes the 97,387-byte original artifact ZIP, 603,511-byte pytest log, bounded test roots, source/docs/Git copies and receipts; keep C free >=50GB. Do not install environments/images or run a local hour-long suite. Kernel phase accounting remains separately preserved at 6,810,711 bytes; its native test is not qualified. No paid resources or production services change.

## One bounded slice

- [x] RED: use existing WSL Python to execute missing-binding then parameterized owned-publication cases, preserving the wrong-job failure and exit code with short tracebacks/cache disabled and a new owned basetemp.
- [x] Change only `tests/test_worker_execution.py`: split module immutable numerical data from function-scoped SQLite store/output fixtures.
- [x] GREEN: run the whole Linux test module including success, nonzero, OOM, cancellation, reclaim, binding drift, heartbeat refusal and unconfigured entry; also run affected job-runner/store tests. Use fresh workspace-owned basetemps, no global-temp deletion.
- [ ] Run Ruff/format/diff checks, bounded fresh review of the fixture isolation, then commit/push to existing PR #175. Update CONTEXT/ACTIVE/iteration with actual failure and focused evidence.
- [ ] Let the new exact-head CI run once; never re-run the old failed candidate or merge before CI/human gates.

Acceptance: each case claims the job it submitted; cancellation and stale-owner publication assertions remain intact. A fake Engine on Linux is interface evidence only, never native numerical containment or Worker admission. Entire Option A goal stays ACTIVE.

Verification: Linux module12pass/15.32s; affected job-runner/store50pass/21skip/29.80s; one existing NumPy warning per run. Narrow review clear. Retain the first local launcher timeout and affected WSL Git-path failure; corrected process-only Git binding is verified against real HEAD.
