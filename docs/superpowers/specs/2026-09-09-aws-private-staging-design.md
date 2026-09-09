# AWS Private Staging Workstation Design

Status: operator approved on 2026-09-09
Tracking issue: [#135](https://github.com/ZP151/quantmesh/issues/135)

## Outcome

Give the solo operator an always-running, privately reachable QuantMesh
acceptance station on AWS. The station must identify the exact deployed Git
commit, retain the existing demo/paper safety posture and be updateable or
rollbackable from the operator's Windows computer without exposing QuantMesh
to the public internet.

## Account and cost facts

The operator's AWS Billing console showed on 2026-09-09:

- USD 0.00 month-to-date and previous-month cost;
- no active AWS credits and USD 0.00 credit balance;
- no Free Tier service usage;
- no AWS Budget; and
- no Lightsail instances.

The Lightsail console offered the account one instance free for 90 days. The
design therefore treats the Lightsail trial as the only confirmed subsidy. It
does not assume the generic USD 100 AWS sign-up credit. The selected public
IPv4 Linux bundle is 2 vCPU, 2 GB RAM and 60 GB SSD at USD 12/month after the
trial. Snapshots, domains and other services are excluded from that amount.

## Architecture

### Compute and process

- One Ubuntu 24.04 LTS Lightsail instance in Asia Pacific (Singapore).
- One unprivileged `quantmesh` service account.
- One systemd service running the package-served FastAPI/React application in
  deterministic `--demo` mode.
- The application listens only on `127.0.0.1:8765`. ADR-0011's non-loopback
  refusal stays in force.
- Runtime data lives at `/var/lib/quantmesh/demo`; release trees live under
  `/opt/quantmesh/releases/<40-character-commit>`.

No container runtime, database service, load balancer or Node.js runtime is
introduced. The committed SPA bundle remains part of the Python package.

### Private access

Tailscale runs as a host service and joins the operator's personal tailnet.
`tailscale serve --bg http://127.0.0.1:8765` terminates private HTTPS for the
tailnet name and proxies to the loopback application. Tailscale Funnel is
prohibited. Lightsail exposes no application port (80, 443 or 8765) publicly.

Browser writes retain the workstation's CSRF boundary. Staging requires one
canonical `https://<device>.<tailnet>.ts.net` origin discovered after the host
joins the operator's tailnet. Only that exact configured origin and existing
loopback origins pass the write guard; arbitrary public origins remain denied.

Port 22 may be temporarily restricted to the operator's current public IP for
bootstrap. After Tailscale SSH/private access is verified, the public SSH rule
is removed. Device authorization and any Tailscale account action remain an
operator handoff.

### Deployment identity

The existing `QUANTMESH_ENVIRONMENT` setting becomes a closed `local` or
`staging` value. A new `QUANTMESH_BUILD_REF` accepts either no value in local
mode or exactly 40 lowercase hexadecimal characters. A new
`QUANTMESH_STAGING_ORIGIN` accepts only one canonical Tailscale HTTPS origin.
Staging refuses to start without both values, while local mode refuses both.

`/health` and `/api/health` add a `deployment` object only in staging:

```json
{
  "environment": "staging",
  "build_ref": "0123456789abcdef0123456789abcdef01234567"
}
```

Local responses remain byte-for-byte unchanged. The React shell renders a
visible `STAGING · 0123456` badge with the full commit in its accessible title.
The badge does not grant authority and is separate from the existing
demo/live/operator runtime label.

### Exact-commit update and rollback

The repository owns a standard-library Python deployment program, a small
Linux bootstrap script and a systemd unit. Keeping release orchestration in
Python makes success and rollback behavior executable under focused tests
without requiring a live AWS host. The deployment program:

1. accepts only an exact 40-character commit and canonical Tailscale origin;
2. fetches that commit from the canonical public GitHub repository;
3. verifies the checked-out object resolves to the requested commit;
4. creates a fresh release directory and virtual environment;
5. installs the package without research, Moomoo or E2E extras;
6. atomically changes `/opt/quantmesh/current`;
7. writes only the non-secret environment/build reference and private origin;
8. restarts the service and checks loopback `/api/health`; and
9. restores the previous symlink and restarts it if the new health check fails.

A retained release can be deliberately reactivated by exact commit. It must
match its recorded build/origin environment and pass the same health identity
check; a failed reactivation restores the release that was current beforehand.

The program refuses an existing or dirty target release, never deletes the
previous release and never writes credentials. Git, systemd restart and health
I/O are narrow injectable boundaries in tests; the real path uses subprocess,
atomic symlink replacement and `urllib`. Old-release pruning is manual and out
of scope.

## Security and trading boundaries

- Demo/paper is the only deployed runtime mode.
- `QUANTMESH_ALLOW_LIVE_TRADING=false` and
  `QUANTMESH_DEFAULT_PAPER_MODE=true` are explicit in the service environment.
- No broker, wallet, model or AWS credentials enter repository files, service
  environment files, logs, fixtures or browser prompts.
- The workstation's origin and risk guards remain unchanged.
- Tailscale is infrastructure, not an application authorization dependency;
  removing it leaves the application loopback-only.
- A public deployment, multi-user service or real execution requires a new
  design and separate operator authority.

## Verification policy

Development uses only focused evidence:

- deployment-setting and health-contract unit tests;
- AppShell component tests for the opt-in badge;
- deployment-program success/failure/rollback tests and service-unit semantic
  checks;
- Ruff on touched Python files, frontend typecheck/lint, bundle build/current
  check, shell syntax check where Git Bash is available, and `git diff --check`.

No full pytest, domain sweep, browser E2E or release gate runs at slice
checkpoints. The AWS station receives a bounded smoke: systemd active,
loopback health identity, private HTTPS health identity and three core SPA
routes. A future release promotion still uses the repository's complete gate.

## Delivery slices

1. **Visible staging identity:** fail-closed configuration, health contract and
   shell badge, with local behavior unchanged.
2. **Repeatable host deployment:** systemd unit, exact-commit update/rollback
   program, bootstrap script and behavioral safety tests.
3. **Operator station:** Windows-first runbook, cost guardrails, AWS/Tailscale
   bootstrap and bounded acceptance evidence.

## Explicit exclusions

- Iteration 0030 / issue #132 and its gate-efficiency worktree.
- Iteration-0021 soak, OpenD, trusted-data roots and witnesses.
- Public DNS/TLS, Funnel, CloudFront, ALB, RDS, ECS, EKS or Terraform.
- CI/CD deployment, autoscaling, multi-user tenancy or uptime claims.
- Automated snapshots during the trial.
- Live/testnet order submission, mainnet signing or secret provisioning.
