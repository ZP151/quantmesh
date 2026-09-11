# Active Goal

Status: active — PR #137 CI and external-review correction, 2026-09-11.

Deliver Iteration 0032 Probabilistic Scenario Lab using the approved chart-first
Instrument Workspace design. One measurable loop: NVDA ticker to saved Watch
within 120 seconds, with exact 7/30-session evidence and restart-safe replay.

- Issue: https://github.com/ZP151/quantmesh/issues/136
- Reviewable PR: https://github.com/ZP151/quantmesh/pull/137 (open, not merged).
- Branch: `codex/0032-probabilistic-scenario-lab`, baseline `origin/main@a78ff0a`
- Ledger: `docs/iterations/0032-probabilistic-scenario-lab.md`
- Spec: `docs/superpowers/specs/2026-09-10-probabilistic-scenario-lab-design.md`
- Plan: `docs/superpowers/plans/2026-09-10-probabilistic-scenario-lab.md`
- Frontier: correction `517702f` is pushed to PR #137. It closes external
  review 3981553959 and the js-yaml audit blocker with 66 passing affected
  frontend tests plus build/type/lint/OpenAPI/lock-license evidence. Automatic
  run 34604897018 has passed fresh install, audit, frontend tests, bundle and
  lint; Python tests are still running. Recent main CI runs take 41–42 minutes.
  On resume inspect the latest PR head/checks and diagnose only actual failures;
  do not rerun already-passing local gates or start another product slice.
  Architecture integration remains a separate boundary.
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
