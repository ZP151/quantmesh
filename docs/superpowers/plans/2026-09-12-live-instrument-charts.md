# Live instrument charts implementation plan

> For agentic workers: use the repository subagent-driven/TDD/review lifecycle.

**Goal:** real updating full-size BTC/ETH/SOL charts from Markets and Watchlist
on the existing private AWS workstation.

**Architecture:** reuse LiveHistoryService, the replay buffer, shared history/
workspace APIs, live snapshot/stream utilities and InstrumentChart. Add only an
explicit 1m Hyperliquid replay fallback for 1D, live-mode entry/default handling
and a small shared live instrument list. Preserve research/decision authority.

**Tech stack:** existing Python/FastAPI/DuckDB and React/TypeScript/TanStack Query/
Lightweight Charts 5.2.0; no dependency changes.

**Spec:** `docs/iterations/0035-live-instrument-charts.md`, issue #144.

## Global constraints

- One product slice; independent 0021 soak and #135 firewall remain untouched.
- Paper true/live trading false; no order, new resource, credentials or purchase.
- Keep source timestamps, actual coverage, gaps and provenance visible; no
  fabricated history, synthetic fallback, volume or forecast qualification.
- Retain explicit URL selections, demo behavior and registered decision watches.
- Shared Python: `C:/Users/15492/Develop/QuantMesh/.venv/Scripts/python.exe` with
  current-worktree `PYTHONPATH` and unique OS-temp pytest basetemp. No shared
  environment installations. Frontend uses the existing node_modules junction.

## Task 1 — Actual 1m observations reach history/workspace (backend owner)

Files: `src/quantmesh/instruments/live_history.py`, `tests/test_live_history.py`.
Only affected existing integration tests if required; no frontend edits.

- [ ] Add production-shaped 1m candles, source-time sequence, same-minute
  revision and next-minute append fixtures. Assert both history and workspace
  APIs return matching actual bars/coverage and `5m->1m` fallback for 1D.
- [ ] Run RED: `python -m pytest -q tests/test_live_history.py`.
- [ ] Permit Hyperliquid 1m only when 1D lacks an eligible preferred/coarser
  interval. Preserve manifest preference and every continuity/source-time gate.
- [ ] GREEN same tests plus `tests/test_instrument_history.py` and
  `tests/test_instrument_workspace_api.py`; test missing/disconnected history,
  same-minute dedupe, coverage retention after reopening the buffer, and other
  venue/range refusal. Record exact RED/GREEN and limits; controller owns commit.

## Task 2 — Both entry points lead to real updating charts (controller)

Files: `frontend/src/components/live-market-list.tsx` (new), its component test,
`frontend/src/screens/Markets.tsx`, `frontend/src/screens/Markets.test.tsx` (new),
`frontend/src/screens/Watchlist.tsx`, `frontend/src/screens/Watchlist.test.tsx`,
`frontend/src/screens/InstrumentWorkspace.tsx`, its existing test,
`frontend/src/lib/messages.ts`. Change route helper only if needed, with tests.

- [ ] Add RED tests for live Markets and empty decision-Watchlist still exposing
  actual BTC/ETH/SOL rows, exact venue/symbol chart links, quote timing/labels,
  unavailable/stale states and accurate live wording. Keep saved inbox evidence.
- [ ] Add RED workspace tests: live Hyperliquid defaults to 1D/line, explicit
  range/mode and demo defaults persist; matching candle update refreshes the
  observed series without navigation. Render source/actual coverage and empty
  collection state without claiming a full day or a forecast.
- [ ] Implement shared small live list using existing snapshot/stream/aging
  functions and owned table/badge components. No direct browser venue access.
- [ ] Implement live-aware defaults and collecting-history messaging; reuse
  the full InstrumentChart/MarketCanvas. Preserve selection/zoom on refresh.
- [ ] GREEN relevant Vitest files plus chart tests. Typecheck/lint, generated
  API freshness, build committed bundle. Run Impeccable detector once on changed
  UI targets; inspect desktop/mobile/keyboard in one batch, one correction pass.

## Task 3 — Review, integration and AWS source acceptance (controller)

- [ ] Combined targeted backend/frontend gates, focused packaged-browser
  chart navigation/update fixture and source freshness/disconnect regressions.
- [ ] Independent spec/standards review at the working user-loop boundary;
  at most two rounds. Record outcomes in iteration. Commit one coherent slice.
- [ ] Publish PR referencing #144; resolve findings promptly while final-head
  CI runs. Required full Python/frontend/install/audit/build/lint CI must pass
  before merge; do not start a duplicate full local suite or unrelated soak.
- [ ] Use checked exact-release private AWS update under standing user scope.
  Retain currently accepted live `e185c3b` rollback and older demo `4022942`;
  verify exact build/profile, loopback/private route and paper/live invariants.
- [ ] In actual AWS browser, navigate from both Markets and Watchlist to all
  three symbols. Witness >=2 updates of the active real candle and >=1 next
  minute append; compare chart table points to history/workspace API. Reload
  and verify actual covered points remain. Chart source/coverage must be honest.
- [ ] Controlled fixture proves quiet/disconnect stops fresh claims and recovery
  never bridges a missing interval. Record real-source evidence separately.
- [ ] Complete iteration, roadmap/ACTIVE, exact merge/deployment/acceptance
  record; close #144 only when proven. Moomoo/OpenD readiness remains next.
