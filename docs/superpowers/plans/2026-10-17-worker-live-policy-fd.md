# Worker live-policy FD implementation plan

> Execute the operator-approved specification with one implementer and a fresh
> reviewer; root owns integration, shared documents and release gates.

**Goal:** Verify live kernel policy through manager-opened FD 3 after a narrowly
defined EACCES, preserving all existing admission checks.
**Architecture:** A private descriptor reader inside worker_admission.py uses
fcntl metadata checks, held-directory identity comparison and positional reads.
**Technology:** Existing Python runtime, pytest, Ruff and POSIX descriptor APIs.
**Specification:** ../specs/2026-10-17-worker-live-policy-fd.md.
**Constraints:** No public API/pin/dependency changes, no new environment, no
SSH/SQL/provider/deployment. Keep all existing failure evidence.
**Review focus:** Permission fallback boundary, stale descriptor rejection,
revision races, bounds, ownership, Windows import compatibility and concurrency.

## Task 1: one source and test slice

Files: src/quantmesh/research/worker_admission.py and
tests/test_worker_admission.py.

- [x] Read existing kernel reader, revision checks, test helpers and TDD skill.
- [x] Write behavioral tests for the EACCES success path using real POSIX file
  descriptors, partial reads, virtual size zero and two concurrent callers.
- [x] Add rejection cases for wrong inode, root ownership, regular-file type,
  access flags/O_PATH, absent descriptor, changed named identity/revision,
  overflow/read error, non-EACCES and non-raw_data paths. Keep ordinary reads.
- [x] Run the new selection before source changes with the existing runtime:
  `python -m pytest tests/test_worker_admission.py -k kernel -q`; preserve actual
  command, stdout, stderr and exit status. Use the existing POSIX runtime for
  fcntl/pread evidence; do not install one.
- [x] Implement the smallest private fallback; keep fcntl POSIX-only so module
  import remains compatible on Windows. Do not close inherited FD 3.
- [x] Run the same selection green, then affected admission/runtime tests:
  `python -m pytest tests/test_worker_admission.py tests/test_worker_entry.py
  tests/test_worker_daemon.py -q`.
- [x] Run Ruff check/format on changed files and git diff --check; save hashes,
  counts and command evidence under output/0038-kernel-policy-live-fd-fix/.
- [x] Deliver one handoff, then stop. Root owns commits, push and review.

## Task 2: review and integration

- [x] Root verifies raw evidence, exact source/test hashes and scope.
- [x] Fresh reviewer evaluates specification and code quality, maximum two
  rounds. Any third structural issue returns to Planner for scope reduction.
- [x] Root verifies known fixes, full-repository Ruff, changed-file formatting,
  diff and submodule pins. A full-repository format observation found 199
  unchanged files and zero overlap with this diff; retain that failure rather
  than reformat unrelated code. Run broad tests through the new exact-head CI, not another
  unbounded Windows full run.
- [x] Update six shared status documents with actual evidence and prepare a
  coherent green commit.
- [ ] Normal push and attached draft PR (root release receipt records actual outcome).
- [ ] Dispatch the sole CI observer for the new head; require all required
  terminal checks and no actionable review before one precise Class C question.
- [ ] After actual two-human approval including SafetyOwner, do one fresh
  premerge check, normal match-head squash and complete merged-tree comparison.

## Requirements and operator acceptance

- [x] Ordinary path and 22 pins/public interfaces unchanged.
- [x] FD identity/access/type/owner/bounds/revision/concurrency cases verified.
- [x] No credentials, SQL, model calls, dependencies or host permissions changed.
- [ ] Native acceptance remains pending until merged-source staging with a
  fresh resource forecast, a fresh live profile/revision and actual OpenFile.
- [ ] Full Option A remains incomplete until permanent Worker, production
  recovery, advisory and server OpenD acceptance are actually complete.

## Software checkpoint — 2026-10-17

Runtime SHA256 b501956e01a45c1162adb5517a2aac73229d19285f4639ca8520d438eaf654b1;
test SHA256 ad78a968abcaa4d97b586a75579fccbb0d9df6462e40632d217cf7bfa339f296.
Initial valid RED: one failure at missing EACCES fallback. Final 18 kernel and
94 affected tests pass. Four checked mutants each produce the expected RED;
round2 READY closes R1/R2 with no runtime changes and no third review. Evidence:
output/0038-kernel-policy-live-fd-integration/{handoff-root-checked.json,
review-fix-root-checked.json,review-round1.md,review-round2.md,root-final-2/results.json}.
Native post-fix acceptance and the new exact-head CI/human merge gates remain open.
