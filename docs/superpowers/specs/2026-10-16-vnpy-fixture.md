# vn.py fixture research slice

Issue: [#177](https://github.com/ZP151/quantmesh/issues/177). Parent: iteration0038.
The operator explicitly authorized this bounded implementation and continued native testing.
Main coordinator owns shared iteration/roadmap/ACTIVE updates; this packet records local roles.

## Planner / Product

One action: from Research jobs, choose an official vn.py strategy, configure parameters
and costs, submit, follow real progress and open/download its verified report.
Success: a browser submission runs the unchanged upstream engine on the pinned small
fixture and displays actual balance, costs, daily equity and fills with matching hashes.

The optional experimental app mounts `/api/research/vnpy-fixture` alongside the
existing workstation. Default production app and baseline job/report contracts stay
unchanged. Runtime is Windows-only, externally installed Python 3.12 with vnpy4.5.0,
vnpy_ctastrategy1.4.1 and vnpy_sqlite1.1.3. No core dependency/lock changes.
Direct imports reuse official DoubleMaStrategy and AtrRsiStrategy without copied or
modified strategy/engine code. Runtime source hashes must match retained official wheel
sources. Exact package/version/source and adapter hashes enter request identity.

## Quant researcher

Fixture is the earlier CC0 synthetic SPY minute CSV, SHA256
`b27b6ed461cf58e9e1c3e4a40edb9e718feab6ace52cc29afb38ef6aa8f7dd96`.
Replay is October7–11 2013,1950bars; warmup is separate and cannot trade. Calendar,
timezone and bar ordering must roundtrip exactly. No predictive or profitability claim.
Capital100000USD, contract size1, tick0.01,252annual days. Fee is bps of turnover;
half spread and slippage are USD per unit per fill, added for native slippage. Each
cost is positive and bounded. Engine-native P&L uses its own accounting, daily marking
and open-position semantics; no fake baseline walk-forward metrics or confidence.
Repeat economic outputs and doubled-cost deterioration are acceptance checks.

## Interfaces and ownership

- New `src/quantmesh/research/vnpy_fixture.py`: strict version1 request/DTOs,
  whitelist/schema, source/fixture pins, local manager, immutable report verification.
- New `src/quantmesh/research/vnpy_fixture_runner.py`: standalone external-venv
  runner, official imports, isolated SQLite, callbacks/progress, native outputs.
- New `src/quantmesh/api/vnpy_fixture.py`: experimental routes and optional local CLI
  app factory. No edit to existing workstation/default routes.
- New `frontend/src/lib/vnpy-fixture-api.ts`, `frontend/src/screens/VnpyFixturePanel.tsx`;
  bounded modification of `frontend/src/screens/ResearchJobs.tsx` for engine choice.
- New dedicated backend and frontend tests, `docs/adr/0029-vnpy-fixture-adapter.md`,
  this spec, matching plan, `docs/research/vnpy-fixture.md` operator/evidence packet.
- No shared ACTIVE/iteration/roadmap/reuse-matrix writes; coordinator mirrors packet.

Options expose strategy parameter bounds/defaults and pinned lineage. Request accepts
strategy_id, parameters and costs only (`schema_version=1`); no executable paths,
imports, datasets or arbitrary code. POST `/jobs` requires UUID Idempotency-Key;
same key/body replays same job; changed body conflicts. GET `/jobs/{id}` reports
queued/running/succeeded/failed/cancelled, stage and measured bars. POST cancel stops
only owned child. GET `/jobs/{id}/report` returns canonical JSON plus SHA256.
Reports contain request/identity, native statistics, daily balance, fills and lifecycle.
Nonfinite statistics become null and are explicit. Failed output never becomes a report.

One local active slot, bounded queue/history,120second/1024MiB/one-core owned child;
use existing Windows owned-process primitive without changing it. No credential
inheritance or user-supplied command. Loopback CLI only. Fixed safe API errors.
Active jobs are in-memory, interrupted on app shutdown, and do not resume after restart.
Completed reports are content addressed and verified when opened; no new JobStore,
PG schema, production ledger or advisory authority. A restart can retain completed
bytes but does not claim durable job discovery. Browser retains its latest job id
and handles unavailable jobs explicitly. Reports can be downloaded independently.

## Licensing and non-goals

Upstream vn.py/CTA/SQLite are MIT; retain official wheel LICENSE and source hashes in
external runtime packet and link upstream. Full external dependency metadata includes
Qt/PySide/shiboken and LGPL components: isolation does not license redistribution.
No wheel/runtime shipping or admission to permissive release closure in this slice.
No production deployment, cloud, model, arbitrary Python, market ingestion, live or
paper orders, strategy promotion, existing validator relaxation or Linux execution.

## Reviewer / Verifier acceptance

Tests first: strict params/cost/identity, stale/tampered inputs, exact source pins,
idempotency/conflict, concurrency, cancellation/timeout/failure, report corruption,
UI unavailable/error/progress/report identity. Native two-strategy runs, repeat and
cost sensitivity; browser desktop/mobile loop. Review spec and quality at the
demonstrable boundary (max two rounds). Record actual exits and limitations in
`docs/research/vnpy-fixture.md`, deliver packet to main before final integration.
