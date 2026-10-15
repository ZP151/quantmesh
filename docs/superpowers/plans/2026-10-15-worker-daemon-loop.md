# Persistent Worker Daemon Loop — Task 1

> **For agentic workers:** Implement only this bounded slice. Steps use checkbox syntax. Use test-first RED/GREEN. The root integration owner retains ACTIVE/iteration evidence updates.

**Goal:** A qualified Linux `WorkerRunner` can continuously claim registered jobs in exactly two independent slots, stop cooperatively without completing an interrupted lease, and fail-stop both slots on admission/runtime errors.

**Architecture:** Add a small daemon loop around the existing one-attempt `WorkerRunner`. Use a private `ContextVar[threading.Event | None]` and context-manager scope in `worker_execution.py` so `job_runner.run_next_job(store, owner, inputs_root, artifacts_root)` and `WorkerRunner.run_next_job(...)` retain their exact four-argument interface. The database remains the global concurrency authority; each loop verifies the current execution fingerprint before every claim.

**Tech Stack:** Existing Python threading/ContextVar, `SQLiteJobStore` for deterministic local lease/fence tests, existing `WorkerRunner`, registered fixture profile and test fixtures. No dependency or lock changes.

**Spec:** Root authorization in the 2026-10-15 delegated Task 1 handoff; `docs/iterations/0038-research-foundation.md`; `docs/superpowers/plans/2026-10-12-research-workers-workstation.md`; `docs/adr/0026*`.

## Global Constraints

- Public signatures stay exactly `run_next_job(store, owner, inputs_root, artifacts_root)` and `WorkerRunner.run_next_job(store, owner, inputs_root, artifacts_root)`.
- Add no `JobStore` method, protocol or schema fields. SQLite/PostgreSQL store remains the only authority for the global two-active-job ceiling and lease fencing.
- Daemon uses exactly two slots; owner IDs include a fresh process UUID and slot number.
- Refuse a missing `WorkerRunner.execution`; no native/default executor fallback.
- Re-measure `execution.runtime_fingerprint()` before every claim. Any admission/runtime failure stops all slots with one fixed sanitized daemon error; never tight-loop or swallow it.
- Reuse existing exact-container start/poll/close and child exit validation. Do not change Linux containment/admission policy.
- Graceful daemon stop and explicit user cancellation remain different: stop leaves the claimed job running under its lease without heartbeat/finish/cancel mutation; explicit cancel follows existing cancellation semantics.
- Preserve `fixture_only` and opaque native cache unverified claims unchanged. No math, request/report schema, Agent, live trading, CLI, deployment, DB protocol/schema, dependency, PR176, cloud, native OCI, or PostgreSQL integration changes.
- Each cooperative stop check immediately before an operation is its linearization point. An operation already entered may finish; once stop is observed, no subsequent heartbeat, child pulse, publication, or finish begins.
- Use the existing WSL CPython 3.12 environment only; no install. Retain each test's owned failure basetemp; do not delete it to rerun green.

## Review Focus

- Stop is already set before the daemon starts: no claim and no child. Test `test_worker_daemon_stopped_before_start_does_not_claim`.
- Stop arrives after claim or during a running child: no finish/heartbeat/cancel mutation; exact child closes; after 60 seconds LocalJobStore reclaims attempt+1. Test `test_worker_daemon_stop_leaves_claimed_attempt_for_lease_reclaim`.
- A child reports completion while stop is set before publication/finalization: no successful finish; any uploaded immutable blob stays unreferenced. Test `test_worker_daemon_stop_before_finish_leaves_no_authoritative_report`.
- A third-party claimant competes with both slots: store admits at most two active leases globally, not two plus the daemon. Test `test_worker_daemon_shares_store_global_two_slot_limit`.
- Admission changes before a claim: daemon exits with fixed sanitized failure and performs zero claims. Test `test_worker_daemon_admission_drift_stops_before_claim`.
- One slot fails while the other owns a child: shared stop is set, other child closes and both slot threads join; no arbitrary exception text escapes. Test `test_worker_daemon_slot_failure_stops_and_joins_sibling`.
- Nested, cross-thread and exceptional scope exits restore both `_execution` and `_stop_event`. Extend `test_context_resets_on_exception_nested_default_and_independent_thread`.

---

## Files and responsibility

- Create `src/quantmesh/research/worker_daemon.py`: fixed two-slot loop, unique owner IDs, shared stop, store-wide concurrency reliance, sibling stop/join and fixed sanitized failure.
- Modify `src/quantmesh/research/worker_execution.py`: private stop `ContextVar`, context-manager scope that sets/resets its token, and no change to public `WorkerRunner.run_next_job` signature.
- Modify `src/quantmesh/research/job_runner.py`: read the private scoped event; honor it before claim, immediately after claim, before starting/polling the child, after every child poll, before publishing, and before `store.finish`; interrupted work returns without heartbeat/finish and existing `finally` closes the exact owned child.
- Create `tests/test_worker_daemon.py`: deterministic threaded tests with real `SQLiteJobStore` lease/claim/finish behavior and existing research fixtures. Use fakes only for execution timing/control; do not fake away the store fence or lease behavior.
- Extend `tests/test_worker_execution.py` for private stop-scope reset, cooperative boundary races, and sibling-owned-child cleanup.

## Task 1: Two-slot daemon with cooperative stop

- [x] Write the focused RED tests in `tests/test_worker_daemon.py`: stopped-before-start zero claims; two distinct slot owners; stop-after-claim with actual `SQLiteJobStore` showing attempt 1 remains running and attempt 2 is claimable only after lease expiry; post-upload stop cannot create an authoritative report; global third claimant remains blocked at two active leases; admission drift prevents claim; slot failure stops and joins its sibling.
- [x] Run only the new tests in the existing WSL environment and preserve the failing basetemp. Expected RED: module missing or behavior assertions fail, not collection/setup errors.
- [x] Add `_stop_event` plus private context manager in `worker_execution.py`; set/reset with token restoration in `finally`, including nested/exceptional use. Do not alter either four-argument public call signature.
- [x] Add `WorkerDaemon` with two worker threads. Each slot has a random process UUID plus slot ID, refuses absent Linux execution, verifies the live runtime fingerprint before each claim, and executes one existing four-argument `WorkerRunner.run_next_job(...)` inside the stop scope. An idle slot waits on the event for exactly one second. Any slot exception sets shared stop, joins the sibling and raises only the fixed sanitized daemon error.
- [x] Update `job_runner.py` to observe the scoped event at each defined boundary. Stop before claim does not claim; stop racing after claim leaves the current lease untouched; stop during execution closes through the existing `finally`; stop before finish never calls `finish`. No stop path may mark a job failed/cancelled or heartbeat it.
- [x] Run the new focused tests and the amended context-scope test. Expected GREEN: actual store lease/attempt/fence assertions pass; no API signature changes.
- [x] Run focused affected tests once: `tests/test_worker_daemon.py`, `tests/test_worker_execution.py`, and `tests/test_research_job_store.py` in the WSL CPython 3.12 environment. Do not run the full suite or repeat the historical 159-test run.
- [x] Run Ruff and formatting on changed Python files, inspect the diff and check submodules. Resolve at most two independent Spec/Quality review rounds. Any third structural failure returns to the root owner for scope reduction.
- [x] Commit one coherent green checkpoint and push `codex/0038-worker-daemon-loop`; do not open a PR, merge, deploy, or update root ACTIVE/iteration records.
- [x] Save `output/0038-worker-daemon-loop/HANDOFF.md` and `checked-summary.json` with source HEAD, commit, exact command/count evidence, scope, and explicit not-done items (native OCI, CLI, PostgreSQL/cloud, deployment).

## Acceptance

A caller can build a `WorkerDaemon` with a current, explicitly bound Linux `WorkerRunner`, shared store and roots, then call `run(stop_event)`. It starts exactly two slots; the store never grants more than its existing global two active leases; each claim is preceded by current admission verification. Idle waits are event-interruptible at one second. A shared stop interrupts active work without publishing or altering terminal job state; expired leases are reclaimable as a new attempt under the real store. Any admission or slot failure stops both slots, waits for thread cleanup and exposes only the fixed error category. Existing API signatures, store protocol/schema, report bytes and profile labels remain intact.

## Stop condition

Stop after this reviewed/tested daemon slice, one coherent commit pushed to its own branch, and the two ignored evidence files are saved. No worker CLI, packaging, systemd unit, active iteration/root goal edits, OCI/PG/native/cloud operation, PR, merge or deployment.
