# Agent Collaboration Workflow

## Operating model

QuantMesh uses an issue-driven, role-based workflow. The main agent coordinates scope and integration. Specialist agents may research or implement bounded work in parallel when their file ownership does not overlap.

For multi-session objectives, `/goal` is the durable coordinator. It restores state from `docs/goals/ACTIVE.md`, Git, GitHub and the iteration ledger before choosing the next unblocked slice.

Codex and Claude Code share the tracked plan and recovery protocol in
`docs/agents/cross-agent-execution.md`. Superpowers plans under
`docs/superpowers/` are repository artifacts that either agent may execute.

## Standard sequence

1. **Intake**: Read the GitHub issue, domain context, roadmap and active iteration.
2. **Plan**: Record acceptance criteria, dependencies, risks and verification commands.
3. **Research**: Inspect upstream components and licenses before building equivalent functionality.
4. **Implement**: Deliver one vertical slice behind stable domain interfaces.
5. **Review**: Check correctness, architecture, licensing, data leakage and trading safety.
6. **Verify**: Run tests and record exact results in the iteration file.
7. **Integrate**: Open a PR, resolve feedback and update the roadmap/iteration ledger.

## Handoff contract

Every handoff states:

- Objective and linked issue
- Files changed or owned
- Decisions made and alternatives rejected
- Tests run and observed results
- Known risks or missing evidence
- Recommended next action

## Required checks

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check src tests tools
git diff --check
git submodule status
```

Add domain-specific checks for connectors, replay data, migrations and frontend work as those components land.

## Branch and review policy

- Branch names: `feat/<issue>-<slug>`, `fix/<issue>-<slug>`, `docs/<issue>-<slug>`.
- One PR should close one coherent vertical slice.
- Protected/shared branches are never force-pushed.
- Live-trading changes require a dedicated risk review and paper-mode regression tests.
