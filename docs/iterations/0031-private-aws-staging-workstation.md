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
- Staging now also requires one exact canonical Tailscale HTTPS origin. That
  origin and loopback are the only browser-write origins allowed; local mode
  retains the previous loopback-only guard.
- Backend RED: `11 failed, 1 warning` in 1.27s. Backend GREEN:
  `25 passed, 1 warning` in 0.85s for the new identity tests plus the existing
  API selection. The warning is the inherited Starlette TestClient warning.
- Frontend RED: `1 failed, 14 passed` in 5.82s for the missing staging badge.
  Frontend GREEN: `51 passed` across the navigation and message selections in
  3.95s. Typecheck passed; lint exited 0 with the four inherited Fast Refresh
  warnings. The production bundle rebuilt successfully in 12.92s.
- No cloud resource, budget subscription, public ingress, Tailscale device,
  provider connection, scheduler, testnet, or live-trading state changed.

### 2026-09-09 — Task 2 exact-commit deployment assets

- Added a Linux systemd unit that runs only the deterministic demo on the
  existing loopback default, explicitly keeps paper mode on/live trading off,
  and grants writes only beneath `/var/lib/quantmesh`.
- Added a standard-library release program that rejects malformed or existing
  targets, shallow-fetches and verifies the exact requested commit, installs
  one isolated venv, atomically activates its non-secret staging identity, and
  validates that same identity through loopback health.
- A failed activation restores and restarts the previous release. A failed
  first activation removes the current link and stops the service. Release
  trees are retained for explicit rollback; no automatic pruning occurs.
- Added a minimal Ubuntu bootstrap for the service account, directories, unit
  and exact-commit deployment. Tailscale and firewall actions remain explicit
  operator steps rather than opaque bootstrap mutations.
- Asset RED: `9 failed` in 0.24s because the program and unit did not exist.
  Asset GREEN: `10 passed` in 0.11s, including wrong-FETCH_HEAD refusal,
  success, rollback, first-deploy failure and parsed unit semantics. Bash
  syntax, Python compilation, Ruff check/format and `git diff --check` passed.
- The first RED attempt also exposed an inherited inaccessible global pytest
  temp symlink; subsequent evidence used a fresh explicit basetemp and did not
  repeat or investigate that unrelated environment issue.
- Integration review found that the original loopback-only CSRF rule would
  make a privately served UI readable but prevent browser writes. Focused RED
  produced `18 failed, 11 passed`; the corrected exact-origin selection passed
  `43` tests in 1.60s, and the existing origin-guard regression class passed
  `5` tests in 1.97s. Arbitrary origins remain denied.
