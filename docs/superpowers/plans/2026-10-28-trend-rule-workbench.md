# Trend-rule workstation implementation plan

> For agentic workers: execute inline with a fresh independent reviewer at the
> demonstrable slice boundary. Use TDD and verification-before-completion.

**Goal:** Open and explain each fixed synthetic policy case from ordinary research.

**Architecture:** Shared packaged trace runner, allowlisted read-only FastAPI
route, generated typed transport and localized responsive step inspector.

**Tech stack:** existing Python/FastAPI/Pydantic and React/TypeScript/shadcn.

**Spec:** ../specs/2026-10-28-trend-rule-workbench.md

## Global constraints

No changed policy, fixtures, financial protocol, dependencies, trading authority,
real data or subprocess at runtime. Do not edit other Product helper,8878/18765,
PR240, version/locks/README or committed static assets. Sole publisher owns CI.

## Review focus

- Reject unknown/path/body/query inputs, never execute caller-provided code.
- API complete JSON matches all three CLI cases including identity and strings.
- A stale request must not replace a newly selected case or step.
- Cash/receivables/fills are labeled supplied, never calculated performance.
- Mobile uses one selected step without page overflow or hidden critical truth.

## Task1: shared trace and allowlisted API

Files: tools/run_trend_overlay_candidate.py; new
src/quantmesh/research/trend_overlay_trace.py; new src/quantmesh/api/trend_overlay.py;
src/quantmesh/api/workstation.py (mount only); tests/test_trend_overlay_api.py.

Interfaces: build_trace(case: str) -> dict; GET
/api/research/trend-overlay/{case_id} returns the complete trace, closed case enum.

- [x] Write API parity/invalid methods/unknown inputs/bounded body tests.
- [x] Run `python -m pytest tests/test_trend_overlay_api.py -q` and retain RED.
- [x] Extract existing runner without changing cases/policy, register read-only API.
- [x] Run API tests plus tests/test_trend_overlay_candidate.py and retain GREEN.

## Task2: ordinary entry and step inspection

Files: new frontend/src/{lib/trend-overlay-api.ts,lib/trend-overlay-copy.ts,
screens/TrendOverlay.tsx,screens/TrendOverlay.test.tsx}; App.tsx route;
ResearchJobs.tsx entry; src/api/client.ts generated from new endpoint.

- [x] Write tests for cases/steps/dual-arm values/supplied labels/retry/race/locale.
- [x] Run focused Vitest and retain expected RED.
- [x] Build the localized inspector with real typed API, disclosure and prev/next.
- [x] Focused Vitest, TypeScript/build and lint pass.
- [x] Serve built dist on one owned loopback ordinary workstation; perform new
  entry-to-three-cases and full API/CLI comparisons, screenshot1440 and390.

## Task3: review, verification and handoff

- [x] One independent correctness/spec/UX review; fix only material findings,
  maximum two review rounds. Preserve failing attempts.
- [x] Run relevant broad gates at slice boundary: affected Python pytest, Ruff, focused frontend
  Vitest, build/lint, generated client check, git diff --check/submodule status.
  Record pre-existing failures; no duplicate remote CI/full old browser suite.
- [x] Update docs/iterations/0038-trend-rule-workbench.md with role evidence.
- [x] Commit coherent tested slice; root receives commit/tree/file manifest,
  HANDOFF.json/progress.json, exact owned URL/PID/start/stop and limits.
- [x] Stop author changes. Root owns publication/CI/merge; author generated the allowed static package serially.

Execution ruling: root explicitly prohibited duplicate old full frontend/mobile/financial gates; reuse passing baseline and run only changed-path checks. Standard SPA generation became authorized after the initial lock. R1 mobile P2 received a single bounded correction and final R2 READY. Source commit/handoff checkbox denotes the final transaction performed immediately with this plan update, not a prior claim.
