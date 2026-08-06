# Durable Goals

`ACTIVE.md` is the resumable state for the current long-running objective. It is deliberately small: details belong in GitHub issues, iteration records, ADRs, commits and PRs.

## Rules

- Keep at most one active goal.
- Update it at meaningful checkpoints, before compaction/handoff and before ending a session.
- Reference primary sources rather than copying their full contents.
- Never include secrets, tokens, private keys or personal account data.
- Append detailed work evidence to the active iteration record.
- When complete, move the final snapshot to `docs/goals/archive/YYYY-MM-DD-<slug>.md` and reset `ACTIVE.md`.

Claude Code starts or resumes work with:

```text
/goal
```

Start or replace it explicitly with:

```text
/goal Advance M2 deterministic paper-trading kernel through issue #1
```

