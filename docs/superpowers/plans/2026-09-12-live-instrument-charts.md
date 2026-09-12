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
Approved narrow expansion: `src/quantmesh/instruments/contracts.py` and
`tests/test_instrument_history.py` admit the same identity-checked 1m fallback;
no schema-field change. No frontend edits.

- [x] Add production-shaped 1m candles, source-time sequence, same-minute
  revision and next-minute append fixtures. Assert both history and workspace
  APIs return matching actual bars/coverage and `5m->1m` fallback for 1D.
- [x] Run RED: `python -m pytest -q tests/test_live_history.py`.
- [x] Permit Hyperliquid 1m only when 1D lacks an eligible preferred/coarser
  interval. Preserve manifest preference and every continuity/source-time gate.
- [x] GREEN same tests plus `tests/test_instrument_history.py` and
  `tests/test_instrument_workspace_api.py`; test missing/disconnected history,
  same-minute dedupe, coverage retention after reopening the buffer, and other
  venue/range refusal. Record exact RED/GREEN and limits; controller owns commit.

## Task 2 — Both entry points lead to real updating charts (controller)

Files: `frontend/src/components/live-market-list.tsx` (new), its component test,
`frontend/src/screens/Markets.tsx`, `frontend/src/screens/Markets.test.tsx` (new),
`frontend/src/screens/Watchlist.tsx`, `frontend/src/screens/Watchlist.test.tsx`,
`frontend/src/screens/InstrumentWorkspace.tsx`, its existing test,
`frontend/src/lib/messages.ts`. Change route helper only if needed, with tests.
Bounded live-follow/aging acceptance additionally owns
`frontend/src/components/charts/InstrumentChart.tsx` and its test, plus
`frontend/src/screens/instrument/WorkspaceHeader.tsx` and new header test.

- [x] Add RED tests for live Markets and empty decision-Watchlist still exposing
  actual BTC/ETH/SOL rows, exact venue/symbol chart links, quote timing/labels,
  unavailable/stale states and accurate live wording. Keep saved inbox evidence.
- [x] Add RED workspace tests: live Hyperliquid defaults to 1D/line, explicit
  range/mode and demo defaults persist; matching candle update refreshes the
  observed series without navigation. Render source/actual coverage and empty
  collection state without claiming a full day or a forecast.
- [x] Implement shared small live list using existing snapshot/stream/aging
  functions and owned table/badge components. No direct browser venue access.
- [x] Implement live-aware defaults and collecting-history messaging; reuse
  the full InstrumentChart/MarketCanvas. Preserve selection/zoom on refresh.
- [x] GREEN relevant Vitest files plus chart tests. Typecheck/lint, generated
  API freshness, build committed bundle. Run Impeccable detector once on changed
  UI targets; inspect desktop/mobile/keyboard in one batch, one correction pass.

## Task 2a — Closed-minute revision admission (actual-source prerequisite)

Files: `src/quantmesh/live/hyperliquid.py`, `tests/test_live_supervisor.py`,
`tests/test_live_feed.py`; optional isolated `tests/test_live_candle_revisions.py`
if needed to keep the real-pump regression cohesive. Controller owns ADR-0024
and iteration/goal evidence. No other implementation files are authorized.

- [x] RED: shared Python `-m pytest -q tests/test_live_candle_revisions.py`
  (or the selected new tests in the two existing files). Replay the recorded
  14:22 BTC candle at 14:23:00.033701 and .538628, volume 26.45105 -> 26.45336,
  through real LiveFeed.run/LiveBuffer. Assert both observations reach replay
  and subscribers and later BTC/ETH/SOL quotes still flow.
- [x] Use one normalized OHLCV-qualified identity helper for WebSocket and REST
  candles, including closed intervals. Preserve provisional identities, final
  flag semantics, source sequence, persistence acknowledgement and gap gates.
- [x] Assert identical receipts and WS/REST content deduplicate; different
  content revises. Reopen a legacy-ID buffer without rewriting its evidence;
  admit the new observation and coalesce same-minute chart replay. Keep actual
  explicit-ID/content conflicts quarantined and rejected.
- [x] GREEN selected regressions plus `tests/test_live_supervisor.py`,
  `tests/test_live_feed.py`, `tests/test_live_buffer.py` and
  `tests/test_live_history.py`; independent review capped at two rounds.
  Include this dependency in the coherent commit and final CI before deployment.

Compatibility: ADR-0024 preserves legacy IDs and rows. One equal-content
observation may append under the new identity after upgrade; subsequent
new-format redeliveries deduplicate. No retroactive exactly-once claim. Recovery
does not promise discovery of older-minute corrections outside its fetch window.
No ledger migration, conflict suppression, watchdog, grace period, provider or
trading change. Older-minute cursor policy is recorded as a separate follow-up.

## Task 3 — Review, integration and AWS source acceptance (controller)

### Planner return after deployed acceptance attempt 1

PR #145 is merged and `90fe577` is deployed, but the continuous-source gate
failed. Freeze the chart UX and reopen only two directly reproduced source
boundaries on `codex/0035-chart-acceptance` / issue #144:

**Task 3a — Local-observation identity:** own `src/quantmesh/live/hyperliquid.py`
and new `tests/test_live_observation_identity.py`. Audit `activeAssetCtx` and
`allMids`, whose observation clock lacks an upstream stable event identity.

- [x] RED: `python -m pytest -q tests/test_live_observation_identity.py`.
  Same-millisecond observations with distinct microseconds must survive the real
  feed/buffer path, including identical and changed normalized payloads. Same
  full clock with changed payload must also remain distinct; exact same clock
  and content must deduplicate. Subsequent three-symbol quotes must still flow.
- [x] Include full-precision normalized UTC observation time and normalized
  payload in identities for these two channels only. Preserve exchange-timed
  quote/book/trade and candle semantics, explicit-ID conflict quarantine,
  append-only legacy evidence and all source/freshness/continuity fields.
- [x] GREEN focused tests plus candle revisions, feed, buffer and supervisor;
  controller records compatibility in ADR-0024 and independent review.

**Task 3b — Workspace request cut:** own `src/quantmesh/live/feed.py`,
`src/quantmesh/instruments/workspace.py`, `tests/test_live_feed.py` and
`tests/test_instrument_workspace_api.py`. Existing public API reproduction is
RED: one assembly-race failure, two genuine future-time controls pass.

- [x] RED the public workspace interleaving: inject a quote during history
  assembly after the request clock; response retains its captured quote and the
  next request observes the new quote. Test clock sampled once with detached
  payload/proof and source-state freshness, including the clock/read boundary.
- [x] Capture request clock and exact quote/proof atomically under the existing
  feed lock. Compose header evidence from that captured snapshot. Keep the same
  generated timestamp for history/valuation and preserve existing `snapshot_exact`
  semantics for other consumers. No source/receipt-future tolerance relaxation.
- [x] GREEN `python -m pytest -q tests/test_live_feed.py
  tests/test_instrument_workspace_api.py`; genuine future receipt, excessive
  source skew, missing/stale/disconnected quotes and valuation race stay guarded.

Controller owns docs, integration, a fresh independent review (maximum two
rounds for this reduced batch), combined local gate and final-head CI/PR before
another deployment. No collector watchdog, general time model rewrite, buffer
exception suppression, new provider, UI redesign or trading authority changes.
Acceptance reruns both actual API and browser witnesses together: early price
movement is insufficient if freshness later fails. Preserve four existing
quarantine records; require no new false collisions. Issue #144 stays open.

- [x] New `tests/test_live_chart_e2e.py` proves the packaged live chart loop
  through both entry points, real-shaped 1m revisions/appends and reload.
- [x] Combined targeted backend/frontend gates, focused packaged-browser
  chart navigation/update fixture and source freshness/disconnect regressions.
- [x] Independent spec/standards review at the working user-loop boundary;
  at most two rounds. Record outcomes in iteration. Commit one coherent slice.
  External findings caused a documented Planner return and reduced boundary
  batch; its independent review and final local gate passed.
- [x] Publish PR referencing #144; resolve findings promptly while final-head
  CI runs. Required full Python/frontend/install/audit/build/lint CI must pass
  before merge; do not start a duplicate full local suite or unrelated soak.
- [x] Use checked exact-release private AWS update under standing user scope.
  Retain prior live `e185c3b` and older demo `4022942` rollback artifacts;
  e185c3b has the diagnosed identity limitations recorded in the iteration.
  verify exact build/profile, loopback/private route and paper/live invariants.
- [x] In actual AWS browser, navigate from both Markets and Watchlist to all
  three symbols. Witness >=2 updates of the active real candle and >=1 next
  minute append; compare chart table points to history/workspace API. Reload
  and verify actual covered points remain. Chart source/coverage must be honest.
- [x] Controlled fixture proves quiet/disconnect stops fresh claims and recovery
  never bridges a missing interval. Record real-source evidence separately.
- [ ] Complete iteration, roadmap/ACTIVE, exact merge/deployment/acceptance
  record; close #144 only when proven. Moomoo/OpenD readiness remains next.
