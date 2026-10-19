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

## Automated375px geometry regression —2026-10-20

Release reviewthreadPRRT_kwDOTwH6TM6t-HkC identified missing CI coverage for the
already accepted geometry. Main explicitly assigned a single test-only writer
window; no new design approval. Added
tests/test_spa_e2e.py::test_data_readiness_mobile_geometry_375 using existing real
SPA/server/page fixtures and the established route-fixture pattern. A synthetic
snapshot exposes all seven page-local targets and long URL/digests without data
import or research admission. Assertions cover separate file/import rows,44px
minimum rendered heights and no horizontal document overflow. Fonts settle before
measurement; viewport375x812 is set before navigation to avoid resize transitions.
Existing browser-gate discovery already includes this module; no CI/harness change.

Targeted RED serves retained pre-fix31b1c74 static assets through an ignored test
plugin:1failed, detecting the shared row and undersized controls. Same selected
test against unchanged PR189 assets:1passed. Ruff check/format and whitespace pass.
Default local Playwright1.63 Chromiumrevision1243 is absent (retained cache1234), so
its availability probe skipped; that is not counted as a pass. Actual RED/GREEN
used the supported already installed Edge Chromium channel via an ignored local
launch adapter. Repository browser fixture is unchanged; CI retains its standard
matching-Chromium installation. No dependencies installed or broad suite run.
Initial sharedpytest-temp cleanup permission failure and browser skip are retained;
subsequent runs use separate owned basetemp directories, preserving all evidence.
Logs/plugins/baseline under authoritativeoutput/0038-uiux-continuous/PR189-e2e-*.

This commit changes only the E2E module and this record: production source and
packaged assets equal11f54e3; PR193head044febd is untouched. No merge or fresh CI
success/thread resolution is claimed; the release owner applies the exact-head gate.

Consumed actualPR195 receiptpr195-postmerge-20261019.json: mergeddddc6783,
treebef3ce79f79cbc0be082a197af6921b77307f407. Read-only merge-tree prediction finds
generatedJS rename/index conflicts between189 and that main. No merge was performed
inside this explicitly test-only/no-bundle window. Combined-source asset integration
must retain P2 route plus UI and be coordinated separately, never choose one bundle
wholesale. After normal push this writer window is released to the main/server owner.

## Authorized combined-main integration —2026-10-20

Main extended the same window to finish necessary nonforce integration. Preserved
the regression commitdda29d7 and normally merged actualorigin/main
dddc67830da77b621c4d543de65fc6fd6e61e6c9/treebef3ce79f79cbc0be082a197af6921b77307f407.
No runtime source conflict: P2App/nav/messages/FrozenExperiments/client remain
byte-identical toactualmain, while DataReadiness/test module remain identical to
dda29d7. Other backend/frontend runtime paths have no unintended delta frommain.
Source-blob proof: authoritativeoutput/0038-uiux-continuous/PR189-combined-source-proof.json.

Only generatedJS rename/index conflicts occurred. Ran TypeScript/Vite build once
from the real combined sources, copied thatdist to package and removed only stale
generated files after verifying the fixed isolated bundle target. No ours/theirs
source or bundle choice; all merge conflicts resolved. P2route and mechanical UI
therefore coexist in the generated package; package/dist file counts and bytes match.
Type/buildPASS, generatedAPI client current, whitespacePASS. Same selected375px
regression against this new package:1passed on retained supported Edge channel.
Existing dependency deprecation, chunk and plugin-time warnings retained. No old
fullsuite, extra review, dependency install or repeat product acceptance.

PR193head044febd remains untouched. This final normal-sync candidate supersedes
dda29d7 for release verification; earlier history remains, with no force/reset.
The release owner must consume the final exacthead/CI, not a prior candidate. No
CI success, actionable-thread closure or merge claimed here. Integration is done;
this writer is STOP/released for main/server/P3 scheduling, with no extra193/polish.

## Required-CI browser fixture compatibility —2026-10-20

Main authorized a narrow test-only fix after PR189 run39287794502 at1400966
failed its browser job118180119368. The NVDA heading timeout was secondary:
instruments/api.py passes named horizon/forecast_id to render; the real workspace
supports both, but the two local browser-test wrappers omitted them. Planner and
implementer scope is only this fixture contract plus this record. Research/data
qualification, runtime, generated assets and PR193 remain unchanged; no new data,
backtest or trading authority is introduced.

Both wrappers now accept and forward the two explicit parameters unchanged.
Four parameterized contract cases cover default/selected values through both
wrappers and preserve the intentional AAPL OSError without reaching the delegate.
They first reproduced4failures with unexpected keyword argument horizon, then
passed4/4 after the fix. Existing browser assertions remain intact; there is no
generic kwargs acceptance, exception swallowing or business-code workaround.
Bounded diff review checked those scope and refusal invariants.

Verifier reran the original failing case
tests/test_instrument_workspace_e2e.py::test_nvda_inspect_to_paper_loop_and_race_refusal:
1passed in159.57s, retaining5existing dependency deprecation warnings. The local
run used the already installed supported Edge Chromium channel through the ignored
retained launch adapter because the local default Chromium revision is absent;
CI keeps its matching browser installation. Ruff check/format and whitespace pass.
No dependency installation or broad old-suite rerun. Logs are retained under
authoritativeoutput/0038-uiux-continuous/PR189-stub-contract-{RED,GREEN}.log and
PR189-workspace-original-GREEN.log, alongside the original failed CI log.

The new commit supersedes1400966 only after normal push; the release owner must
gate its exact new head with fresh CI. No CI success, thread closure or merge is
claimed. After delivery this narrow writer window is STOP/released; PR193 stays
frozen at044febd35febe7d9e5f2afaebd58d56cd5d05630.

## Required-CI daily-session expectation correction —2026-10-20

Release owner returned a new material failure from run39292566007/head0a446b7,
browser job118196809563: the mobile daily-session test expected No action1 after
a successful refresh. Its previous NVDA inspect/paper/race case now passes in CI.
Main/release owner authorized this bounded diagnosis/fix, retaining failed evidence
and PR193 freeze. Planner scope is this one browser case plus iteration evidence;
no third structural review, new product scope, old broad suite or blind CI rerun.

Quant/reviewer boundary: attention buckets do not upgrade evidence readiness.
Local original single-case RED reproduced the identical assertion:1failed in250.03s.
Failure-page text and inbox agree on AAPLwatching, BTC-USD/SOL-USDnot_started and
NVDAwatch_triggered. Existing attentionBucket explicitly places not_started before
unavailable readiness, yielding No action3/Triggered1/Blocked0. Both missing-packet
rows retain unavailable readiness and no_saved_packet. Actualmaindddc6783 and this
candidate have identical Watchlist source blobs and emitted bucket-function bytes;
this is an old test expectation mismatch, not render timing or a bundle regression.
Both incompatible assertions and bucketing date to the originald14fa635 commit.

Implementer corrected the English No action and Chinese Blocked expected counts,
added English Blocked0/Chinese No action3 checks, and exercised the No action filter:
all three exact symbols visible, NVDA excluded, both original missing-evidence
messages retained. Existing refresh/focus/triggered/exact-packet/restart/partial-
failure/Chinese/overflow/reset assertions remain. No runtime or bundle change,
new wait, exception catch or removed assertion. Bounded diff review checks this
scope; the accepted source/data/trading semantics and PR193 remain unchanged.

Verifier: corrected original single browser case1passed in450.08s with5existing
dependency warnings; Ruff check/format and whitespace pass. Actual RED/GREEN used
the retained supported Edge Chromium channel via the ignored local adapter; no
default-browser skip counted as success and no dependency installed. Logs,
failed-page text/inbox/screenshot and source-bundle comparison
are under authoritativeoutput/0038-uiux-continuous/PR189-mobile-*; failed CI log is
PR189-CI39292566007-browser-failed.log. Original failures remain preserved.

Normal commit/push supersedes0a446b7 for fresh exact-head CI. The release owner
owns that gate and conditional merge; none is claimed here. This bounded writer
is STOP/released after delivery. PR193 remains044febd and must await actual189
receipt before its separately scoped normal integration.

## Consolidated workspace boundary diagnosis and current-main sync —2026-10-20

Run39295546565 at2e9a03b reached the third workspace browser case and failed its
Chinese390px/reduced-motion document-width assertion at line560. Both earlier
NVDA and daily-session cases passed in that run. Main authorized one concentrated
fixture/contract audit and the complete instrument-workspace E2E module, rather
than successive one-assertion pushes. Original failure log is retained. Prior
signature/count causes and their evidence remain in
output/0038-uiux-continuous/PR189-WORKSPACE-CONSOLIDATED-DIAGNOSIS.json.

The unchanged isolated third case passed locally:1passed in95.88s,5existing
warnings, final document390/viewport390/fonts loaded/no offending elements.
This is not a reproduction or proof of a fix. CI uses Linux Chromium156 while
local acceptance uses the installed supported Windows Edge154 channel. Ordered
complete-module diagnosis passed:7passed in720.92s with5existing warnings. The
ignored observation adapter recorded the original assertion result as true, with
document390/viewport390/fonts loaded/no offending elements both immediately and
after screenshot. No assertion, timeout or runtime layout changed for this probe;
the complete test module remains byte-identical to2e9a03b. Neither the isolated nor
ordered run reproduces the Linux CI overflow; its root cause remains unproven.

Normal main integration consumed actual PR197 receipt:008b3536006ecfdfc652bf54062346fcfd350ba9,
tree1316af4567b682d93e6b86f2e8016831403cfe27, parentd0230240 from PR186. The shared
origin/main advanced from PR186 to PR197 before merge began. Source merged cleanly;
only generated resources conflicted. P2 routes, P3 Ops/paper controls/CommandPalette
equal actual main; accepted DataReadiness source equals2e9a03b. One TypeScript/Vite
build from combined source passed; generated package and dist bytes match. Existing
chunk/plugin advisories remain. API currency passed with explicit existing Python313
and this worktree's PYTHONPATH; the default-environment stale result is preserved.
No dependencies, PR186/197 CI observations, old layout suite or PR193 change.

At the release owner's request a process-state snapshot recorded PID45540/start
18:42:18UTC, elapsed584.26s, log0bytes and no final probe yet. Direct pytest had
no module wall timeout; a prospective1800s supervision bound was then recorded,
matching the CI browser gate. The existing run finished normally within that bound;
no suite was relaunched. The snapshot and terminal log both remain preserved.

Ruff check/format, whitespace, source preservation and package-byte checks pass.
This normal merge is a current-main candidate, not a claimed overflow fix. Failed
run39295546565 remains evidence; fresh exact-head CI must establish the Linux
boundary before conditional merge. Return the concentrated unproven-root limitation
to the coordinator/release owner without speculative CSS, weakened assertions or
blind rerun. UI STOP/writer released after delivery; PR193 stays frozen at044febd.

## One authorized Linux failure-diagnostic candidate —2026-10-20

Exact-head run39306537948 atedd4b15 again failed the same width assertion.
Its browser artifact contains only pytest/events logs, with no actual widths,
DOM rectangles, font state or screenshot. Root cause remains unproven. Main
explicitly corrected the earlier CI-breadth stop condition: one necessary test-only
diagnostic commit may trigger normal PR CI and its other selected gates. Do not
manually rerun broad jobs, install a Linux environment or alter CI policy.

This candidate changes only this record and the workspace E2E module. The failing
case now records diagnostics inside its AssertionError path, then re-raises the
same original assertion. All eight original assertions have identical ASTs; the
native width expression/value, timeouts, browser fixtures and production layout
remain unchanged. A diagnostic Playwright/IO error is chained to that same
assertion rather than swallowed or substituted for it.

Post-failure output includes viewport/body/document widths, exact structural
selectors and rectangles for up to24 overflowing elements and their parents,
computed sizing/overflow/font styles, font status and device/browser parameters.
No text, form values, credentials, cookies or storage are collected. In CI, the
helper writes JSON and one viewport PNG to the existing QUANTMESH_GATE_LOGS folder,
which the unchanged workflow already retains. A passing case emits nothing.

Two original-error propagation cases first failed without the helper; after the
implementation, those plus the artifact-root contract passed3/3 in2.17s. A bounded
pure-HTML check on the installed Windows Edge identified a known480px element,
document488/viewport390, retained JSON/PNG and rethrew the same original assertion.
Its fitting control passed without new artifacts. This validates the diagnostic
mechanism, not the Linux defect. Ruff/format, whitespace and source-scope checks
pass; no old workstation or broad suite reran. Evidence under authoritative
output/0038-uiux-continuous/PR189-CI-diagnostic-*; run39306537948 remains preserved.

The release owner consumes this candidate's normal exact-head CI once. Only its
real Linux failure geometry may justify one minimal root-cause fix batch; if the
evidence is insufficient or requires product structure changes, return the exact
gap to Planner. No overflow fix, CI success or merge is claimed. PR193 remains
frozen at044febd; no new Goal, automation, dependency or workflow change.

## Evidence-backed key-level wrap fix —2026-10-20

Planner consumed the one real Linux diagnostic run39314587808 at164a919.
Retained JSON reports document/body394 versus viewport/client390, loaded fonts,
zh-CN/reduced motion and zero overflowing element rectangles. Its PNG shows the
three raw key-level values concatenating beyond their columns under 看涨结构.
The exact source is MarketCanvas.tsx/LevelFact, not ScenarioEvidence: the parent
already uses three minmax(0,1fr) columns and min-w-0, while the numeric dd has no
break opportunity. Text can overflow a bounded element without widening its box,
explaining the zero-element result. Mapping agrees with the screenshot; no
further diagnostic candidate or structural review is needed for this narrow fix.

Quant boundary: preserve the complete server-owned numbers and their authority.
No rounding, recalculation, precision reduction, data admission or trading change.
Implementer added only overflow-wrap:anywhere to LevelFact's dd using the existing
utility. Column count, values, typography, controls and all other source remain
unchanged. Rebuilt packaged assets once from the same combined P2/P3/UI sources.

Verifier added cell scrollWidth<=clientWidth checks to the existing390px Chinese/
reduced-motion E2E, retaining all eight old assertions in order. Before fix this
case fails locally: all cells106px wide but text119/112/119px (1failed,50.38s).
After the one-utility change:1passed,50.31s,5existing warnings. All three cells now
measure106/106; document/body/viewport390, fonts loaded. Values remain exactly
115.13060827994977,118.7120627398097,115.13060827994977. Ordinary viewport screenshot
confirms readable wrapping in the original columns; one confirmation pass only.

MarketCanvas's focused render cases now include long fractional values and retain
the original integer case:9passed, full precision preserved. TypeScript/Vite,
targeted Oxlint, Ruff/format, whitespace and package/dist byte equality pass;
Impeccable detector returns[]. Existing chunk advisory retained. Bounded diff review
confirms only one production class, its regression coverage and generated assets;
P2/P3/DataReadiness and PR193 remain unchanged. No new structural review, dependency,
workflow, timeout, strategy/OOS or old broad suite. Windows Edge is the actual local
browser; Linux acceptance still belongs to final exact-head CI.

Failed Linux artifact is preserved under authoritativeoutput/0038-uiux-continuous/
PR189-CI39314587808-browser-artifact/. Local RED/GREEN, measured glyph rectangles,
untouched PNG and checks are PR189-key-level-*. Deliver one normal final commit/
push to the unified release owner; no manual CI rerun, CI success or merge claimed.
This bounded fix batch is complete and writer released after delivery. PR193 stays
frozen at044febd until the actual189 merge receipt, with no further polishing.
