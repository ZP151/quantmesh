# Desktop Day/Week Charts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. The original UX owner writes source inline; fresh final reviewers are read-only.

**Goal:** Compare correct daily and weekly observations in time-linked desktop views.
**Architecture:** Existing history API and InstrumentChart, a pure daily/calendar adapter,
pure time-link coordinator and child route. No backend or forecast protocol changes.
**Tech Stack:** Pinned React19/TypeScript/Lightweight Charts5.2.0 and existing CalendarService
package exchange_calendars4.13.2; no dependency installation or copy.
**Spec:** ../specs/2026-11-17-desktop-day-week-charts.md.

## Global constraints

Daily/XNYS semantics only; no hourly-to-RTH conversion, price interpolation or false
completeness. Preserve source identity/unknowns and every trading/admission boundary.
Desktop only; protect8878/18956/64462 and original files. Sole frontend writer; later
forecast/account seams wait their frozen contracts. Retain all failures/future holds
within the independently registered192MiB, supplement before any overrun.

## Review focus

- UTC/New York date rollover, DST, holiday Mondays and early closes.
- Missing whole weeks, duplicate sessions, live tails and boundary partial weeks.
- Range/crosshair echo, view unmount and locale/theme rebuild cleanup.
- Lookback changes preserve bar resolution and make no new model/research request.
- Long identities, source errors/empty inputs and sample qualification remain readable.

## Task 1 — Reproducible daily/weekly data view

**Files:** lib/chart-daily-series.ts+test; lib/chart-calendar.ts+test; generated
lib/calendars/xnys-sessions.ts; frontend/scripts/export-chart-calendar.py.
**Interface:** `buildDailyWeeklySeries(history, calendar)` returns validated daily bars,
weekly OHLCV with actual session lineage, completeness flags and missing dates, or a
named refusal; `chartLookbackWindow(asOf, lookback)` is independent of bar duration.

- [ ] Add failing cases for weekly OHLCV/volume and immutability, holidays/DST,
  missing/partial/live/future sessions, duplicates and hourly/calendar refusal.
- [ ] Run RED and retain stage/output. Export bounded pinned public calendar facts.
- [ ] Implement the pure adapter without API/schema or financial protocol changes.
- [ ] Run GREEN plus chart baseline. Commit source and exact-hash checkpoint.

## Task 2 — Existing chart adapter with time linkage

**Files:** lib/chart-time-link.ts+test; components/charts/InstrumentChart.tsx+test;
components/charts/LinkedMarketCharts.tsx+test.
**Interface:** optional chart interaction binding registers an owned port with
set-time-window/set-crosshair-time and reports range/hover changes; a pure coordinator
maps day/week times, accepts user leadership and suppresses programmatic echoes.

- [ ] RED for both-direction hover/time range, absence, echo and stale/unregistered port.
- [ ] Add only optional time-zone/session-format/height and interaction hooks to the
  existing adapter; preserve legacy defaults, attribution, forecasts and accessibility.
- [ ] Render labeled daily/weekly views, valid lifecycle registration and source tables.
- [ ] GREEN on adapter/coordinator/wrapper plus affected existing chart tests; commit.

## Task 3 — Operable desktop child route

**Files:** screens/MultiPeriodCharts.tsx+test; App.tsx; instrument/MarketCanvas.tsx
bounded entry; lib/messages.ts/nav.ts and owned chart CSS only as required.
**Interface:** fixed daily-source history request (`1y`); independent lookback and
Daily/Weekly/Both controls; source/as-of/limitations; no forecast or business mutation.

- [ ] RED for fixed source request, independent controls, malformed/unavailable input,
  same-instrument entry and English/Chinese copy.
- [ ] Implement route and UI within existing design; no hidden forecast/qualification
  behavior. Keep future Quant forecast controls as an internal existing-prop seam.
- [ ] GREEN affected tests, actual tsc-build/lint, full frontend suite at slice boundary.
- [ ] One bounded owned desktop render/interaction batch if capability available,
  one consolidated fix/confirmation; report unavailable browser capability honestly.

## Task 4 — Review and normal publication

**Files:** own docs/iterations/0038-desktop-day-week-charts.md and reuse note;
registered ignored purpose only for logs/profiles/captures/receipts.

- [ ] Fresh independent spec/code/visual review at coherent slice boundary, at most
  two correction rounds; preserve failing evidence. One final changed-target detector.
- [ ] Update iteration with actual command results, source/tree, source/calendar facts,
  render evidence and remaining limits; freeze to unique Publisher.
- [ ] Normal necessary matching-head CI/merge and runtime-owner actual desktop delivery;
  no old PR307 replay. Notify Root before later account/forecast UI begins.

## Validation commands

Use installed `node node_modules/vitest/vitest.mjs run --maxWorkers=1` on each task's
named files for RED/GREEN; `npm run build`, `npm run lint`, full frontend Vitest and
`git diff --check` at coherent boundary. Publisher runs exact-lock release gates once
the branch is frozen. Do not change dependencies to conceal local/lock version drift.
