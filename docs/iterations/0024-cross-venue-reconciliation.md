# Iteration 0024 — Cross-venue reconciliation module

- Status: in progress
- Started: 2026-08-15
- Tracking issue: [#114](https://github.com/ZP151/quantmesh/issues/114)
- Branch: `0024-cross-venue-reconciliation` (from `origin/main` at `733ff97`)
- Ledger: this file

## Objective

Deepen the shared reconciliation module: the Moomoo
(`quantmesh.moomoo.reconciliation`) and Hyperliquid
(`quantmesh.hyperliquid.reconciliation`) bindings repeat the same pairing,
classification, tolerance comparison and adoption flow, differing only in wire
shapes and status mapping. Consolidate the venue-neutral engine into
`quantmesh.execution.reconciliation` and keep venue-specific evidence/status
mapping in each adapter. Preserve ADR-0006 conservative defaults (exact
tolerance, no best-effort mapping, adoption only for clean pairs).

## Background

Iteration 0013 Phase E ranked this a "Strong" follow-up, sequenced after
durable JSONL persistence stabilized (now done in iterations 0022/0023, merged
at `733ff97`). The shared vocabulary in `execution/reconciliation.py` is already
venue-neutral, but the comparison *engines* — `_compare_quantities`,
`_compare_prices`, `_compare_fees`, `_compare_timestamps`, `_compare_fill_ids`,
`_compare_positions`, and the `_finding` / `_dedupe_by_id` / `_is_terminal` /
`_is_progress` helpers — are copy-pasted across both bindings with only accessor
names and message nouns differing.

## Scope (first slices)

1. Move the pure helpers (`finding`, `dedupe_by_id`, `is_terminal`,
   `is_progress`) into `execution/reconciliation.py`; both bindings import them.
2. Build a venue-neutral numeric comparison engine (quantities, prices, fees,
   timestamps, fill ids, positions) over a small broker-order/fill view; migrate
   Moomoo to it byte-identically.
3. Migrate Hyperliquid to the same engine; delete every duplicated comparison
   and helper block.

## Acceptance criteria

- The shared module exposes the venue-neutral engine; neither binding
  reimplements pairing/tolerance/classification/adoption numerics.
- Centralized comparison behavior is covered by crash/corruption-equivalent
  seam tests: drift, progress, missing-data, revoked-fill and position cases.
- Moomoo (then Hyperliquid) reconciliation produces byte-identical findings and
  their existing tests pass unchanged.
- ADR-0006 conservative defaults preserved (exact tolerance, no fabricated
  mapping, adoption only for clean pairs).
- The shared engine contract is recorded in an ADR (new or updated).

## Non-negotiable constraints

- Independent of iteration 0021: do not depend on or modify
  `0021-trusted-data-fabric`; its 168-hour soak keeps HEAD at `77141b9`.
- Keep external venues read-only and execution paper-only.
- No credential, live-trading, paid-service or major architecture change
  without explicit operator authorization.

## Resume instructions

1. Work in the `QuantMesh-iteration-0024` worktree on branch
   `0024-cross-venue-reconciliation` (from `origin/main` at `733ff97`).
2. Do not touch `QuantMesh-iteration-0021` or its soak evidence root.
3. Follow TDD; run the relevant checks listed in `docs/agents/collaboration.md`.
4. Append a dated checkpoint to this ledger after each slice.

## Current frontier

The venue-neutral numeric comparison engine is extracted and both bindings
migrated (checkpoints 1–2); the contract is recorded in ADR-0017. Remaining:
full-suite verification and the final PR. `is_progress`, status mapping,
timestamps (Moomoo only) and adoption stay venue-local by design.

## Checkpoint 1 — 2026-08-15: scaffolding + shared pure helpers

- Recorded the iteration ledger, issue #114 and this branch from `origin/main`
  at `733ff97` (after #112 and #113 merged the persistence consolidation).
- Extracted `finding`, `dedupe_by_id` and `is_terminal` from the Moomoo and
  Hyperliquid bindings into `execution/reconciliation.py`; both bindings now
  import them and their duplicated private copies are deleted. `is_progress`
  stays venue-local: Hyperliquid's "open" row treats `ACCEPTED` as progress
  against a journal already `PARTIALLY_FILLED`, unlike Moomoo.
- Evidence: `tests/test_moomoo_reconciliation.py`,
  `tests/test_hyperliquid_reconciliation.py` pass unchanged; Ruff clean.

## Checkpoint 2 — 2026-08-15: shared numeric comparison engine

- Extracted `compare_positions`, `compare_quantities`, `compare_prices`,
  `compare_fees` and `compare_fill_ids` into `execution/reconciliation.py`,
  parameterized by the venue noun and (for quantities) a number formatter and
  (for fees/fill-ids) a row noun; both Moomoo and Hyperliquid bindings now call
  them and their duplicated `_compare_*` blocks are deleted.
- Venue-specific behavior stays in the adapters: Moomoo's timestamp compare and
  unhealthy-deal check, Hyperliquid's derived surface status.
- Added `tests/test_reconciliation_engine.py` (13 seam tests) covering the
  engine directly: drift, missing-data, revoked-fill and position cases.
- Reviewed equivalent: Moomoo's fee missing-data message now reads "the broker
  reports N deals" (a definite article added to match the shared wording); the
  tests assert finding kinds, not message text.
- Evidence: 85 focused tests pass (reconciliation + engine); Ruff clean;
  full suite `2646 passed, 0 failed` (exit 0); `git diff --check` clean.
- ADR-0017 records the engine contract.
