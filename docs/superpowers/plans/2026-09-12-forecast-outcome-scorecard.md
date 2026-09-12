# Forecast Outcome Scorecard Implementation Plan

> **For agentic workers:** Use the repository subagent implementation/review lifecycle. Steps use checkboxes; each role records evidence in iteration 0033.

**Goal:** Compare a saved packet's exact forecast with realized daily closes and replay its frozen review within 120 seconds.

**Architecture:** Pure response projection of existing validated outcome snapshots, served by the existing review endpoint. Existing durable identities and ledgers are unchanged. The review panel owns display and uses the established chart adapter.

**Tech Stack:** Python/Pydantic/FastAPI; React/TypeScript/Lightweight Charts; existing shared Python/npm dependencies.

**Spec:** `docs/superpowers/specs/2026-09-12-forecast-outcome-scorecard-design.md`

## Global constraints

- 7/30 exact sessions, legacy 30; no interpolation or latest-artifact substitution.
- Saved `review.outcome` wins. No persisted schema/ID changes.
- Aggregates only for complete paths. Descriptive path errors are neither calibration nor P&L.
- No new dependencies, providers, cloud, live execution, operational tracks or notifications.
- Commands <=300s and coherent targeted verification <=600s; automatic CI supplies broad suite evidence.

## Task 1: Derived response and quantitative tests

Files: create `src/quantmesh/instruments/forecast_outcomes.py`,
`tests/test_forecast_outcomes.py`; modify `src/quantmesh/instruments/reviews.py`.
Interface: `compare_forecast_outcome(outcome: DecisionOutcomeSnapshot) -> ForecastOutcomeComparison`;
computed property `DecisionOutcomeReviewState.forecast_comparison` selects saved outcome first.
Response fields: policy_version, outcome_id, forecast_artifact_id, horizon_sessions,
status, reason, observed_sessions, rows; mean_absolute_error, benchmark_mae,
interval_hits, interval_coverage, terminal_error (nullable complete-only scores).
Rows: session, timestamp, p10, p50, p90, actual_close, absolute_error, within_interval.

- [x] RED: lightweight real-store fixtures; hand-calculated errors/edge-inclusive hits,
  7 versus legacy 30, timestamp gap, pending/empty/missing forecast, frozen saved
  result after newer preview and store restart. Run `python -m pytest tests/test_forecast_outcomes.py -q`.
- [x] GREEN: implement exact pure projection, wire response computed property.
- [x] Verify no comparison key enters persisted snapshot JSON and legacy packet
  ID fixture remains unchanged. Run targeted test above plus `tests/test_scenario_lab.py`.

## Task 2: Visible comparison and existing save/replay loop

Files: create `frontend/src/screens/instrument/ForecastOutcomeComparison.tsx`
and `.test.tsx`; modify `PacketOutcomeReview.tsx`, `.test.tsx`, messages en/zh-CN,
generated OpenAPI and `components/charts/InstrumentChart.tsx` only as needed
for an explicit overlay/whitespace mode with its adapter regression test.

- [x] RED: component tests render known complete scores, missing session and
  honest incomplete state, Chinese labels, saved-over-preview response and exact
  save ID. Run Vitest on named comparison/review files.
- [x] GREEN: insert comparison before detailed attribution, with frozen median/
  interval and exact observed prices, responsive metrics and full row disclosure.
  No service fetch or metric recomputation inside the chart adapter.
- [x] Generate/check API with existing `frontend/scripts/openapi-client.mjs`.
- [x] Run actual `tsc -b`, scoped Oxlint, relevant chart/review/ScenarioLab tests,
  rebuild/check packaged assets using `tools/build_frontend.py`.

## Task 3: Acceptance, review and publication

- [x] Local same-origin real-service acceptance: open a saved packet, inspect
  comparison, save review, reload; compare response rows/metrics after source
  replacement and review-store restart. Time the user loop (<120s).
- [x] One desktop and 390px EN/zh browser batch: readable plot/table/status,
  keyboard disclosure, no document overflow. One correction batch if needed.
- [x] Independent Standards/Spec reviewer: exact evidence, incomplete semantics,
  unchanged identities, API/UI alignment and trading safety. Maximum two rounds.
- [x] Controller verifies targeted Python/Vitest, Ruff/format, TypeScript,
  OpenAPI, packaged freshness and `git diff --check`; records exits and counts.
- [x] Commit coherent reviewed slice, push, open one PR linking its issue. Do
  not dispatch release/soak. Record automatic CI state truthfully at handoff.

Plan self-review: every spec requirement maps to Tasks 1–3. No architecture
migration, new data collection, independent frontend backlog or deferred placeholder.
