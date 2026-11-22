# Iteration0038 — desktop day/week chart slice

Issue [308](https://github.com/ZP151/quantmesh/issues/308).
[Spec](../superpowers/specs/2026-11-17-desktop-day-week-charts.md) ·
[Plan](../superpowers/plans/2026-11-17-desktop-day-week-charts.md).

## Planner / source ownership

The operator requested this chart slice on 2026-11-17. Root's registered authority/capacity records
parallel-beta-charts-quant-20261117 govern this new work. It supersedes the older
two-track/soak-only wording for this explicitly authorized parallel product scope.
This owner exclusively writes frontend/router/locale/generated-client/frontend tests;
Product writes backend/auth and Quant supplies read-only data/prediction contracts.

Chosen implementation: dedicated existing-chart child view with independent
lookback/bar display and linked daily/week observations. No new visual identity,
chart framework, financial protocol or broad workspace redesign. Existing library,
API, design and exact pinned XNYS calendar are reused. Account/forecast UI wait their
contracts after this chart slice. Original PR307 acceptance is complete and not rerun.

## Quant / data boundary

Daily1d/XNYS history contract is required. New IVV extended-session hourly raw data
is not converted to RTH daily or claimed qualified. Calendar/holiday/partial/gap and
source evidence remain explicit. No new trial, provider, SDK, model, Paper/live,
external raw display, invitations, billing, mobile or AWS operation.

## Implementer / checkpoint

ACK2026-11-17 00:08:46SGT, reference2h/4h from ACK (not completion promises).
Reused clean isolated checkout9 on new codex/desktop-day-week-20261117 from current
remote origin/main a9934019/tree2085d219. Old source refs/artifacts/profiles/holds
remain. New complete192MiB forecast201326592B; free435573899264B>50GiB. Existing
node_modules junction reused, no install/copy. Local Vitest3.2.7 differs from locked
4.1.11; Publisher exact-lock gates remain required.

Baseline current chart tests:28 passed in3 files,37.50s, retained in
output/desktop-multiperiod-charts-20261117/BASELINE-CHARTS-01.log.
Existing exchange_calendars4.13.2 import and Thanksgiving week schedule confirmed;
regular Friday2026-11-27 closes18:00UTC, Thursday omitted. Existing backend history
already maps daily instants through America/New_York. No backend edits needed.

Impeccable isolated4.8.2/engine0.1.21 context loaded once; existing PRODUCT/DESIGN
retained. A newer4.9.1 is reported, but no mid-task tooling update is performed.
The user-specified paired comparison/independent dimensions and delegated narrow
implementation settle the design instead of another interview/concept tournament.
Native computer-control and node_repl tools are currently absent; no browser pass
or unauthorized fallback is inferred. Testable code proceeds while capability is
reported. Implementation/RED/GREEN and actual desktop delivery remain pending.
