# Iteration 0027 — Trusted Research Evaluation Lab

- Status: ready (not started)
- Started: —
- Tracking issue: [#122](https://github.com/ZP151/quantmesh/issues/122)
- Branch: `0027-trusted-research-evaluation-lab` (from `origin/main` at `31aeb5c`)
- Ledger: this file

## Objective

Build a trusted algorithm evaluation lab that lets many data and model
candidates be compared safely behind stable adapters, on the trusted-data
foundation delivered by iteration 0021 (M14 part 2).

## Scope

- Unified Dataset/Manifest/Quality pin for every evaluation run.
- A single adapter interface for baseline models plus Qlib and Darts candidates.
- Walk-forward validation, look-ahead/leakage detection, and cost + slippage
  modeling on every run.
- Reproducible runs, model ranking, and drift detection.
- Frontend comparison of strategies by data version, metrics and failure reason.

## Acceptance criteria

- A run is pinned to an exact dataset/manifest/quality identity and reproduces
  byte-identically from a clean checkout.
- At least one baseline plus one Qlib and one Darts candidate run through a
  common interface.
- Every evaluation reports walk-forward, leakage and cost/slippage results; a
  leakage or look-ahead violation blocks promotion.
- Model ranking and drift detection are surfaced in the frontend with
  data-version provenance.

## Non-negotiable constraints

- FinRL-X is NOT added to the product runtime (iteration 0020 evidence rejected
  it); NautilusTrader remains an isolated comparator only.
- Independent of the 168-hour real-data soak in progress: do not modify the
  `QuantMesh-0021-finalize` worktree or its soak commit `31aeb5c`.
- External venues read-only; execution paper-only; no credential handling.
- No algorithm/AI output gains order authority.

## Resume instructions

1. Work in the `QuantMesh-iteration-0027` worktree on branch
   `0027-trusted-research-evaluation-lab` (from `origin/main`).
2. Do not touch `QuantMesh-0021-finalize` (its 168-hour soak keeps HEAD at
   `31aeb5c`).
3. Follow TDD; run the relevant checks in `docs/agents/collaboration.md`.
4. Append a dated checkpoint to this ledger after each slice.

## Current frontier

Nothing implemented yet. First task: choose the common evaluation adapter
interface and the pinned-run identity contract, write failing tests, then
implement the first baseline + Qlib + Darts path.
