# QuantMesh Agent Guide

This file is the canonical collaboration contract for every coding agent working in this repository. Platform-specific files may add operational details, but they must not contradict this guide.

## Mission

Build QuantMesh as a local-first, cross-market quantitative research and guarded-trading workstation. Reuse mature open-source components behind stable adapters. Keep research reproducible, execution deterministic and live trading disabled by default.

## Required reading

Before changing code, read:

1. `CONTEXT.md`
2. `docs/roadmap/ROADMAP.md`
3. The active file in `docs/iterations/`
4. Relevant decisions in `docs/adr/`
5. `docs/REUSE_MATRIX.md` before copying or embedding upstream code
6. `docs/agents/cross-agent-execution.md` and, when present, the active tracked
   plan before starting or resuming a multi-session implementation

## Collaboration mode

Use role-based handoffs for non-trivial work:

- **Planner** defines scope, dependencies, acceptance criteria and risks.
- **Quant researcher** evaluates datasets, algorithms, leakage, costs and statistical validity.
- **Implementer** changes one bounded vertical slice and updates tests.
- **Reviewer** checks correctness, architecture, licensing and trading-safety invariants.
- **Verifier** runs automated checks and records evidence in the iteration log.

One agent may perform several roles, but each role's output must remain visible in the active iteration record. Parallel agents must work on independent files or branches and merge through a reviewer.

## Work protocol

1. Start from a GitHub issue with clear acceptance criteria.
2. Link the issue from the active iteration record.
3. Prefer a small vertical slice that produces observable user value.
4. Reuse upstream packages, SDKs or isolated services before copying code.
5. Preserve upstream license and copyright notices for copied code.
6. Add or update tests before marking implementation complete.
7. Run the relevant checks listed in `docs/agents/collaboration.md`.
8. Update the iteration record with decisions, evidence, risks and follow-ups.
9. Use a pull request for review; do not force-push shared branches. For a
   solo milestone explicitly marked as a fast lane in `ACTIVE.md`, use one
   integration branch and one final milestone PR instead of a PR per slice;
   retain one tested, reviewed commit and iteration checkpoint per issue.

## Branch hygiene after squash merges

Squash merges rewrite commit IDs: the feature-branch commits never become
ancestors of `main`, so after a merge, local `main` can diverge from
`origin/main` (a previously merged commit sits on top of the new head). When
this happens:

- Preserve the divergent local `main`; never `reset --hard` it away unless the
  divergence is fully contained in `origin/main` and verified.
- Create every new work branch from `origin/main`, never from local `main`.
- Reconcile local `main` by fast-forwarding when possible; otherwise leave it
  in place, note the divergence in the active iteration record, and keep
  working from `origin/main`.

## Long-running goals

Use `docs/goals/ACTIVE.md` as the resumable state for multi-session work. Claude Code invokes `.claude/commands/goal.md` with `/goal`; Codex can use `.codex/prompts/goal.md`. Every resume begins by reading repository docs, Git history, GitHub issues and open PRs. Chat history is never the sole source of project state.

Specifications and executable plans under `docs/superpowers/` are shared
repository artifacts, not Claude-only files. Claude Code may execute them with
the installed Superpowers plugin; Codex follows the equivalent plan, TDD,
subagent-review and verification lifecycle. Durable completion evidence must
also be mirrored into the active iteration so either agent can resume.

## Trading safety invariants

- Paper mode remains the default.
- Live execution requires explicit configuration and a deterministic risk approval.
- AI output is research input, never direct order authority.
- Secrets, private keys and raw account credentials never enter prompts, logs or fixtures.
- Backtests must model fees, spread, slippage and time ordering.
- No strategy is promoted without out-of-sample and paper-trading evidence.

## Definition of done

A change is done only when code, tests, documentation and iteration evidence agree. The worktree must pass formatting, linting and tests. User-visible or architectural changes require a roadmap/iteration update; durable architecture choices require an ADR.

## Agent skills

### Issue tracker

Issues and PRDs are tracked in GitHub Issues for `ZP151/quantmesh`. See `docs/agents/issue-tracker.md`.

### Triage labels

The repository uses the five canonical labels `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human` and `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

This is a single-context repository with `CONTEXT.md` at the root and system decisions under `docs/adr/`. See `docs/agents/domain.md`.

### Product interface design

For operator-facing frontend work, read `PRODUCT.md` and invoke the
project-scoped `impeccable` skill before shaping or changing a surface. Use
`design-taste-frontend` as an anti-template and design-system-selection guard,
but respect its explicit exclusion of dashboards and data tables. Dense tables
and financial charts require purpose-built components. Record durable visual
decisions only after implementation evidence exists.

### Superpowers-compatible delivery

For non-trivial implementation plans, follow
`docs/agents/cross-agent-execution.md`. Claude Code invokes
`superpowers:writing-plans`, `superpowers:subagent-driven-development`,
`superpowers:test-driven-development`, `superpowers:requesting-code-review`
and `superpowers:verification-before-completion` as applicable. Codex uses its
available skills and subagents to enforce the same observable gates. The
repository plan and iteration ledger govern both agents.
