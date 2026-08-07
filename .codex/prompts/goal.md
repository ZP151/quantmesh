# QuantMesh Long-Running Goal

Objective: `$ARGUMENTS`

Follow the same durable workflow defined in `.claude/commands/goal.md`. Reconstruct state from `AGENTS.md`, `CONTEXT.md`, `docs/goals/ACTIVE.md`, the roadmap, active iteration, ADRs, Git history, GitHub issues and open PRs before acting.

Continue through safe, unblocked vertical slices. Use the project Agent Skills for wayfinding, implementation, TDD, diagnosis, review and handoff. Keep progress in GitHub plus `docs/goals/ACTIVE.md` and `docs/iterations/`; never rely on chat history as the only source of state.

Standing merge authority: merge a self-created, non-draft PR to `main` with a
squash merge and delete its remote feature branch when its authorized scope is
clean, all required CI and local checks pass, review has no unresolved finding,
and it contains no credentials, live trading, destructive migration, paid
service, incompatible license, or major architecture change. Merge dependent
PRs one at a time and re-check the next PR after each merge.

Squash merges rewrite commit IDs, so local `main` can diverge from `origin/main` after merging a PR. Preserve a divergent local `main` and always create the next work branch from `origin/main`; reconcile by fast-forward only.
