# ADR-0016 — Shared durable JSONL persistence module

- Status: accepted
- Date: 2026-08-12
- Deciders: solo delivery (iteration 0022, issue #111)
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

A new `quantmesh.persistence.JsonlStore` owns the discipline. Its interface is
four operations plus the store path:

- `read() -> list[Model]` — fail-closed, line-attributed, duplicate-refusing.
- `write(records) -> None` — atomic temp+replace full rewrite.
- `append(record) -> Model` — duplicate-refusing atomic append.
- `scan() -> list[Path]` — report crash orphans and hostile entries, never delete.
- `path` — the store file under the root.

### 2. The store is generic; callers parameterize, not subclass

The constructor takes the record `model`, the duplicate-identity `key`, the
human `label` and `id_label` used in refusal messages, the `error_type` refusals
raise, and an optional `extra_validate` hook for read-time invariants beyond the
schema (e.g. the order journal's replay validation). Domain concerns — the
report registry's lake pin gate, the journal's idempotency-key identity — stay
in their owning modules and plug in through this constructor.

### 3. Byte-identical serialization is part of the contract

A record serializes as `record.model_dump_json() + "\n"`, the exact bytes the
registries already wrote, so a migrated registry round-trips byte-identically
and its on-disk files are unchanged.

### 4. Hostile-path refusal is centralized and complete

Reads and writes refuse a root that is a file, a store path that is not a
regular file, and a symlinked root or store file (which could redirect reads or
writes outside the root). A missing root or store file remains an empty read,
never an error. `scan` surfaces the same hostile entries plus leftover temp
files from a crash, without deleting anything.

### 5. Migrate one registry at a time

The first migration is `ReportRegistry` (the canonical ADR-0006 reference). Its
public surface (`record`, `get`, `all`, `resolve`, `resolve_pin`) is unchanged;
`_append` and `_read` are replaced by a store bound to `StrategyReport`, and the
lake pin gate (`_require_pin`) remains a domain precondition before `append`.
Un-migrated registries keep their current behavior until later slices migrate
them the same way.

## Consequences

- Positive: crash, corruption, duplicate, hostile-path and schema behavior are
  tested once at the seam; callers stop reimplementing the discipline and stop
  drifting from it.
- Positive: the migrated registry's files and messages are byte-for-byte
  equivalent, and its existing tests pass unchanged.
- Negative: `ReportRegistry.record` now validates the lake pin before refusing a
  duplicate (the previous code short-circuited the duplicate first); both paths
  fail closed and no test exercised the combined case, but the ordering nuance
  is a deliberate, reviewed change.
- Open: the remaining registries (order journal, experiments, features, models,
  ensembles, drift ledgers, forecasts, mappings, enablement, metrics, watchlist,
  decisions, documents, funding ledger, proposals) migrate in later slices; the
  journal's second identity key (idempotency) needs a small extension to the
  single-key constructor when it migrates.
