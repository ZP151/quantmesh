# Iteration 0011 — M9: Local frontend workstation

- Status: active
- Started: 2026-08-08
- Completed:
- Owner: Claude
- GitHub issue: issues #51-#56 (Phases A-F, dependency-ordered: #52/#53/#54/#55 block on #51, #56 blocks on #52-#55)
- Pull request: (opened after acceptance criteria complete; base = `feat/m8-local-ai-research-layer`, stacked — merges after the M8 PR #50, which stacks behind the M7 PR #44, which stacks behind the M6 PR #38, which awaits the M5 PR, which awaits the M5 operator drill)
- Roadmap milestone: M9 (`LATER` → `ACTIVE`)

## Outcome

Operate research, paper portfolios and risk from a local web interface:
a server-rendered workstation served by the existing FastAPI/uvicorn
stack over loopback, with screens for market overview and watchlists,
experiment comparison and strategy promotion, positions/orders/fills
and P&L, prediction probability and calibration, risk alerts, an audit
explorer and a global kill switch — plus Playwright end-to-end coverage
and keyboard/accessibility tests on the critical controls. The core
paper workflow becomes usable without direct database or CLI access,
and every screen reads through the existing registries and ledgers
(fixture-first: the app binds injected read surfaces, never the network).

## Scope and boundaries

In scope:

- A workstation server shell: `create_workstation_app` (a superset of
  the M1 read-only `create_app`) serving Jinja2-rendered pages with a
  shared layout and navigation, static assets, and a settings-driven
  loopback host/port. Server-rendered with a small vanilla-JS
  enhancement layer — no node toolchain, no build step, no CDN; every
  asset ships from the same uvicorn process.
- Screens per the roadmap deliverables: market overview + watchlists +
  cross-venue instruments; experiment comparison + strategy promotion;
  positions, orders, fills and P&L; prediction probability and
  calibration; risk alerts, audit explorer and global kill switch.
- Watchlist persistence: the one UI-owned write surface, JSONL on the
  ADR-0006 discipline under the new `watchlists_dir` setting.
- A Playwright end-to-end suite (dev-only extra) driving a real uvicorn
  process on 127.0.0.1 over a fixture universe, plus keyboard-only and
  accessibility-snapshot tests on the critical controls.
- Keyboard/accessibility posture: native semantic HTML (landmarks,
  real links/buttons/forms), skip link, visible focus, table headers,
  ARIA labels where needed; Playwright accessibility snapshots.

Out of scope (recorded, not deferred silently):

- **New execution authority**: the workstation never creates or
  cancels orders; the M2 paper kernel remains the only execution
  surface, and the M9 screens read it through the existing read-only
  `PaperAccount`/`OrderJournal` surfaces. The global kill switch in M9
  flips the paper kernel's existing `kill_switch` flag (a safe,
  paper-level control); live per-venue disable *enforcement* remains
  M10 — the UI is wired now, the execution-plane enforcement lands
  with M10's contract.
- **Live market data**: overview prices come from registered fixture
  providers and injected marks, exactly like every other milestone.
  Live providers remain explicit-construction-only and are never part
  of an M9 drill.
- **Authentication/network exposure**: the workstation binds loopback
  only (`127.0.0.1`, refuse a non-loopback bind at construction — the
  ADR-0010 loopback discipline). No credentials, no remote API.
- **Write paths beyond watchlists and the kill switch**: experiments,
  promotions, orders, decisions and alerts remain CLI/registry-owned;
  the screens are read-only views over them (promotion approval is a
  screen that *shows* the promotion ledger; the approval action itself
  stays CLI/registry-owned unless a phase plan says otherwise — the
  ledger's report-only kill-switch flag is already in its identity).
- **M10 scope**: metrics, structured logs, incident runbooks, secret
  store integration, live enablement.

## Acceptance criteria

1. [ ] The workstation serves a core paper workflow end-to-end without
      direct database or CLI access: over a fixture universe the
      operator can reach market overview, a watchlist, an instrument
      view, positions, orders (with events/fills) and P&L purely
      through the web UI. — Phases A/B/D (issues #51/#52/#54).
2. [ ] Experiment comparison and strategy promotion are visible in the
      UI: the M3 registry's experiments render side by side with
      metrics, and the M7 promotion ledger renders with its evidence
      links resolved. — Phase C (issue #53).
3. [ ] Prediction probability and calibration views render the M6
      forecast reports: implied probabilities with their liquidity
      confidence, and reliability-bin calibration with the Brier
      score. — Phase D (issue #54).
4. [ ] Risk alerts and the audit explorer render the M7 alert ledger,
      the M5 risk posture, the M2 order journal, the M6 mapping ledger
      and the M8 decision log in one chronological view; the global
      kill switch control flips the paper kernel's flag and the UI
      reflects the state. — Phase E (issue #55).
5. [ ] Critical controls pass keyboard, accessibility and end-to-end
      tests: the Playwright suite covers the core paper workflow
      (criterion 1) and the critical controls (kill switch, navigation,
      promotion view) operate with keyboard only and satisfy
      accessibility snapshots. — Phase F (issue #56).

## Plan and role assignments

Solo fast lane (Claude, one branch per milestone): one tested and
reviewed commit per issue, pushed every checkpoint, one final milestone
PR. Every phase is fixture-driven; there is no human gate in M9 (the
Playwright browser download at install time is a dev-environment step,
documented in Risks and gates below).

## Reuse survey (2026-08-08)

- **jinja2 (BSD-3, new core dependency)**: the canonical FastAPI
  template engine; server-side rendering with autoescape by default —
  every registry value rendered as data, never markup. Pure python.
- **Playwright for Python (Apache-2.0, dev-only extra `e2e`)**: the
  roadmap names Playwright for E2E coverage; the `sync` API starts a
  real uvicorn process over a fixture universe (no network, pinned
  loopback port), drives the keyboard-only and accessibility-snapshot
  tests, and needs no test-runner plugin.
- **FastAPI/uvicorn/httpx/pydantic (already core)**: the M1
  `create_app` pattern (read-only app bound to injected state) is the
  construction precedent for `create_workstation_app`.
- **No frontend framework, no node toolchain, no CDN**: server-rendered
  pages with a small vanilla-JS enhancement layer (live P&L/mark
  refresh, kill-switch confirmation) keeps the workstation fully
  local-first and offline-capable.

## Phase A — workstation server shell (issue #51)

- `create_workstation_app(*, account, marks, ...)` supersets the M1
  read-only app: same injected-state construction, loopback-only bind
  refused at construction (non-loopback `workstation_host` is a
  `WorkstationConfigError` — the ADR-0010 loopback discipline),
  `workstation_host`/`workstation_port` settings.
- Jinja2 environment with autoescape, a base layout (landmarks:
  skip-link, header, nav, main; visible focus styles; responsive
  table/panel CSS in a local stylesheet — no external fonts/CDN) and a
  strict route→template→data-provider registry pinned by test (a page
  registry test asserts every route renders and every template exists).
- Static assets served from a package directory; a `quantmesh-workstation`
  console script boots uvicorn over `create_workstation_app`.
- Acceptance drills: TestClient renders every shell page (200, HTML
  shape), the page registry is complete, the health/account endpoints
  from M1 still pass, and a fixture boot (scripted uvicorn-less smoke
  drill) renders the home page.

## Phase B — market overview, watchlists, cross-venue instruments (issue #52)

- Overview screen: aggregate cards across registered fixture providers
  (per-venue instruments with last marks) plus the paper account
  summary; all data through injected read surfaces — no provider is
  ever constructed inside a route.
- Watchlists: `Watchlist`/`WatchlistStore` — JSONL on the ADR-0006
  discipline under `settings.watchlists_dir` (atomic temp+replace
  appends, fail-closed reads with line attribution, duplicate symbol
  refusal, root-not-dir refusal); add/remove/list via POST form
  endpoints; cross-venue instrument screen listing every registered
  venue's instruments with mark prices.
- Acceptance drills: overview renders fixture provider data; watchlist
  add/remove round-trips through the store and renders; duplicate
  watchlist symbols refused with the page showing the typed error;
  instruments page renders the cross-venue table.

## Phase C — experiment comparison and strategy promotion screens (issue #53)

- Experiment comparison: the M3 `ExperimentRegistry` records rendered
  side by side (dataset, revision, commit, parameters, metrics) with
  byte-stable metric formatting; an experiment detail row links to the
  lake pin.
- Promotion screen: the M7 `PromotionLedger` records rendered with
  their full evidence bundle (benchmark ids, ablation ids, OOS report
  id, `windows_oos`) resolved through the M7 `ReportRegistry` — a
  missing evidence link renders as a typed "missing evidence" state,
  never a crash. Report-only: the promotion *approval* action remains
  registry/CLI-owned (the ledger's kill-switch flag is already in the
  record identity; enforcement is M10).
- Acceptance drills: a fixture registry + ledger renders the
  comparison and the promotion evidence; a ledger row with a missing
  report id renders the missing-evidence state; empty registries
  render empty states.

## Phase D — positions, orders, fills, P&L and prediction views (issue #54)

- Portfolio screens over the M1 API surface: positions with injected
  marks (unrealized P&L computed exactly like the M1 endpoint),
  orders with their event streams, fills, and the account summary.
- Prediction views: the M6 `ForecastReport` artifacts (report.json +
  windows.csv + calibration.csv) rendered as implied-probability cards
  (quote, mid, liquidity confidence) and a reliability-bin
  calibration view with the Brier score; unresolved windows render as
  "pending", never fabricated values.
- Acceptance drills: a fixture account + marks renders positions/P&L
  deterministically; a fixture forecast report renders its windows and
  calibration; a missing forecast artifact renders a typed empty
  state.

## Phase E — risk alerts, audit explorer, global kill switch (issue #55)

- Risk screen: the M7 `AlertLedger` renders with source attribution
  (feature:/index:/nan sources) and the M5 risk posture surface.
- Audit explorer: one chronological view over the M2 `OrderJournal`
  (with events), the M6 `MappingLedger`, and the M8 `DecisionLog`
  (with citations and model metadata) — every entry links to its
  source record; the M8 decision records render their `kind:id`
  citations as resolvable links.
- Global kill switch: a form control that flips the injected paper
  account's `kill_switch` flag (confirmation step; state reflected in
  the header of every page); the endpoint is paper-level only and the
  UI copy states enforcement is M10.
- Keyboard/accessibility pass on the critical controls (nav, kill
  switch, audit links): focus order, skip link, snapshot tests land in
  Phase F but the markup is built semantic from the start.
- Acceptance drills: alert ledger renders with sources; audit explorer
  renders the three ledgers in order with working citation links; the
  kill switch toggles the injected account flag and the UI reflects
  it; a hostile POST (non-form body) is refused.

## Phase F — Playwright E2E and acceptance (issue #56)

- `playwright` added to a dev-only `e2e` extra; `playwright install
  chromium` documented as the one-time install step (browser binaries
  are free; no paid infrastructure).
- The E2E suite boots uvicorn on a pinned loopback port over a fixture
  universe (deterministic; the fixture universe is built exactly like
  the unit-drill universes) and walks the core paper workflow: home →
  overview → watchlist add → instruments → positions → orders → P&L
  (exit criterion 1), then the critical controls: navigation and the
  kill switch with keyboard only (Tab/Enter/Space), plus
  `page.accessibility` snapshots on every screen (exit criterion 2).
- Acceptance drills: the full E2E walk passes; keyboard-only nav
  passes; accessibility snapshots pass; the suite is skipped cleanly
  (not failed) when the browser is not installed — the fallback gate
  recorded in Risks and gates below.
- Iteration acceptance criteria 1-5 checked off; ADR-0011 recorded;
  final M9 PR opened (base = the M8 branch; "Closes #51-#56" fires on
  merge).

## Delivery protocol

- One tested and reviewed commit per issue, pushed every checkpoint.
- Full suite must stay green: every phase runs `pytest -q` (the suite
  is ~1535 tests before M9 and grows from there), `ruff check src
  tests` and `git diff --check` clean, submodules clean.
- Issues close only when the final M9 PR merges.
- ADR-0011 records the durable decisions as they land (loopback-only
  workstation, server-rendered Jinja2/no-build-step, watchlists on the
  ADR-0006 discipline, read-only data plane with the two named
  exceptions, Playwright dev-only acceptance).

## Durable decisions to record when reached

- Decision 1 (Phase A): the workstation is server-rendered Jinja2 over
  the existing FastAPI stack with no node toolchain, no build step and
  no CDN; every asset ships from the same uvicorn process; jinja2 is
  the only new core dependency.
- Decision 2 (Phase A): `create_workstation_app` binds injected read
  surfaces and refuses a non-loopback bind at construction (the
  ADR-0010 loopback discipline).
- Decision 3 (Phase B): watchlists are the one UI-owned write surface,
  JSONL on the ADR-0006 discipline under `watchlists_dir`.
- Decision 4 (Phase D/E): the workstation is a read-only data plane —
  every screen reads through existing registries and ledgers; the only
  control that mutates state is the paper-level kill switch (M10 owns
  execution-plane enforcement).
- Decision 5 (Phase F): Playwright is a dev-only extra whose suite
  boots a real uvicorn process over a fixture universe; keyboard-only
  and accessibility-snapshot tests are first-class acceptance
  evidence; a missing browser is a recorded fallback, never a
  fabricated pass.

## Work log

**Issue #51 (Phase A, workstation server shell) committed 2026-08-08**
— `quantmesh.api.workstation`: `create_workstation_app` supersets the
M1 `create_app` on the same app object (JSON observability and HTML
screens cannot drift apart — pinned by a comparison test); `PAGES`
registry (route → template → data provider, `PageContext` = injected
account + marks, rendered as data); jinja2 (3.1.6) the only new core
dependency; base layout with the accessibility posture from the first
screen (skip link, header/nav/main landmarks, tables with `scope`,
`:focus-visible` in the local stylesheet — no CDN, no external fonts);
loopback-only bind refused at construction with a typed
`WorkstationConfigError` (localhost/::1/127.0.0.0/8 accepted;
0.0.0.0/192.168.x/example.com/:: refused — the ADR-0010 loopback
discipline); `workstation_host`/`workstation_port` settings;
`quantmesh-workstation` console script (uvicorn deferred-imported,
same fail-closed check, empty-paper bootstrap); static CSS served
locally. 26 tests (construction matrix, page-registry pins incl.
autoescape-on-html, landmarks/skip-link, account/marks/missing-marks
rendering, markup escaping end-to-end, M1 endpoints byte-identical to
`create_app`, console-script loopback/refusal drills). ADR-0011
decisions 1-2 recorded.

## Verification evidence

(empty)

## Risks and gates

- **Playwright browser download at install time** (dev-environment
  step, not an operator gate): `pip install -e ".[dev,e2e]"` plus
  `playwright install chromium` downloads browser binaries once
  (free). If the download is blocked in an environment, the E2E
  acceptance records the gate in this iteration and the suite skips
  cleanly — never a fabricated pass; unit-level drills still run.
- **No human gate in M9**: every surface is fixture-driven local
  computation; the operator drill would only be running the real
  workstation against live fixture providers, recorded here as an
  optional step, never a blocker.
- **Template/route drift**: the page-registry test pins route →
  template → data provider, so a screen cannot render from the wrong
  source silently.
- **Markup injection**: Jinja2 autoescape is on and registry values
  are rendered as data; the hostile-POST drill covers the one control
  endpoint.
- **Kill switch scope creep**: the switch flips the paper
  account's existing flag only; any live-enforcement wiring is M10 and
  is refused here by the loopback/read-only construction.
