# OpenD invocation witness implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans, inline implementation only after Parent's independent targeted design check. Parent assigns fresh Spec/Quality R1, maximum one known-fixR2. No implementation yet.

**Goal:** Retain a bounded invocation-bound pane/owned-child stage and exit witness without changing release authority.
**Architecture:** Inline fixed writer/reader in the already pinned launcher, fixed preallocated runtime file, reuse existing child report pipe and owned process/reap/cleanup. No new runtime dependency or observer.
**Tech Stack:** Existing Python3.12 stdlib/POSIX interfaces and pytest.
**Spec:** [one-page design](../specs/2026-11-01-opend-invocation-witness.md).

## Global constraints

No host/Source execution, fifth start, marker/claim reset, SDK/UI, environment/dependency, guard/recovery/drop-in/base/resource/permission/2s-gate change. Existing generic retries USED2/remaining0. Source32MiB includes all checkout/admin/shared Git/history and finite future; N24MiB/remote72/ops8 remain retained. Current schema4 consumed marker blocks any new diagnostic run, independent of software completion.

## Review focus

- Early pane admission can fail before current protected try: no authority from a diagnostic header.
- ACK/EOF/40/41 collision cannot establish exec; missing/fragmented/stale input stays UNKNOWN.
- ENOSPC/partial writes/final flush failures cannot obscure primary error or orphan child/FD.
- Registration interruption and cleanup-sent signal differ from an unsolicited vendor exit.
- Independent pin/catalog integration must not dynamically load an unpinned witness module.

## Task1 — one coherent diagnostic-only source/test/docs slice

Files: modify deploy/aws/opend/stage_console.py; create tests/test_opend_invocation_witness.py; affected tests/test_opend_same_unit_recovery.py and existing owned-fixture tests as required by direct interface changes. Update this spec/plan, ADR0032 and active storage iteration; no fixture-native run.

Interface: fixed runtime/invocation-witness, schema1 header and bounded slots; source/control/invocation/owned-PID binding; closed stage/result enums. Parent persists events, child only fixed report frames. No public grant/schema change.

- [x] Parent independently checks design, especially early binding, report-CLOEXEC and primary-error precedence. Stop if it requires expanded actor/recovery scope.
- [x] Add tests and retain actual old-source RED before runtime edits: all stage branches; early refusal; source/control/invocation/PID mismatches; absent/full/truncated/stale files and short writes; total32768/48writes/24576 limit; preallocation ENOSPC; no private sentinel in bytes/errors.
- [x] Add child lifecycle RED: gate timeout/parent mismatch, chdir/exec exceptions with real numeric errno, ACK and EOF unknown, genuine vendor40/41 collision, observed vendor inode positive versus unobserved short-lived UNKNOWN, registration interruption, TERM/KILL provenance, waitpid exit/signal and primary-error preservation/FD closure. Use owned synthetic subprocesses only where existing tests already permit, never original Source CLI/native host.
- [x] Implement only inline fixed diagnostic functions and instrumentation at existing stages; preserve admit/consume clocks/order,2s wait and owned cleanup. Add no persistent-loop event or new file destination.
- [x] Run new focused tests, directly affected recovery/owned lifecycle tests and scoped Ruff/format/Python3.12 syntax/diff/submodule checks. Record exact commands, RED/GREEN, harness failures and runtime frozen-pin deltas separately. Broader normal CI is Parent-owned after fresh review.
- [x] Record Planner/Quant/Implementer/Reviewer/Verifier outputs and coherent GREEN commit; one full -U10 diff + pin/physical forecast index. Stop before push/PR for Parent's fresh R1/maxknown-fixR2; no self-READY.

## Release / execution boundary

Parent owns exact-head CI, normal merge/full-tree catalog. Source/recovery/drop-in pins are explicit: only launcher changes; no new module import. A future run remains BLOCKED on the existing consumed fixed-nonce marker and needs a separate selected protocol/disposition. No code/test/CI result grants a fifth start, market/SDK or private-window acceptance.

## Current checkpoint

Design-only, no production/test edit or execution. Fresh origin/main e2eab51d7476f8e741f2ce2998294a8743ea06c1/tree9e04c35450ba72aacb5e804ce4c4cfa7bf0d41e6; branch codex/0038-opend-invocation-witness preserves old feature/localmain. Issue263 open ready-for-agent; current open PR list empty. Physical prewrite actual18102464, whole32MiB forecast33443768 including shared Git and all finite future. Evidence under ignored output/opend-visible-mount-nearest-ancestor-20261031/invocation-witness-01.

## Targeted design ruling

Original design NOT_READY; four Parent resolutions in spec are binding. Tests must include pre-ACK zero FS writes, child inherited witness FD closure, all seven failure enums/fragment collision, write-once checksum prefix/terminal completeness and fsync-not-inferred, early c8/schema4 binding and old mode bypass. Implementation is now authorized offline, not native.

## Current verification and handoff

COMMIT-AFFECTED:234passed/42skipped in5.60s, directly affected witness/recovery/staging/persistent files only; the six new POSIX synthetic child cases and36 prior POSIX-dependent cases are Windows skips, not native qualification. New witness file has48passed/6skipped. Scoped Ruff/format, Python3.12 in-memory compile, whitespace and unchanged submodule pins pass. Current code supersedes interim215/231/232/233 results; no old guard/private-fixture294/candidate/native/frontend replay. Preserved REDs include absent API14fail/9fixture-errors, privacy unknown-field1fail, gate-write-asACK/error metadata2fail, pre-fork invented exit0, report retention after reap (separate Windows WNOHANG model setup failure), and original cgroup gate before witness creation. Parent performs fresh whole-slice R1/maxoneknown-fixR2; no self-READY, push, CI or native effect.
