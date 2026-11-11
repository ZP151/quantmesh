# Desktop Workflow and Language Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking. Original UI owner remains the sole source writer; fresh reviewers are read-only.

**Goal:** Open a saved/current research context, identify qualification and next action, and inspect evidence in the selected language without a long evidence transcript.

**Architecture:** Extend existing preferences/messages and Base UI primitives. Use native, mounted disclosures and wider evidence groups while keeping blockers and current actions visible. All service/query/mutation/admission/calculation interfaces remain unchanged.

**Tech Stack:** Existing React19/TypeScript/Vite8/Tailwind4/Base UI; existing installed dependencies only.

**Spec:** docs/superpowers/specs/2026-11-11-desktop-workflow-locale.md.

## Global Constraints

- Desktop Web only; no mobile work, port8878 or foreign service lifecycle actions.
- No backend/API/client/protocol/data/math/qualification/risk/request identity changes.
- Preserve exact raw evidence, digests, timestamps, originals and unknown meanings.
- Engineering fixtures never establish real-data, OOS, Paper or live qualification.
- One existing locale preference, typed shared copy and no DOM translation layer.
- No new dependency, Pro purchase, bulk upstream copy, global hooks/tool overwrite.
- Keep all failures and old resource/future holds; use this registered purpose only.
- Existing product world is fixed. All detailed layout calls are implementer choices.

## Review Focus

- A saved native_job or packet URL remains exact through locale and disclosure changes.
- Uncertain acknowledgements retain same-key recovery, while ordinary saved inspection is concise.
- A collapsed panel retains draft form state and never invokes a business action.
- Unknown evidence and nonpassing admission remain explicit and cannot become success.
- Long identifiers, locale switching, keyboard disclosure and desktop zoom remain usable.

## Task 1: Shared language and evidence presentation

**Files:** frontend/src/lib/messages.ts, preferences.tsx, format.ts; new
frontend/src/lib/messages/research.ts and frontend/src/lib/evidence-presentation.ts;
frontend/src/screens/ResearchJobs.tsx, NativeDailyPanel.tsx, SpyReplayPanel.tsx,
DataReadiness.tsx and remaining audited fixed-copy JSX; relevant locale tests.

**Interfaces:** pure `translate(locale, key, vars?)` reads the existing typed
messages; preferences.t delegates to it. Domain copy exports typed locale pairs,
without a second state store. `evidenceLabel(value, locale)` maps only known values
and returns unknown values unchanged. Shared `dateTime(value, locale)` includes
year/time context; raw inputs remain in evidence details/time attributes.

- [ ] Write failing behavior tests for selected-language research navigation,
  retained engine/native_job URL, localized known archive statuses and exact
  unknown evidence preservation.
- [ ] Run affected new tests with the installed Vitest binary and retain RED output.
- [ ] Centralize existing dictionaries, replace fixed bilingual/English UI copy,
  and route known semantic states plus date/number formatting through shared code.
- [ ] Run new tests and messages/preferences/native archive/research route locale
  tests; retain GREEN output. Typecheck. Commit coherent language change.

Commands from frontend: `node node_modules/vitest/vitest.mjs run --maxWorkers=1
src/screens/ResearchJobs.locale.test.tsx src/lib/evidence-presentation.test.ts
src/lib/messages.test.ts src/screens/NativeDailyPanel.saved-studies.test.tsx
src/screens/ResearchJobs.engine-navigation.test.tsx` and `npm run typecheck`.

## Task 2: Task-aware workspace and archive hierarchy

**Files:** new frontend/src/components/evidence-disclosure.tsx with its behavior
test; InstrumentWorkspace.tsx; instrument/ScenarioEvidence.tsx, ForecastEvidence.tsx,
PacketCopilot.tsx, PacketMonitoring.tsx, PacketOutcomeReview.tsx, DecisionRail.tsx;
NativeDailyPanel.tsx and focused tests; index.css for owned layout styles.

**Interfaces:** EvidenceDisclosure accepts title, optional summary, children and
initial open state and keeps children mounted. Existing component/API props stay
unchanged wherever possible. Workspace section IDs and native result focus remain.

- [ ] Add failing tests for concise default evidence/tools, material blockers
  outside hidden details, exact originals reachable, preserved draft state and
  saved-result task navigation.
- [ ] Run only those cases to establish RED; record before implementation.
- [ ] Implement readable market/decision widths and broad evidence area. Show
  qualification/source/cost summary; disclose provenance/full metrics. Make
  optional tasks concise with named status/next action. Preserve mounted state.
- [ ] Make saved native archive semantic and concise; subordinate manual ID
  tools without hiding uncertainty recovery or original downloads.
- [ ] Run affected workspace/instrument/native tests and type/lint/build; retain
  failures, resolve only actual regressions. Commit coherent workflow change.

Commands: installed Vitest on new disclosure/workflow tests, InstrumentWorkspace
and instrument tests, NativeDailyPanel*.test.tsx, ResearchJobs*.test.tsx;
`npm run typecheck`; `npm run lint`; `npm run build`.

## Task 3: Global shell and presentation integration

**Files:** components/shell/AppShell.tsx, lib/nav.ts, components/page.tsx,
index.css, shared messages and audited screen presentation call sites/tests;
PRODUCT.md/DESIGN.md only for operator-approved language/surface facts, with
no unapproved identity replacement; dedicated iteration0038 checkpoint.

- [ ] Add RED coverage for active instrument/trend locations and accessible
  operational navigation disclosure; retain keyboard/kill-switch availability.
- [ ] Implement shared hierarchy/type/focus/spacing conventions and selected
  locale labels. Preserve risk/kill-switch affordances and actual routes.
- [ ] Run meaningful affected checks and frontend type/lint/build once final
  source is coherent. Run one final changed-target detector, not an edit loop.
- [ ] Capture one bounded desktop browser batch from an OWN preview using
  current synthetic reads. Check1440/1912 plus representative1280/zoom/keyboard,
  initial height target<=2200, expanded originals, long strings, locale/state
  retention and zero unintended POST/external/provider/model actions.
- [ ] Inspect every capture, consolidate fixes, confirm once if needed. Fresh
  independent whole-branch code/design review; resolve material findings with
  focused RED/GREEN and a bounded confirmation, not repeated old acceptance.

## Task 4: Normal publication and usable merged Web delivery

**Files:** dedicated docs/iterations/0038-desktop-workflow-locale.md; Publisher's
normal generated src/quantmesh/api/static/app bundle; own evidence handoff only.

- [ ] Update iteration with issue306, spec/plan, independent assessments,
  actual commands/counts, desktop evidence and qualification limits.
- [ ] Freeze reviewed source commit/tree and send Publisher exact handoff.
- [ ] Publisher packages/reviews the coherent tree, runs necessary matching-head
  CI, normally merges through one PR and supplies final merge/tree receipt.
- [ ] Root coordinates original runtime owner to serve the merged-equivalent
  source while preserving original state; this writer never takes over8878 or
  other existing processes. Read-only verify actual published desktop pages.
- [ ] Return usable URL(s), source/tree/CI references and desktop Web results.
  Do not call this complete at source-only delivery or claim real/Paper success.

## Completion checklist

- [ ] All five review-focus preservation cases have meaningful passing evidence.
- [ ] Typed shared locale/status/error/date/number mechanism is used by changed surfaces.
- [ ] Reduced initial page length is measured; essential evidence remains visible.
- [ ] Raw originals and unknown evidence remain exact and keyboard reachable.
- [ ] Independent review plus required normal CI/merge/runtime delivery complete.
- [ ] 8878 unchanged; no new research/provider/model/trading effects; desktop only.
