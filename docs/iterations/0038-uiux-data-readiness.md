# Iteration0038 — Data readiness UI/UX batch01

Issue: [188](https://github.com/ZP151/quantmesh/issues/188). Mode: Operate.
This is a separate bounded frontend repair. PR187 merged normally as31b1c74
on2026-10-19 at06:02:22UTC; its tree494d2acc equals the original95df504 candidate.
This branch originally started at actualorigin/main d4bee7f with that explicit
dependency. It now normally merges31b1c74 and PR189 targetsmain, preserving the
UI repair. It never changes PR187's branch/head or its independent release gate.

## Planner / product

One user action: choose a local snapshot and operate Data readiness at375px.
Actual desktop1280/mobile375 inspection found the file selector squeezed beside
the import action, plus28–40px local button targets and a20px lineage summary.
The authorized mechanical design stacks the compact file row and expands local
targets to44px while preserving desktop density and content order. Shared shell,
messages, backend/API and product-owner files are excluded.

Success: full-width selection field, separate import action, all page-local mobile
controls at least44px, no document overflow and visible keyboard focus. Stop after
one repair batch and one combined confirmation. A separate proposal to move download
actions and disclose passing checks awaits an actual human response; no such
information-architecture change is implemented.

## Quant researcher

No data or research changes. The2965-row retained SPY snapshot remains structural
PASS/researchINSUFFICIENT; R1/R2INSUFFICIENT, allowed useinspect_evidence_only.
The2021-12-17 conflict and rights/PIT/vendor-session/issuer-lineage gaps stay visible.
No strategy/OOS execution, provider calls or trading authority follows from UI checks.

## Implementer

Only DataReadiness.tsx changes production logic: responsive flex direction and
compact minimum heights on refresh/import/download/history/lineage controls.
Labels, facts, requests, disabling, status/error rendering, disclosure default,
download bytes and DOM order remain unchanged. Existing dependencies were copied
to this independent worktree without install/upgrade. The production bundle is
rebuilt and copied byte-for-byte to the isolated package's static directory.
No upstream code is copied. No arbitrary Python or server command ran.

## Verifier

The read-only rendered-geometry probe failed before implementation for the shared
file row and six sub44px targets. After the repair it passes: file width328px
(previously164.56), file height46px and every other local target44px. Desktop
retains the same-row input/action with32px import button; document width1265 within
1280viewport. Mobile document width360 within375viewport (native scrollbar).

Keyboard Tab from the file input reaches the named table scroll region with
focus-visible=true/outlineauto; ArrowRight changes its horizontal scroll position.
Enter opens lineage with visible focus. Four64-character digests wrap in208px
columns without overflowing; sourceURL wraps. The table already had local overflow
and tabindex0, so its implementation was preserved.

Targeted existing DataReadiness tests:10passed. TypeScript and Vite production
build:PASS; existing large-chunk advisory retained. Mechanical Impeccable detector:
[] findings. Whitespace check:PASS. New read-only browser probe is committed as
frontend/scripts/probe-data-readiness-mobile.js; its RED/GREEN evidence and ordinary
viewport screenshots are under the authoritative coordination checkout's ignored
output/0038-uiux-continuous/screenshots/batch-01/ directory.

An immediate viewport-switch probe briefly measured the history button at40.375px
inside the incumbent150ms transition. That failure is preserved separately; the
same committed probe passes after layout settles (computedmin-height44px).

One desktop and four phone after-screenshots cover import/result, keyboard table,
download/history and expanded lineage. These are actual JPEG screenshots; no crop,
resize, annotations, generated pixels or account secrets. Preview8864 and its
snapshot store were not stopped/reset/imported into. The isolated UI preview8868
uses read-only existing API calls for history/reopen. No old full suite or CI reran.

## Reviewer and delivery

Independent read-only review round1:READY, no actionable findings. Reviewer checked
the source and packagedJS/CSS against95df504 and confirmed only the intended
responsive classes/reference changes. Final lint and whitespace checks pass.
New PR requires its own review/CI; PR187's conditional merge authority does not
authorize this PR. No merge or CI success is claimed here.

## PR187 merged baseline reconciliation —2026-10-19

Consumed the release owner's existing postmerge receipt under
output/0038-pr187-release-gate/postmerge-20261019T060510Z.json in the realdata
worktree; no PR187 CI/security/layout gates were rerun. Actualorigin/main31b1c74
and original95df504 both have tree494d2acc2113be375ab0312aba0c610f3c6fd397.

Normal nonforce merge3c92d0f resolved squash-history add/add and generated-asset
rename conflicts using the exact verified UI candidatecb4f746. The complete
reconciled tree remains21331216aaeed0c2f5cd3b2e7645c87b4450aaa9, byte-identical to
that candidate. A follow-up documentation checkpoint updates only this record;
frontend source, browser probe and packaged assets do not change. Whitespace,
ancestry and complete-tree/path comparisons provide the targeted reconciliation
evidence. No old layout test/build/screenshot suite was rerun.

PR189 still needs its own exact-head release gate and merge authority. PR187's
operator approval is not transferred. UI03/UI04 retain the original pending
human choice; no repeated question, new implementation, Goal or automation.
