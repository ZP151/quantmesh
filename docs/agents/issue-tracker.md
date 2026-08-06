# Issue Tracker: GitHub

Issues, PRDs and implementation tasks for this repository live in GitHub Issues at `ZP151/quantmesh`. Use the `gh` CLI from the repository root.

## Conventions

- Create: `gh issue create --title "..." --body-file <file>`
- Read: `gh issue view <number> --comments`
- List: `gh issue list --state open --json number,title,labels,assignees,milestone`
- Comment: `gh issue comment <number> --body "..."`
- Label: `gh issue edit <number> --add-label "ready-for-agent"`
- Close: `gh issue close <number> --comment "Completed by <commit-or-pr>."`

Each implementation issue should include user outcome, scope, out-of-scope items, acceptance criteria, risk notes and verification commands. Link the issue from the active file in `docs/iterations/`.

When an agent workflow says “publish to the issue tracker”, create a GitHub issue. When it says “fetch the relevant ticket”, use `gh issue view <number> --comments`.

