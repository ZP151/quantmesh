# Contended snapshot-lock lease heartbeat plan

> For agentic workers: execute this single bounded task inline using TDD,
> followed by a fresh read-only reviewer and verification. Root's2026-10-22
> assignment approves the exact design/seams from R-CAUSAL-NEXT section5.

Goal: a valid owner waiting65s for the existing snapshot lock can reach exactly
one inert child constructor within its original90s attempt, while maintaining
the existing fenced60s lease at the existing15s heartbeat cadence.

Architecture: use the unchanged SQLiteJobStore/WorkerRunner interface. Only
after observed lock contention may the waiting loop call the existing heartbeat
method; every call stays behind stop/deadline checks. False returns the current
record without reviving a lease. No background thread or new diagnostics.

Spec/issue: https://github.com/ZP151/quantmesh/issues/198 and the explicit root
assignment of R-CAUSAL-NEXT section5. This is not attribution of the old exit3
or217.593s production result, and does not prove90s production recovery.

Files owned:

- src/quantmesh/research/job_runner.py: contended lock waiting loop only.
- tests/test_worker_snapshot_serialization.py: coherent local clock/real store,
  approved lock/snapshot/admission/inert-child seams and focused assertions.
- This plan and docs/iterations/0038-snapshot-lock-heartbeat.md.

Global constraints: lease60s, heartbeat15s, original attempt deadline, store/
schema/protocol, snapshot safety lock, constructor/copy/validation and frozen
worker_execution/worker_daemon/service runtime remain unchanged. No host, SSH,
Engine/provider, dependency install/scan, push, CI watch or production pair.
Use the existing WSL Python3.12.3/pytest9.1.1 runtime. Keep frontend207's writer
independent. Local source timebox85–90min from approximately18:09UTC.

Review focus: stop before renewal; expired/stale/cancelled fences; no renewal
on an uncontended lock; no deadline extension; original claim is not a fresh
lease sample. Test clocks replace module references, never stdlib globals.

## One task: real mechanism RED, minimum fix, durable checkpoint

- [x] Verify clean managed worktree from actual origin/mainaa62; consume issue,
  required docs, ownership and bounded design. Existing serialization4 tests
  pass in the unchanged source baseline.
- [x] Add one real store/runner regression: claimt0; actual repeated timed lock
  misses to65; read fresh store state at65; expect renewed lease and exactly
  one constructor/cleanup with no publication/outbox. Observe actual RED due to
  old expiry60, no constructor and normal runner return before any source edit.
- [x] Only if that RED holds, minimally renew in the contended waiting loop
  using existing heartbeat and stop/deadline fences. Re-run the exact test GREEN.
- [x] Add focused controls one at a time: uncontended invocation count, stop,
  deadline, cancelled job, legitimate reclaim with stale owner/attempt, expired
  fence refusal, and old-claim-negative/fresh-lease-positive distinction.
- [x] Run affected snapshot/stop/deadline/observation/store tests; full Ruff,
  changed-file format, whitespace and submodule checks. At commit boundary run
  the root suite in the existing Linux environment once with a finite budget;
  report every failure/timeout without expanding to unrelated repairs.
- [x] One fresh read-only complete-diff review, maximum two rounds. If the RED
  fails to establish the mechanism, scope requires store/thread/long-copy/
  constructor changes, or safety lock semantics cannot remain intact, stop and
  return the specific fact to Planner.
- [x] Record exact RED/GREEN, checks, hashes and limitations in the own iteration,
  create one immutable local commit, hand it to root/release. Do not push a head
  known to hit207 dependency-audit failures or deploy unmerged source.

Checkpoint disposition: bounded mechanism proven by RED/GREEN and R1 READY;
integration/release is blocked by unresolved verification. Final affected run
is138passed/21skipped/1failed (existing expiry-cleanup exception expectation);
the root suite timed out at600s. Preserve this local immutable checkpoint for
Planner/release-owner disposition. The completed checkboxes record performed
work, not a green-suite or production-completion claim. No further retry,
unrelated repair, push or deployment is part of this leaf.

Targeted command (existing runtime, no install):

`wsl.exe --cd /mnt/c/Users/15492/.codex-clean/worktrees/198-snapshot-lock-heartbeat/QuantMesh --exec /usr/bin/env PYTHONPATH=src:tests:. PYTHONDONTWRITEBYTECODE=1 /var/tmp/quantmesh-backup-final-xvcv1u9k/venv/bin/python -m pytest -q tests/test_worker_snapshot_serialization.py`

Release owner remains responsible for minimum combined normal CI, review/merge
and any later exact-source/resource admission. New complete source may exceed
the remote parent's remaining capacity; this local leaf does not raise caps or
delete evidence. A later production pair requires a causal fix and all gates.
