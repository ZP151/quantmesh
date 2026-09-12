# Iteration 0031 — Private AWS staging workstation

- Status: completed; integrated through PR #142 / iteration 0034
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

- Paper execution remains mandatory; live execution is not enabled. Demo stays
  the default profile; operator-approved iteration 0034 adds read-only live data.
- The target boundary exposes no application port, HTTP or HTTPS to the public
  Internet. A newly created Lightsail instance starts with a default public
  HTTP rule; remove it before installing or accepting the service.
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
- **Implementer:** deployment identity, packaged UI, exact-release tooling,
  checked rollback and the operator handoff are complete in the repository.
- **Reviewer:** mapped issue #135 to the final diff and checked loopback,
  exact-origin, demo/paper, secret and public-ingress boundaries.
- **Verifier:** ran the bounded final gate below; live-server smoke remains the
  post-confirmation acceptance step.

## Checkpoints

### 2026-09-09 — Adjacent work inventory

- GitHub has no open pull request. The only open issues are #135 (this
  iteration), #132 (tiered validation gates), #127 (two-hour connection
  witness) and #124 (human-owned 168-hour soak witness).
- Issue #132 remains isolated in `QuantMesh-gate-efficiency` with committed and
  uncommitted work. The 0021 finalization worktree contains uncommitted #127
  witness files. Both are preserved and excluded from this branch.
- Other attached legacy worktrees are clean historical/squash-divergent
  checkouts, not evidence of an open integration request. They are retained;
  workspace cleanup requires a separate explicit decision.

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
- Operator handoff review found that failed updates rolled back automatically,
  but a deliberate rollback had no guarded command. The deployment program
  now supports `--activate-existing`, validates the retained release identity,
  applies the same loopback health check, and restores the current release if
  reactivation fails. RED was `2 failed, 10 passed`; GREEN was `12 passed` in
  0.12s, followed by clean Ruff, Bash syntax and Python compilation checks.

### 2026-09-09 — Repository-ready operator handoff

- Added ADR-0021 and a Windows-first runbook covering the exact Lightsail
  selection, both firewall families, Tailscale authorization/Serve, initial
  bootstrap, private health identity, updates, checked rollback, bounded
  diagnosis, cost alerts and deletion. AWS/Tailscale commands and pricing were
  checked against current primary documentation.
- Corrected stale durable state for merged iterations 0028/0029, recorded 0031
  without modifying 0030's branch-owned ledger, added Tailscale to the reuse
  matrix as an external host adapter and made this goal resumable.
- Final backend/asset selection: `50 passed, 1 warning` in 2.21s. The sole
  warning is the inherited FastAPI/Starlette TestClient deprecation warning.
  Ruff check and format, Bash syntax, Python compilation and
  `git diff --check` passed.
- Final frontend selection: `51 passed` in 4.24s. Typecheck passed; lint exited
  0 with the four inherited Fast Refresh warnings. OpenAPI client freshness
  passed and the production bundle rebuilt byte-equivalent in 8.86s; the
  existing >500 kB chunk advisory remains unchanged.
- No full pytest, domain sweep, browser E2E or release gate ran. No AWS
  resource, budget, Tailscale account/device, public ingress or execution state
  changed. The remaining acceptance evidence is the bounded server smoke after
  the operator separately confirms the external actions.
- The live Lightsail form was prefilled without submission and rechecked as:
  Singapore Zone A, Linux operating system, Ubuntu 24.04 LTS, General Purpose,
  Dual-stack, USD 12/month, 2 GB/2 vCPU/60 GB, one `quantmesh-staging`
  instance, automatic snapshots off. The form remains stopped at
  **Create instance**.

### 2026-09-09 — Lightsail instance created

- After an action-time operator confirmation, created exactly one
  `quantmesh-staging` instance in Singapore Zone A from the reviewed form.
  Lightsail reports `Running` with Ubuntu, General Purpose, Dual-stack and
  2 GB RAM / 2 vCPU / 60 GB SSD. Automatic snapshots remain disabled; no
  static IP, load balancer, distribution or budget was created.
- Read-only networking inspection found the image defaults: public HTTP 80
  and SSH 22 accept IPv4 or IPv6 traffic; browser SSH is enabled. No firewall
  change was made because modifying security rules requires a separate
  action-time confirmation.
- The application has not been installed or exposed. Next acceptance work is
  to close the default HTTP rule, narrow temporary SSH access, authorize the
  Tailscale device, deploy the exact commit, and run the bounded private smoke.

### 2026-09-09 — Private staging release activated

- Installed Tailscale 1.102.3 after operator confirmation, authorized
  `quantmesh-staging` in the personal tailnet and enabled Tailscale SSH. The
  node is connected with no advertised subnet routes or exit-node role.
- Activated exact commit
  `402294248406fa865d601633f4e5ba3bd3521b5b` under
  `/opt/quantmesh/releases/` and enabled the systemd unit. The independent
  loopback health probe reported `status=ok`, `environment=staging`, the exact
  build ref, `runtime_mode=demo`, `paper_mode=true` and
  `live_trading=false`.
- Enabled tailnet HTTPS/Serve only; the console's default optional Funnel was
  explicitly cleared before confirmation. Serve proxies private HTTPS to the
  loopback-only application on `127.0.0.1:8765`.
- A transposed character in the initially copied MagicDNS suffix was caught by
  a Windows DNS probe. The deployed origin was corrected from the node's
  authoritative Tailscale status, then the retained release was reactivated
  through the checked deployment command. The correct private hostname
  resolves over the Windows Tailscale adapter and TCP 443 succeeds.
- Bounded external smoke passed: private `/api/health` returned the exact
  identity, the workstation rendered the visible `STAGING · 4022942` badge,
  the correct private origin reached request validation (`422` for a deliberate
  invalid venue), a foreign origin was rejected (`403`), and kill-switch state
  remained false before and after the probes.
- No full pytest, domain sweep, browser E2E or release gate ran. The operator
  chose to retain the default public HTTP 80 and SSH 22 Lightsail rules for
  now; the application itself remains loopback-only, but removing those rules
  after multi-device Tailscale verification remains a hardening follow-up.

### 2026-09-12 — Main integration and approved live-data extension

- PR #142 merged the independent deployment implementation into main as
  `e185c3b052ca0cdd3590b0d5d05fd7460d783fb7`. The independent worktree remains
  untouched. Final-head CI passed 3443 Python / 336 frontend tests.
- The same exact merged build is active in AWS with the explicitly approved
  read-only data profile. Paper is true, live trading is false, private Serve
  still targets 127.0.0.1:8765 and the original `4022942` demo release remains.
- Five-minute real-feed and browser/replay evidence is in the
  [0034 ledger](0034-live-data-delivery.md). This supersedes the original
  demo-only observation profile, without changing order authority. The
  previously retained Lightsail firewall rules remain a separate follow-up.
