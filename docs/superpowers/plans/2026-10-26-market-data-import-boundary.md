# Market-data-only import boundary correction

Issue218 continuation; approved decisionA SHA256
b1acdba5e2220316aa3a1ac646881800ecd6a0109bfb7176cacf7902750e658d.
Exact base e0a8d7107758236f32abe92522937dcd97e779a7/tree
de8b642ae049f5ecbc66574b67cb8c5fc30bd053 (merged PR229).
Root chose implementation; no repeated design/human approval requested.

ACK2026-10-26T00:15:24Z (Singapore08:15:24). First RED/GREEN by00:35:24Z;
hard final01:00:24Z (09:00:24). Old leaf branches/outputs remain intact.

## User action and scope

Import and start the existing BTC market-only CLI without loading unused research
PostgreSQL code. Success: fresh child missing pg8000 can construct market-only
factory/CLI without bind/provider calls; ordinary factory/CLI still fail explicitly
before catalog/account/model/store effects. This is software evidence only.

Product code only src/quantmesh/api/workstation.py; one new fresh-child test file
and own plan/iteration. No dependency/lock/PG/feed/buffer/math/vendor/UI edits,
new environment, package install, host/native/GH/CI or full/old-suite replay.
pg8000 remains core required. Do not catch ImportError, hide a broken ordinary
runtime, remove routes or relax client types to Any.

## Implementation steps / expected evidence

- [x] Four fresh-child REDs: market factory, normal factory, normal CLI and market
  CLI all hit current eager import before intended construction seam.
- [x] Same-file loader for the three research router factories. Invoke after
  market-only early-return in ordinary factory and CLI, before other effects.
  Client class import is TYPE_CHECKING only for postponed annotations; preserve
  public signature and route registration. No actual annotation consumer found;
  a concrete conflicting consumer stops scope expansion and returns to root.
- [x] Same four cases GREEN. Scoped Ruff/format/diff; one necessary new
  complete-runtime route-boundary check if the implementation changes that seam.
- [ ] Freeze source commit/tree; reuse original reviewer for independent narrow
  diff review. At most known-correction round2, no third structural review.
- [ ] Final iteration and immutable HANDOFF with hashes/limits to root/publisher.
  Sole publisher owns push/CI/normal merge; native window remains separate.

## Test method

Fresh Python subprocesses, process-local PYTHONPATH=this-worktree/src, cwd this
exact source, blocked pg8000 finder (no uninstall), own tmp path, bounded child
timeout. Actual read-only LiveBuffer in-memory reader + LiveFeed/app/health/403;
sentinels forbid unrelated constructors, uvicorn bind and public transport.
New test file only; retain historical59new/5compat evidence without rerunning it.
Preserve REDs and failed harness logs. No mocked native success or new capacity
claim. Existing dependency/rights/PIT/OOS/paper/native gates remain unchanged.

## Progress / rulings

All four REDs fail at the exact eager-import chain; minimal source delta gives
four PASS11.39s at00:18:09Z, before the20-minute deadline. Final four PASS9.74s
after scoped formatting. No historical59new/5compat rerun.

The one actual-router call-boundary check first encountered a harness assumption:
current FastAPI includes an _IncludedRouter item without .path. Preserve06 log;
only inspect route item types instead of pretending they are flat routes. Corrected
08 check confirms exact factory identities, construction of all three routers,
public signatures and ordinary function bodies unchanged except loader calls.
No product/source change for this oracle correction. Scoped Ruff/format/diff PASS.
