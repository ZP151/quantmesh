# Iteration 0026 — Local runtime assembly

- Status: in progress
- Started: 2026-08-15
- Tracking issue: [#118](https://github.com/ZP151/quantmesh/issues/118)
- Branch: `0026-local-runtime-assembly` (from `origin/main` at `a4ef3c2`)
- Ledger: this file

## Objective

Extract a deeper runtime module so workstation construction, local paths and
stores no longer repeat inline. This is iteration 0013 Phase E's "Worth
exploring" item (not release-critical), sequenced after the three Strong items
(0022–0025). The deferred specialized surfaces (watchlist venue-aware identity,
proposal event ledger, forecast artifact directories) stay out of the simple
`JsonlStore` interface — they are distinct semantics, not repeats of the
discipline.

## Scope

1. Introduce a frozen `WorkstationStores` bundle and a `build_workstation_stores`
   factory that lays the eleven ADR-0006 stores/registries out under one demo
   root or the operator's settings dirs.
2. Wire the factory into the demo runtime read path (`load_demo_root`); later
   slices may adopt it in `create_workstation_app`.

## Acceptance criteria

- The factory constructs every store at the documented path; a seam test pins
  both layouts (demo root and settings dirs).
- The demo `load_demo_root` builds its store assembly through the factory with
  identical paths (behavior-equivalent).
- No production representation or trading-safety change.

## Non-negotiable constraints

- Independent of iteration 0021: do not depend on or modify
  `0021-trusted-data-fabric`; its 168-hour soak keeps HEAD at `77141b9`. No
  changes under `data/` (providers, lake, manifest, layout, ingestion).
- Keep external venues read-only and execution paper-only.
- No credential, live-trading, paid-service or major architecture change
  without explicit operator authorization.

## Resume instructions

1. Work in the `QuantMesh-iteration-0026` worktree on branch
   `0026-local-runtime-assembly` (from `origin/main` at `a4ef3c2`).
2. Do not touch `QuantMesh-iteration-0021` or its soak evidence root.
3. Follow TDD; run the relevant checks listed in `docs/agents/collaboration.md`.
4. Append a dated checkpoint to this ledger.

## Current frontier

`build_workstation_stores` and `WorkstationStores` exist and are wired into
`load_demo_root` (checkpoint 1). Remaining: full-suite verification and the
final PR.

## Checkpoint 1 — 2026-08-15: runtime assembly seam

- Added `src/quantmesh/runtime.py`: `WorkstationStores` (frozen bundle of the
  eleven ADR-0006 stores) and `build_workstation_stores(root, lake_root)`.
- Wired the factory into `demo/seeder.py:load_demo_root` so the demo read path
  builds its store assembly once (identical paths, behavior-equivalent).
- `tests/test_runtime.py` (2 tests) pins the demo-root and settings-dir
  layouts. Evidence: focused tests + Ruff green; full suite recorded next
  checkpoint.
