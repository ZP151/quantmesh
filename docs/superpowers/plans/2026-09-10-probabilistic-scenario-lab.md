# Probabilistic Scenario Lab Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development for independent files and test-driven-development for behavior changes. The controller may implement tightly coupled integration steps directly. Steps use checkbox syntax for tracking. The operator's one final review plus one correction/confirmation ceiling overrides repeated task-review templates.

**Goal:** Open a supported equity into a large daily chart, inspect exact 7/30-session forecast evidence, save a decision and replay it unchanged.

**Architecture:** Extend Instrument Workspace and DecisionPacket, preserving legacy serialization. Reuse the forecast registry, chart adapter, calendars, trusted-data exact-ID readers and existing risk/paper/monitor/review services. New confidence qualification can only restrict Paper.

**Tech Stack:** Python/FastAPI/Pydantic, React/TypeScript, owned shadcn primitives, Lightweight Charts 5.2.0.

**Spec:** `docs/superpowers/specs/2026-09-10-probabilistic-scenario-lab-design.md`

## Global constraints

- Issue #136; branch `codex/0032-probabilistic-scenario-lab`, base `a78ff0a`.
- Moomoo AAPL/NVDA only, daily history, 7/30 sessions; legacy 126 and other venues unchanged.
- Legacy packet/artifact/monitor/review canonical identity remains valid.
- No probability from quantiles; demo-synthetic is explicit; real lineage uses exact IDs only.
- No cloud/operations/0021/0030/0031/provider/root changes or new dependencies.
- Commands have a 300s ceiling; one coherent verification selection targets 600s. No full pytest/domain sweep/release/soak or environment multiplication.
- One final Standards/Spec review and batched desktop/390px UI check; one correction and confirmation maximum. No sidecar repair.

## Runtime and verification protocol

Reuse `C:/Users/15492/Develop/QuantMesh/.venv/Scripts/python.exe` with `PYTHONPATH=<this worktree>/src;<this worktree>` and `PYTHONUTF8=1`. Use a unique OS-temp pytest basetemp. Reuse existing npm modules through a worktree-local junction if the lock digest matches; otherwise install only the locked frontend environment once. Python tooling must not import the shared checkout's editable source. Use `tsc -b` (the existing root `tsc --noEmit` alone does not check referenced projects). Keep command output and elapsed time in the ledger, and terminate owned process trees at the ceiling.

## Task 1: Open the chart from each entry

**Files:** `frontend/src/components/instrument-entry.tsx` (new), `frontend/src/lib/instrument-route.ts`, `frontend/src/screens/Overview.tsx`, `Markets.tsx`, `Watchlist.tsx`, `frontend/src/components/shell/CommandPalette.tsx`; tests in `frontend/src/components/instrument-entry.test.tsx`, `frontend/src/screens/Overview.test.tsx`, `NavigationAndValuation.test.tsx`.

**Interfaces:** `scenarioLabPath(symbol: 'AAPL' | 'NVDA', horizon: 7 | 30 = 30): string` returns the existing instrument route with explicit horizon and fresh-analysis intent. `InstrumentEntry` normalizes supported tickers and renders one keyboard-submittable action; localized copy uses preferences. Existing `decisionPacketPath` stays an exact replay link.

- [x] Write behavior tests for lowercase NVDA submission, unsupported ticker feedback, home stock route, command-palette ticker activation and preserved exact Inbox replay.

```tsx
await user.type(screen.getByRole('textbox', { name: 'Ticker' }), 'nvda')
await user.click(screen.getByRole('button', { name: 'Open chart' }))
expect(screen.getByTestId('location')).toHaveTextContent('/instruments/moomoo/NVDA?horizon=30&analysis=fresh')
```

- [x] Run new named Vitest cases and retain expected navigation/control RED.
- [x] Implement the route helper and shared entry; change Home's instrument links; add ticker options to existing palette; preserve separate order actions and exact Inbox decision links.
- [x] Re-run affected files; record GREEN and TypeScript result. This entry becomes usable against the existing chart while Tasks 2–4 complete the same slice.

## Task 2: Persist and qualify exact selected-horizon evidence

**Files:** `src/quantmesh/instruments/contracts.py`, `scenario_lab.py` (new), `decision_analysis.py`, `decision_packets.py`, `workspace.py`, `api.py`, `monitoring.py`, `reviews.py`; `tests/test_scenario_lab.py` (new), directly affected nodes in decision packet/API/monitor/review tests. Controller owns generated OpenAPI and frontend transport after the Python contract is final.

**Interfaces:** Add optional `DecisionPacket.scenario_lab` with format version, `selected_horizon: Literal[7,30]`, immutable `history: HistoricalSeries`, `confidence: Literal['qualified','low-confidence','abstain']`, reasons and policy version. Add `effective_horizon(packet) -> int` with legacy 30. Extend workspace render/HTTP query with optional `horizon: Literal[7,30]` and `forecast_id: str | None`; extend save body/service with horizon for exact staged-draft fallback. Existing calls without these parameters retain legacy behavior.

- [x] Write tests for absent extension preserving pre-extension JSON/hash, new horizon identity, two same-as-of roots, selected path targets, strict MAE equality/loss, insufficient residual/interval count, stale/missing paths and immutable child analysis.

```python
assert decision_packet_id(DecisionPacket.model_validate_json(legacy_json)) == legacy_id
assert seven.scenario_lab.selected_horizon == 7
assert seven.packet_id != thirty.packet_id
assert not non_improving.paper_capability.allowed
assert all(item.probability is None for item in seven.scenarios)
```

- [x] Run `pytest tests/test_scenario_lab.py -q` for RED.
- [x] Implement a pure evidence assessor; persist bounded chart snapshot and selected horizon. Omit only the absent extension from legacy serialization. Carry new extension through scope, staged save and child comparisons. Derive confidence and paper refusal server-side; never trust browser facts.
- [x] Resolve requested forecast by exact ID. Bind history to its dataset/revision/manifest/as-of; missing or mismatched exact closure refuses forecast without latest fallback. Ensure saved replay can render independently of current history.
- [x] Parameterize only new packet horizon consumption in scenario/risk, monitoring baseline and outcome target/length validation. Old records retain 30 and their bytes/IDs. Keep existing quote/risk/second-confirmation path intact.
- [x] Prove fast real-store save/reconstruction, tampered history/selection refusal, exact artifact non-substitution, selected 7-session monitoring/review and legacy 30 compatibility. Run the new file plus named adjacent regressions within command ceilings.

## Task 3: Admit XNYS forecast dates without invalidating legacy artifacts

**Files:** `src/quantmesh/instruments/forecast.py`, `src/quantmesh/demo/seeder.py`, relevant historical fixture generator only if necessary; `tests/test_scenario_calendar.py` (new), named `tests/test_price_forecast.py`/demo regressions.

**Interfaces:** `run_price_forecast(..., session_calendar: Literal['legacy','XNYS'] = 'legacy')` adds explicit new config selection, with config digest and limitations owning version identity. Existing calls and existing artifact validators preserve legacy calculations. Registry dispatches recomputation from the admitted config digest, never arbitrary model text. New scoped demo forecasts opt into XNYS; no provider calls.

- [x] Pin legacy artifact bytes and ID; write holiday/DST tests using CalendarService and new forecast configuration.

```python
assert legacy.id == old_id
assert new.config_digest != legacy.config_digest
assert all(point.timestamp.date() != date(2026, 12, 25) for point in new.paths[0].points)
```

- [x] Run `pytest tests/test_scenario_calendar.py -q` for RED.
- [x] Implement version-dispatched date/gap/age/config/limit validation and exact registry reconstruction. Use pinned CalendarService; unsupported calendars fail closed. Preserve the baseline drift/residual algorithm and old eligibility; Task 2 supplies stricter lab qualification.
- [x] Generate coherent synthetic equity daily sessions for the new path as needed; retain explicit demo labelling and bounded 650-row history. Do not modify trusted-data collectors or data roots.
- [x] Run new tests and named legacy registry/reproducibility regressions once; record exact results.

## Task 4: Deliver the chart-first saved analysis loop

**Files:** `frontend/src/screens/InstrumentWorkspace.tsx`, `frontend/src/screens/instrument/MarketCanvas.tsx`, `ScenarioLab.tsx` (new), `ForecastEvidence.tsx`, `DecisionRail.tsx`, `PacketMonitoring.tsx`, `PacketOutcomeReview.tsx`; `frontend/src/components/charts/InstrumentChart.tsx`; `frontend/src/lib/api.ts`, generated API, scoped message copy. New tests `ScenarioLab.test.tsx` and selected Workspace/chart tests.

**Interfaces:** `api.instrumentWorkspace(venue,symbol,range,compare=[],horizon?,forecastId?)`; use generated Python contracts. `ScenarioLab` renders packet evidence and selected horizon with callbacks; no data generation in chart components. `InstrumentChart` adds a filled P10/P90 band and observed/forecast separator behind the existing props.

- [x] Write tests showing chart before detail rails, 7/30 exact packet binding across refresh, persisted history rather than current history, no missing-horizon fallback, literal metric/sample windows and blocked Paper.

```tsx
expect(chartProps.primary).toEqual(saved.scenario_lab.history)
expect(chartProps.forecast).toEqual(saved.evidence.forecast_paths.find(p => p.sessions === 7))
expect(screen.getByRole('button', { name: '7 sessions' })).toHaveAttribute('aria-pressed', 'true')
```

- [x] Retain RED; implement URL selection/pinned artifact, chart-first composition and disclosures. Polling must not replace displayed exact evidence. Explicit New analysis changes the pinned analysis; Back/Forward and saved replay restore it.
- [x] Add full-width chart, volume/SMA controls, textual split/line patterns/band, accessible data table and bilingual confidence/evidence copy. Reveal risk/action in place and preserve visible blockers and action results.
- [x] Generate OpenAPI once after Python contract completion; run selected Vitest, `tsc -b`, scoped Oxlint, and package build/freshness.

## Task 5: Bounded acceptance and integration

**Files:** `tests/test_scenario_lab_acceptance.py` (new lightweight API/restart fixture), optional isolated browser acceptance file, iteration/ADR/DESIGN/PRODUCT/roadmap/ACTIVE records and generated SPA.

- [x] Prove NVDA entry → 7/30 → saved Watch → exact reload, AAPL demo labelling, and missing/stale/non-improving evidence rejection. Assert no order from Watch and unchanged explicit confirmation flow.
- [x] Inspect desktop and 390px in one batched browser pass, with keyboard, reduced motion, locale and visible observed/forecast split. Record elapsed entry-to-save time and screenshots.
- [x] Run scoped Python/Vitest checks, Ruff/Oxlint, TypeScript project build, OpenAPI and bundle freshness; stop any over-budget command and isolate the fixture. No broad historical gate.
- [x] Run one fresh Standards/Spec review and the Impeccable detector once. Apply at most one bounded correction batch and one confirmation. Record residual findings honestly.
- [x] Update durable visual decisions only from implementation evidence; record packet/calendar compatibility in an ADR. Commit/push the coherent slice; open one PR referencing #136 with exact validation and limits. Do not merge this architecture iteration under the routine non-architectural merge allowance.
- [ ] Update ACTIVE and iteration with PR/CI state and next action. Mark the tool Goal complete only when the authorized deliverable is actually achieved.

## Plan self-review

Tasks 1/4 cover entry and chart hierarchy; 2/3 cover identity, dates, confidence and compatibility; 4/5 cover UI/restart/locale/accessibility. Backend and calendar ownership are disjoint; generated-client integration is controller-owned. No task authorizes cloud state, a broader suite, new dependencies or an extra review loop. Interface refinements discovered by tests must be recorded in this plan and the ledger before dependent work proceeds.
