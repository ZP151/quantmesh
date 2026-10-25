# SPY replay progressive disclosure implementation plan

> **For agentic workers:** Execute inline with the available TDD and verification skills. Root explicitly keeps the completed two-round structural review closed; verify this layout delta with focused behavior/accessibility/rendered checks, without a third structural review or another implementer.

**Goal:** Let an operator understand the current SPY replay result and reach its next action without scrolling through every configuration, scenario and recovery detail.

**Architecture:** Retain the dedicated API adapter and persistence lifecycle. One state-aware workspace exposes Input, Report and Decision navigation, with a persistent safety/source/status summary and one main step at a time. The report compares the fixed baselines in one scenario table; base/stress selection preserves both cost assumptions. Secondary evidence and recovery remain explicit disclosures.

**Tech stack:** Existing React/TypeScript, native buttons/details/table, incumbent workstation tokens; no dependencies.

**Spec:** Human instruction in this UI chat on2026-10-25: shorten phone/web layouts according to business operation, neither hide nor expose everything; keep8878 unchanged, engineering acceptance separate from real qualification, continue combined engineering acceptance through root.

## Constraints and design decision

- Issue205; source base is reviewed UI commitd528278 on7a0b062. Same independent UI worktree; backend review/integration remains root-coordinated.
- SPY/SMA100,100+21sessions,100000USD,5/10bps, same-cost buyhold and zero-interest cash remain fixed.
- Persist-before-POST, GETsameID, exact decision bindings/retry, original artifact bytes and all financial guards remain unchanged.
- Paperfalse, INSUFFICIENT and engineering-vs-reviewed source visible in every step. No source activation or real-data acquisition here.
- Never modify8878 WT/process/data; never modify backend, generated API or productionstatic assets.
- Alternatives considered: all-accordion page still makes the operator hunt through a long record; mandatory wizard blocks returning to a completed report. Choose navigable state-aware steps with a compact always-visible summary, one comparison and explicit detail drawers. This is the implementer's choice under the user's delegated layout judgement.
- Mobile and desktop share semantic DOM/focus order. Primary tasks have44px touch targets; details retain visible labels, keyboard access, same-cost comparators and original downloads.

## Task1: one step-focused UI loop

Files: modify `frontend/src/screens/SpyReplayPanel.tsx` and its existing test; retain `spy-replay-api.ts` behavior and minimal `ResearchJobs.tsx` selector.

- [x] Add behavioral REDs: succeeded opens report not next-input block; base/stress selector exposes one complete comparison; decision accessible through explicit next action and review-back; cold final reopen prioritizes original decision; unavailable/uncertain recovery remains reachable; safe keyboard/locale semantics.
- [x] Run new panel tests; preserve real behavioral failures.
- [x] Implement stage selection derived from server state until explicitly navigated; resetting on new/open job. Keep source/status/cost/safety and key result summary visible. Show one current panel, advanced evidence and job tools in native disclosure.
- [x] Keep current/new-input configuration distinctly labeled from reopened report. Scenario switch changes only view, never requests/recomputes.
- [x] Run focused panel+API tests; preserve the unchanged ResearchJobs boundary as historical evidence; build own dist; changed-file lint/diff.

## Task2: independent review, rendered evidence and integration handoff

- [x] Preserve the completed two-round review; check only this layout delta's behavior/accessibility/recovery invariants, per root's explicit no-third-review instruction.
- [x] One batched desktop/phone layout pass across report/decision states; combined initial/cold verification follows publisher assembly; assert viewport overflow, actionable location, collapsed-height improvement, source/safety persistence and original-byte downloads. At most one confirmation pass.
- [ ] Root supplies frozen backend and exclusive integration worktree/port; assemble and exercise actual five-operation engineering API+SPA if assigned here, otherwise provide exact source to the designated assembler and inspect its receipt. Never duplicate a root-owned run.
- [ ] Record exact commit/tree, focused checks, observed user-loop evidence and remaining real-data qualification in the owned iteration/checkpoint. Send source and evidence to root under explicit human authorization; root owns combined finalPR/publication.

## Review focus

Asynchronous success must not replace an explicitly selected review view; old job must not inherit current input qualification; hidden panels must not create accidental actions; scenario choice must not change calculation; uncertain requests/decisions and their keys must survive navigation and reload. Tests exercise these boundaries and retain the existing API byte/pin tests.

## Completion and release boundary

Build/lint/focused tests/diff checks and real rendered workflow evidence must agree. Combined backend engineering evidence remains distinct from synthetic transport mocks and real OpenD acceptance. No broad historical suites, server capture, Paper/live activation or production publication belongs to this UI slice.
