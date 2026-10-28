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
