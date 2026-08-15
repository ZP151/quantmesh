# Iteration 0025 — Execution numeric policy

- Status: in progress
- Started: 2026-08-15
- Tracking issue: [#116](https://github.com/ZP151/quantmesh/issues/116)
- Branch: `0025-execution-numeric-policy` (from `origin/main` at `4f41f95`)
- Ledger: this file

## Objective

Characterize and pin the current execution numeric behavior — price, quantity,
fee, tolerance and tick/lot handling — with tests and an ADR, without changing
the representation. This is the third "Strong" follow-up from iteration 0013
Phase E, sequenced after durable JSONL persistence (0022/0023) and cross-venue
reconciliation (0024).

## Background

Price, quantity, fee and tolerance behavior uses distributed float operations
with a local six-decimal quantization convention and bps-based tolerances.
Iteration 0013 Phase E recommended writing characterization tests and an ADR
covering tick size, lot size, quantization and comparison, with no
representation change in the RC.

## Scope

1. Write characterization tests that pin the current numeric conventions:
   fee/slippage six-decimal quantization, bps→fraction conversion, exact-default
   comparison tolerance, `math.isclose` zero/equality checks, and the fact that
   venue tick size is metadata, not a local quantization unit.
2. Record the numeric policy in an ADR (new).
3. Make no representation change.

## Acceptance criteria

- Characterization tests pin every documented convention.
- An ADR records the numeric policy (quantization unit, bps convention,
  tolerance semantics, tick-size status) and its open gaps.
- No production representation changes.

## Non-negotiable constraints

- Independent of iteration 0021: do not depend on or modify
  `0021-trusted-data-fabric`; its 168-hour soak keeps HEAD at `77141b9`.
- Keep external venues read-only and execution paper-only.
- No credential, live-trading, paid-service or major architecture change
  without explicit operator authorization.

## Resume instructions

1. Work in the `QuantMesh-iteration-0025` worktree on branch
   `0025-execution-numeric-policy` (from `origin/main` at `4f41f95`).
2. Do not touch `QuantMesh-iteration-0021` or its soak evidence root.
3. Follow TDD; run the relevant checks listed in `docs/agents/collaboration.md`.
4. Append a dated checkpoint to this ledger.

## Current frontier

Characterization tests and ADR are written (checkpoint 1).

## Checkpoint 1 — 2026-08-15: characterization + ADR

- Wrote `tests/test_numeric_policy.py` pinning the six-decimal quantization,
  bps→fraction conversion, exact-default tolerance, `math.isclose` semantics and
  the tick-size-is-metadata boundary.
- Wrote `docs/adr/0018-execution-numeric-policy.md` recording the policy.
- No production code changed. Evidence: focused tests + Ruff green; full suite
  recorded next checkpoint.
