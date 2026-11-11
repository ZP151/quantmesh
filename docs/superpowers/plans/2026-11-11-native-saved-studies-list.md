# Saved Native daily studies implementation plan

> **For agentic workers:** Use superpowers:executing-plans for this backend slice. Original UX owns the separate frontend slice after the exact API handoff. Preserve one fresh whole-slice review, with at most one located correction round.

**Goal:** Discover existing Native daily studies without remembering their UUID, then reopen the original admission, report and Reject/Watch decision without calculation.

**Issue:** [#304](https://github.com/ZP151/quantmesh/issues/304).

**Spec:** Operator-approved `NEXT-SLICE-DESIGN-01.json`, 7753 bytes, SHA-256 `1e210b359eea46956964f56eb1e531df52790014ad20bed314869952d964d346`. Actual human approval event SHA-256 `782c3ca588d7f49b6eae7e2e10fd2ba424c676423b4b905fb45bece2a39f218d`, 2026-11-11 Singapore. Immutable local originals and capacity registration are referenced by the main coordinator's canonical current-status entry. The original proposal's pending-approval wording is historical and is superseded by that approval.

**Architecture:** Add one read-only collection operation to the existing service and router. Reuse the existing condition, verified journal/object reader and public legacy/recovery projection. Original UX consumes this collection and reuses existing UUID/artifact reads; no new registry or storage format.

**Tech stack:** Existing Python/FastAPI/Pydantic/pytest; existing React/TypeScript frontend under the sole UX owner. Baseline is merged `ed1ceffed5b79cb2b780e50853538d51bdec57db`.

## Global constraints

- Backend owns only `src/quantmesh/research/native_daily_real.py`, `src/quantmesh/api/native_daily_real.py`, `tests/test_native_daily_saved_studies.py` and this uniquely owned plan.
- Return at most the existing `MAX_JOBS = 32`; no index, migration, directory selector, new dependency or environment.
- Listing/selection never submits, resumes, decides, calculates, reserves a trial or calls a provider. Preserve original bytes and all existing authority/financial labels.
- Preserve current legacy/recovery response shape and omit existing internal grant, runtime, transaction and decision-key fields through `_public`.
- Configured empty is successful `jobs: []`; unavailable and integrity failure remain existing safe errors, never partial/empty success.
- Do not edit frontend/generated files, shared ROADMAP/ADR, source math/cost/quantity policies or the original running root/8878/18956/publication checkout.
- New backend purpose has a registered 96 MiB full hold. Retain all old holds, futures, failures and all new failed runs; do not install or delete evidence.

## Review focus

1. A corrupt late record must fail the entire collection instead of returning an apparently healthy prefix.
2. Same-time records must have deterministic order, independent of journal order: `created_at DESC, job_id ASC`.
3. Cold readers need neither current registrations nor calculation/calendar/provider execution; saved report/decision bytes and file timestamps remain unchanged.
4. Both actual recovery records and legacy null report/decision records retain their exact public contract; malformed public projection must be refused safely.
5. The collection remains bounded and serialized with existing service access; it does not silently truncate an over-capacity journal or leak private bindings.

## Backend slice — one verified collection

**Files:** the three backend paths above.

**Interfaces:** `NativeDailyService.list_jobs() -> dict` returns `{"jobs": [current public job views]}` while holding `_condition`. `NativeJobCollection(Contract)` types `jobs: list[NativeJobResponse]` with `max_length=MAX_JOBS`. `GET /api/research/native-daily/jobs` uses that response model, existing authority/error mapping and no-store caching. Existing POST and UUID routes are unchanged.

- [x] Write focused tests for configured empty, unavailable service, original-ID ordering/ties, bounded legacy/recovery public views, no mutation/effects, invalid original/journal and cold report/decision reopening.
- [x] Run actual RED on current source: `python -B -m pytest -q tests/test_native_daily_saved_studies.py -p no:cacheprovider --basetemp=output/saved-studies-backend-20261111/red-temp`; retain exact source import path, log, exit and expected missing-seam/405 failures.
- [x] Implement the minimal collection using `_condition`, `_records` and `_public`, plus the typed GET route. Do not change existing verification or numerical behavior.
- [x] Run GREEN on the new tests with a fresh owned basetemp. Confirm original report/decision bytes and journal/object hashes/timestamps unchanged across collection and cold reads.
- [x] Run the targeted affected `tests/test_native_daily_recovery_api.py`, changed Python Ruff/format and `git diff --check`. Broader checks and publication belong to the sole Publisher; no duplicate old suites/CI.
- [x] Export the exact router OpenAPI and source hashes to the ignored evidence directory for the coordinator to hand to original UX. Existing public legacy/recovery payloads are reused, with an outer `jobs` collection only.
- [ ] Commit the coherent backend/plan checkpoint; fresh independent Spec/Standards review checks only this bounded diff. Resolve substantive located findings with targeted RED/GREEN, at most one R2.
- [ ] Freeze a reviewed handoff with commit/tree, source/schema/test/raw-log/capacity pins and known limitations. Main coordinator mirrors phase evidence into the active iteration and dispatches sole Publisher integration.

## Frontend / publication boundary

Original UX alone owns the saved-study list in NativeDailyPanel and its API helper/tests after the exact backend handoff and its current locale freeze. It must preserve manual-ID reopen and honest loading/empty/unavailable/integrity states, then prove selecting an existing UUID performs GETs only and retains original artifact hashes. Existing desktop/mobile components and English/Chinese preferences apply; no redesign or new authority action.

The sole Publisher owns generated schema/client/static assets, coherent integration, applicable normal CI and review/merge. This backend checkpoint does not claim a completed browser loop or deployment. Qualified real-input research, OOS, Paper/live eligibility and the long research Goal remain separate and unmet.

## Role / evidence checkpoint

- Planner: actual approved one-action design and #304; first backend increment target 60–90 minutes, at most two hours after resource registration at 20:57 SGT.
- Quant researcher: only offline synthetic software tests; original quantities, cashbook, costs, financial labels and trial rules remain unchanged.
- Implementer: original Product, isolated managed `saved-studies-backend` worktree; original UX is sole frontend writer.
- Verifier: ignored `output/saved-studies-backend-20261111/RED-01.*` preserves an isolated-launcher missing-HOME collection error (not a functional RED). The launcher now supplies purpose-owned home/temp, disables bytecode/cache and uses this checkout's source. `RED-02.*`: 13 expected failures from GET405/missing service seam, 7.97s. `GREEN-01.*`: 13 passed, 5.86s. `AFFECTED-01.*`: the existing 10 recovery API tests passed, 9.19s. Existing upstream deprecation warnings remain; no dependency changes. Initial changed-file static checks identified one overlong test line, corrected by formatting only.
- Coherent checkpoint: `FINAL-01.*` verifies the exact formatted source/test bytes, 23 passed/6 existing warnings in 13.19s. `STATIC-02.json` records changed-file Ruff/format and whitespace exit0. Submodule metadata is unchanged (uninitialized existing pins, no install). `NATIVE-OPENAPI-01.json` is the actual router schema, 20287 bytes, SHA-256 `a9ac87d5a26b51fedca0bcb6297f5e01b271cc468f256b7c8a2d298a203de83c`; `API-CONTRACT-01.json` records exact API/service/test pins and the endpoint/errors/order for original UX. Later plan-only checkpoint changes do not alter the frozen API or tests.
- Reviewer: pending fresh whole-backend Spec/Standards review. This phase is software-only; UI integration, normal publication and actual real research remain unaccepted.
