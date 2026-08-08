# Release process

M10 Phase D (issue #61). How a milestone slice moves from a branch to
main, and the checklist that governs any future move from *paper* to
*live*. Written down so the process is executable by the next session
without tribal knowledge.

## Branch and PR conventions (the solo fast lane)

- One integration branch per milestone: `feat/m<M>-<name>`, branched
  from the previous milestone's tip, stacked behind the previous
  milestone's PR until it merges.
- One tested and reviewed commit per issue (`M<M>-<N> (#issue):
  <summary>`), plus a records commit per phase (`ADR-00NN decision K
  and Phase X evidence`) when the phase closes ADRs/iteration/state.
  Every commit carries `Co-Authored-By: Claude <noreply@anthropic.com>`.
- Every checkpoint is pushed (`git push origin feat/...`).
- One final milestone PR: base = the previous milestone branch, body
  lists the closed issues (`Closes #x #y #z`), opened only after the
  milestone's acceptance criteria **and** operator-validation
  evidence are complete.
- Issues close only when their commits land in the merged milestone
  PR. `main` is protected; merges are squash merges.
- Milestone state lives in `docs/goals/ACTIVE.md` (last checkpoint,
  frontier, resume instructions) and the milestone's iteration
  document (`docs/iterations/00NN-...md`); durable decisions live in
  ADRs under `docs/adr/`.

## The full-suite gate (every phase, before the checkpoint push)

```text
pytest -q                    # full suite, must stay green
ruff check src tests         # E/F/I/UP @ 100 cols
git diff --check             # no whitespace errors
git submodule status         # clean (vendored components pinned)
```

The suite currently: 1725 passed / 3 skipped (symlink creation not
permitted on Windows — the lake's symlink tests run only on Linux CI),
1 pre-existing warning, 15 Playwright E2E tests (skip cleanly when the
`e2e` extra or chromium is missing — ADR-0011 decision 7).

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

`quantmesh 0.x` follows the project milestone structure: a milestone
PR merge bumps the minor (M3 → 0.3, M4 → 0.4, ...); patch bumps fix
issues on main without a milestone. Versions are tags on main
(`v0.M.n`); the version string lives in `pyproject.toml` and
`quantmesh/__init__.py` (they must agree — the package data test
pins it).

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
