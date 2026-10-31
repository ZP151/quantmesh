# Visible mount nearest-ancestor Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for this one bounded task; Parent assigns fresh reviewer afterward.

**Goal:** Remove the hidden-old-child false visibility denial without weakening true ambiguity or writable-escape rejection.
**Architecture:** Retain the existing parser and same-target parent-chain selection; select the deepest already-visible proper pathname parent once per target group and compare its actual mount ID to each candidate ancestry. Unknown nonroot parent relationships deny.
**Tech Stack:** Existing Python stdlib, pytest, Ruff; no installation.
**Spec:** [selected correction](../specs/2026-10-31-opend-visible-mount-nearest-ancestor.md).

## Global constraints

Original Source/profile/claim/six-write/resource gates remain. No host call, new image/control/nonce, Source import on Stage, SDK/UI or fourth original-unit start. Dedicated local8MiB fullhold; sparse checkout shares existing objects. Stop before push/PR.

## Review focus

Proper pathname component boundaries; root outside-parent exception; missing/cyclic nonroot parent refusal; same-parent sibling ambiguity; legitimate same-target stacks and visible RW child denial.

## Task1 — visibility correction

Files: deploy/aws/opend/private_storage.py; tests/test_opend_private_storage.py; mechanical pins in stage_console.py and private_storage_fixture.py; this spec/plan and active iteration.

- [x] Add independently expected captured-topology tests with public synthetic paths, reversed/arbitrary IDs and reversed rows, hidden-only child, true siblings, valid stack, path boundary, root/missing parent/cycle and new visible writable child.
- [x] Run `python -B -m pytest -q tests/test_opend_private_storage.py` on unchanged guard. Expected: captured topology/hidden child and missing-parent regressions fail, existing direct controls pass. Retain raw RED; commit test/docs checkpoint before guard changes.
- [x] Apply only the nearest selected proper-prefix invariant inside `_visible_mounts`; preserve all other guard functions. Update only both exact guard SHA literals.
- [x] Run the direct file GREEN, then directly affected storage/fixture/recovery/console tests and changed-file Ruff/format/compile/diff. Record counts/RC and exact imported paths. Do not run unrelated full suite/native/old313 replay.
- [x] Update iteration and raw pin/forecast/handoff; commit coherent green slice. Parent reviews fresh, max R1/known-fixR2, and owns later exact-head CI/publication.

No shared task interfaces; unchanged public function signatures. Operator acceptance remains later merged Source/native/original backend/private window, not inferred from software tests.
