# Worker snapshot serialization implementation plan

> Execute inline with executing-plans/TDD, followed by one fresh independent
> branch review. The operator already approved execution; no repeated design vote.

**Goal:** Prevent sibling attempt creation from invalidating valid snapshots (#185).

**Architecture:** One process-local lock protects attempt creation and existing
snapshot copying only. Original budget bounds waiting; OCI children remain concurrent.

**Tech stack:** Existing Python threading, pytest, POSIX fixture handles; no dependencies.

**Spec:** ../specs/2026-10-19-worker-snapshot-serialization.md

## Global constraints

Keep public signatures, two store-global slots, request/lease/publication fences,
all22 pins, limits and FD/ctime checks. No secret/vendor/server effects. No upstream
code copied. Paper/live defaults and numerical fee/spread/slippage semantics unchanged.

## Review focus

- Lock must precede recursive attempt mkdir, including shared job-root creation.
- Snapshot failure must release the lock for another job.
- A waiting stopped Worker must exit without snapshot/child creation.
- Waiting and preparation must consume the original job deadline.
- A completed snapshot must release before two execution starts rendezvous.

## Task 1: repair one bounded preparation slice

Files: src/quantmesh/research/job_runner.py; new
tests/test_worker_snapshot_serialization.py; iteration0038 checkpoint and this spec/plan.
Public run_next_job(store, owner, inputs_root, artifacts_root) remains unchanged.

- [x] Write deterministic two-thread real-POSIX snapshot regression: pause first
  copy after target handle acquisition, claim second job, observe no second
  job-root mkdir until release; both inert child starts rendezvous after snapshots.
- [x] Run new test on main source and retain expected failure (RED).
- [x] Add minimal private lock, deadline/stop-aware bounded acquisition, guarded
  mkdir/bundle/snapshot and finally release, with no later compute under lock.
- [x] Add failure/release, deadline/wait and stop/wait regressions; verify GREEN.
- [x] Run fixture snapshot, job runner, Worker execution/daemon regressions in
  the existing Linux tool environment; preserve unsupported Windows baseline result.
- [x] Run broad Ruff, affected formatting, whitespace and submodule checks; record
  existing unrelated failures without repairs. Commit coherent tested slice.
- [ ] Fresh independent whole-branch review (max2 rounds); fix bounded findings
  with observed regression evidence. Push own branch, open/attach PR, inspect
  required exact-head CI. Do not merge/deploy without new applicable human gate.

Verifier command: existing WSL venv python -m pytest
tests/test_worker_snapshot_serialization.py tests/test_fixture_snapshot.py
tests/test_research_job_runner.py tests/test_worker_execution.py
tests/test_worker_daemon.py -q --basetemp <fresh native-owned path>.

Acceptance: all new cases execute on POSIX, no unsafe mutation exemptions,
independent review/current CI evidence and explicit later native acceptance limits.
