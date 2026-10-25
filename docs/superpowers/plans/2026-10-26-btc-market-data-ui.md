# BTC market-data-only UI implementation plan

> Execute inline with TDD and at most two independent narrow review rounds. Root released the UI writer slot; backend and UI are the only implementation writers.

**Goal:** Open the existing BTC1D chart, observe source-backed minute-end REST observations and acquisition state, and find no research/trading/write actions in this opt-in mode.
**Architecture:** Extend optional Health fields; use AppShell as a route/navigation presentation boundary and the incumbent InstrumentWorkspace query/WS/SSE/5second refresh with a restricted chart-only render. Server restriction remains authoritative. Ordinary fields-absent behavior remains compatible.
**Tech stack:** Existing React/TypeScript/TanStack Query/MarketCanvas/InstrumentChart; no dependencies.
**Spec:** Root-approved design7962449c6050c14428a716bad3252a3c4a67184fd791584cebfa4eac9b1a013f; final QM-BTC-MARKET-DATA-ONLY-v1 interfacef7278698f20f676801058395044bdea4ca7f8e4ce855d9d0c7543ccd4ce628c0. Issue[218](https://github.com/ZP151/quantmesh/issues/218). Base7c49d341a40eb000ffd95cac0e4a56e06fc9d336. ACK2026-10-25T16:30:26Z; first testable17:15:26Z; hard18:00:26Z.

## Global constraints

- Own only api.ts Health, AppShell.tsx, InstrumentWorkspace.tsx, messages.ts, new focused tests and this owned plan/iteration. Preserve previous leaves/output; do not touch backend/generated/static/Chart/MarketCanvas/live algorithms/services.
- Only explicit market_data_only activates restrictions. Health acquisition state/reason keys always present; reason is null or exact frozen safe enum. runtime live means acquisition, trading remains disabled.
- Only BTC/1d workspace read; no extra API parameters, research/model/account/proposal/packet/watchlist calls. Forbidden routes/queries must not mount child screens even while health is pending.
- Minute-end public REST snapshot observations, not interim WS archive/provider finality/PIT/full24h. Keep source timestamps and partial/null evidence honest; health polling cannot renew source freshness.
- Preserve last real history on refetch errors/stop; terminal acquisition overrides old connected status. Missing quote/depth is unavailable, never derived from candle close. No mock/native equivalence claim.

## Review focus

1. Health still pending while forbidden deep-link child could issue GETs.
2. Legacy packet/scenario/404 cockpit fallback could mount despite hidden buttons.
3. Stopped feed with connected WS could be labelled actively acquiring/fresh.
4. Repeated same bars or health timestamps could manufacture progress/freshness.
5. Fields absent or false must retain ordinary research behavior.

## Task1 — Shell and optional health

Files: frontend/src/lib/api.ts (Health only), frontend/src/components/shell/AppShell.tsx, frontend/src/lib/messages.ts; new AppShell.market-data-only.test.tsx.
- [x] RED: health-pending child not mounted; explicit mode exposes only BTC route and disabled-trading label; forbidden route/extra query stays unavailable without child mount; CtrlK/search/reset/kill/settings/palette absent; fields absent allows ordinary child.
- [x] Implement exact optional fields, mode-specific nav/copy/outlet boundary and5s health refresh for acquisition only. No forbidden side effects from child or palette.
- [x] GREEN: npx vitest run src/components/shell/AppShell.market-data-only.test.tsx.

## Task2 — Restricted existing chart loop

Files: frontend/src/screens/InstrumentWorkspace.tsx and new InstrumentWorkspace.market-data-only.test.tsx.
- [x] RED: BTC1d formal API shape; invalid venue/range/packet/horizon/compare cannot issue calls;404collecting has no Cockpit fallback; no scenario/model/order/account/decision mutation consumers.
- [x] Implement guarded queries and chart-only render before decision composition; reuse incumbent WS/SSE and completion-spaced5s refresh. Acquisition state visibly distinct from actual data timestamps; show source, observed rows, gaps/limitations and unavailable quote/depth. Existing chart display controls remain local to this mode, no extra URL/API keys.
- [x] RED/GREEN: last bars survive capacitystop/failed/refetch error; health-only update does not change observed timestamps; next actual test timestamp changes chart data, identical refresh does not claim advancement; fields-absent ordinary behavior remains.
- [x] GREEN: npx vitest run src/screens/InstrumentWorkspace.market-data-only.test.tsx.

## Task3 — Freeze and handoff

- [x] Run only new and directly affected tests, scoped lint, own-dist build and diff. No full old numerical/backend suites.
- [x] Independent narrow review(max2rounds), aggregate known corrections, update owned iteration and commit source/head/tree/hashes with honest mock/native boundary.
- [x] Stop for root/publisher combination; do not start preview or generate production static. Actual desktop390/1440 browser and distinct new completed minute timestamps require the root-supplied merged source/PID/URL and sole native operator.

## Verification result

28new focused tests pass in2files; the earlier affected run passed61tests(24new+37existing InstrumentWorkspace cases) on the same production delta. Own-dist build/scopedlint/diff pass; both target detectors[]. R1 independent readonly reviewREADY, no Important/Critical findings; no second round required. Evidence is in output/market-data-ui/HANDOFF.json and [owned iteration](../../iterations/0038-btc-market-data-ui.md). DOM fixtures and a chart spy establish component behavior only; no preview/native/provider/browser or complete-day qualification evidence is claimed.
