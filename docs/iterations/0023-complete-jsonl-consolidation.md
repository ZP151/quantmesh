# Iteration 0023 — Complete durable JSONL consolidation

- Status: in progress
- Started: 2026-08-15
- Tracking issue: [#111](https://github.com/ZP151/quantmesh/issues/111) (continuation; #112 merged)
- Branch: `0023-complete-jsonl-consolidation` (from `origin/main` at `e5a321f`)
- Ledger: this file

## Objective

Finish what iteration 0022 started: extend the shared `JsonlStore` seam with
the two behaviors the order journal needs (a secondary idempotency identity
key and an in-place `update`), migrate **every** remaining ADR-0006 registry
onto the store, and delete every reimplemented append / read / duplicate /
hostile-path / schema block so the discipline lives in exactly one place.

## Background

Iteration 0022 built `quantmesh.persistence.JsonlStore` and migrated one
registry (`ReportRegistry`) as proof. The remaining registries still
reimplement the discipline: the order journal (with a second identity key and
in-place update), experiments, features, models, ensembles, drift ledgers,
forecast reports, mapping ledgers, scenario reports, AI decisions, retrieval
documents, enablement, metrics, the watchlist, the funding ledger, proposals
and forecast artifacts. Cross-venue reconciliation deepening is sequenced
after this consolidation is stable.

## Scope

1. Extend `JsonlStore` with a `secondary_keys` constructor parameter (unique
   optional identities, e.g. the journal's idempotency key) and an `update`
   primitive (atomic in-place snapshot replacement by key).
2. Migrate `OrderJournal` first (highest value, hardest case): secondary
   idempotency-key identity, in-place update, replay validation through
   `extra_validate`.
3. Migrate the remaining registries in batches, byte-identically, deleting
   their `_append`/`_read` (or equivalent) blocks.
4. After consolidation, deepen cross-venue reconciliation on the stable
   persistence layer (next iteration).

## Acceptance criteria

- `JsonlStore` covers secondary identity keys and in-place update, both
  tested at the single seam.
- Every migrated registry round-trips byte-identically and its existing tests
  pass unchanged (or a reviewed equivalent).
- No registry reimplements atomic append / fail-closed read / duplicate /
  hostile-path / schema logic; all such blocks are deleted.
- Trading-safety invariants unchanged (paper default, no live, no credential
  handling).
- ADR-0016 is updated to reflect the secondary-key and update extensions.

## Non-negotiable constraints

- Independent of iteration 0021: do not depend on or modify
  `0021-trusted-data-fabric`; its 168-hour soak keeps HEAD at `77141b9`.
- Keep external venues read-only and execution paper-only.
- No credential, live-trading, paid-service or major architecture change
  without explicit operator authorization.

## Resume instructions

1. Work in the `QuantMesh-iteration-0023` worktree on branch
   `0023-complete-jsonl-consolidation` (from `origin/main` at `e5a321f`).
2. Do not touch `QuantMesh-iteration-0021` or its soak evidence root.
3. Follow TDD; run the relevant checks listed in `docs/agents/collaboration.md`.
4. Append a dated checkpoint to this ledger after each batch.

## Migration batches

1. **Seam extension + OrderJournal** — `execution/journal.py`.
2. **research** — experiments, features, models, ensemble, drift (alerts +
   promotions).
3. **events + portfolio** — forecast registry, mapping ledger, scenario reports.
4. **ai + ops + api + hyperliquid + instruments** — decisions, retrieval
   documents, enablement, metrics, watchlist, funding ledger, proposals,
   forecast artifacts.

## Current frontier

Seam extension and OrderJournal migration are implemented (checkpoint 1);
batches 2–4 remain, then cross-venue reconciliation deepening.

## Checkpoint 1 — 2026-08-15: seam extension + OrderJournal migration

- Extended `JsonlStore` (`src/quantmesh/persistence/jsonl.py`): added
  `article` (a/an in refusal messages), `secondary_keys` (a sequence of
  `(label, key_fn)` optional unique identities, None-skipping) and `update`
  (atomic in-place replacement by primary key, refusing an unknown key).
- `tests/test_persistence_jsonl.py` grew to 32 tests: secondary-key duplicate
  refusal, None-secondary allowance, configured article, append's
  primary-key-only collision rule, and update replace / byte-identical /
  missing-refusal / no-touch-on-missing.
- Migrated `OrderJournal` (`src/quantmesh/execution/journal.py`) onto the store
  with `label="order journal"`, `id_label="order"`, `article="an"`,
  `secondary_keys=[("idempotency key", ...)]` and
  `extra_validate=validate_order_replay`; `_write`/`_read` deleted.
- Evidence: `test_execution_journal.py`, `test_recovery.py` (idempotency
  identity) and `test_persistence_jsonl.py` → 70 passed; Ruff clean. Full-suite
  result recorded in the next checkpoint.
