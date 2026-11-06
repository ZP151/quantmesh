# Reference Init delegate return implementation plan

> For agentic workers: use the repository subagent implementation/review lifecycle.

**Goal:** Preserve one existing Init delegate return classification through a
versioned diagnostic terminal, without changing SDK behavior or admission.
**Architecture:** Extend the current reference backend and closed selectors;
adapt a new immutable private Ops successor, retaining all old publications.
**Tech stack:** Existing Python313/pytest9.1.1, existing Linux environment and
Ruff; SDK10.10.7008 public source for offline function-level contract evidence.
**Spec:** docs/superpowers/specs/2026-11-07-reference-init-return.md.

## Global constraints

Issue293; no SDK/host/network effect from implementation or tests. No new
environment/install. Original default capture and all safety predicates stay.
Only exact int0/int-1 classify OK/NON_OK; UNKNOWN otherwise. No raw payload or
message/exception text. New v2 emission; historical v1 remains closed. Parent
owns shared docs/private Ops/publication; Implementer owns bounded core/tests.

## Review focus

- Exact one delegate, same return object and exception, including bool/subclass.
- Frozen SDK function path proves both OK→NOT_READY and official NON_OK.
- Version confusion/extra keys/invalid enum refuse without changing READY.
- Parent closure, manager1/client1, standalone failure codec and bootstrap ABI.
- Actual new carrier/status/header/frame/IPC geometry and old capture identity.

## One vertical slice

Files: tools/research/capture_opend_ivv_daily.py (reference backend/terminal),
tools/research/ivv_trusted_runner.py (reference selector/result),
tests/test_ivv_reference_init_return.py and affected reference tests. Parent
owns versioned private Ops outside Git plus this plan/iteration/ADR checkpoint.

- [x] Write targeted failing cases for the real existing override and frozen
  SDK return path, identity/exception/unknown and strict v1/v2 propagation.
- [x] Run only those targets first; retain actual RED command, log and rc.
- [x] Add the scalar and inline closed-schema dispatch in existing selectors;
  do not introduce a new failure-codec dependency or optional SDK hook.
- [x] Run the same targets GREEN, then the affected reference/default-capture/
  conditional/IPC/bootstrap closure, preserving earlier failures.
- [x] Parent adapts a new private Ops successor; test actual versioned STOP
  roundtrip and maximum geometry without executing a real carrier.
- [ ] Freeze one coherent commit and exact source/evidence pins; independent
  Spec/Standards narrow review (maximum two rounds), relevant broad gates and
  normal matching-head CI. No healthy cancellation or stale-base duplicate CI.
- [ ] Guarded normal merge, actual source publication and merged geometry.
- [ ] Only then prepare one different-method diagnostic with new immutable
  data/once/capacity/Fresh, preserving old negative pair and UNKNOWN usage.

Targeted first command: existing Python313 -I -B -X utf8 -m pytest
tests/test_ivv_reference_init_return.py -q. Full release uses the repository's
normal CI/release gate; no reduced collection or changed success semantics.

Checkpoint: source-reviewed core5db43c29; exact runtime7 bytes remain unchanged
through the final evidence-only checkpoint. Both R1 reports READY; normal CI,
merge/publication and any actual different-method diagnostic remain pending.
