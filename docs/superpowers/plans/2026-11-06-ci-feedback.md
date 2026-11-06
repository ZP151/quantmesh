# CI Feedback Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans and test-driven-development. Parent supplies independent review after the complete local slice.

**Goal:** Return early contract failures and precise retained release failure evidence.

**Architecture:** Extend existing quality/release commands and pytest plugin. One
fixed contract selection and one bounded subprocess event stream reuse current
ownership and artifact infrastructure.

**Tech Stack:** Existing Python/pytest/stdlib and Git, current CI moomoo extra.

**Spec:** ../specs/2026-11-06-ci-feedback.md

## Constraints and review focus

Issue292, no runtime7 changes, provider effects, new dependencies, required-role
changes or broad local suite. Keep failed originals and P33 capacities. Exact
collection, source drift, phase errors, teardown and subprocess artifact isolation
are acceptance boundaries. Parent owns push/PR/CI/review/merge. Existing isolated
branch is already selected. No extra worktree or cleanup of earlier evidence.

## One complete slice

Own tools/{quality_gate,release_gate,ci_profile_plugin}.py, their direct tests,
tests/test_ci_release_contract.py, .github/workflows/ci.yml and minimal usage docs.
The contract command produces pytest arguments consumed by the plugin. The
release executor supplies unique event/log paths to that plugin. Static closure
tests consume only actual public source and owning constants.

- [x] Add selection/required-target, source drift and first-failure phase regressions.
- [x] Run focused pytest for those new tests and preserve causal RED logs.
- [x] Implement contract selection/collection check, exact source closure, early
  workflow step and normal release --maxfail=1. Preserve existing profile exports.
- [x] Implement bounded JSONL collection/progress/first-failure/session evidence
  with safe identities and visible diagnostic failure. Verify setup/call/teardown
  and all-pass subprocess cases, plus normal release later-step continuation.
- [x] Run focused GREEN once the implementation matches its regression cases.
- [x] Run named contract locally. Check only the known WSL interpreter's existing
  package availability. Record unsupported Linux closure without installing.
- [x] Run one deduplicated affected union of contract and the three gate test
  modules using serial owned scratch. Preserve failures and clean passing scratch.
- [x] Ruff changed files/full materialized source, format, whitespace, canonical
  Git-byte/source7 proof, iteration evidence and one coherent local commit.
- [ ] Parent independent Spec/Standards review and ordinary final-head CI.

Commands use the existing Python313 with -B, disabled cache/bytecode/autoload,
checkout/src import path, --maxfail=1 and unique external scratch. Expected RED
is the missing behavior, expected GREEN is all selected tests passing. Evidence
lives in the registered recovery integration/ci-feedback-20261106-01 directory.
The task-specific ledger uses this same directory to preserve capacity and all
failures. This explicit task location overrides skill scratch/deletion defaults.

## Verification outcome and remaining boundary

The named production selection remains all12 modules/650 nodes. The authorized
local affected execution was segmented after environment failures: software602
passed; Windows direct Python86PASS/1SKIP; clean Linux portfolio45PASS/3SKIP.
The unchanged optional frontend node timed out on Windows and has no installed
Linux native dependency closure. Full Linux contract/plugin qualification and
combined net timing are pending normal CI. Preserve the original failed named
runs and affected runs; these segmented results do not turn them green.

The coordinate-translation run was interrupted on authority withdrawal; its
partial74/135 event trace is not a validation verdict. Buffered terminal stdout
was never materialized and /tmp scratch later became unavailable. Parent closed
the native index semantic check and released the temporary commit hold. No
metadata-history claim or unknown-peak capacity refund follows. Further local
checks used native Windows Git and the clean original Linux portfolio entry.
See the iteration checkpoint and the external handoff for exact originals.
