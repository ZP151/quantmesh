# Iteration0021 — issue207 admission fixture consistency

Date:2026-10-22 Asia/Singapore. [Issue207](https://github.com/ZP151/quantmesh/issues/207),
Refs205. Base24c10df1e37be3c37245c2c959ce0128d3a9f8a5.
Plan: docs/superpowers/plans/2026-10-22-worker-lock-fixture-consistency.md.

## Planner

One action: restore tests of the old admission contract while preserving the
current installation security patch. Main ACKed two test files, one inert lock
fixture and own records. No production gate change. Release owns review2 and one
new-head CI; this leaf self-reviews and runs focused checks only.

## Researcher — actual cause

Exact CI39658707582 passed dependency/license/frontend gates, then reported
5554PASS/12FAIL/143SKIP. Original raw/events remain in canonical
output/0038-orchestration/combined-ci-39658707582; no rerun. R441/L208 excluded.

Both worker_build._pins and seal_image.produce retain SHA
07f4e7ec64805a375e0bdc707d0158fbdb08bd07d02aa569e2d119496b32592a.
The secure current installation lock is
0de42c60394ad96a6a052b1e24a8cb88f14c87f0690b3b1e2467bf857afb7ea6.
Two fixtures copied current bytes into purported historical-admitted inputs.

- Nine worker-build failures: eight positive paths reject. The late_bytes
  negative also requires its late mutation to execute; lock rejection occurs
  earlier, so that reached assertion fails. It must not be removed.
- Two producer failures: raw trace identifies fixed-lock preflight at
  seal_image.py541-542. Publication-race case has no manifest because it never
  passes preflight, not because an ownership cleanup contract changed.
- One registered-profile failure imports the same sealed fixture. No profile
  contract/source modification is needed.

Actual WSL3.12.3 probe imported this worktree's worker_build SHA
8a7e64c19a5c9076b858b429a5a4cad1c763474b5659a00d0e01775c7f97b692.
Old bytes parse81 pins, current bytes refuse. Two actual positives fail and
external-manifest/bad-lock-digest negatives pass:2FAIL/2PASS in6.08s.
Own output/207-worker-lock-fixture/02-minimal-red.json/log preserves exact
argv/import/exit1. Initial01 relative-path probe was a separate pre-test error.

## Implementer

The new inert test fixture is byte-for-byte from aa62 Git blob
3647fd3b4e7b36a74d5ca030ef972cfb370cb189, original path
services/research_agent/requirements.linux-cp312.lock:8047bytes/SHA07f4e7ec.
It intentionally contains historical security pins and MUST NOT be installed or
used as a current runtime certificate. Existing old-admission unit positives
now select this explicit sample rather than the changing install lock.

Two added negatives use real current secure lock bytes. Consumer first proves
the old positive, then independently reseals inventory/manifest and matching
synthetic distribution versions before refusal. Producer recalculates actual
source catalog bytes/hash before refusal and checks no metadata publication.
All previous expectations/negative cases remain intact. No new-runtime positive
is faked, and no production gate/pin is changed.

## Reviewer / verifier

Focused evidence, in own output/207-worker-lock-fixture:

- 02-minimal-red:2FAIL/2PASS in6.08s, authentic old/new lock control included.
- 03-original-and-controls: all twelve original CI failures, two new current-lock
  negatives and two original controls passed16/16 in3.64s.
- 04-three-affected-files:116PASS,0SKIP,0deselected in7.17s; only worker_build,
  worker_image_metadata and worker_registered_profile contract files ran.
- Both GREEN runs printed actual imported worker_build path/SHA and all three
  test hashes. Same existing WSL CPython3.12.3, no GIT_DIR/GIT_COMMON_DIR/
  GIT_WORK_TREE, no diagnostic plugin, new environment or dependency installation.
- Changed-file Ruff/format and whitespace checks pass. Self-review AST comparison
  proves every preexisting test/helper function unchanged apart from the two
  explicit fixture input functions;37 and12 original functions respectively
  retain identical AST, with one new negative per file. Existing late_bytes
  reached assertion, atomic-publication ownership tests and profile native-cache
  refusal remain present and passed.
- Byte comparison confirms production worker_build/seal_image, registered-profile
  test and all four dependency inputs identical to exact24c10df. Historical
  evidence is outside this patch. Legacy fixture equals the original Git blob.

Test SHA256 values: worker_build f82b772948a25ea3ff75f68695c2ec98c61d882690199d8ec8243c7d7506fb69;
worker_image_metadata86a7f4051a39ca5820f88fcfe10e0966198a750dbaafed94d5ab5c75d02c0b4a.
This is a self-reviewed immutable correction, not independent release approval.
Release's single known-correction round2 and new-head CI remain required; no
third structural loop, root suite, dependency scan or deployment occurred here.

## Runtime boundary

Production producer/consumer still refuse the current secure lock. If release
requires a newly admitted runtime, a narrow production pin/registry decision
and matched artifact/image/native proof remain unfinished. This test fixture
does not substitute for them. Historical81 evidence,22-pin policy, install
locks, host state and blocked input205 are unchanged.
