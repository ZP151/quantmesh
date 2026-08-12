---
description: Start or resume a long-running QuantMesh goal from repository and GitHub state
argument-hint: "[objective, active iteration, roadmap milestone, or GitHub issue]"
---

# Long-Running QuantMesh Goal

Operate as the coordinating engineering agent for a durable, multi-session goal.

User input: `$ARGUMENTS`

If the input is empty, resume the goal in `docs/goals/ACTIVE.md`. If that file
has no active objective, select the active iteration or roadmap frontier.
Create or select a GitHub issue only when independent pickup, external tracking
or a durable discussion thread is useful.

## 1. Reconstruct state before acting

Read these primary sources in order:

1. `AGENTS.md` and `CLAUDE.md`
2. `CONTEXT.md`
3. `docs/goals/ACTIVE.md`
4. `docs/roadmap/ROADMAP.md`
5. `docs/iterations/INDEX.md` and the active iteration file
6. `docs/agents/cross-agent-execution.md` and any active tracked plan under
   `docs/superpowers/` (create it from the approved iteration before code if it
   does not exist)
7. Relevant ADRs under `docs/adr/`
8. The full body, comments and labels of linked GitHub issues/PRs

Then inspect repository history and current state:

```text
git status --short --branch
git remote -v
git fetch origin --prune
git log --graph --decorate --oneline --all -30
git submodule status
gh issue list --state open --json number,title,labels,assignees,milestone
gh pr list --state open --json number,title,headRefName,baseRefName,statusCheckRollup
```

Preserve user changes. Never discard, reset, clean or overwrite work you did not create. Never expose credentials or private keys in output.

Squash merges rewrite commit IDs, so local `main` can diverge from `origin/main` after merging a PR (the merged branch commit is not an ancestor). Preserve a divergent local `main` and always create the next work branch from `origin/main`; reconcile local `main` by fast-forward only.

## 2. Resolve the requested goal

- A GitHub issue/PR reference is the immediate work specification.
- An active iteration with complete acceptance criteria is a sufficient work
  specification; it does not require duplicate GitHub issues.
- A roadmap milestone means work its unblocked issue frontier in dependency order.
- A broad destination with unresolved decisions uses `/wayfinder`; resolve decisions before implementation.
- A buildable issue uses `/implement`, which must drive `/tdd` and finish with `/code-review`.
- A hard bug uses `/diagnosing-bugs` before implementation.
- If context approaches its useful limit, use `/handoff` at the phase boundary and record the handoff path in `docs/goals/ACTIVE.md`.

Do not silently broaden scope. If `$ARGUMENTS` conflicts with the active goal, update `docs/goals/ACTIVE.md` with the replacement and explain why.

## 3. Establish a safe work unit

## Solo delivery fast lane

For one-developer delivery, create one short-lived branch from `origin/main`
for a coherent release or architecture slice. The active iteration is the
default source of scope and acceptance criteria. Keep coherent, tested commits,
update the iteration at meaningful checkpoints and push when remote durability
or CI evidence is useful; do not create checkpoint-only PRs or one PR per
checkbox.

Open one PR at the slice gate, or earlier only for a credential, license,
destructive migration, paid-service or major architecture decision. Review
each coherent commit before continuing, run proportional checks during the
slice and the full required gate before the PR. GitHub issues are optional:
use them when work needs independent pickup, external discussion or separate
durable tracking.

For implementation work:

1. Confirm the active iteration or linked issue has complete acceptance criteria.
2. Claim a linked issue when one exists; do not create one only to satisfy process.
3. Work on `feat/<slug>`, `fix/<slug>` or `docs/<slug>`, optionally including an issue number, never directly on `main`.
4. Pull no unrelated work into the branch.
5. Link the branch, active iteration and any optional issue in `docs/goals/ACTIVE.md`.

If the current worktree is dirty, identify ownership of every change. Continue only when the changes are part of this goal or can be safely isolated.

## 4. Persistent execution loop

Continue until the objective is achieved or a genuine human/external gate is reached:

For a non-trivial multi-task implementation, invoke the installed Superpowers
skills directly. Use `superpowers:writing-plans` to produce the tracked plan,
then prefer `superpowers:subagent-driven-development`; use
`superpowers:test-driven-development`, `superpowers:requesting-code-review`
and `superpowers:verification-before-completion` at their required gates. The
operator's standing integration authority below overrides only the final
interactive merge menu; it does not waive tests, reviews or safety gates.

1. Choose the smallest complete vertical slice on the unblocked frontier.
2. Record its acceptance criteria and role assignments in the active iteration.
3. Implement test-first at a public behavior seam.
4. Run focused tests during development and the full required checks at the end.
5. Update documentation and ADRs when domain language or durable decisions change.
6. Append a dated checkpoint to the active iteration and update `docs/goals/ACTIVE.md`.
7. Commit a coherent checkpoint referencing the active iteration and any
   linked issue.
8. Re-read `git status`, `git log`, issue comments and PR state before the next slice.

Do not stop merely because one intermediate step is complete. Do stop at credential/legal gates, destructive operations, live-trading enablement, or a decision that materially changes product scope.

## 5. Verification and review gate

At minimum run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check src tests
git diff --check
git submodule status
```

Add connector, replay, migration, security or frontend checks as relevant. Run `/code-review` against the branch point and resolve actionable findings. Record exact commands and results in the active iteration.

Trading-safety rules are non-negotiable: paper mode defaults on, stale data fails closed, AI cannot bypass deterministic risk approval, and live execution requires explicit human authorization.

## 6. Publish and preserve history

When a work unit is ready:

1. Commit with the iteration or optional issue reference needed to understand scope.
2. Push the active release or feature branch without force.
3. In the solo delivery fast lane, open one PR at the coherent slice gate or an earlier high-risk gate. Link the active iteration and any optional issue.
4. Wait for CI and review at every opened PR; run local verification and commit-level review for every fast-lane slice.
5. The user grants standing approval to merge a self-created PR into `main`
   using a squash merge and delete its remote feature branch when all of the
   following are true: the PR is non-draft; its scope is already authorized;
   merge state is clean; all required CI checks passed; no review is pending or
   requesting changes; `/code-review` found no unresolved actionable issue;
   local required checks pass; and the change contains no credential handling,
   live trading, destructive migration, paid service, incompatible license, or
   major architecture change.
6. For a dependent PR chain, merge one PR at a time in dependency order.
   After every merge, fetch `main`, inspect the next PR's reduced diff and
   checks, then continue only if it still satisfies the standing approval.
7. If GitHub branch protection refuses the merge despite all checks, record the
   exact rule and continue with another safe unblocked task; do not ask merely
   to repeat a routine merge approval.

Use the active iteration for scope and delivery evidence, ADRs for durable
decisions and `docs/goals/ACTIVE.md` for session-resume state. Use GitHub PRs
for review/merge evidence and issues only when separate tracking adds value.

## 7. Completion or pause

On completion:

- Mark acceptance criteria and iteration status accurately.
- Update the roadmap milestone status only when its exit criteria are met.
- Archive the goal under `docs/goals/archive/` and reset `ACTIVE.md` to the next objective or `Status: idle`.
- Report commits, PR, CI, tests and remaining risks.

On a genuine block:

- Record the blocker, attempted alternatives and exact human action required.
- Apply `ready-for-human` or `needs-info` as appropriate.
- Leave the branch, issue, iteration and goal files sufficient for a fresh session to resume without chat history.
