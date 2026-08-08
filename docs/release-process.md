# Release process

M10 Phase D (issue #61). How a milestone slice moves from a branch to
main, and the checklist that governs any future move from *paper* to
*live*. Written down so the process is executable by the next session
without tribal knowledge.

## Branch and PR conventions (the solo fast lane)

- Use one short-lived branch per coherent release or architecture slice,
  always created from `origin/main`. Do not stack branches by default; stacking
  is reserved for a documented dependency that cannot be delivered safely in
  one slice.
- Group related implementation, tests and records in the same PR. Do not create
  an issue or PR for every checkbox; create an issue only when durable external
  tracking or independent pickup is useful.
- Checkpoint commits are tested and intentionally scoped. Push the branch when
  a checkpoint needs remote durability or CI evidence.
- Open one PR when its acceptance criteria and proportional verification are
  complete. `main` is protected and merges are squash merges.
- After a squash merge, branch future work from `origin/main` and reconcile
  local `main` by fast-forward only; never force a divergent local history over
  the remote.
- Current state lives in `docs/goals/ACTIVE.md`; detailed work and evidence live
  in the active iteration document. Durable architectural decisions live in
  ADRs under `docs/adr/`.

## The full-suite gate (every phase, before the checkpoint push)

```text
pytest -q                    # full suite, must stay green
ruff check src tests         # E/F/I/UP @ 100 cols
git diff --check             # no whitespace errors
git submodule status         # clean (vendored components pinned)
```

Clean-checkout baseline on 2026-08-08: 1,790 passed / 0 skipped with the
`.[dev,research,e2e]` extras and Chromium available. A release checkpoint must
record its own current count; do not copy this historical number as proof.

## Drill evidence requirements

Every acceptance criterion that promises operator-facing behavior is
proven twice: by unit tests (the behavior) and by a drill (the
operator path). Drills live as test classes named after the
criterion (e.g. `TestKillSwitchEnforcement`, the keyboard-only E2E
drill) or as CLI fixtures. A milestone PR lists the drill evidence in
its body; the iteration document's Verification evidence section
records counts, dates and any debugging detours.

## Dependency changes

- Adding or removing a dependency touches: `pyproject.toml` (the
  extra/constraint), `requirements-audit.txt` (the frozen install
  closure the CI security job audits), `docs/licenses.md` (the
  inventory) — and, when the change is a removal, ADR-0009-style
  dependency-contract decisions.
- Regenerate the audit lock after any dependency change:

  ```text
  python -m pip install --dry-run --ignore-installed -e ".[dev,research]" \
      --report audit-report.json
  # then convert the report's install set (name==version) to
  # requirements-audit.txt, excluding quantmesh itself.
  ```

  `pip-audit` in CI checks the pinned file (`--no-deps`, no
  re-resolution); the license review classifies the installed
  environment.
- A license outside the allowlist (docs/licenses.md) or a
  Commons-Clause-style source-available restriction fails the
  `security` CI job. Removing the dependency is the preferred
  resolution — the vectorbt removal (ADR-0012 decision 4) is the
  precedent; a kept dependency would need an ADR-level decision.

## Versioning

Roadmap milestone identifiers are delivery-history labels, not package
versions. The first operator-facing product release line is `0.1.x`:

- release-candidate package metadata uses the PEP 440 form `0.1.0rcN`;
- the corresponding Git tag uses the readable form `v0.1.0-rcN`;
- operator acceptance promotes the same verified line to package version
  `0.1.0` and tag `v0.1.0`;
- later compatible fixes increment the patch; a deliberately incompatible
  product release increments the minor.

Tags are created only from a verified main commit. The version string lives in
`pyproject.toml` and `quantmesh/__init__.py`; they must agree, and the package
data test pins that invariant. Release notes must identify the commit, install
extras, verification counts, known limitations and external gates.

## The human gate checklist (live operation — THE gate)

The following are **forbidden without explicit human approval**, and
no M10 code path can perform them at all:

- Real-money trading / live broker orders
- Wallet signing / private-key use
- Credentials (real secrets, any venue)
- Paid infrastructure
- AI order authority

Before any of these can ever be enabled, all of the following must
hold (this is the Phase E enablement workflow, recorded in ADR-0012
decision 5, iteration 0012 and ACTIVE.md):

1. The per-venue enablement state machine exists and refuses any
   transition to `enabled` without an approval record naming who,
   when, and which gate text was presented (fixture-tested).
2. The secret-store integration is keyring-backed and was exercised
   only against fixtures in tests.
3. The kill switches (global + per-venue, enforced in the accounting
   risk gate) are verified by the E2E drill.
4. The threat model (`docs/threat-model.md`) is reviewed and the CI
   security job is green.
5. The operator drills a full dry run on the venue's testnet with
   evidence recorded in the milestone iteration document (the M4/M5
   drill gates are the precedent).
6. A human approval record exists in the enablement journal with the
   verbatim gate text from ACTIVE.md.

When a milestone reaches such a gate, complete every safe deliverable
and record the exact gate, then proceed to the next safe unblocked
roadmap work — the gate is a checkpoint, not a stop condition.
