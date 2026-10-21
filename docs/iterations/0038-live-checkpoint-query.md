# Iteration0038 — checkpoint query-only leaf

Issue: [201](https://github.com/ZP151/quantmesh/issues/201).
Base:28221e1bb87ccf0a13ddbccb7e156f9bc4945eab; branch codex/live-checkpoint-query.
Plan: [checkpoint query](../superpowers/plans/2026-10-20-live-checkpoint-query.md).

Planner/Quant: one operator outcome is loading the same durable checkpoint events
without a historical wide-row window. A single grouped winner row preserves
sequence ordering and stream identities. This does not validate production
latency, diagnose the old outage, qualify research observations or enable live
trading. No projection/schema/retention/threading changes are in scope.

## Implementer

Only recovery_checkpoints changes: one arg_max of an explicit17-field struct
per unchanged stream partition, with filters applied before aggregation and
ordered by winning local_seq. Nullable fields and whole payload/identity/evidence
come from the same unique sequence winner. Original parameters, synchronous
contract, RLock, row mapper and transaction boundaries are preserved.
latest/retention/schema/indexes/ingestion/cursors/cache/threads are untouched.

The actual imported WSL source path and hash are pinned in
`output/0038-live-checkpoint-query/source-and-plan-receipt.json`. Windows git
exported original buffer hash651ba1d5877fe392142d13d63cfddc7824da02c1825cf4059c891430a575c295,
matching deployed69515 buffer bytes. The verifier confirms original/current text
outside recovery_checkpoints is identical. No upstream source was copied.

## Verifier phases

Evidence directory: `output/0038-live-checkpoint-query/` in this isolated worktree.
Interpreter: existing `/var/tmp/quantmesh-backup-final-xvcv1u9k/venv/bin/python`;
actual DuckDB1.5.5. Windows git handles Git; WSL only runs the existing interpreter.

1. RED, before source edits: `red.txt` records the actual production method's
   real DuckDB EXPLAIN with a wide-row ROW_NUMBER WINDOW; the new plan gate fails.
   With semantic fixtures added, `red-with-semantics.txt` is1failed/8passed.
2. First GREEN: `green-focused.txt` is9passed/3.99s. Frozen pre-change query
   executes against the same tiny real lake; independent expected event objects
   and ordered JSON match. Cross-venue/instrument/kind/channel, provisional and
   disrupted candle exclusions, quarantine, sparse sequences, null fields,
   timestamps, L2 epochs and entire row winners are covered.
3. Affected gate: `green-affected.txt` is161passed/24.63s across live buffer,
   lookup, feed, supervisor and new checkpoint tests. Five existing NumPy generic
   timedelta deprecation warnings are retained. No failures were hidden.
4. After test-data additions for remaining disrupted continuity states and
   formatting, final focused `green-focused-final.txt` is9passed/4.08s. No second
   affected-suite run: root owns normal broad commit/PR gates.
5. Actual new plan captured at2026-10-20T14:19:51Z in
   `green-checkpoint.plan.txt`: one SEQ_SCAN, grouped arg_max, zero WINDOW.
   This is physical plan evidence, not a source-string assertion. Actual loaded
   buffer SHA is a98ac5d2abc431c36f2dd871f1e195de74510ff2645559831dbd424b7f25aa12.
   No index access, throughput/latency threshold, original production root cause
   or retained-history live recovery is claimed.

Commands (from this worktree, through the existing WSL interpreter):

```text
python -B -m pytest tests/test_live_checkpoint_query.py -q -p no:cacheprovider
python -B -m pytest tests/test_live_buffer.py tests/test_live_buffer_lookup.py tests/test_live_feed.py tests/test_live_supervisor.py tests/test_live_checkpoint_query.py -q -p no:cacheprovider
python -B -m ruff check src/quantmesh/live/buffer.py tests/test_live_checkpoint_query.py
python -B -m ruff format --check tests/test_live_checkpoint_query.py
python -B -m ruff format --check --range 650-710 src/quantmesh/live/buffer.py
git diff --check
```

Ruff0.16.6 reports pre-existing formatting differences elsewhere in buffer.py;
that first check is retained in the handoff, and only the changed method was
formatted. Lint, new-test format, changed-method format and whitespace pass.
Full-file/global formatting is not asserted and unrelated lines were not changed.

## Reviewer handoff and limits

Independent review round1 is READY, with no blocking finding. The reviewer
verified the frozen source/test hashes, complete row/null/timestamp/channel/filter
semantics, unchanged lock/mapper/method-external text, actual tests and plans.
No161-test rerun was used for review. Automated READY does not supply human review.

Root's full Ruff, whitespace and submodule-status commands exit0; all nine
submodule pins remain unchanged/uninitialized. The first local full pytest
attempt was incomplete: stopped after341.19s with partial failures. A narrow
failure probe and child import probe exposed missing inherited PYTHONPATH for
subprocess tests (`ModuleNotFoundError: quantmesh`). It is not counted as a pass
or as a production-source regression. Raw output remains in root-pytest.txt and
root-one-broad-failure.txt. One corrected full check passes explicit source/root/
service PYTHONPATH to children and stops at the first failure; it is running at
this draft checkpoint. Exact Linux release CI is required before merge.

Source/tests remain frozen. The draft commit/PR exposes the reviewed change and
starts its normal CI; broad validation and Class B human implementation review
remain merge gates. No integration, deployment, original lake scan/write, new
dependency/index, provider/model/OpenD call or R-source edit occurred.
The query still scans history and can block synchronously on I/O or RLock.
Formal production acceptance and original90s recovery acceptance remain open.
