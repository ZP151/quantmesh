# ADR-0011 — M9: Local frontend workstation

Status: accepted
Date: 2026-08-08
Milestone: M9 — Local frontend workstation (iteration 0011)
Issues: #51-#56

## Context

M9 adds the local frontend workstation: operate research, paper
portfolios and risk from a local web interface. The roadmap contract
is market overview/watchlists/cross-venue instruments, experiment
comparison and strategy promotion screens, positions/orders/fills and
P&L, prediction probability and calibration views, risk alerts, an
audit explorer and a global kill switch, with Playwright end-to-end
coverage and keyboard/accessibility tests on the critical controls.
The long-running goal binds this milestone: local-first (loopback
only, no paid infrastructure), and no new execution authority — the M2
paper kernel remains the only execution surface.

The M1 baseline is a read-only FastAPI app (`create_app`) binding the
paper-account observability endpoints to one injected `PaperAccount`;
the M9 workstation supersets it.

### Decision 1 — The workstation is server-rendered Jinja2 over the
existing FastAPI stack: no node toolchain, no build step, no CDN
(Phase A, issue #51)

`quantmesh.api.workstation`:

- `create_workstation_app` calls the M1 `create_app` and adds the
  HTML routes to the same app, so the JSON observability surface and
  the HTML screens cannot drift apart (pinned by the
  `TestM1SurfaceStillServed` comparison test).
- Pages are a strict registry (`PAGES`): route -> template -> data
  provider, pinned by test (routes unique and registered, every
  template loadable, every page renders through its provider,
  autoescape on). Providers receive an injected `PageContext`
  (account + marks; extended with registries in later phases) and
  return data — rendering is data-in, markup-out, and the data plane
  is read-only by construction.
- jinja2 (BSD-3, `>=3.1,<4`) is the only new core dependency.
  Rendering is server-side with autoescape (`select_autoescape` on
  the html templates), static assets (one local stylesheet) ship from
  the same uvicorn process, and there is no external font, script or
  CDN — the workstation renders correctly air-gapped.
- The keyboard/accessibility posture is built into the markup from
  the first screen: skip link, landmarks (header/nav/main/footer),
  real links and tables with `scope` headers, and `:focus-visible`
  outlines in the local stylesheet.

### Decision 2 — The workstation binds loopback only; a non-loopback
host is refused at construction, never env-escalable (Phase A, issue
#51)

- `settings.workstation_host` defaults to `127.0.0.1` and
  `workstation_port` to 8765; `create_workstation_app` (and the
  `quantmesh-workstation` console script) refuse any host that is not
  loopback — `localhost`, `::1`, or the `127.0.0.0/8` range — with a
  typed `WorkstationConfigError` naming the host. This is the
  ADR-0010 loopback discipline applied to the workstation bind: the
  surface is local, and no environment setting can escalate it.
- The console script boots uvicorn over the app with the settings
  bind (fail-closed on the same check) and binds a fresh empty paper
  account as the safe local bootstrap; operators wire their real
  account/journal surfaces programmatically.

### Decision 3 — The watchlist is the one UI-owned write surface,
persisted as JSONL on the ADR-0006 discipline (Phase B, issue #52)

- The workstation data plane is otherwise read-only; the only state
  the UI owns is a single default watchlist of instrument symbols
  (`quantmesh.api.watchlist.WatchlistStore`), stored as
  `watchlist.jsonl` under `settings.watchlists_dir` (default
  `~/.quantmesh/watchlists`).
- The store follows the ADR-0006 discipline exactly: atomic
  temp+replace writes (`mkstemp` in the store root, `os.replace`,
  cleanup-unlink in `finally`), fail-closed reads with line
  attribution (`watchlist <path> line N is invalid`,
  `line N repeats symbol ...`), duplicate-symbol refusal on add and on
  read, root-not-dir refusal, and a missing root or file reading as an
  empty list — never an error. Symbols are shape-validated
  (strip, refuse empty/whitespace, refuse internal whitespace) and
  `added_at` is stamped aware-UTC.
- Writes flow only through the form endpoints (`POST /watchlist/add`,
  `POST /watchlist/remove`); both fail closed — a duplicate, absent,
  or malformed symbol, or an unbound store, renders a typed error page
  (`role="alert"`) instead of mutating or crashing. Success is a 303
  redirect back to the watchlist page (PRG), so a refresh never
  re-submits.
- The overview screen renders a watchlist snapshot (mark resolved
  through the first sorted venue, or "no mark"), and the watchlist
  page is the editing surface; hostile symbols are escaped by the
  autoescape posture in both.

### Decision 4 — The research screens (experiments, promotions) are
read-only views over injected registries; unbound registries and
unresolvable evidence render typed states, never crashes (Phase C,
issue #53)

- `PageContext` gains `experiments` (`ExperimentRegistry`),
  `promotions` (`PromotionLedger`) and `reports` (`ReportRegistry`) as
  optional injections — read-only views, exactly like `marks` and
  `markets`. None is default-bound: the console bootstrap serves a
  paper account and the watchlist; the operator wires registries in
  programmatically. An unbound registry renders a typed empty state
  ("No experiment registry is bound."), never a 500.
- The experiments page renders the M3 registry's records side by side
  (dataset, revision, commit, parameters, metrics) newest-first with
  byte-stable value formatting (`repr` floats, lowercased bools, en
  dash for None) and links each row to its detail page, which shows
  the record plus its lake pin resolved through the registry's own
  gate. A pin that no longer holds (missing lake, stale revision,
  moved manifest) renders a typed "Lake pin unavailable" state with
  the failure named — the record still renders.
- The promotions page renders the M7 ledger with the full evidence
  bundle (benchmark ids, ablation ids, OOS report id) resolved through
  the report registry. A missing report, or an unbound report
  registry, renders a typed `missing-evidence` state naming the id —
  never a crash. The kill-switch flag renders report-only ("gate
  (report-only)"), matching the M7 identity: display today,
  enforcement in M10.
- No write surface is added: experiment, promotion, decision and
  alert writes remain CLI/registry-owned.

### Decision 5 — Portfolio and prediction screens render the M1 and M6
surfaces by the same code path, under `/portfolio/*` (Phase D, issue
#54)

- The positions, orders and P&L screens render the M1 surface. A
  position's unrealized P&L uses exactly the `/positions` formula
  `(mark − average_cost) × quantity`, and a position without a mark
  renders a typed "no mark" state — never a number. Orders serialize
  through the same `_order_summary` the JSON endpoint uses, so the
  HTML screen and the API surface cannot drift apart (decision 1's
  consequence, applied by construction); the event stream renders
  fill events, and a rejected order renders its reason.
- The HTML screens live at `/portfolio/positions`, `/portfolio/orders`
  and `/portfolio/pnl`: the M1 JSON endpoints keep their own routes on
  the same app object, and the no-shadowing test pins both surfaces
  served (the HTML layer never shadows the observability API).
- The forecast screen renders the M6 `ForecastReportRegistry` records:
  setup and aggregate metrics; per-market evaluation cards (identity,
  resolution state, and the windows that evaluate the venue's
  mid-derived implied probabilities); a reliability-bin calibration
  view with the per-bin Brier; and the artifact state named from the
  registry root (`report.json`/`windows.csv`/`calibration.csv`
  existence). A forecast record holds window results, not the
  observation grid — a "current implied probability" would be
  fabricated, so none is rendered: the card is the evaluation, an
  unresolved window renders "pending", an empty calibration bin
  renders an en dash, and a missing artifact renders a typed
  "Forecast artifacts missing" state naming the absent files. An
  unbound registry renders a typed empty state (decision 4 applied to
  the forecast surface).

### Decision 6 — Risk screen, audit explorer and the paper kill-switch
control (Phase E, issue #55)

- The risk screen renders two distinct limit surfaces and never merges
  them: the accounting `RiskLimits` the paper kernel enforces (read
  from the injected account; an unset limit renders an en dash, never
  a fabricated number) and the M5 Hyperliquid pre-submission posture
  as an optional injected surface with a typed "No M5 posture is
  bound" state. The two are different types (`execution.accounting`
  vs `hyperliquid.risk`) with different semantics, so they are
  separate sections. The M7 alert ledger renders beneath them with
  source attribution (`feature:`/`index:`/`nan` sources), newest
  first, the deterministic id as tie-break.
- The audit explorer is one read-only chronological view over the M2
  `OrderJournal` (with event streams and fills), the M6
  `MappingLedger` (verdict, commit, evidence) and the M8 `DecisionLog`
  (model metadata, schema, digests, refusals, citations), merged
  newest-first with the id as tie-break per ledger. Every entry
  anchors to its source record, and the M8 `kind:id` citations render
  as resolvable links — experiments and documents get their detail
  routes, audit citations jump to the order's anchor — with ids
  URL-quoted against injection.
- The paper-level kill switch is the workstation's second write
  surface: a confirm-gated POST flips the injected paper account's
  `kill_switch` flag through `dataclasses.replace`, so the M1 JSON
  surface and the page context never disagree; the header of every
  page reflects the state. A hostile POST (missing or wrong confirm,
  non-form body) is refused with a typed error page and no state
  change. The control lives at `/kill-switch/control` because M1 owns
  GET `/kill-switch` on the same app object (route-shadowing
  discipline: first-registered wins; different methods coexist).
  Enforcement across the wider execution plane is M10 — the UI states
  this.

### Decision 7 — End-to-end coverage is a dev-only Playwright extra
that boots the real workstation on a pinned loopback port and skips
cleanly when the browser is absent (Phase F, issue #56)

- `playwright` (Apache-2.0, `>=1.44,<2`) is a dev-only extra
  (`.[dev,e2e]`), never a runtime dependency. The browser binaries are
  installed separately (`playwright install chromium`), and the suite
  skips cleanly — never fails — when the package is missing
  (`pytest.importorskip`) or the chromium binary is absent (the launch
  failure becomes a skip with the install hint): a pipeline without
  the browser stays green, and the skip is a recorded fallback, never
  a fabricated pass.
- The E2E suite boots the real workstation (uvicorn over the same
  `create_workstation_app` a fixture universe is built for) on a
  pinned loopback port (127.0.0.1:8642), with a port-in-use pre-check
  that skips rather than clobbering an existing server. It exercises
  the exit criteria as browser-driven evidence: the core paper
  workflow walk (overview → watchlist add → instruments → positions →
  orders → P&L) through the UI alone; keyboard-only navigation and
  kill-switch engage/disarm round trip (Tab/Arrow/Space/Enter, real
  focus order — no injected focus helpers, no mouse); and aria
  snapshots of the registry's list screens asserting the
  banner/nav/main landmarks and the page heading. The mark is
  asserted through the mark-derived unrealized P&L — the only place a
  mark reaches the surface.
- The accessibility assertions use the Playwright aria snapshot (the
  modern replacement for the removed `page.accessibility` API); tests
  pin the page h1 by name, disambiguating headings that share a name
  with a section (`P&L`) rather than relaxing exactness.

## Consequences

- The workstation adds one core dependency (jinja2, BSD-3) and no
  node toolchain; a browser is only needed for the dev-only E2E
  acceptance (Phase F, decision 7).
- A non-loopback `workstation_host` is a construction error: the
  workstation cannot be accidentally exposed, and environment
  configuration cannot change that.
- The HTML layer renders the same account state the M1 JSON endpoints
  serve, computed by the same code path (the portfolio screens reuse
  the endpoint functions by construction); understated or missing
  data (positions without marks, unmarked equity) is named in the UI,
  never silent. The `/portfolio/*` namespace keeps the JSON routes
  served on the same app object.
- The prediction view renders only recorded evaluation data: an
  unresolved window says "pending" and a market whose observation
  grid the record does not hold renders no probability at all — the
  UI never invents a number the report cannot substantiate.
- The UI owns exactly one persisted surface (the watchlist); its
  JSONL file is on the same discipline as the experiment and audit
  journals, so a corrupted or hostile watchlist file fails closed
  with attribution instead of rendering attacker state into the UI.
- The research screens stay honest about their bindings: an unbound
  registry or a missing evidence link is named in the UI as a typed
  state, never rendered as data it cannot see and never raised as an
  error the page cannot explain.
- Later phases append screens to the page registry and extend the
  injected context; the registry tests keep the route/template/
  provider triple pinned.
- The workstation's write surfaces are exactly two: the watchlist
  (persisted JSONL) and the paper kill switch (the injected account's
  in-memory flag). Nothing else in the UI mutates state; the audit
  explorer and the risk screen are read-only views.
- The paper kill switch is display-and-enforce for the paper surface
  only. The paper kernel's own risk gate refuses order submissions
  while the flag is engaged; wiring the flag into the wider execution
  plane is M10, and the control page names that boundary.
