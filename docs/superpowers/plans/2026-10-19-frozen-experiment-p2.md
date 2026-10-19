# Frozen experiment P2 implementation plan

> **For agentic workers:** Follow the single-writer implementation, TDD,
> independent review and verification lifecycle in cross-agent-execution.md.

**Goal:** Complete import → inspect consumed-OOS verdict → download → reopen for
the existing frozen SMA100/SPY evidence, without evaluating the strategy again.

**Architecture:** Reuse immutable ObjectStore and verified SnapshotCatalog behind
one bounded local catalog/router. Add one dedicated page through the existing
workstation, preserving all execution authority and prior evidence.

**Tech Stack:** Existing Python/FastAPI/Pydantic, React/TypeScript and installed
pytest/Vitest. No installation or dependency changes.

**Spec:** `docs/superpowers/specs/2026-10-19-frozen-experiment-p2.md`.

## Global constraints

The approved specification is binding. Exactly one P2 source writer; parent
performs docs/env/evidence concurrently and generated-source work only after the
writer stops. Base main31b1c74. Exclude DataReadiness, original data, P1 preview,
old full suites, strategy/OOS execution, deployment and live authority changes.
Raw evidence stays in ignored output. Review at most two rounds per slice.

## Review focus

- Mutually consistent hashes can still encode unsafe historical claims; refuse
  incorrect verdict/exposure/OOS claims without pretending to prove chronology.
- Local object/index corruption after a good import must fail closed on reopen.
- Real protocol fields and null metrics must survive the synthetic-to-real
  boundary without silently defaulting to zero or changing primary case.
- Unsupported local ZIP inputs must not execute code, fetch links, leak paths,
  escape storage or exhaust unbounded memory.
- Phone first view must distinguish recorded results and formal qualification;
  long IDs, download names and history controls must stay locally contained.

## Task 1 — immutable evidence catalog

Files: new `src/quantmesh/research/frozen_experiments.py` and
`tests/test_frozen_experiments.py`. Consumes SnapshotCatalog public verified
get/archive and ObjectStore/ObjectRef; produces FrozenExperimentCatalog with
import/list/get and fixed artifact retrieval. DTO fields are shared with Task2.

- [x] Write synthetic package tests for complete binding and fail-closed cases.
- [x] Run `python -m pytest tests/test_frozen_experiments.py -q` with a unique
  owned `--basetemp`; expected RED for the missing behavior, retained in output.
- [x] Implement bounded inert ZIP preservation, strict association checks,
  atomic references and verified reopen; do not recompute economic results.
- [x] Repeat the same focused command; expected GREEN including corruption,
  unsafe-claim, nonfinite, null and dedup regressions.

## Task 2 — opt-in workstation API

Files: new `src/quantmesh/api/frozen_experiments.py`, dedicated
`tests/test_frozen_experiments_api.py`; bounded
`src/quantmesh/api/workstation.py` root/router hooks. Consumes Task1 catalog,
produces the fixed `/api/research/frozen-experiments` contract and CLI flag.

- [x] Write API/default-off/origin/content-size/download/CLI tests.
- [x] Run `python -m pytest tests/test_frozen_experiments_api.py -q`; expected
  RED before implementing router/flag, then retain the log.
- [x] Wire explicit opt-in root with snapshot dependency validation before demo
  seeding, safe errors, body limits and digest-bearing fixed artifact responses.
- [x] Repeat API tests plus the dedicated workstation startup tests; expected
  GREEN, preserving existing vn.py and snapshot startup behavior.

## Task 3 — dedicated inspection page

Files: new `frontend/src/screens/FrozenExperiments.tsx` and dedicated test;
`frontend/src/lib/frozen-experiments-api.ts` and dedicated test;
`frontend/src/lib/frozen-experiments-copy.ts`; bounded App.tsx/nav.ts route entry
and messages.ts nav.frozenExperiments only in two locales.

- [x] Write UI/API tests for unavailable, import/error/progress, list/reopen,
  recorded verdict/consumed OOS, nulls, integrity and original downloads.
- [x] Run the two dedicated Vitest files; expected RED before implementation.
- [x] Implement existing-console page with clear historical verdict first,
  fixed diagnostics and downloads; escaped original report, local locale parity.
- [x] Repeat focused tests plus affected navigation/message tests; expected
  GREEN. Run `npm run typecheck` and focused lint; expected exit0.
- [x] Stop source writing and send exact files, commands, logs and limitations
  to parent. Do not stage, commit, push or create additional writers.

## Task 4 — parent integration and delivery

Files: generated `frontend/src/api/client.ts`, packaged static SPA, this plan,
the specification, ADR0031, P2 iteration and operator guide. Parent owns all
acceptance evidence in `output/0038-frozen-experiment-p2/parent/`.

- [x] Confirm writer stopped; generate API client and bundle using existing
  runtime. Validate the builder's fixed absolute deletion target is inside this
  worktree before invoking it. Expected successful build and current API check.
- [x] Run fresh focused backend/frontend integration, changed-file Ruff/format,
  TypeScript and `git diff --check`; record exact commands, counts and exits.
- [x] Use isolated P2 snapshot/experiment stores and another loopback port.
  Import the retained original-byte package, inspect actual UI, verify original
  download digests, dedup and first receipt after controlled cold reopen.
- [x] Capture one desktop/mobile batch with ordinary readable viewports; inspect
  real images, contain horizontal overflow and preserve raw capture provenance.
- [x] Independent bounded whole-slice review; at most one fix batch and second
  review. Record role outputs and any remaining risk in the iteration.
- [x] At a coherent green boundary, commit/push and create a draft PR for issue191;
  attach it, report exact head and release shared-file window to main.
- [x] Keep source merge and unseen P3 design as separate approval gates. Report
  continuation of the full P1→P2→P3 objective, not premature completion.

## Recovery

Read Git status/history, issue191, this spec/plan, P2 iteration and the canonical
P2 contract/progress in the authority checkout's ignored product output. Check
existing task logs before rerunning. Current task checkboxes are acceptance
state, not a substitute for recorded observed command output.

## Completed checkpoint

Source71b9547; Draft PR195. Parent selected backend52/frontend72, actual original
import/download/dedup/cold reopen, final desktop/mobile evidence and independent
round1 READY are recorded in the P2 iteration. One Important source finding was
fixed with2RED→52GREEN. Final closeout is docs only; no future merge or P3 design
approval is inferred.
