# vn.py Fixture Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for inline implementation; one fresh whole-branch reviewer before integration. Steps use checkboxes.

**Goal:** Complete strategy selection → native fixture backtest → progress → verified report in QuantMesh.

**Architecture:** Separate opt-in API/report contract; external fixed vn.py virtualenv and unmodified strategies. Existing production job/store/report contracts remain frozen.

**Tech Stack:** Python/FastAPI/Pydantic, Windows owned process, vn.py CTA/SQLite, React/TypeScript/Vitest.

**Spec:** `docs/superpowers/specs/2026-10-16-vnpy-fixture.md`, issue177.

## Global Constraints

- Windows external Python3.12; vnpy4.5.0 / CTA1.4.1 / SQLite1.1.3; no core dependencies.
- Fixed synthetic fixture SHA256 b27b6ed461cf58e9e1c3e4a40edb9e718feab6ace52cc29afb38ef6aa8f7dd96.
- Fee bps; half spread/slippage USD per unit per fill. No baseline validator changes.
- Source/fixture/parameters/cost units pinned to identity; paper/live order authority absent.
- Main coordinator owns shared ACTIVE/iteration/roadmap; local evidence in owned packet.

## Review Focus

1. Malformed numeric input/unknown parameters must fail before external execution (Task1).
2. External interpreter/source or fixture drift must fail closed (Task1/2).
3. Duplicate submit, cancelled process and app shutdown must not leak children (Task2).
4. Corrupt/mismatched result must never display as successful verified report (Task2/3).
5. Offline/unknown job after restart must preserve downloadable prior report and allow recovery (Task3).

### Task1: Pinned contracts and execution adapter

**Files:** create `src/quantmesh/research/vnpy_fixture.py`,
`src/quantmesh/research/vnpy_fixture_runner.py`, `tests/test_vnpy_fixture.py`.

**Interfaces:** `FixtureRequest` strict schema; `options()` whitelist metadata;
`FixtureManager(python: Path, fixture: Path, root: Path)` admits fixed runtime;
`submit(request, key)`, `get(id)`, `cancel(id)`, `report(id)`, `close()`.
Runner takes one owned directory argument and gates on stdin before imports.

- [x] Write tests for defaults, cross-param validation, finite positive costs,
  unknown keys, canonical parameter identity, fixture drift and source pins.
- [x] Run `python -m pytest tests/test_vnpy_fixture.py -q`; retain missing-module RED.
- [x] Implement contracts and direct upstream runner with callback-driven progress,
  native stats/daily/fills, timezone roundtrip and cost/lineage identity.
- [x] Run targeted tests GREEN. Native external runner tests stay explicit opt-in.

### Task2: Observable owned job API

**Files:** create `src/quantmesh/api/vnpy_fixture.py`, `tests/test_vnpy_fixture_api.py`;
extend Task1 manager and tests.

**Interfaces:** `create_vnpy_fixture_router(manager)` prefix
`/research/vnpy-fixture`; `create_fixture_app(manager)` returns workstation with
router mounted at `/api`; `main(argv=None)` local opt-in startup via `python -m`.
Status DTO includes id/request_digest/state/stage/completed_bars/total_bars/error_code;
report envelope includes schema_version/request_digest/sha256/report.

- [x] Write and run RED for absent runtime, idempotent replay/409, invalid422,
  bounded queue, unknown404, real terminal failure/cancel and corrupt report rejection.
- [x] Implement manager single slot/background thread, fixed owned subprocess,
 120s/1024MiB/one-core, safe errors, immutable content-addressed JSON and shutdown.
- [x] Implement router and loopback CLI without changing production app factory.
- [x] Run `python -m pytest tests/test_vnpy_fixture*.py -q` GREEN.

### Task3: Research jobs product loop

**Files:** create `frontend/src/lib/vnpy-fixture-api.ts`,
`frontend/src/screens/VnpyFixturePanel.tsx` and corresponding `.test.tsx`;
modify `frontend/src/screens/ResearchJobs.tsx` only to expose engine choice;
generate `src/quantmesh/api/static/app/**` with existing `tools/build_frontend.py`.

**Interfaces:** `vnpyFixtureApi.options/submit/get/cancel/report`; component owns
strict response validation, bounded polling, latest-id localStorage, SHA verification
and independent JSON download. Baseline component remains default.

- [x] Run impeccable context helper and preserve incumbent Operate design tokens.
- [x] Write component RED for available strategies, param/cost changes, actual
  submit body, progress, terminal report, corruption/error/restart recovery.
- [x] Implement accessible forms, explicit units, fixture marker, measured progress,
  native metrics, daily equity/fills and downloadable lineage-rich report.
- [x] Run `npm exec vitest run src/screens/VnpyFixturePanel.test.tsx`; `npm run
  typecheck`; `npm run lint`; backend targeted suite GREEN.

### Task4: Native evidence, review and integration packet

**Files:** create `docs/adr/0029-vnpy-fixture-adapter.md`,
`docs/research/vnpy-fixture.md`; update this plan only.

- [x] Actual two-strategy API runs on retained venv/fixture; repeat DoubleMA and
  doubled costs; validate1950 replay bars, separate warmup, source equality and cashbook.
- [x] Actual desktop/mobile browser submits to native backend and views report;
  capture evidence, no mock substituted for final user loop.
- [x] Run targeted backend/frontend checks plus relevant boundary gates from
  `docs/agents/collaboration.md`, formatting/lint/diff; record exits.
- [x] Fresh read-only spec/quality review; at most two rounds, fix with RED/GREEN.
- [ ] Commit coherent green slice, push own branch and open/attach draft PR;
  report issue/commit/PR, proof paths and limitations to main. Main owns integration.

## Requirements checklist

- [x] Strategy choice and validated parameters/costs
- [x] Real upstream native process and progress
- [x] Verified immutable report with native accounting and lineage
- [x] No production protocol/dependency/trading boundary changes
- [ ] Tests, native browser loop, notices and independent review agree

## Execution ledger

2026-10-16 Planner/Quant: scope approved by direct human instruction, main confirms
experiment protocol boundary. External bakeoff42checks retained, not rerun wholesale.
Git recovery confirmed by coordinator; reused partial native worktree at d90e3ac,
branch codex/0038-vnpy-fixture-loop. Native attachment rejected ownerless verification;
checkout remains valid and independent. No shared Git config changed here.

2026-10-16 Implementer/Verifier: contracts/API RED missing modules then17GREEN;
accounting/strict-cost RED6failed19passed then28GREEN. Review regressions reproduce
cancel cleanup, restart404 and source-drift failures, then final backend31GREEN.
Frontend RED missing component; two state regressions RED then20GREEN; transport
and review recovery tests give31GREEN. Full frontend436passed/35files, exit0.
Final reviewed native four-run acceptance passes8.47s/exit0; repeat economic report
hash identical, doubled costs adverse, official ATRRSI33fills. Built SPA actual
browser loop passes fast8/slow18/fee6,1950bars,31fills; downloaded report hash
57134549cb2f95127c3a129d24656ccb03723d25f057469643f062a4780f6720.

2026-10-16 Reviewer: first bounded review3P2, fixed test-first; second/final
review PASS/no remaining P1P2. Durable review receipt in
`output/vnpy-fixture/review-pass.md`; no third review. Main coordinator explicitly
confirmed generated bundle ownership extension required by existing CI.
Ruling: retain existing builder's generated SPA output in this slice because
the package serves committed assets and CI refuses stale output; no new behavior.
Full backend gate is running once at final boundary; no repeated hourly suite.

2026-10-16 Coordinator ruling: local full backend gate did not finish; at9% after
roughly10minutes read-only stacks show existing demo/DuckDB seeding. One original
testcase probe passed51.45s/exit0. Root requested identity-checked stop of owned
PID72068 and explicitly authorized scoped green commit plus Draft PR with this
gate NOT PASSED and Linux CI pending. Actual full exit-1 and process receipt are
retained; root cause remains undetermined, no unrelated source/dependency changes.
Frontend full436pass/exit0, bundle--check current/exit0, generated API current/exit0,
all Ruff src/tests/tools pass; final original-job/adapter boundary suite pending.
This is an explicit delivery gate handoff, not a full completion or merge approval.

Final original-job/adapter boundary106passed/1skipped/28.50s, explicit exit0 in
`backend-boundary-exit.json`; Windowsfull remains interrupted. Locked frontend
license review passes362packages. Built browser verification10checks all true,
actual raw balance100046.097438USD (display rounded5decimals);390px viewport has
375px content and no horizontal overflow. All successful native/browser evidence
is retained without further repetitions or a third review.
