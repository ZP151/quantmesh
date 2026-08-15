# Iteration 0022 — Durable JSONL persistence module

- Status: in progress (first slice: shared module + one migrated registry)
- Started: 2026-08-12
- Tracking issue: [#111](https://github.com/ZP151/quantmesh/issues/111)
- Branch: `0022-durable-jsonl-persistence` (from `origin/main` at `d4aeed3`)
- Ledger: this file

## Objective

Consolidate the repeated append-only JSONL persistence discipline — atomic
temp+replace appends, fail-closed line-attributed reads, duplicate handling,
hostile-path checks and schema validation — into one shared module with a small
interface, then migrate one registry at a time with behavioral equivalence
proven at the shared seam.

## Background

Iteration 0013 Phase E ranked durable JSONL persistence the top post-RC
hardening candidate. The same ADR-0006 append-only JSONL discipline is
reimplemented across execution journals, research/report registries, operations
ledgers, AI decision logs, event mappings and watchlists. Cross-venue
reconciliation deepening is sequenced after this slice ("after persistence is
stable").

## Scope (first slice)

1. Build the shared JSONL persistence module (append / read / scan) that
   centralizes atomic temp+replace appends, fail-closed line-attributed reads,
   duplicate handling, hostile-path checks and schema validation.
2. Migrate ONE existing registry to the module and prove byte-identical
   behavioral equivalence.

## Acceptance criteria

- A shared module exposes a small interface; callers no longer reimplement
  atomic append / fail-closed read / duplicate / hostile-path / schema logic.
- Centralized behavior is covered by crash, corruption, duplicate, hostile-path
  and schema tests at the single seam.
- One migrated registry round-trips byte-identically and its existing tests
  pass unchanged (or a reviewed equivalent).
- Un-migrated registries keep current behavior.
- Trading-safety invariants unchanged (paper default, no live, no credential
  handling).
- The shared module contract is recorded in an ADR (new or updated).

## Non-negotiable constraints

- Independent of iteration 0021: do not depend on `0021-trusted-data-fabric`,
  and do not modify that branch (its 168-hour soak keeps HEAD at `77141b9`).
- Keep external venues read-only and execution paper-only.
- No credential, live-trading, paid-service or major architecture change
  without explicit operator authorization.

## Resume instructions

1. Work in the `QuantMesh-iteration-0022` worktree on branch
   `0022-durable-jsonl-persistence` (from `origin/main`).
2. Do not touch `QuantMesh-iteration-0021` or its soak evidence root.
3. Follow TDD; run the relevant checks listed in `docs/agents/collaboration.md`.
4. Append a dated checkpoint to this ledger after each slice; update
   `docs/goals/ACTIVE.md` only when the iteration becomes active.

## Current frontier

First slice delivered: the shared `JsonlStore` seam exists and one registry
(`ReportRegistry`) is migrated onto it. Remaining work: migrate the other
registries one at a time (order journal, experiments, features, models,
ensembles, drift ledgers, forecasts, mappings, enablement, metrics, watchlist,
decisions, documents, funding ledger, proposals), extend the constructor for the
journal's second identity key, then open the final PR.

## Checkpoint 1 — 2026-08-12: shared module + ReportRegistry migration

- Built `src/quantmesh/persistence/jsonl.py` (`JsonlStore`): a generic
  `read` / `write` / `append` / `scan` seam over the ADR-0006 discipline. The
  caller supplies the record model, identity key, human labels and error type;
  an optional `extra_validate` hook covers read-time invariants beyond the
  schema.
- Centralized behavior is covered at the single seam by
  `tests/test_persistence_jsonl.py` (23 tests): byte-identical round-trip,
  crash (temp-file cleanup and failed-replace leaves the target unchanged and
  no orphan), corruption (line-attributed fail-closed read, unreadable bytes),
  duplicate (read and append refusal), hostile-path (root-not-dir, path-not-file,
  symlinked root/file refusal, `scan` reporting orphans and symlinks) and schema
  (invalid and schema-violating lines) plus configurable error type.
- Migrated `ReportRegistry` (`src/quantmesh/research/reports.py`) onto the
  store. Public surface (`record`, `get`, `all`, `resolve`, `resolve_pin`) is
  unchanged; `_append` and `_read` are deleted. The lake pin gate
  (`_require_pin`) stays a domain precondition before `store.append`.
- Evidence: `tests/test_research_reports.py` 29 passed unchanged and
  `tests/test_persistence_jsonl.py` 23 passed; Ruff clean on the changed files
  and on the whole tree; full suite `2622 passed, 0 failed` (exit 0);
  `git diff --check` clean. The migrated registry round-trips byte-identically
  because serialization is the same `model_dump_json() + "\n"` contract.
- Independent review: GO — no Critical or Important findings. Two Minor items
  fixed inline (write-side path-not-file refusal; ADR scan wording). Deferred
  Minors for later slices: ancestor-of-root symlink checks (the root is a
  trusted operator boundary, matching the lake model), and `extra_validate`
  only wrapping `ValueError` (matches the journal precedent).
- ADR: `docs/adr/0016-durable-jsonl-persistence-module.md` records the shared
  contract (interface, parameterization, byte-identical serialization,
  hostile-path refusal, one-registry-at-a-time migration).
- Reviewed equivalent (documented in the ADR): `record` now validates the lake
  pin before refusing a duplicate; both fail closed and no test covered the
  combined case.
- Constraints honored: nothing in iteration 0021 was touched; execution stays
  paper-only with no credential handling.
