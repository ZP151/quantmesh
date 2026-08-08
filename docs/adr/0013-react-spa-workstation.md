# ADR-0013 — M11: React/TypeScript workstation over the FastAPI kernel

Status: accepted (approved through implementation evidence in iteration
0014 Phase A)
Date: 2026-08-09
Milestone: M11 — Interactive workstation and `v0.1.0-rc2` (iteration 0014)
Supersedes: ADR-0011 Decision 1 (server-rendered Jinja2 rendering stack)
keeps ADR-0011 Decisions 2 (loopback-only bind) and 3 (watchlist JSONL
write surface) and every later execution/risk/enablement ADR in force.

## Context

RC1's operator review rejected the server-rendered UI as a product:
every route looked like minimally styled HTML, the primary navigation
exposed raw API links, pages started empty, and no demo/provider/import
path made the business workflow testable from the browser. The backend
contracts (JSON observability, research registries, paper kernel, risk
and enablement gates) are present and green; the failure is runtime
assembly and product experience. `v0.1.0` must not be promoted from
RC1 (iteration 0014).

PRODUCT.md fixes the direction: a React and TypeScript application
that reuses selected shadcn/ui components and compiles into the Python
package for a one-command local production launch, with the exact
frontend boundary, build pipeline and generated API-client contract
settled by an ADR before implementation. Iteration 0014 adds the
constraints: FastAPI and the Python domain/research/execution layers
are kept; the operator still starts one process and needs no Node.js
at runtime; legacy URLs become redirects or compatibility routes while
the primary information architecture is replaced; every displayed
value identifies source, timestamp and freshness; AI output cannot
bypass deterministic risk approval.

The existing `PAGES` registry (13 screens in
`quantmesh.api.workstation`) and its Playwright/keyboard tests remain
green at the RC1 tag and are the migration baseline.

## Decision 1 — The operator surface is an SPA served by FastAPI as
one process; the JSON API is the contract

`quantmesh.api.workstation.create_workstation_app` keeps mounting the
RC1 JSON data plane unchanged (`/health`, `/account`, `/positions`,
`/orders`, `/pnl`, `/kill-switch`, the research/audit JSON surfaces,
watchlist and enablement routes). The SPA is served at `/` and any
route not owned by the JSON API or the legacy-compat set:

- The production bundle lives under the Python package
  (`src/quantmesh/api/static/app/`) and is served by the same uvicorn
  process (StaticFiles mount + a catch-all that returns `index.html`
  for SPA deep links).
- The SPA is the only primary navigation. Raw JSON routes remain
  reachable for developer diagnostics, not linked from the UI.
- The SPA never executes anything itself: order submission, reset,
  import and connector actions are backend services behind the
  existing risk and enablement gates. New write endpoints are added
  to the workstation app only (Phase B/C of iteration 0014), never to
  the read-only `create_app` observability surface.

## Decision 2 — Build and package path: committed production bundle,
no Node at runtime

- The application lives in `frontend/` (React + TypeScript + Vite).
- Development: `npm run dev` serves the app and proxies `/api` to
  the FastAPI process on `127.0.0.1:8765`.
- Production: `npm run build` emits the bundle to `frontend/dist`;
  a committed copy is packaged at `src/quantmesh/api/static/app/`
  (package-data), so `pip install .` and the release gate never need
  Node. A `frontend-bundle` check (CI + release gate) rebuilds with
  `npm ci` and fails when the committed bundle differs from a fresh
  build — the packaged UI is always the source UI.
- The operator surface is still `quantmesh-workstation` → one process
  → loopback. Node is a developer/CI tool only.

## Decision 3 — API client is generated from the OpenAPI schema

- FastAPI's `/openapi.json` is the single contract source.
- `openapi-typescript` codegen produces `frontend/src/api/client.ts`
  from it; the generated file is committed and a CI check fails when
  it is stale (regenerate and commit with backend changes).
- TanStack Query owns server state over the generated typed client;
  components never hand-roll fetch shapes.

## Decision 4 — Routing: deep links mirror the legacy routes

- `react-router-dom` with routes that preserve RC1's deep links
  (`/experiments`, `/forecasts`, `/promotions`, `/orders`,
  `/positions`, `/pnl`, `/risk`, `/audit`, `/enablement`,
  `/kill-switch`, `/instruments`, `/watchlist`) under the target
  information architecture (Overview, Markets, Research, Paper
  trading, Risk & operations).
- Legacy HTML routes respond with a 302 redirect to their SPA
  equivalent (or return 410 with a link for removed routes), so
  bookmarks and the RC1 E2E baseline fail loudly toward the new UI
  instead of serving stale markup.

## Decision 5 — Dependency budget (permissive licenses only)

Adopted after the Phase A spike, smallest set that satisfies it:

- `react`, `react-dom`, `typescript`, `vite`, `@vitejs/plugin-react`
  (MIT)
- `tailwindcss` (MIT) for tokens/layout, themed to the dark-technical
  direction (near-black surfaces, one green accent)
- shadcn/ui components (MIT), copied selectively through its CLI and
  owned/themed in `frontend/src/components/ui/` — never the full
  upstream repository, never the default visual treatment
- `@tanstack/react-query` (MIT) server state; `react-router-dom`
  (MIT) routing
- `@tanstack/react-table` (MIT) for dense grids where the spike shows
  it pays; TradingView Lightweight Charts (Apache-2.0) for market
  series; Apache ECharts (Apache-2.0) for portfolio/calibration/
  scenario views — adopted only if the spike passes with the smallest
  licensed subset

Anything else enters through a license/maintenance check recorded in
`docs/REUSE_MATRIX.md` and the frontend license inventory in
`docs/licenses.md`. No decorative animation libraries; state motion is
CSS-only and honors `prefers-reduced-motion`.

## Decision 6 — Data plane, provenance and safety states

- Every data surface renders source, synthetic/real classification,
  timestamp and freshness (Phase B provenance contract), including
  empty states that say *why* nothing is shown and what to do next.
- Live enablement stays visually and technically separate; paper
  status and kill-switch state are persistent in the shell.
- The SPA ships the RC1 accessibility posture forward: skip link,
  landmarks, keyboard-operable controls with visible focus, tables
  with scope headers, non-color status cues, WCAG 2.2 AA contrast and
  reduced-motion support.

## Decision 7 — Rollback strategy

- The RC1 Jinja2 templates and the `PAGES` registry stay in the
  repository and remain tested; they are mounted only when
  `QUANTMESH_LEGACY_UI=1` is set at startup (fail-closed: unset or
  false serves the SPA).
- Reverting the RC2 PR restores RC1 behavior exactly (the tag
  `v0.1.0-rc1` is unchanged); the legacy switch is a same-release
  fallback for operator environments that cannot run the bundle.

## Consequences

- New: `frontend/` application, `tools/build_frontend.py` (or
  equivalent) packaging step, generated API client, frontend unit/
  component tests, migrated Playwright E2E.
- Changed: `quantmesh.api.workstation` mounts the SPA and redirects
  legacy HTML routes; `test_workstation.py`'s PAGES contract tests
  migrate to SPA-serving + redirect contract tests; the golden path's
  13-screen checks verify the SPA serves and its data endpoints
  respond; `pyproject.toml` package-data gains the static bundle;
  `docs/licenses.md` gains the frontend inventory; release gate gains
  the frontend build check.
- Unchanged: `create_app` read-only observability, the domain/paper/
  risk/enablement kernel, ADR-0011 Decisions 2-3, loopback-only bind.
- No execution authority moves into the browser; AI cannot submit or
  approve orders through any new surface.
