# Active Goal

Status: active — operator-approved continuous goal, 2026-09-11.

Deliver Iteration 0032 Probabilistic Scenario Lab using the approved chart-first
Instrument Workspace design. One measurable loop: NVDA ticker to saved Watch
within 120 seconds, with exact 7/30-session evidence and restart-safe replay.

- Issue: https://github.com/ZP151/quantmesh/issues/136
- Branch: `codex/0032-probabilistic-scenario-lab`, baseline `origin/main@a78ff0a`
- Ledger: `docs/iterations/0032-probabilistic-scenario-lab.md`
- Spec: `docs/superpowers/specs/2026-09-10-probabilistic-scenario-lab-design.md`
- Plan: `docs/superpowers/plans/2026-09-10-probabilistic-scenario-lab.md`
- Frontier: Task 1 entry, Task 2 exact packet evidence, Task 3 calendar compatibility.
- Authority: implement, targeted tests, commit/push feature branch and one final
  reviewable PR. Architecture merge remains outside routine merge allowance.
- Limits: no cloud/deployment/#124/#127/#132/#135/0021 operations, providers,
  trusted-root writes, new models or notifications. No full pytest/domain sweep,
  release gate or soak. Commands <=300s; coherent verification targets <=600s.
  One final Standards/Spec review plus one batched UI check, at most one fix and
  confirmation. Do not repair the Impeccable sidecar.
- Evidence: approved design/spec self-review; implementation and tests pending.
