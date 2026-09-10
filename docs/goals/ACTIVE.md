# Active Goal

Status: authorized implementation goal delivered — architecture integration pending, 2026-09-11.

Deliver Iteration 0032 Probabilistic Scenario Lab using the approved chart-first
Instrument Workspace design. One measurable loop: NVDA ticker to saved Watch
within 120 seconds, with exact 7/30-session evidence and restart-safe replay.

- Issue: https://github.com/ZP151/quantmesh/issues/136
- Reviewable PR: https://github.com/ZP151/quantmesh/pull/137 (open, not merged).
- Branch: `codex/0032-probabilistic-scenario-lab`, baseline `origin/main@a78ff0a`
- Ledger: `docs/iterations/0032-probabilistic-scenario-lab.md`
- Spec: `docs/superpowers/specs/2026-09-10-probabilistic-scenario-lab-design.md`
- Plan: `docs/superpowers/plans/2026-09-10-probabilistic-scenario-lab.md`
- Frontier: PR #137 is open with implementation, tests, packaged artifacts and
  durable evidence. GitHub's automatic `python` check was in progress on product
  head `ba8eb5e` at publication. No manual broad gate was dispatched. Next action
  is architecture PR review/integration; no new product slice authorized here.
- Authority: implement, targeted tests, commit/push feature branch and one final
  reviewable PR. Architecture merge remains outside routine merge allowance.
- Limits: no cloud/deployment/#124/#127/#132/#135/0021 operations, providers,
  trusted-root writes, new models or notifications. No full pytest/domain sweep,
  release gate or soak. Commands <=300s; coherent verification targets <=600s.
  One final Standards/Spec review plus one batched UI check, at most one fix and
  confirmation. Do not repair the Impeccable sidecar.
- Evidence: 80 targeted backend and 153 frontend tests; correction selections 35
  backend/77 frontend; real same-origin NVDA-to-Watch 52.865s, identical saved-chart
  reload, Chinese 390px acceptance, packaged build/freshness, one Standards/Spec
  review and correction/confirmation. See ledger for the controller-verified
  staged-refusal edge found during confirmation; no second review claimed.
