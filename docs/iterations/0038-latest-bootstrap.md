# Iteration0038 — latest read-only bootstrap (#239)

Issue https://github.com/ZP151/quantmesh/issues/239. Plan ../superpowers/plans/2026-10-28-latest-bootstrap.md. User outcome: ordinary saved-history startup can hydrate every latest stream using the same read-only/resource contract; no data/math/permission change. Root authorizes the narrow repair after a newly staged diagnostic, not a replay of the prior type-only failure.

Planner: new ACK2026-10-28T00:38:32Z; cause00:53:32, RED/GREEN02:38:32/reviewed04:38:32. Fetched origin/main B6; new codex/latest-bootstrap WT. Only buffer.latest runtime lock plus new tests/own docs; running merged-preview18765/helper/fixture and all old failures stay untouched. No new Goal/timer/host/provider/dependencies or source permission.

Quant: infrastructure reading only; no new observations/prices/qualification/strategy or execution authority. STATUS/channel/source identity, all winners/full fields and temporal order preserved. Resource improvements and native success are separate claims.

Investigator: native new stdout5442d123... proves buffer ctor/enter returned, then feed.py304 -> buffer.latest1180 _duckdb.IOException with safe readonly/open categories; reader closed. C++ operator and physical spill unknown. Source128MiB/1thread/temp0 configuration unchanged and verified locally. latest combines group-MAX with payload JSON CASE, wide IN probe and ORDER BY. Existing _tail_rows alone is insufficient in controls.

Local controls (DuckDB1.5.5, own fixtures only): 01stored DB133967872B: original128PASS1217, helper128PASS;32/20bothOOM.02stored40/48/64 key-onlyPASS but old/gather bothOOM;03stored96bothOOM, tiny generated-view CASE key/old/helper allOOM even128.04disjoint kind scalar selection+existinghelper returns1217 at generated-view128 and32; stored128PASS/96stillOOM. No new connection/spill relaxation; all failures retained. These are local layout controls, not the original native operator proof. No further calibration loop planned.

## Implementer and verifier checkpoint

Runtime diff is only LiveBuffer.latest. Ordinary/NULL-kind, L2-side and metrics
category branches select the original scalar winners, then reuse unchanged
_tail_rows under the existing lock. No settings, helper, feed/API, permission,
dependency, data source or runtime preview changes. ADR0037 records this choice.

Commands use existing global Python313/DuckDB1.5.5 with process-local
PYTHONPATH=src;. and worktree codex/latest-bootstrap. Logs are retained in
output/latest-bootstrap (ignored execution evidence, not upstream data).

- 05-red.log:12failed/3passed. Real readonly LiveFeed on the persisted generated
  VIEW raised OOM at frozen original latest1180 with unchanged128MiB/1thread/0B.
  Fixture mistakes also failed: inconsistent gap flags, invalid final mid-null
  winner, too-small cap refused during SET, and writer-constructor legacy identity
  migration. These are recorded separately from the causal product RED.
- After fixture corrections,06-red-validated.log:6failed/9passed. The genuine
 128MiB public-path OOM and four second-batch fault assertions still failed under
  original latest. Remaining snapshot mismatch came from the test writer's legacy
  migration, confirmed in07-snapshot-red.log. Canonical digest fixtures fixed it;
  production migration code was not changed.
- 08-green.log:15passed in16.50s after the latest-only change. Full independent
  oracle1217 models, real readonly feed constructor and all then-present dedicated
  semantics/snapshot/fault tests passed.
- 09-targeted.log:69passed/2deselected in28.06s. Command:
  `python -m pytest -q tests/test_live_buffer_latest_bootstrap.py tests/test_live_buffer_batched_tail.py tests/test_live_buffer.py -k 'not wide_default_tail and not bounded_memory_for_a_large_lake'`.
  This includes the new invalid-channel refusal/caller-success tests and existing
  small buffer/helper tests. The two prior wide-resource controls were excluded;
  no old broad history/math/Windows/native suite or host probe was rerun.
- 10-query-proof.log: frozen B6 original latest extracted by AST from the fetched
  Git source, then both old/current invoked against the same owned readonly VIEW
  and stored fixtures. Actual SQL, bound parameters, EXPLAIN JSON and exact settings
  captured in actual-query-proof.json. VIEW oldOOM/currentPASS1217; stored bothPASS
  with equal full-model SHA256
  57311c6ca7b4ce456a1a73e17d0fee79c18b88e6c0b7694ceae204ff6562442c.
  Both fixture hash/mtime signatures and directory contents unchanged.
- Current actual key plan removes payload_json from ordinary-kind grouping. The
  first complete-row batch has no wide hash join/order;1217 winners use one key
  plus10 payload queries, with no result/key truncation. No C++ native inference.
- 11-full-fields.log:19passed in15.34s after enriching the stored oracle with
  non-null epochs/canonical digests/disruption evidence and asserting all raw17
  retrieved columns as well as ordered decoded models. Command:
  `python -m pytest -q tests/test_live_buffer_latest_bootstrap.py`.
  This is the final dedicated-test checkpoint before independent review.

The same broad research Goal remains active under root ownership. This leaf
improves ordinary startup hydration; actual archive/native startup and the
subsequent API/history acceptance remain pending. Preview18765 stays running.
Sole publisher owns final applicable broad CI and merge.

## Independent review and author handoff

Green source checkpoint709088a587a199b925075666a559d8df1a108697,
tree7d7c2a05ea8f1dd31ff99c940f1466adca8ee36c, pushed to
origin/codex/latest-bootstrap. Independent read-only whole-slice R1 returned
READY with no actionable spec/correctness/quality findings. Reviewer independently
ran19 dedicated tests:19passed in16.70s (review-r1-pytest.log; author read the
actual output). No source or test changes followed that checkpoint.

Scope verification13-scope.log compares baseline/HEAD AST after removing only
LiveBuffer.latest: all other runtime AST identical; exactly five allowed tracked
files, clean worktree. Changed Ruff/format and diff checks pass. New-source test
and source hashes remain fixed through the final review/handoff; only these own
docs record R1. Final sealed HEAD/tree, file/evidence SHA256 manifest, independent
review receipts and root handoff are in output/latest-bootstrap/HANDOFF.md and
manifest.json. Final sealed-head read-only review may confirm that docs-only
checkpoint without adding source scope; no third review round is permitted.

Author deliverable is the reviewed narrow repair and reproducible local evidence.
Root receives the immutable branch/HEAD for sole publisher's applicable CI and
normal merge, followed by sole server's merged-source native/API reacceptance.
No author PR/merge/host rerun is substituted. Native startup remains pending;
the complete original QuantMesh research Goal is not declared achieved.

## PR240 required-CI regression — original owner resumed, 2026-10-28

Planner: root's roadmap audit restored this owner under the human's standing
repair/check/normal-merge authorization. Actual ACK13:41:34UTC (21:41:34Singapore);
cause due13:56:34UTC, increment15:41:34UTC, reviewed handoff17:41:34UTC. Scope is
one new narrow CI regression, not a third structural review of the earlier leaf.
The original sealed d0716c2/earlier HANDOFF are preserved checkpoints. New plan:
../superpowers/plans/2026-10-28-read-snapshot-ci-regression.md. Same issue239 and
existing PR240; no duplicate PR. Only _tail_rows, necessary tests and own docs.

Quant: infrastructure transaction closure only. Selection/math/observations,
costs/rights/qualification/confidence and Paper/live authority do not change.
Existing128MiB/one thread/zero temp/readonly/budgets remain fixed. No preview18765,
fixture/helper, host/SDK/provider/archive/dependency or old source operations.

Investigator: actual GitHub PR240 still points to d0716c2. Required CI40612112663
at that exact head had6282passed/1failed/143skipped in full pytest. Only failing
test_normal_shutdown_joins_accepted_commit_before_clean_close enters LiveFeed
constructor -> latest -> _tail_rows:1144 COMMIT; CommitGate blocks before the
actual accepted-write/shutdown scenario. Original local unchanged reproduction
also fails at the same stack. COMMIT on a pure read is legal SQL, but exposes a
write-commit signal at initialization. This is an observable lifecycle regression,
not new evidence about the native filesystem IOException.

Both production callers of the private helper (latest and tail replay) supply
SELECT-only key queries; gathering also only SELECTs. Existing RLock covers the
probes/BEGIN/query batches/end, so no writer can enter the connection between
ownership detection and closure. Caller-owned transactions never enter that
closure. Rolling back the owned read-only snapshot discards no writes and leaves
already fetched complete Python rows valid. Exception cleanup remains unchanged.
Publisher candidate28be4c2 was inspected as a proposal, not accepted as proof.
Cause/scope reported to root within the15minute limit.

Implementer: minimally replace successful owned COMMIT with ROLLBACK and explain
read-only closure. Only an existing small helper test's transaction-close comment
changes; original shutdown and CommitGate/write-observation files remain byte-
identical. New tests reuse existing real tiny-DuckDB fixtures and row/observer
helpers. No fake successful query/transaction or weaker observer is introduced.

Verifier evidence in output/latest-bootstrap/ci-regression-20261028:

- 01-original-red.log/.exit: unchanged original shutdown test,1failed/7.34s,exit1.
- 02-snapshot-red.log:12failed/4passed against original helper;4 failures were
  new-test fixture mistakes (Windows denies raw DB reads while RW connection
  holds it), kept separate from causal read-COMMIT failures. 03-first-green.log
  actually has4failed/13passed: original shutdown passes with candidate, while
  those four new fixture cases still fail. The filename is not a GREEN claim.
- New-test-only correction hashes readonly DB bytes before opening and after
  closing; RW cases assert actual SELECT-only SQL/full results. No production
  permission/open/lock behavior or existing lifecycle test was changed.
- 04-corrected-red.log/.exit: corrected tests plus original shutdown run against
  the exact d0716c2 helper extracted from Git AST in frozen-red.py;13failed/
  4passed/10.18s,exit1. All8 owned-read variants emit unwanted COMMIT;4 close-fault
  cases cannot exercise read rollback; original shutdown fails. Caller cases pass.
- 05-targeted-green.log/.exit:39passed/1old-wide-deselected/19.77s,exit0. This runs
  new16 tests, unchanged original failure, small shared-helper file excluding its
  old wide-resource model, latest snapshot/caller/fault cases, and two relevant
  accepted-I/O cancellation/stop cases. No broad old suite or host/native rerun.
- Changed-file Ruff/format and Git diff checks pass. Existing dependency warnings
  remain. The first real verifiable increment was reported at13:48:54UTC.

Reviewer gate: fresh independent narrow review follows the coherent GREEN
checkpoint; at most two rounds. Sole publisher updates original PR240/new exact
head and reruns required CI before normal merge. Prior CI failure remains failed;
native merged-source reader/feed/API acceptance remains sole server's gate.
