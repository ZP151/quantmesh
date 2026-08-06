# Iteration 0004 — Engineering Agent Skills and Durable Goal Command

- Status: completed
- Started: 2026-08-07
- Completed: 2026-08-07
- Owner: ZP151 + Codex
- GitHub issue: direct environment request
- Pull request: direct repository setup
- Roadmap milestone: M1 maintenance

## Outcome

Equip Codex and Claude Code with project-scoped engineering Agent Skills and a durable `/goal` command that reconstructs project state from Git, GitHub and versioned documents.

## Delivered

- Twelve engineering Agent Skills installed for both Codex and Claude
- Claude Code `/goal` command and Codex goal prompt
- Versioned active-goal state and archive convention
- Git/GitHub reconstruction, safe branching, TDD, review and handoff loop
- Wayfinder labels and issue-tracker operations

## Decisions

- Repository and issue history are primary sources; chat history is never sufficient state.
- Long-running implementation stops at review, credential, destructive-action and live-trading gates.
- Each issue remains a bounded branch/PR even when the broader goal spans many sessions.

## Verification evidence

```text
pytest -q: 3 passed, 1 dependency deprecation warning
ruff check src tests: all checks passed
git diff --check: passed
Codex Agent Skills discovered: 20
Claude Agent Skills discovered: 20
.claude/commands/goal.md: present
docs/goals/ACTIVE.md: present
GitHub wayfinder labels: created and verified
```

## Risks and follow-ups

- Project-scoped skills are pinned copies and need deliberate review when updated.
- Claude Code should start a fresh session after pulling so new skills and `/goal` are discovered.
