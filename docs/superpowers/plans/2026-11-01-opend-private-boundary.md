# Complete c8 private boundary implementation plan

> **For agentic workers:** Use superpowers:executing-plans for this single inline
> slice. Parent assigns fresh whole-slice review; no implementer delegation.

**Goal:** Bind c8 to the already-proven private/off/full-RO vector.
**Architecture:** Atomically change the c8 drop-in and launcher exact manager
properties/pin; reuse KernelWorld and existing recovery lifecycle seams.
**Tech Stack:** Existing Python stdlib, pytest and systemd255 configuration.
**Spec:** [approved contract](../specs/2026-11-01-opend-private-boundary.md).

## Global constraints

Six RW/two RO/common reset order, guard/recovery/base/observer, image/claim/ALIAS,
nonce/schema4, identities, eight flags and resource caps remain fixed. No host,
native/auth/UI/SDK, dependency, CI change, source variant or evidence deletion.
Root selects affected/static gates instead of unrelated broad local replay.
Source16MiB includes old evidence and ONE previously charged4MiB margin;
N24MiB/remote72MiB/ops8MiB remain unchanged. Stop before push/PR for Parent review.

## Review focus

- RO parents can hide writable children and a generated pressure entrance.
- Private blocks later topology propagation, not same-inode socket/file sharing.
- Missing POOL self-record must not hide loss of fs/lower/ALIAS/claim protection.
- Either empty bind directive clears the common list; exact six/two must survive.
- Invalid manager properties deny before child/consume; actual nested CG works.

## Task1: one atomic runtime/test/docs slice

Files: c8 private-storage.conf, stage_console.py, test_opend_private_storage.py,
test_opend_same_unit_recovery.py, spec/plan, ADR0032, storage iteration and roadmap.
Interface: pinned drop-in bytes -> c8 exact manager properties -> existing gates.

- [x] Write exact config/full-vector and private/off/fullRO manager expectations;
  checkpoint test-only diff while production bytes remain actual0620.
- [x] Run selected config/manager cases, retaining genuine RED and setup failures
  separately before runtime changes.
- [x] Apply only private/off/RO append and manager expectations/mechanical hash.
- [x] Add independent KernelWorld cases for four classes, pressure, normalization,
  hidden mounts, later propagation and six positives; preserve original oracle.
- [x] Run targeted two files and affected fixture file; scoped Ruff/format,
  Python3.12 syntax, whitespace/submodule and frozen-runtime hash checks.
- [x] Record roles, proof/deployment distinction and lifecycle in iteration,
  ADR/roadmap; preserve all historical outcomes.
- [x] Commit coherent GREEN, retain exact BASE/HEAD/tree, full -U10 diff and
  complete evidence/allocation forecast. Parent assigns fresh R1/maxknown-fixR2.

## Release boundary

No backend/login acceptance follows. After review and actual publication/catalog,
Parent rebinds the finite formal transaction: admitted Source and normal actor
close, then fresh gates and at most original fourth start, backend/socket and a
fresh visible private-window gate. SDK remains0.

## Observed software verification

Old-runtime RED:3failed/23passed/217deselected; config/manager GREEN26passed.
Targeted two files256passed; final affected three files294passed (overlapping
counts). Scoped Ruff check/format, Python3.12 in-memory syntax, diff/submodule
checks pass. One initial E501 lint result is retained separately from product RED.
Exact commands/raw/pins and final commit/diff live in private-boundary-repair-01.
Fresh independent review/CI/publication/runtime remain pending; stop before push.
