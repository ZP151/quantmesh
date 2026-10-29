# Fixed native daily offline workstation implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline; one independent whole-slice review before publisher handoff. Record rulings and RED/GREEN evidence here and in the iteration.

**Goal:** ordinary Research jobs → fixed candidate/package/grant → one submission → immutable admission/report/Reject-Watch → same-ID cold reopen.
**Architecture:** candidate-specific local service uses ObjectStore, JsonlStore and WriterLease. Its trusted configuration registers inputs and candidate-specific grants; public requests contain references only. Extract the existing ten-arm calculation without changing cashbook or policy. Existing synthetic v1 and old IDs remain separate.
**Tech stack:** existing Python/FastAPI/Pydantic/pandas and React/TypeScript, no installs.
**Spec:** approved design SHA256 `6df22e9a1ad06d9a907c378c9b23c0dd8c68e8b207ac1c67915b8875e5011aa3`, retained at `output/v2-real-research-vertical-design-20261030-0045/ONE-PAGE-DESIGN.md`; approval `call_c992f98451a242979a1e8e3d1fdb2011/0`, “批准离线实现，真实数据另行准入”. Issue [253](https://github.com/ZP151/quantmesh/issues/253).

## Constraints and review focus

- Native-daily-v2 / fixed candidatev1 / sole cashbook / five arms at5/10bps unchanged. No new mathematics, market/provider/window/sample/OOS choice or acquisition; trusted engineering substitutes only. Paper/live false.
- Old SPY/once authority cannot migrate. Missing packages/grants create INSUFFICIENT/not_run with null report, not a successful backtest.
- Single writer until Server glue freezes. Exact runtime file ownership is the approved ten-file set plus necessary tracked spec/plan/ADR/iteration/reuse/roadmap docs.
- New local32MiB, every study≤8MiB included, remote0. Full forecast at `output/v2-real-offline-implementation-20261030-0057/FORECAST.json`; failures retained. No old broad suites, installs or environment copies. Existing node_modules is reused through ignored junction.
- Focus: hostile/tampered references; same UUID changed payload; second UUID reusing one grant; crash between reservation and computation; cold reopen after source/calendar changes. Each gets a regression below.
- First user increment18:57:09Z, reviewable slice20:57:09Z on2026-10-29; ACK16:57:34Z. Existing app Goal is reused (historical blocked status observed; no duplicate created).

## Task 1 — durable missing-input decision and same-ID reader

Files: new `src/quantmesh/research/native_daily_real.py`, `src/quantmesh/api/native_daily_real.py`, `tests/test_native_daily_real.py`; compose only `src/quantmesh/api/workstation.py`.
Interfaces: `NativeDailyService(root, *, registered=())`; `options()`, `submit(NativeRequest,key)->(job,created)`, `read(key)`, `artifact(key,kind)->bytes`, `decide(key,DecisionRequest,key)`, `close()`. `NativeRequest` holds optional package/grant/scope refs and the fixed candidate protocol identity. API under `/api/research/native-daily`: options, jobs submit/read, artifact and decision.

- [ ] RED: `test_missing_input_persists_insufficient_and_cold_reopens_without_compute` asserts terminal not_run/admission INSUFFICIENT/report null, same UUID same original bytes after service restart with calculation disabled.
- [ ] RED: changed request at same UUID conflicts; untrusted/missing refs never invoke calculator; tampered admission/decision fails closed.
- [ ] Implement typed records, bounded safe ObjectStore reads/writes, single WriterLease + JsonlStore intent/state and immutable admission/decision artifacts. Persist intent before any calculation; reader verifies identity, never recomputes.
- [ ] GREEN: `python -B -m pytest -q tests/test_native_daily_real.py --basetemp=<owned task1>`; then API roundtrip tests through ordinary workstation composition.
- [ ] Commit coherent green checkpoint; update iteration with exact commands, exit and user action.

## Task 2 — registered engineering substitute, grant and common calculation

Files: same backend tests/service; `src/quantmesh/research/native_daily_candidate.py` only extracts the existing calculation loop as `_calculate_matrix(frame, distributions, protocol_digest)`; engineering guard/protocol/cold reader unchanged. No engine/policy or old once edits.

- [ ] RED: trusted test registration computes exactly once for the entire same-cost matrix; compare shared calculation with hand-derived existing fixture expectations without rerunning old sample CLI/suite.
- [ ] RED: candidate/data/window/use mismatched grant, second UUID same one-use grant, overlapping submit and interrupted reservation cannot cause a second computation. Failed/insufficient admission does not reserve a trial.
- [ ] Implement registered `RealInput`/candidate grant binding from trusted ObjectRefs, strict package facts; default real execution remains unavailable. Engineering registration is labeled engineering and cannot claim actual permission. Valid reservation stored with intent under the sole lease before computing; one active call; close waits, restart interrupts without rerun.
- [ ] Store input-bound real envelope, complete ten-arm report and immutable admission. Record phase running/succeeded/failed/interrupted; no fabricated percentage. Reject/Watch binds original request/admission/report refs.
- [ ] GREEN new targeted backend/API tests, bounded type/size/complete-matrix cold verification and negative controls, no old broad native run. Commit/checkpoint.

## Task 3 — ordinary UI and startup integration

Files: new `frontend/src/screens/NativeDailyPanel.tsx`, `frontend/src/lib/native-daily-api.ts`, `frontend/src/screens/NativeDailyPanel.test.tsx`; modify `ResearchJobs.tsx` selector and generated `frontend/src/api/client.ts`. Workstation only adds optional service/root startup composition, preserving normal loopback entry and lifecycle.

- [ ] RED component: choose fixed candidate, missing package visible, submit decision, retain UUID before POST, see actual state/INSUFFICIENT/report null, Reject/Watch and original download, same ID reopen. Alternate trusted substitute displays five-arm/two-cost report and engineering disclaimer.
- [ ] Implement incumbent Operate steps, saved UUID, safe errors, tamper/ref mismatch refusal, keyboard and375px layout. Explicit root config allows saving missing-input decisions; without configured storage show unavailable, never ephemeral success. Do not change old SPY panel.
- [ ] GREEN targeted Vitest file, regenerate client, typecheck/build. Use existing dependencies only; bound logs/temp/build within forecast.
- [ ] Actual browser on ordinary page: missing-input save/cold reopen and one owned trusted-engineering study; download original admission/report/decision hashes, desktop+375px screenshots. No real data or trading action.

## Task 4 — review, tracking and publisher

- [ ] Add accepted ADR for the new entry/envelope boundaries, iteration/roadmap/REUSE_MATRIX and archived approved spec. Track issue253, active progress and all resource failures. ADR number must be unoccupied locally and coordinated with publisher.
- [ ] Fresh independent whole-slice correctness/safety review, at most two rounds, read-only reviewer; fix substantive issues with targeted RED/GREEN.
- [ ] Verify changed formatting/lint, targeted tests and generated contract/build once coherent; `git diff --check`, source/fixture pins, per-study/full-hold usage and clean close. Relevant broad gate belongs to publisher final CI, not duplicate local old suites.
- [ ] Freeze reviewed commit/artifacts and hand off to sole publisher for applicable CI/ordinary PR. Do not claim real-data or financial Goal complete. No push/merge/watch duplication.
