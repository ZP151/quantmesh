# Cross-Agent Execution Contract

Status: canonical execution handoff for Codex and Claude Code

## Single source of truth

Codex and Claude Code must reconstruct work from the repository, not from chat
memory. The durable order is:

1. `AGENTS.md` and the platform entry file (`CLAUDE.md` or `.codex/` prompt);
2. `CONTEXT.md`, `PRODUCT.md` and `docs/product-strategy.md`;
3. `docs/goals/ACTIVE.md` and the active iteration;
4. the active tracked specification and implementation plan;
5. relevant ADRs, Git history, open PRs and CI evidence.

Tracked specifications live in `docs/superpowers/specs/` and executable plans
live in `docs/superpowers/plans/`. The directory name describes the planning
format, not an exclusive runtime: both Codex and Claude Code may read, update
and execute these files.

Claude Code should invoke the installed Superpowers skills directly. Codex
should follow the same lifecycle with its available planning, subagent, TDD,
review and verification capabilities. A plan must never require a tool-only
command without also stating the intended behavior and acceptance evidence.

## Plan format

Every executable plan must include:

- exact goal, architecture and global constraints;
- exact files and interfaces for each independently reviewable task;
- checkbox steps with a failing-test command, minimal implementation target,
  passing-test command and coherent commit boundary;
- license, data-lineage, leakage and trading-safety gates where relevant;
- a final requirements checklist, full verification commands, release gate
  and operator acceptance instructions.

Do not use placeholders such as `TBD`, “add tests” or “handle errors.” If a
step cannot be executed by either agent from the repository state, the plan is
not ready.

## Execution lifecycle

1. Treat an operator-approved iteration design as the specification. Use
   Superpowers `writing-plans` (or the equivalent Codex planning workflow) to
   create the tracked implementation plan.
2. Work from a branch or isolated worktree created from `origin/main`, never
   directly from a divergent local `main`.
3. Use test-first red/green/refactor for every behavior change. Preserve the
   failing and passing command evidence in the task report or iteration log.
4. For independent tasks, use Superpowers `subagent-driven-development` or an
   equivalent fresh-implementer/fresh-reviewer loop. Review both specification
   compliance and code quality before advancing.
5. Record completion in the tracked iteration at every phase boundary. The
   git-ignored `.superpowers/sdd/<plan>/progress.md` ledger may accelerate a
   local Claude session, but it is never the only recovery record.
6. Commit after every coherent green checkpoint and at least once per 60
   minutes of active changes when a green boundary exists. Push the integration
   branch after each durable phase so either agent can resume remotely.
7. Use one integration branch and one final PR for the solo-developer fast
   lane. Resolve review findings, wait for required CI, then squash-merge under
   the standing authority in `docs/goals/ACTIVE.md`.
8. Before any completion claim, run fresh verification and record commands,
   exit codes and counts. Agent reports are not verification evidence.
9. Cut a release candidate only from the merged tree after the clean-checkout
   gate. Generate English primary and Simplified Chinese operator acceptance
   notes. Never promote the final version without explicit operator acceptance.

## Vertical-slice operating limits

- Run no more than two concurrent tracks: the active product iteration and the
  iteration-0021 soak maintenance track. They use independent worktrees,
  prompts, files and verification evidence; soak never blocks product work and
  never changes product code opportunistically.
- Every agent prompt has one deliverable, one stop condition and explicit
  forbidden operations. Findings outside that boundary are recorded for later
  triage rather than absorbed into the current task.
- Planner/Product defines one user action and success metric. Quant Researcher
  reviews leakage, costs, metrics and confidence semantics before implementation
  but does not independently expand the research platform.
- Implementer delivers one API/page/state/test loop that exposes visible value
  within 24–48 hours. Reviewer evaluates the demonstrable slice boundary and is
  capped at two rounds; a third structural problem returns the slice for scope
  reduction instead of another patch cycle.
- Verifier runs targeted checks during development. Broad suites run at each
  coherent slice commit and the final PR boundary. Progress records the user
  loop completed, not test count, code volume or ledger length.

If execution is interrupted, the next agent starts with `git status`, fetches
remote state, reads the tracked plan checkboxes and iteration checkpoints, and
resumes the first incomplete task. It must not redispatch work whose commit and
verification evidence already exist.
