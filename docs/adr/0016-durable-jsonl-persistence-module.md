# ADR-0016 — Shared durable JSONL persistence module

- Status: accepted
- Date: 2026-08-12
- Amended: 2026-08-15 (iteration 0023 — secondary identity, update, full migration)
- Deciders: solo delivery (iteration 0022 issue #111, iteration 0023)
- Related: ADR-0006 (the append-only JSONL discipline this module encodes),
  ADR-0005 (identity is derived from pinned state, never fabricated),
  ADR-0009 (research registries and dependency contract)

## Context

The ADR-0006 append-only JSONL discipline — atomic temp+replace appends,
fail-closed line-attributed reads, duplicate identity refusal, hostile-path
refusal and schema validation — was reimplemented across execution journals,
research/report registries, operations ledgers, AI decision logs, event
mappings and watchlists. Each copy drifted subtly (message wording, whether
the store file was checked as a regular file, whether symlinks were refused,
which temp-file idiom was used). Iteration 0013 Phase E ranked durable JSONL
persistence the top post-RC hardening candidate, and cross-venue
reconciliation deepening is sequenced after it.

## Decisions

### 1. One shared store, one small interface

A new `quantmesh.persistence.JsonlStore` owns the discipline. Its interface is:

- `read() -> list[Model]` — fail-closed, line-attributed, duplicate-refusing.
- `write(records) -> None` — atomic temp+replace full rewrite.
- `append(record) -> Model` — duplicate-refusing atomic append.
- `update(record) -> Model` — atomic in-place snapshot replacement by key.
- `check_absent(record, existing=None)` — duplicate refusal against a
  caller-supplied read, so a caller can sequence a domain precondition (a lake
  pin gate) between the refusal and the write without reimplementing it.
- `scan() -> list[Path]` — report crash orphans and hostile entries, never delete.
- `path` — the store file under the root.

### 2. The store is generic; callers parameterize, not subclass

The constructor takes the record `model`, the duplicate-identity `key` (or
`None` to disable deduplication — the mapping ledger and funding ledger
legitimately repeat an identity with different evidence), the human `label`,
`id_label`, `article` (a/an) and `record_label` used in refusal messages, the
`error_type` refusals raise, an optional `extra_validate` hook for read-time
invariants beyond the schema (the journal's replay validation), and a
`secondary_keys` sequence of optional unique identities (the journal's
idempotency key). Domain concerns — a report's lake pin gate, a document's
"already indexed" verb — stay in their owning modules and plug in through this
constructor.

### 3. Byte-identical serialization is part of the contract

A record serializes as `record.model_dump_json() + "\n"`, the exact bytes the
registries already wrote, so a migrated registry round-trips byte-identically
and its on-disk files are unchanged.

### 4. Hostile-path refusal is centralized and complete

Reads and writes refuse a root that is a file, a store path that is not a
regular file, and a symlinked root or store file (which could redirect reads or
writes outside the root). A missing root or store file remains an empty read,
never an error. `scan` reports a symlinked root or store file and leftover temp
files from a crash, without deleting anything; the root-not-dir and
path-not-file refusals fire on read/write, not on scan. Ancestors of the root
are a trusted operator boundary, matching the lake's model.

### 5. Migrate the true ADR-0006 registries; leave specialized surfaces alone

Every registry that reimplements the same append/read/duplicate/hostile-path/
schema discipline migrates onto the store and deletes its local `_append`/`_read`.
Fifteen registries migrated: report, experiment, feature, model, ensemble,
drift alerts and promotions, forecast report, mapping ledger, scenario report,
decision log, document index, enablement ledger, metrics store, funding ledger
and the order journal. Three surfaces are deliberately out of scope because
they are not reimplementations of the same discipline: the watchlist (venue-aware
identity with a None-wildcard conflict rule plus a `remove` rewrite), the
proposal event ledger (transactions + interprocess lock + reparse rejection),
and the forecast artifact directories (directory-based).

## Consequences

- Positive: crash, corruption, duplicate, hostile-path and schema behavior are
  tested once at the seam; callers stop reimplementing the discipline and stop
  drifting from it.
- Positive: every migrated registry's files and messages are byte-for-byte
  equivalent and its existing tests pass unchanged (or a reviewed equivalent
  for the newly-added hostile-path cases the old code never handled).
- Negative: a keyed store's `append`/`update`/`check_absent` are not safe under
  concurrent writers (read-then-write, the same race the original registries
  had); the proposal ledger keeps its explicit transaction/lock for exactly
  that reason.
- Open: the watchlist and the proposal event ledger could later adopt a more
  general conflict predicate or a transactional variant of the store, but they
  are not blocking the consolidation.
