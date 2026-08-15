# Iteration 0022 — Durable JSONL persistence module

- Status: ready (not started)
- Started: —
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

Nothing implemented yet. First task: choose the highest-leverage registry to
migrate, write the shared module's failing tests, then implement.
