# Issue207 correction — explicit legacy admission fixture

Base: exactcombined24c10df1e37be3c37245c2c959ce0128d3a9f8a5,
treef812ca862e3cbfc8efbd67f9aa094b16e1724e61. Managed worktree/branch
codex/207-worker-lock-fixture-consistency. Tracking: issue207, Refs205.

## Goal, cause and scope

Restore tests of the existing fixed historical Worker admission contract after
the separate installation-lock security update. Two fixtures read the current
installation lock, SHA0de42c60, while both production gates still require exact
historical07f4e7ec. CI39658707582 consequently fails nine worker-build cases,
two producer cases and one registered-profile case reusing sealed. Do not change
trust gates or represent a new runtime as admitted.

Main ACKed only tests/test_worker_build.py; tests/test_worker_image_metadata.py;
tests/fixtures/worker-admission/linux-cp312-legacy.lock; this plan and
docs/iterations/0021-worker-lock-fixture-consistency.md. One implementation seat.
No production/policy/registry/lock/frontend/Git identity/history changes, installs,
new environment/Goal, push, CI, SSH or host operation.

## Bounded steps

- [x] Read original traces and exact source. Authentic old/new lock control:
  old parses81 pins, new refuses. Consumer/producer positives fail and two
  existing security negatives pass (2FAIL/2PASS). Initial relative-path probe
  failed before pytest; preserve it separately, never count as behavioral RED.
- [x] Extract exact aa62faeddd84c31887e43bf0dae532e649a4ecbe Git blob
  3647fd3b4e7b36a74d5ca030ef972cfb370cb189 into inert test data. Verify
  8047bytes/SHA07f4e7ec and byte equality; never install this historical fixture.
- [x] Select that explicit fixture in both old-contract tests. Keep every old
  assertion/negative. Add consumer/producer current-secure-lock negatives that
  independently reseal metadata/catalog and still refuse the unchanged pin.
- [x] Run twelve original failed nodes plus new negatives and two original
  controls on actual imports, with no global Git overrides. Then run only the
  three affected contract files as the focused gate, not root/old CI.
- [x] Self-review exact diff, fixture provenance and unchanged production/locks/
  pins/history; changed-file Ruff/format/whitespace. Commit one immutable
  checkpoint for release's known-correction round2 and exact new-head CI.

## Remaining acceptance

This fixes old-admission unit fixture consistency only. No new-lock producer or
admission positive is claimed. A newly deployed runtime still needs separately
reviewed production pin/registry changes and matched wheel/RECORD/metadata/image/
native proof. Old81 evidence stays intact.205/R441/L208 remain independent.
