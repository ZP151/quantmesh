# Snapshot-lock waiting lease — issue198 local mechanism leaf

Issue: https://github.com/ZP151/quantmesh/issues/198
Plan: ../superpowers/plans/2026-10-22-snapshot-lock-heartbeat.md

Planner: root explicitly assigns the single contended-wait mechanism on
2026-10-22, with existing15s heartbeat/60s fence and original attempt deadline.
The approved seam is real SQLiteJobStore plus real WorkerRunner, module-local
coherent wall/monotonic clocks, contended lock, snapshot/admission and inert
child. Source ownership is job_runner's waiting loop and the serialization
test file; frozen observation modules/store/protocol remain excluded.

Quant researcher: synthetic operational liveness only. No market dataset,
strategy/math/cost change, provider, accounting or order authority. A local
lease-wait defect does not identify the historical exit3/217.593s slow path.
Production90s recovery and formal retained-data live remain unaccepted.

Implementer: isolated managed worktree198-snapshot-lock-heartbeat, branch
codex/198-snapshot-lock-heartbeat from freshly fetched origin/main
aa62faeddd84c31887e43bf0dae532e649a4ecbe. Original worktrees/main are preserved.
No new package/environment, host change or production task is part of this leaf.

Verifier baseline: existing WSL Python3.12/pytest command passed the unchanged
serialization file:4passed/1existing NumPy warning/9.61s. No code was modified
before that baseline. RED/GREEN and final checks are pending; no completion,
review, CI or deployment claim is made at this planning checkpoint.

Implementer/Verifier RED: the new real-store/real-runner test failed as intended
before the source change,1failed/1existing warning/5.05s. At simulated65s the
fresh record still has expiry60, heartbeat returnedFalse, constructor count0,
running/attempt1 returned normally, no report or claimable analysis outbox.
Raw output/receipt: output/0038-snapshot-lock-heartbeat/lease-wait-red.{txt,json};
original runner SHA25633e79061991a6dce2a73b82818b31859c4fc6a66ed44420556654b291cf5657b.

Minimum source change:18 added lines in the waiting loop. Only after a timed
lock miss, renew at the existing15s cadence through the same store heartbeat,
behind stop/deadline checks. False uses the existing current-record return;
successful renewal returns to those checks before another acquire. Snapshot
locking/copy/constructor/validation,60s lease, schema/protocol and all frozen
observation files remain unchanged.

The exact same initial test bytes passed after this change,1passed/4.59s.
Initial RED/GREEN both pin test SHA39852f530e9163101de542bb417a167a718ea4b283acc55109e1947c8cd44291.
The65s waiter renews15/30/45/60 and receives the original prestart65 heartbeat;
constructor/cleanup each occur once. At lock acquisition the original claim
shows-5s while the fresh authoritative lease shows+55s. No publication occurs.
Subsequent focused controls pass: uncontended1, stop boundaries2, actual SQLite
expired/cancelled/reclaimed-owner/reclaimed-attempt fences4, original deadline
and an entered-renewal delay2. Raw outputs/receipts use those named labels in
the same output directory. These are one mechanism's controls, not the old gap
matrix or native/production evidence.

Initial Ruff found an unsorted test import and changed-test layout; imports/
format were corrected, then full src/tests/tools Ruff, changed-file format,
whitespace and unchanged/uninitialized submodule pins passed. Final affected
checks and fresh independent review are in progress; full CI remains with the
release owner. No host action, push, dependency audit waiver or deployment.

Reviewer R1: fresh read-only independent agent reviewed the complete bounded
diff and returned READY with no P1/P2 findings. This is not human review or
release approval. Report: output/0038-snapshot-lock-heartbeat/REVIEW-R1.md,
SHA25651c16bbf4a8ec1c8f5f8b27a0f6a2a14331a0d8f880f9a6e3be4be5eba44d56d.
Runtime SHA25690622134b1bb0529b550f6949db03fb4ac91478be7c534914f0d5660c1b76828;
test SHA2561d43078c51f8c10ad44196b15609418985cd2ee4e3fe7822ba23071b46ae4e46.
These bytes did not change during verification/diagnosis.

Verifier final status: NOT RELEASE READY. The entire final-byte serialization
file passed14tests; all10 new mechanism/control cases pass. First seven-file
affected run had3failed/136passed/21skipped: existing sibling-overlap barrier,
existing prerequisites deadline returning dataset_rejected, and WSL Git128.
The first two exact nodes then passed together. A second affected run had
1failed/137passed/21skipped/1deselected: existing controlled-stop cleanup=True
did not raise the expected exception; that run partly overlapped another
diagnostic pytest process. Namespace interference is a candidate only, not a
proven cause. No production or frozen implementation was changed to hide it.

The managed .git pointer contains a Windows path. Explicit actual Linux GIT_DIR
and GIT_WORK_TREE resolve the real worktree/base; no .git or runtime fingerprint
was mocked or rewritten. A native Windows probe instead failed collection for
missing pg8000. No package/environment was installed. A serial diagnostic
baseline loaded original runner SHA33e79061... before test collection, using
the existing real tests/store/runner; it passed129, skipped21, and explicitly
excluded the10new heartbeat cases. This did not reproduce the sporadic failures.

The final serial affected invocation uses actual Git-directory environment
parameters and no diagnostic plugin:138passed/21skipped/1failed in61.47s. Failure:
tests/test_worker_launch_deadline.py::test_expiry_cleanup_failure_records_timeout_and_stops_instead_of_claiming_cleanup
did not raise LinuxContainmentError. Its cause remains unestablished; no retry
or repair of excluded/frozen files followed. Raw receipt/output:
output/0038-snapshot-lock-heartbeat/final-affected-correct-git.{json,txt}.

The one actual root-suite invocation (`pytest -q tests`) reached the600s budget
without a final result; raw progress reached9percent. It is TIMEOUT600, never a
full-suite pass; the exact scoped pytest process was subsequently absent. Full
CI/audit remain unrun locally. Raw receipt/output: root-suite-all.{json,txt} in
the same directory. DIAGNOSIS.md preserves all earlier failures and clarifies
two imprecise diagnostic labels; the commands, printed execution-source hash
and raw receipts govern evidence, not a filename's label.

Planner handoff: preserve one local source checkpoint, with normal integration/
release held for the unresolved cleanup verification and incomplete broad gate.
Do not modify safety checks, frozen observation/execution modules or store to
make these checks green. Release owner can select a bounded diagnosis in an
appropriate independent Linux environment and combine the existing207 fix under
normal CI/review/merge. This leaf neither proves the old217.593s cause nor closes
the90s production recovery acceptance. No host, new task pair, live data,
provider/Engine, dependency scan, push, CI watch or capacity expansion occurred.
