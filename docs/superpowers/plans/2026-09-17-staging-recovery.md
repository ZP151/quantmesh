# Private AWS Staging Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the private AWS staging station and prove that the accepted Hyperliquid BTC/ETH/SOL chart path is serving real data again.

**Architecture:** Keep exact release `76203e0` on `127.0.0.1:8765` behind existing Tailscale Serve. Diagnose the host/network boundary before touching the service; after reachability returns, use read-only health, live-smoke and a short browser check. No source change or redeployment is implied.

**Tech Stack:** Tailscale CLI, AWS/Lightsail console, systemd, QuantMesh `/health`, `/live/status`, `/live/state`, and `tools/live_smoke.py`.

**Spec:** [Iteration 0036](../../iterations/0036-staging-recovery.md), [AWS private staging runbook](../../runbooks/aws-private-staging.md), [iteration plan](../../ITERATION_PLAN.md).

## Global Constraints

- Keep `runtime_mode=live`, `paper_mode=true`, and `live_trading=false`.
- Keep loopback and Tailscale private HTTPS; do not add public ingress, Funnel, a new AWS resource, or a paid provider.
- Do not place orders, change credentials, expose OpenD, or put secrets in chat, logs, fixtures, or evidence.
- Preserve release `76203e03476b120e149a0c06d9932849bb4d8e14` and rollback `402294248406fa865d601633f4e5ba3bd3521b5b`.
- A node-offline result is an infrastructure/operator blocker, not an application regression.

## Slice contract

- **One user action:** an operator restores the existing private staging node,
  then opens BTC, ETH and SOL from Markets/Watchlist at `1D / Line`.
- **Success metric:** the exact accepted build is reachable over private HTTPS,
  exposes its environment and build ref, serves read-only live observations,
  and the three chart pages show advancing real Hyperliquid data after reload.
- **Explicit non-goal:** Moomoo/OpenD entitlement and AAPL/NVDA acceptance are
  a separate follow-up slice. Local OpenD preflight evidence is retained below
  only as preparation; it does not advance this recovery gate.

## Interfaces and evidence contract

The recovery boundary is the existing Tailscale device `quantmesh-staging`,
systemd units `tailscaled` and `quantmesh-staging.service`, loopback listener
`127.0.0.1:8765`, Tailscale Serve, HTTPS `/health`, `/live/status`,
`/live/state`, `tools/live_smoke.py`, and the Markets/Watchlist instrument
routes. Every task records a failing diagnostic, the smallest recovery target,
the passing verification command, and one coherent evidence commit; no task
changes application source or creates infrastructure.

---

### Task 1: Confirm the private-node boundary

**Files:** `docs/iterations/0036-staging-recovery.md`, `docs/goals/ACTIVE.md`.

- [x] Run `tailscale status --json`, `tailscale netcheck`, `tailscale ping --c 3 quantmesh-staging`, `Resolve-DnsName quantmesh-staging.tail99d23c.ts.net`, and `Test-NetConnection quantmesh-staging.tail99d23c.ts.net -Port 443`.
- [x] Record node online state, last-seen time, resolved address, TCP 443 and `/health`. The 2026-09-17 baseline is local Tailscale healthy, Singapore DERP reachable, DNS `100.90.189.16`, peer offline since 2026-09-14, no handshake, ping timeout and TCP 443 failure. The Tailscale Machines console independently reports **Machine not connected**, and read-only checks of the existing AWS address time out on TCP 22/443.
- [x] Commit the evidence checkpoint; do not alter AWS or Tailscale from the agent host.

**Task boundary:** The current failing diagnostic is `tailscale ping --c 3
quantmesh-staging` plus TCP 443 and HTTPS `/health` (timeouts are expected in
the recorded baseline). The minimal target is a documented node/network
classification. Passing evidence is the command set above plus the control
plane cross-check; commit only the resulting documentation checkpoint.

### Task 2: Operator restores the existing node

**Files:** `docs/runbooks/aws-private-staging.md`, `docs/iterations/0036-staging-recovery.md`.

- [ ] Inspect the existing `quantmesh-staging` Lightsail instance. If stopped or unhealthy, the operator starts or recovers it; no new instance is created.
- [ ] From the instance console or authorized private SSH, inspect `sudo systemctl is-active tailscaled quantmesh-staging.service`, `tailscale status`, and `curl --fail --silent http://127.0.0.1:8765/health`.
- [ ] If the operator elects to restart after inspection, restart only the existing service and repeat loopback health. Do not change release, environment, firewall, Serve target or lake.
- [ ] From Windows require three successful Tailscale pings and private TCP 443 before application checks. Otherwise keep the blocker open.

**Task boundary:** The failing diagnostic is the instance-side `systemctl
is-active`/loopback health sequence while the peer is offline. The minimal
target is to bring the existing node back without changing its release or
firewall. Passing evidence is both units active, loopback `/health` successful,
`tailscale status` online, three Windows pings and TCP 443; commit only the
operator status evidence.

### Task 3: Verify the accepted release and live read-only surface

**Files:** `docs/iterations/0036-staging-recovery.md`; existing contract `tests/test_live_smoke.py`.

- [ ] Check `https://quantmesh-staging.tail99d23c.ts.net/health` and require build `76203e03476b120e149a0c06d9932849bb4d8e14`, `runtime_mode=live`, `paper_mode=true`, and `live_trading=false`.
- [ ] Run `python tools/live_smoke.py --url https://quantmesh-staging.tail99d23c.ts.net --watchlist BTC,ETH,SOL --timeout 10` with `PYTHONPATH=src`; require `LIVE SMOKE PASSED` and read-only GETs only.
- [ ] Inspect `/live/status` and `/live/state`; record real/delayed/stale/unavailable labels and source times honestly.

**Task boundary:** A failing health check is any mismatch in build, runtime,
paper/live flags, environment/build metadata, or missing live-state labels. The
minimal target is the retained exact release with a visible environment and
exact build ref. Passing evidence is the exact `/health` assertion, successful
read-only live smoke, and `/live/status` plus `/live/state`; on the instance,
`tailscale serve status` must show private HTTPS proxying only to
`127.0.0.1:8765`. Commit only the read-only API evidence.

### Task 4: Verify charts and close recovery

**Files:** `docs/iterations/0036-staging-recovery.md`, `docs/goals/ACTIVE.md`.

- [ ] Open Markets and Watchlist → BTC, ETH and SOL with `range=1d&mode=line`; confirm Hyperliquid, real classification, advancing source time and freshness.
- [ ] Observe a short recovery window and reload; require two advancing source timestamps per symbol and retained points. Do not call this a new ten-minute witness.
- [ ] Run `python -m pytest tests/test_live_smoke.py -q`, `ruff check src tests tools`, and `git diff --check`.
- [ ] Open a reviewed documentation/evidence PR from `origin/main`; wait for required CI. No deployment follows docs-only changes.

**Task boundary:** A failing chart check is a frozen source time, stale/unavailable
classification, missing append, or lost points after reload. The minimal target
is the already accepted three-symbol chart loop, not a new witness or broader
market coverage. Passing evidence is two advancing source timestamps per
symbol, retained points after reload, the focused live-smoke test, and the
reviewed PR; commit the chart evidence separately from any later product work.

## Deferred follow-up (not part of this slice)

After this recovery PR is accepted, create a separate issue and test-first plan
for Moomoo/OpenD. The retained preflight evidence says local OpenD is reachable
on `127.0.0.1:11111`, but AAPL/NVDA quotes still require the vendor Basic data
subscription and no AWS route has been proven. That follow-up must establish
the approved private host/route and two distinct source timestamps per symbol
with truthful delayed/closed/unavailable labels before it can enter a later
iteration.

## Final requirements checklist and release gate

- [ ] Existing peer online; three pings, private TCP 443 and `/health` succeed.
- [ ] `/health` shows build `76203e03476b120e149a0c06d9932849bb4d8e14`,
  `runtime_mode=live`, `paper_mode=true`, `live_trading=false`, and visible
  environment/build metadata; `tailscale serve status` targets only
  `127.0.0.1:8765`.
- [ ] Read-only live smoke passes for BTC, ETH and SOL; `/live/status` and
  `/live/state` retain honest source/freshness labels.
- [ ] Markets and Watchlist `1D / Line` charts show real advancing data and
  retain points after reload.
- [ ] No public ingress, new AWS resource, credential, order or live-execution
  change; application source tree remains unchanged.
- [ ] `python -m pytest tests/test_live_smoke.py -q`, `ruff check src tests tools`,
  `git diff --check`, and `git diff --exit-code origin/main -- src frontend
  deploy tests tools` pass; the reviewed PR has a terminal required CI result.
