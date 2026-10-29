# ADR0037 — Latest-state hydration through existing bounded gathering

Date2026-10-28UTC. Status: implemented local RED/GREEN; independent R1 READY;
publisher/native acceptance pending. Issue239; extends ADR0034.

## Problem and evidence boundary

The new staged reader diagnostic returned from constructor/enter and failed
inside the real LiveFeed hydration call to LiveBuffer.latest, at B6 buffer.py1180.
It captured DuckDB IOException with read-only/open-file categories and closed
the reader. The native C++ operator and any physical spill remain unobserved.
That diagnostic is separate from the earlier type-only failure.

Frozen B6 latest groups MAX(local_seq) with one payload-dependent channel CASE,
then joins the selected keys to complete rows and orders the wide result.
Owned local DuckDB1.5.5 EXPLAIN shows payload_json projected before grouping
even for ordinary kinds, plus a wide SEMI HASH_JOIN and ORDER_BY.
A persisted generated VIEW reproduces an OOM at production128MiB/one thread/
zero disk temporary space. A physically stored134MB control succeeds with both
versions at128MiB and still refuses the new path at96MiB. Local OOM is not proof
of the native filesystem failure's operator or a production-scale fix.

## Decision

Change only latest's scalar selection. UNION ALL three disjoint branches:

- Ordinary and NULL/unknown kinds group by venue, instrument and kind without
  reading payload JSON. NULL retains the original ELSE-group validation refusal.
- L2 snapshots additionally group by the original JSON side extraction.
- Metrics additionally group by the original mid-present category expression;
  JSON null and a missing mid retain their existing distinct SQL semantics.

Repeat the same bound optional venue/instrument predicates in each branch.
Each branch selects the original MAX(local_seq). There is no new global LIMIT,
channel reduction or source-identity deduplication. Unknown/invalid winners
still reach the unchanged decoder and refuse.

Reuse unchanged _tail_rows under the existing connection lock. It selects all
keys and gathers every complete17-column row in128-key batches using the existing
exact scalar membership and inclusive range predicate. It checks key/row
completeness and sorts by local_seq in Python. Its existing transaction probes
retain caller-owned transactions; otherwise one owned snapshot covers selection
and every batch. Cancellation/resource failures propagate without partial success.
No feed, API, schema, connection settings, dependency or upstream copy changes.

## Consequences and verification

The actual current query's ordinary-kind plan omits payload_json. Its payload
batch has an exact range/equality filter without the old wide join/order.
For1217 winners there are11 data queries (one key query and10 complete batches),
plus the existing transaction probes/BEGIN/COMMIT when owned. Three branch scans
and extra batch queries trade statement/scan overhead for narrower engine
materialization. The result and key lists still grow with stream count;128 keys
is a row-count bound, not a byte/RSS or arbitrary-payload guarantee. L2/metrics
still require payload JSON. Large payloads/storage may still refuse explicitly.

The real readonly LiveFeed call on the owned VIEW returns all1217 independently
derived full winners at unchanged settings, with no DB mutation or temporary
siblings. The physically stored old/current full-model fingerprints are equal.
Dedicated tests cover complete raw17-field winners including nullable fields,
epochs/digests/disruption evidence, filters, status barriers, revisions, channels,
more than10000 streams, concurrent writes, owned/caller transactions and faults.
Local plan/config and frozen-B6/current proof are in
output/latest-bootstrap/actual-query-proof.json; commands and retained failed
controls are in ../iterations/0038-latest-bootstrap.md.

Sole publisher owns applicable CI and normal merge; sole native server owns
merged-source reacceptance. The running merged preview and its fixture are
untouched. No new data rights, financial qualification, Paper/live authority or
completion of the original research Goal follows from this infrastructure leaf.

## PR240 CI follow-up: end owned pure reads without a write-commit signal

Required CI40612112663 on d0716c2 exposed an existing lifecycle observer during
LiveFeed initialization: latest now uses the shared _tail_rows, whose successful
owned read transaction ended with COMMIT. The unchanged accepted-I/O shutdown
test blocks that COMMIT before its append scenario. The original local test
reproduces the exact failure; it is not a native filesystem diagnostic.

Under the authorized narrow regression plan, successful self-owned snapshots
now end with ROLLBACK. Both production helper callers supply only SELECTs, and
complete rows are already fetched before closure. The existing connection lock,
single snapshot, batching/selection/order and exception cleanup are unchanged.
No caller-owned transaction is committed or rolled back; its caller still decides
the outcome of any pending writes. Accepted appends retain their actual COMMIT
and original observer/cancellation/shutdown behavior. Original observer tests are
unchanged. This supersedes only the shared helper's successful owned closure,
not the earlier latest selection or archive/resource/trading contracts.

Dedicated tests cover empty/populated latest/tail on RO/RW connections, full
results, SELECT-only statements and immutable readonly DB bytes; caller COMMIT/
ROLLBACK decisions remain independent. End-of-snapshot I/O/cancellation failures
must propagate rather than return gathered rows. Relevant existing replay/latest
snapshot/error and accepted-write lifecycle tests also pass locally. New exact-
head publisher CI and native acceptance remain separate unfinished gates; see the
regression checkpoint in ../iterations/0038-latest-bootstrap.md.

Independent narrow-regression R1 READY on1b3b674: no actionable findings; new16
and unchanged shutdown test17passed in8.75s. Source/test bytes remain unchanged
through documentation-only final review. This does not convert the old failed CI
to success or replace publisher's new exact-head gate.

## Issue 251 follow-up: exact 32-key payload relation

The merged issue-249 repair replaced sparse OR with per-key complete-row UNION
branches. It retained the readonly wide-row protection, but a new synthetic
1,048,576-row generated-view model with 128 sparse selected keys measured
134,217,728 rows scanned across 128 range scans. A single 128-key relation
reduced that model's scan work but failed a separate stored wide ZSTD readonly
resource case. This follow-up supersedes the payload gathering shape and batch
size described earlier in this ADR; it does not change latest's scalar key
selection or the successful owned-read ROLLBACK decision.

Gather at most 32 sorted keys per statement through an exact bound `VALUES`
inner join plus the inclusive low/high range. Fetch the same full 17 columns,
validate count and key-set equality, and keep the shared snapshot, connection
lock, caller transaction ownership, error propagation, sort and decoder. The
new 128-key generated-view test uses four relation statements and scans at most
four source-sized passes. A separate stored 8,192-row/128-key/64 KiB ZSTD
model returns complete selected records under 128 MiB/one thread/zero temp,
while an isolated 128-key relation mutant raises an actual engine IOException.

For the default 10,000-row tail, the tradeoff is 313 payload statements plus
five owned control/key statements, 318 total; caller-owned transactions use
316. This is bounded scan work and stored-model resource evidence, not proof
of archive indexing, physical I/O, native API success, arbitrary payload size
or latency. See the issue-251 checkpoint in
`../iterations/0038-readonly-batch-compat-fix.md` and its sealed local evidence.
