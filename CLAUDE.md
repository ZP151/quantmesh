# QuantMesh Claude Guide

Read and follow `AGENTS.md`; it is the canonical repository-wide collaboration contract.

Claude-specific resources live under `.claude/`:

- `.claude/settings.json` contains project safety permissions.
- `.claude/agents/` contains role prompts.
- `.claude/skills/` contains project-scoped curated skills.

Before implementation, read `CONTEXT.md`, the active iteration record, the roadmap and relevant ADRs. Keep paper trading enabled by default, keep credentials out of prompts and require deterministic risk approval for every executable order.

Use `/goal` to start or resume a durable multi-session objective. It reconstructs state from repository documents, Git history and GitHub before continuing.

For a tracked plan under `docs/superpowers/plans/`, invoke the installed
Superpowers skills directly; do not rely on removed legacy slash commands.
Use `superpowers:writing-plans` before implementation,
`superpowers:subagent-driven-development` for independent tasks,
`superpowers:test-driven-development` for behavior changes and
`superpowers:verification-before-completion` before status claims. Follow
`docs/agents/cross-agent-execution.md` so Codex can resume the same work.
