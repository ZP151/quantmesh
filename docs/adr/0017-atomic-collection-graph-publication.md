# ADR-0017 — Atomic collection graph publication

- Status: accepted for Iteration 0021 Task 9
- Date: 2026-08-14
- Supersedes: the single-dataset activation mechanism in ADR-0016 only for
  datasets advanced by a `CollectionCoordinator`; the canonical object,
  manifest, legacy Lake and reader contracts remain unchanged.

## Context

ADR-0016 gives each dataset an independent append-only history and mutable
current pointer. A real provider collection, however, creates several related
raw, normalized, adjusted and feature manifests. Advancing those pointers one
at a time can expose a partial graph after a crash. Retries also need to prove
that the exact provider bytes, collection request, code revision and staged
roles did not change.

The migration must preserve existing single-dataset publishers and readers.
It must not introduce a second manifest identity or make an uncommitted staged
manifest visible through `current()`, `manifests()` or `open_known_at()`.

## Decision

All schema-v2 manifests retain the one canonical path established by ADR-0016:
`.trusted-data-v2/datasets/<dataset>/manifests/<manifest-id>.json`. Staging may
write immutable candidate bytes there, but a candidate is not committed merely
because that file exists. Legacy datasets continue to derive visibility from
their hash-chained `history.jsonl` and `current.json` pointer.

A collection-managed graph derives visibility from one DuckDB transaction in
`.trusted-data-v2/control/collection-checkpoints.duckdb`. That transaction
compare-and-swaps every dataset revision, appends every graph-history row,
records the complete graph commit and advances the collection checkpoint. A
pending graph reserves all target datasets before preflight, so legacy and
other collection publishers cannot interleave with it. Readers combine legacy
history and graph history only after validating each authority against its own
immutable evidence.

Before opening the transaction, the writer creates an immutable canonical
intent under `.trusted-data-v2/control/graph-intents/<commit-id>.json`. After
DuckDB commits, it creates the identical immutable committed marker under
`graph-commits/<commit-id>.json` and removes the intent. A process that dies
between the database commit and marker creation is repaired only while holding
the single writer lease and only when the exact intent bytes equal the exact
committed DuckDB body. Readers fail closed when the committed marker set,
DuckDB commit set, graph history or graph current disagree. The journal is the
independent append-only high-water evidence that prevents deletion of both
mutable graph-current and graph-history rows from silently reviving a legacy
pointer.

Every journal body carries a consecutive global sequence and the SHA-256
digest of its predecessor body. Readers verify the complete file/database set,
the chain, every checkpoint identity, every dataset history/current row and
every graph ownership marker before returning any control-plane state. A read
of one dataset therefore fails closed when any dataset in the committed graph
is inconsistent. The first reservation also writes an immutable
`graph-owner.json` in each dataset directory. That permanent migration marker
prevents deletion of the database, journal tail or graph rows from making a
stale legacy pointer authoritative. Exact committed checkpoint rows may be
reconstructed from the journal while holding the writer lease; conflicting
rows fail closed.

The pending and committed graph declare every member dataset, including a
member whose canonical manifest is already current and therefore has no graph
advance. Every member records its exact manifest ID, revision and knowledge
high-water, is reserved and is permanently owner-marked. An unchanged legacy
member remains readable only through a pointer matching that immutable anchor;
the owner marker and committed member set prevent any later legacy publisher
from advancing it outside the collection graph.

Reservation state is committed before its owner marker is written. If a
process stops in that narrow window, the next writer reconstructs the marker
from the durable reservation before reading or staging. The same repair derives
missing owner markers from committed graph bodies. A legacy-to-graph advance
also records the exact legacy predecessor ID and revision; current and history
reads require that predecessor pointer and its validated hash-chained history
to remain present. Readers treat a reservation without its owner marker as an
integrity failure, so that crash window cannot expose a stale legacy pointer.

`CollectionJob` hashes the complete provider request boundary, including the
canonical instruments, endpoints, request IDs, data kinds, intervals, session,
window, adjustment policy, schemas, mapping version and producing Git commit.
It also includes an explicit operator/scheduler-selected collection cycle. An
exact cycle retry replays its durable snapshot without contacting the provider;
a later cycle for the same event window may capture a provider correction as a
new knowledge-time revision.
`CollectionRun` is deterministic for that job; the retry attempt is monotonic
but does not change the run identity. The source snapshot binds the aggregate
provider result and the ordered digests of every raw endpoint payload before
transformation. Digest multiplicity is preserved when two endpoints return
identical bytes. Before its mutable row is written, the complete media type,
aggregate digest, byte length and ordered raw digests are anchored by an
immutable per-job source marker. Pending and committed graph evidence repeat
that exact identity. A missing mutable row is reconstructed from the marker;
a missing marker or coherent row change fails closed. Every committed manifest
carries the deterministic collection run ID and producing commit.

The graph advance contract includes predecessor and successor knowledge times.
Knowledge must advance strictly after the predecessor both when staging and
inside the control-plane commit contract. Cursor chains reject repeated
cursors, empty nonterminal pages and pages after a terminal marker before any
publication is eligible.

Raw-envelope schema version 1 remains byte-compatible and cannot carry the new
collection-window fields. Captures that distinguish the provider request
window from the complete collection window use schema version 2 and require
both bounds. The reader accepts both explicit versions.

One cross-process control lock serializes legacy pointer mutation, pending
reservations and graph commits. The lock rejects symlinks, reparse points and
hard links. Windows lock contention retries only recognized sharing/lock
errors and is time-bounded; other errors fail immediately. Journal recovery
removes only same-inode temporary hard links left between atomic link creation
and temporary-name cleanup. Exact one-link temporary files left immediately
before link creation are promoted only when their bytes and identity match
durable authority; an uncommitted intent temporary is validated and discarded.
Authoritative journal paths must then have exactly one link. Crash injection is
a public test-only coordinator argument and never changes production identity.

## Consequences

- A multi-dataset collection becomes visible as one graph or not at all.
- An external parent is admissible only when it is included in the same graph
  or already appears in validated committed history; a staged orphan cannot
  become committed lineage.
- A historical completed job can be replayed after newer publications without
  moving current state, while exact immutable bytes and preflight evidence are
  revalidated.
- A later explicit collection cycle may preserve a corrected provider response
  for the same event window without rebinding the earlier job or snapshot.
- Staged canonical manifest files may remain after a losing or crashed attempt;
  they are inert content-addressed evidence and do not reserve a revision.
- DuckDB is the atomic graph mapping authority; committed journal files are its
  independent immutable rollback detector, not a competing current pointer.
- Legacy single-dataset publication remains supported until an explicit graph
  reservation or graph commit claims that dataset. Once graph-managed, legacy
  publication is fenced permanently.
- The local filesystem remains the trust root. As in ADR-0016, an administrator
  who can coherently replace the database and every journal/object/manifest is
  outside the protection claimed here; external anchoring is future work.
- Quality evidence is deliberately not created by this decision. Task 10 adds
  immutable SLA evaluations and binds accepted graph manifests to them.

## Rollback

Code may stop creating new graph commits, but committed graph mappings and
journals must remain readable. Removing the control database or journal is not
a rollback procedure because it would erase committed visibility evidence.
Returning a graph-managed dataset to legacy publication requires a future
explicit migration ADR and verifiable conversion of the complete graph history.
