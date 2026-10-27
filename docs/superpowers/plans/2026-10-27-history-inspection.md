# Saved history inspection implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. One full-stack writer; one fresh whole-slice review, maximum two rounds.

**Goal:** Select a timezone-explicit historical end beside the chart, inspect the preceding saved day or honest unavailability, then return to current behavior within two minutes.
**Architecture:** Independent fixed1d GET and inspection read method reuse manifest-first and bounded replay without joining live snapshots. An isolated chart child unmounts current consumers while inspecting; the app and trading clocks never change.
**Tech Stack:** Existing FastAPI/Pydantic, LiveBuffer/DuckDB, React/TanStack Query/MarketCanvas. No dependencies.
**Spec:** ../specs/2026-10-27-history-inspection.md; issue https://github.com/ZP151/quantmesh/issues/237.

## Global constraints

- Approved design SHA356ee6e720b593b93de270b9234e72a9bf3aabd7f83349127c02644b25d1f937; human approval2026-10-27. Actual ACK15:37:11Z, first increment17:37:11Z, reviewed slice19:37:11Z. Prior causal leaf remains sealed.
- Source base actual fetched origin/main0e01442; rc1 already prereleased09:22:05Z. Do not alter release metadata/CI/tag/generated/static/locks/README or parallel trend files.
- Read-only, fixed1d, supported Hyperliquid or Moomoo AAPL/NVDA. Original UTC/STATUS/interval/last-segment/identity gates, per-store10000 tail/final10000/128-key/128MiB/one thread/0spill stay. No gap fill/aggregation/new provider/host/real DB/permission.
- observed_at is actual server now; at is window selection only. Original source_time and last selected receipt remain distinct. Manifest receipt unknown stays null. No live-tail join, historical workspace/forecast/Paper/POST/fence, or qualification upgrade.

## Review focus

- Numeric/unzoned/future/duplicate at and unknown query fields must fail before any storage read; offset ISO dates normalize to UTC.
- An earlier max receipt must not substitute for the final selected row receipt; current clock cannot be injected through the existing workspace clock.
- Window changes and return-to-current hide previous results/errors immediately, including out-of-order responses and instrument navigation.
- A missing archive/native resource failure must stay explicit unavailable rather than hot-only success or empty series.
- History UI must be usable before current data loads or when current history is404; no historical mutation consumers mount.

## One vertical slice

Files: instruments/{contracts,live_history,api}.py; frontend/src/{screens/InstrumentWorkspace.tsx,screens/instrument/SavedHistoryInspection.tsx,lib/api.ts,lib/messages.ts}; dedicated tests, own spec/ADR/iteration and this plan. No other implementation writer.

- [x] RED `pytest -q tests/test_history_inspection.py`: independent route missing; assert old JSON unchanged, explicit at validation/real clock, original receipt vs source, no live join, manifest first, STATUS/gap, original bounded filters/refusal and Paper clock unaffected. Tests use small real synthetic DuckDB or narrow boundary doubles only.
- [x] GREEN add HistoricalInspection with primary, observed_at/window_end/source_time/source_received_at/stale and explicit stale_after_seconds (two selected intervals). Add LiveHistoryService.inspect(...,at,observed_at) and preserve private `_replay_series` signature by extracting receipt-returning private helper. Plain HistoryService manifest case supplies no receipt; route uses datetime.now(UTC), never instrument_clock, and only accepts one explicit ISO aware at. Missing service/data maps404, bad input422. Commit backend green checkpoint with iteration evidence.
- [x] RED targeted new UI Vitest: entry before current data; date validation; independent GET only; truthful time/stale/coverage labels; clear on edit/load/error/late response; return current without anchor; unsupported scope and market-data-only restrictions unchanged. Add client-only fixed response type until publisher regeneration (no generated edits).
- [x] GREEN isolated SavedHistoryInspection child reuses MarketCanvas, accessible timezone-explicit text input, error/empty states, source/receipt/coverage and historical-only notice; current child is unmounted, default URL/requests unchanged. Read PRODUCT/DESIGN and impeccable craft-floor before UI editing. Commit full loop green checkpoint.
- [x] Targeted affected Python and frontend checks, changed-file Ruff/format, TypeScript, frontend lint and diff. New RED/GREEN logs retained; no old full suite. Use existing node_modules without install. No production build output; publisher owns one final regeneration/build/CI.
- [x] Owned loopback FastAPI plus Vite development service against construction-time synthetic saved fixture; desktop/390px operation, actual URL/screenshots and time semantics, unavailable and return path. Stop only owned processes and retain artifacts.
- [x] One independent whole-slice review; one aggregate important correction if necessary with RED/GREEN, at most two rounds. ADR/iteration role outputs and actual evidence agree; immutable HANDOFF with source HEAD/tree/filemanifest, commands/exits and limitations to root/publisher. Publisher alone owns final applicable CI/normal merge.

Self-review: approved constraints map to this single slice. Ruling: add a small focused frontend child to isolate historical hooks and prevent current decision consumers from remaining mounted; no visual redesign. Native time uses real datetime.now independent of the historical test clock. Staleness is explicit two-bar-interval display metadata, not trading freshness or rights.
