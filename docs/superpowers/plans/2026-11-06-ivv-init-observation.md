# Fixed IVV Init Observation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox syntax.

**Goal:** Attribute the existing single Init's failure using finite private-safe
facts, then conditionally finish the original same-context IVV capture.

**Architecture:** Extend the existing instance-bound backend and recovery lifecycle,
not SDK globals/files. Use actual pinned SDK method control flow with fake external
seams for offline regression. Preserve source and actual runtime admission separation.

**Tech Stack:** Existing Python stdlib, pytest, pinned moomoo10.10.7008.

**Spec:** docs/superpowers/specs/2026-11-06-ivv-init-observation.md

## Global Constraints

Issue281; data/math/window/costs fixed, livefalse; zero new SDK requests in tests;
no credentials/log/XML/pane/payload inspection; no retry/timeout/close/admission
change; all old holds/failures/UNKNOWN preserved. Source15/common98MiB and P27 are
capacity, not execution GO. Independent agent review follows actual standing proxy
authority, never a fabricated human review. At most one consolidated correction.

## Review Focus

- A brief READY followed by disconnect must retain ever-ready and final CLOSED.
- An unknown enum/foreign request cannot be silently called a known failure.
- SDK send/unpack return objects and raised exceptions must retain their semantics.
- Another backend/context must not share or overwrite observed request state.
- Canary msg/payload/key/account data must never enter retained trace or output.

## Task 1 — one bounded Source slice

Files: modify tools/research/capture_opend_ivv_daily.py and only the finite lifecycle
contract/selector in tools/research/ivv_trusted_runner.py; create
tests/test_ivv_init_observation.py; update only directly impacted lifecycle tests
if their exact contract now includes the finite observation. Update active
docs/iterations/0038-ivv-transaction-recovery.md with visible role/test evidence.

Consumes the real recovery lifecycle, backend open and wire guard; produces an
optional recovery-only finite Init observation attached to that existing lifecycle.
Choose explicit closed field/enumeration names in the implementation and document
them in the test/spec checkpoint. Do not create a generic observation platform.

- [x] Write one causal test at the agreed backend/lifecycle seam; preserve RED.
- [x] Add minimal instance-bound observation, preserve GREEN, then expand the other
  source-accurate failure and concurrency/privacy cases one red/green step at a time.
- [x] Run focused Init/lifecycle/capture/contract regressions; no real SDK import/
  network context, no DuckDB suite or new environment. Use one serial12MiB Common
  scratch and4MiB failed-history reserve, maxfail1/per-test passing cleanup; retain
  every failed fixture and census before another connected run. Ruff/whitespace gate.
- [x] Record role outputs, exact commands, source hashes, all-retained Source census;
  create one green checkpoint commit and self-review. Stop for Parent review.

## Task 2 — Parent review and ordinary release

- [x] Independently verify focused checks and exact candidate source/transport bounds.
- [x] Obtain narrow independent Spec/Standards R1; one consolidated R2 if necessary.
- [x] Open issue281 PR, complete ordinary matching-head required CI, qualify exact-lock
  release bundle, recheck head/base/review threads, normal expected-head squash merge.
- [x] Build/verify one complete merged catalog and private operations publication;
  preserve all old carriers/releases. No admin bypass or quota-paid bot rerun.

## Task 3 — one conditional actual effect

- [x] Bind fresh batch02/current policy, connection7, changed method and full capacity.
  Preserve old expired batch/permits and cumulative UNKNOWN.
- [x] Verify actual current source/provider/config/kernel/namespace/normal-closed
  predecessor/free/memory; no new login/service action or health SDK.
- [x] Sole Parent executor submits once; READY continues original seven fixed calls.
  Failure stops with new finite evidence, never an automatic same-method retry.
- [x] If complete, submit immutable originals for independent H1/H2/H3 acceptance;
  otherwise return the specific remaining gap to Planner. No unsupported computation.

Actual outcome: PR290/CI564 and publication completed; connection7 stopped with
Init sendOK/ReqInfoTimeout/unpackUNOBSERVED/neverREADY. Separate owned close is
proved and the gap returned to Planner. These checkmarks complete the bounded
implementation and conditional failure path, not capture or input acceptance.
Batch02 is SPENT; no retry or numerical grant follows.

Preflight conflict scan: Task1 code emits the same lifecycle Task2 publishes and
Task3 consumes; no second source writer or alternate schema. Task1 tests use pinned
source through existing installed package files, not live SDK imports. Task2 changes
release provenance only; it cannot waive Task3 admission. Task3 makes exactly one
new context in fresh batch02; old six history/holds remain. No file/interface conflict.

## CI release-binding correction

PR290 final head97907ca failed actual CI563 with three DEV_NATIVE_SOURCE_PIN
bootstrap failures; 7941 other tests passed. The issuer's fixed helper hash still
named the pre-observation helper. Planner explicitly classified its correction
as release closure, not another runtime structural patch or a new authority.

Only tools/research/ivv_dev_diagnostic.py::_CAPTURE_HELPER_SHA256 may change to
the actual independently reviewed helper Git-blob SHA21a45576166e4edc0affee01401bc015f06def22b298ec8f1675a82927b3e960.
Keep the literal pin and every origin, held-byte, close and admission check.
Do not change tests to accept different bytes or alter the reviewed runtime.
The three actual bootstrap entrances have retained causal RED originals.

Run their GREENs and one union of the affected issuer/native/runner and prior
285 checks, with the serial scratch and failed-history bounds. Original two
readers verify only this constant-only delta, unchanged reviewed runtime and
actual final pins. Retain all prior R1/R2 and failed CI evidence. A new final
head requires normal full CI and exact-lock qualification; successor manifests,
catalog and actual wire must use its new issuer hash, never old qualification.
Any new runtime structure change returns to Planner before patching.
