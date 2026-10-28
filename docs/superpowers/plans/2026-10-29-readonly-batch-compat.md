# Readonly complete-row materialization — issue249

User action: inspect the saved history through the ordinary workstation API.
Success for this leaf: full selected records fit the unchanged engineering
128MiB/one-thread/no-spill contract instead of expanding unselected wide rows.
Actual native API success remains a separate merged-source acceptance gate.
Issue: https://github.com/ZP151/quantmesh/issues/249.

ACK22:13:46UTC; causal checkpoint22:33:46UTC; first increment00:13:46UTC;
reviewed handoff02:13:46UTC. Existing clean base0a047e8/tree7621e2c6,
codex/readonly-batch-compat. Same96MiB cohort/all failures/unknown holds retained.

- [x] Read safe native receipt: first111-key batch, EXECUTE, lexical default-temp
  root/READ_ONLY_FS; no actual syscall/spill/operator proof.
- [x] Bounded stored ZSTD control: current OR scan refuses one128MiB allocation;
  point-filtered UNION returns identical111x17 rows under unchanged128MiB/0B.
  Four-smaller-vector control passes both forms, isolating allocation amplification.
- [x] Test first: exact tracked regression function on retained owned fixture
  actually fails at real `_tail_rows`1134 with OOM before source change.
- [x] Replace only complete-row predicate construction with at most128 UNION ALL
  independently bound point branches; preserve lock/snapshot/ownership/key query,
  missing/duplicate refusal, final sort and decoding.
- [x] Run exact regression GREEN with independent all17-field formula oracle;
  affected boundary/transaction/error tests and normal default-tail verification.
  Update only assertions made obsolete by the new bound-parameter layout.
- [x] Targeted Ruff/format/whitespace, independent whole-source R1 READY and frozen
  runtime/test hashes for the tested local commit. Final immutable handoff carries
  any second and last freeze review receipt; no implementation change follows R1.

Files: live/buffer.py, necessary buffer tests, this plan and own iteration.
No UI/policy/accounting/schema/deps/CLI/global-doc edits; no source copying,
license change, host/real archive/new API/SDK/model/SPY/OOS/financial experiment,
temp/permission/memory relaxation or partial/empty success. Quant semantics and
paper/live authority do not change. Build compression is synthetic-only.

Verification uses existing WSL3.12.3/DuckDB1.5.5/exact native extension in owned
private RO fixtures; cgroup512MiB/swap0/CPU50%, query128MiB/threads1/temp0,
external35s and CPU35s per targeted control. Fresh fixture forecasts precede
writes; no deleting/refunding/resetting roots. Tests may directly reuse the
retained owned model to avoid rebuilding its physical database. Logs distinguish
direct exact-test-function invocation from pytest fixture generation/counts.

Actual final compatibility checks: the active20MiB and32MiB generated-model
gates each pass once (22.36s/24.63s), resolving R1's CI-coverage uncertainty.
Publisher must run normal applicable CI without the earlier local exclusions.
The already retained portable fixture also refuses immutable base0a's helper
in a private-RAM differential control; the working source bytes remain unchanged.
Two isolated field/selected-key mutants are killed by the exact regression.

Release: author never pushes/polls CI/merges/deploys. Sole publisher runs exact
required CI/normal merge; sole operator tests original merged-source history API
and normal closure. Local OOM repair does not assert native I/O or Goal completion.
