# Read-snapshot closure CI regression (#239 / PR240)

## Approved bounded scope

Root restored the original product owner on2026-10-28 under the human's standing
repair/check/normal-merge authority. Earlier sealed d0716c2 remains a checkpoint,
not a prohibition against repairing a newly discovered CI regression. This is a
new narrow regression slice, not a third structural review of the earlier leaf.

Actual ACK13:41:34UTC (21:41:34Singapore). Cause due13:56:34UTC; first verifiable
increment15:41:34UTC; reviewed handoff17:41:34UTC. One source writer, at most two
new independent review rounds; a third structural issue returns to Planner.

User action: start the existing workstation/feed, persist an accepted observation
and shut down cleanly after joining accepted I/O. Success: original failing
shutdown test passes unchanged, read APIs produce no write COMMIT signal, full
results and all transaction/snapshot/cancellation/refusal semantics persist.

Reuse current codex/latest-bootstrap WT/PR240 from d0716c2; do not duplicate PRs.
Source lock: LiveBuffer._tail_rows only. Necessary tests may add dedicated read
snapshot coverage and update its existing transaction-close comment. Own plan,
ADR0037 and iteration0038-latest-bootstrap may record the decision/evidence.
Do not change CommitGate or its existing shutdown/lifecycle tests, latest/replay
selection, limits, shared feed/API, math/data/budget, dependencies/configuration,
host/provider/SDK/archive, preview18765/helper/fixture or rc1. Original128MiB,
one thread, zero disk temporary space and read_only contracts remain fixed.

## Causal ruling to verify

Required CI40612112663 at d0716c2 reports6282pass/1fail/143skip. Original
test_normal_shutdown_joins_accepted_commit_before_clean_close fails before its
append scenario: LiveFeed ctor -> latest -> _tail_rows COMMIT triggers CommitGate.
Unchanged local reproduction01-original-red.log exits1 at the same boundary.

Both production callers (latest and tail replay) supply SELECT-only key queries;
the helper probes txid_current, owns BEGIN only in autocommit, and executes SELECT
for keys/complete rows under the existing caller-held RLock. Already fetched
Python rows survive read-only snapshot ROLLBACK. It cannot discard caller writes
because the caller-owned branch never closes the caller transaction. Candidate
28be4c2 is input evidence, not assumed correct. Prefer the minimal successful-own-
snapshot COMMIT -> ROLLBACK change if the following actual tests support it.

## Executable sequence

- [x] Read current docs/Git/PR/CI/raw publisher evidence and candidate. Verify
  authentication and exact failed head. Preserve all old logs and checkpoints.
  Reproduce original test before changes; report actual ACK/cause/scope to root.
- [x] Add tests/test_live_buffer_read_snapshot.py for actual owned DuckDB empty/
  populated latest/tail, readonly/readwrite, no read COMMIT, same full results and
  unchanged stored bytes; caller-owned commit/rollback remain caller decisions;
  successful-snapshot close errors/cancellation refuse without partial success.
  Run new tests against d0716c2 and retain real RED separately from existing RED:
  `python -m pytest -q tests/test_live_buffer_read_snapshot.py`.
- [x] Change only successful owned closure in _tail_rows to ROLLBACK; retain the
  exception cleanup, probes, snapshot, lock, batching, key/filter/order and caller
  ownership. Run new tests and unchanged original shutdown case GREEN. Existing
  small shared helper and relevant latest transaction/snapshot/fault cases verify
  shared replay/full-row consistency. No old wide-resource or full suite rerun.
- [x] Record exact commands/results and scope checks, Ruff/format/diff. Commit a
  coherent green checkpoint within60minutes. Reuse existing upstream packages;
  no copied external source, new rights/financial/trading authority or dependency.
- [ ] Independent narrow R1 (correctness/spec, read-only owner/caller semantics,
  faults/cancellation/shared replay), at most one aggregate necessary correction
  and final R2. Review does not reopen old structural scope. Update own iteration
  and ADR0037; seal exact reviewed HEAD/tree/hash packet in
  output/latest-bootstrap/ci-regression-20261028/.
- [ ] Send new exact head to root/sole publisher to update original PR240, rerun
  required applicable CI and normally merge. Publisher alone advances publication;
  native merged-source reader/feed/API acceptance remains sole server's gate.

Commands use existing global Python313/DuckDB1.5.5 and process-local PYTHONPATH
src;.; local software evidence is not native financial/archive qualification.
Do not alter tests to ignore read COMMIT or relabel the original CI failure.
