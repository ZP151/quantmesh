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
Reviewer checkpoint follows after coherent green source commit; maximum two
independent rounds. Sole publisher owns final applicable broad CI and merge.
