# Iteration 0031 — Private AWS staging workstation

- Status: implementation active
- Started: 2026-09-09
- Tracking issue: [#135](https://github.com/ZP151/quantmesh/issues/135)
- Integration branch: `codex/0031-aws-private-staging`
- Baseline: `origin/main@a78ff0a`
- Design: `docs/superpowers/specs/2026-09-09-aws-private-staging-design.md`
- Executable plan: `docs/superpowers/plans/2026-09-09-aws-private-staging.md`

## Outcome

Deliver an exact-commit, private-by-default demo/paper staging workstation on
AWS Lightsail that the operator can open from an approved Tailscale device.
The service remains loopback-bound, displays its staging identity, and can
roll back to the previously activated release after a failed health check.

## Safety boundary

- Paper/demo mode remains mandatory; live execution is not enabled.
- The application port, HTTP and HTTPS are not opened to the public Internet.
- Tailscale Serve is allowed; Funnel is prohibited.
- Secrets and Tailscale auth material never enter the repository or logs.
- Creating paid-capable AWS resources, budgets, or authorizing a device needs
  an operator confirmation at the action boundary.
- Focused tests are the normal iteration gate. Full pytest, domain sweeps,
  browser E2E and release gates are explicitly out of scope here.

## Role outputs

- **Planner:** bounded the work to deployment identity, exact-commit host
  assets, rollback, and a Windows-first operator runbook.
- **Quant researcher:** confirmed that the staging surface adds no new data,
  model, provider, strategy, or order authority.
- **Implementer:** Task 1 is complete; deployment assets remain in progress.
- **Reviewer:** self-review currently covers Task 1's local/staging separation.
- **Verifier:** focused evidence is recorded below; final verification is
  pending and will not expand into the long-test gates.

## Checkpoints

### 2026-09-09 — Task 1 deployment identity

- Added a strict `local | staging` environment setting. Staging requires one
  exact lowercase 40-character Git commit; local behavior stays unchanged.
- Both health endpoints expose deployment identity only in staging. The shell
  renders a visible `STAGING · <short commit>` badge whose accessible label
  and tooltip retain the full commit.
- Backend RED: `11 failed, 1 warning` in 1.27s. Backend GREEN:
  `25 passed, 1 warning` in 0.85s for the new identity tests plus the existing
  API selection. The warning is the inherited Starlette TestClient warning.
- Frontend RED: `1 failed, 14 passed` in 5.82s for the missing staging badge.
  Frontend GREEN: `51 passed` across the navigation and message selections in
  3.95s. Typecheck passed; lint exited 0 with the four inherited Fast Refresh
  warnings. The production bundle rebuilt successfully in 12.92s.
- No cloud resource, budget subscription, public ingress, Tailscale device,
  provider connection, scheduler, testnet, or live-trading state changed.

