# Executable Named-Object Origin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Parent owns reviews/Git; no subagents.

**Goal:** Allow ordinary recovery to continue only after a complete equivalent executable-origin proof, with auditable normal/failure evidence.

**Architecture:** Preserve original lazy guard; recovery-only false executable predicate invokes one bounded simultaneous-held proof. Reuse protected/stamps/close, runtime/SESSION, authenticated channel and existing kernel-close/STOP.

**Tech Stack:** Existing Python stdlib, pytest/Ruff. No dependencies.

**Spec:** ../specs/2026-11-05-ivv-executable-identity.md

## Global constraints

No host/SDK/carrier/Git/CI action by worker; old source/ops/evidence immutable. No new unit/mode or isolation weakening. Named RO mandatory; kernel mount RO observational, O_PATH only/no kernel bytes. Registered capacity09 raises the complete Server hold to8388608B (8MiB), including all retained failures and the prior524288B future. Parent approved complete forecast7565312B; the freeze census must remain within this hold. Current protected operator policy is selected dynamically (P12 at this implementation), not compiled into authority or identity. Record growth before any overflow.

## Review focus

- Do not hash either role before its metadata/object-role binding succeeds.
- Partial construction/read/close failure preserves primary refusal and exact owner.
- Stateful original truth/exception semantics stay exact.
- Positive child witness must pass actual authenticated parent/catalog/ns binding.
- SESSION and kernel-close aggregation cannot silently lose provenance or relax normal seal.

## Task: one complete proof/evidence slice

Files: tools/research/ivv_trusted_runner.py; tests/test_ivv_executable_identity.py plus necessary old evidence fixture updates; these spec/plan and ADR0042 addendum. Private operations-03 complete successor if pure codec dependency changes; server/executable-identity-01 logs/tests/report.

Interfaces: _prove_executable_identity(expected_sha256,namespace) returns finite proof outcome, never private bytes; select_executable_origin(value) and select_executable_identity_failure(value) validate closed records. _runtime signature unchanged, optional executable_origin return witness only recovery; existing ready/observe packets require that witness for new recovery source; _supervise seals initial/last/checks in existing kernel-close. Existing origin selector includes optional finite failure proof.

- [x] RED: actual proof/runtime negatives and positive, kernel-no-read ordering, cleanup and strict evidence tests against old source. Preserve failing log.
- [x] GREEN: implement only closed proof and existing-entry binding; preserve old-family behavior.
- [x] RED/GREEN: actual authenticated ready/observe/parent-close witness and failure IPC/ops source extraction, not disconnected helpers; no carrier build.
- [x] Run affected source/ops tests once coherent, scoped Ruff/format/whitespace; keep failures/cacheoff/failed-only temp retention.
- [x] Freeze pins/diff/geometry/census/report. Parent reviews/commits/normal CI and decides actual ordinary invocation. No native success claim.

Test invocation: existing Python313 absolute executable, -I -B -X utf8 stdin, explicit checkout/src and tests sys.path, PYTEST_DISABLE_PLUGIN_AUTOLOAD=1, pytest -q -p no:cacheprovider -o tmp_path_retention_policy=failed and unique owned basetemp under server/executable-identity-01. Full commands recorded with results.

Implementation evidence: RED-02 observed30 failing new-path cases with2 legacy passes; SEAM-RED-01 observed3 real producer/IPC gaps with37 passes. CLOSURE-RED-02 observed the extracted-codec missing dependency while both real normal consumers passed. TRACE-RED-01 isolated reused-exception metadata before its fix. AFFECTED-01 passed283 tests/61.35s; after the final owned-metadata change, FINAL-01 passed166 focused tests/10.08s. Logs, exact commands, finite geometry, file pins and complete census live under the owned executable-identity-01 handoff. No native invocation or carrier build occurred.
