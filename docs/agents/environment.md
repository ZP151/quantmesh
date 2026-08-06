# Agent Environments

## Codex

- Canonical instructions: `AGENTS.md`
- Project resources: `.codex/`
- Project skills: `.codex/skills/`
- Role prompts: `.codex/agents/`

## Claude

- Canonical shared instructions: `AGENTS.md`
- Claude entrypoint: `CLAUDE.md`
- Project resources: `.claude/`
- Project skills: `.claude/skills/`
- Role prompts: `.claude/agents/`

## Installed curated skills

- `jupyter-notebook`
- `playwright`
- `security-best-practices`
- `security-threat-model`
- `gh-fix-ci`
- `gh-address-comments`
- `yeet`
- `openai-docs`

## Installed engineering Agent Skills

- `ask-matt`: route work to the appropriate engineering flow
- `grill-with-docs`: resolve product/domain decisions and preserve them
- `to-spec`: publish a buildable specification
- `to-tickets`: create tracer-bullet tickets and blocking edges
- `wayfinder`: map large, uncertain efforts as decision tickets
- `implement`: implement a ticket through TDD and review
- `tdd`: red-green-refactor at public behavior seams
- `diagnosing-bugs`: reproduce and isolate hard failures
- `code-review`: review standards and spec compliance separately
- `triage`: move incoming reports through the issue state machine
- `improve-codebase-architecture`: identify deepening opportunities
- `handoff`: create a context-safe session handoff

Skills are vendored at project scope so their versions are reviewable and travel with the repository. Review upstream changes before updating them.
