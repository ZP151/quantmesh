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

## Decision 1 — The workstation is server-rendered Jinja2 over the
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

## Consequences

- The workstation adds one core dependency (jinja2, BSD-3) and no
  node toolchain; a browser is only needed for the dev-only E2E
  acceptance (Phase F, decision 5).
- A non-loopback `workstation_host` is a construction error: the
  workstation cannot be accidentally exposed, and environment
  configuration cannot change that.
- The HTML layer renders the same account state the M1 JSON endpoints
  serve, computed by the same code path; understated or missing data
  (positions without marks) is named in the UI, never silent.
- Later phases append screens to the page registry and extend the
  injected context; the registry tests keep the route/template/
  provider triple pinned.
