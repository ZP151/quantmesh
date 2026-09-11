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
- Frontier: correction `517702f` closes external review 3981553959 and the
  js-yaml audit blocker. Remote Python regression on checkpoint `cc317cc`
  (34605611167) returned 32 failures / 3276 passed / 55 skipped. Most share a
  new-XNYS-demo/legacy-route freshness mismatch; two native float golden hashes
  are platform-specific and one outcome reason lost the legacy horizon label.
  Follow-on corrections now pass 38 fast packet/lab tests, 11 calendar tests
  (two final legacy nodes rechecked), a real demo proposal/confirmation/reset
  test and two outcome/Inbox lifecycle tests. Inspect the latest automatic CI
  after this correction push. Do not repeat passing frontend gates or start
  another product slice. Architecture integration remains a separate boundary.
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
