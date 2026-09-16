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

---

### Task 1: Confirm the private-node boundary

**Files:** `docs/iterations/0036-staging-recovery.md`, `docs/goals/ACTIVE.md`.

- [ ] Run `tailscale status --json`, `tailscale netcheck`, `tailscale ping --c 3 quantmesh-staging`, `Resolve-DnsName quantmesh-staging.tail99d23c.ts.net`, and `Test-NetConnection quantmesh-staging.tail99d23c.ts.net -Port 443`.
- [ ] Record node online state, last-seen time, resolved address, TCP 443 and `/health`. The 2026-09-17 baseline is local Tailscale healthy, Singapore DERP reachable, DNS `100.90.189.16`, peer offline since 2026-09-14, no handshake, ping timeout and TCP 443 failure.
- [ ] Commit the evidence checkpoint; do not alter AWS or Tailscale from the agent host.

### Task 2: Operator restores the existing node

**Files:** `docs/runbooks/aws-private-staging.md`, `docs/iterations/0036-staging-recovery.md`.

- [ ] Inspect the existing `quantmesh-staging` Lightsail instance. If stopped or unhealthy, the operator starts or recovers it; no new instance is created.
- [ ] From the instance console or authorized private SSH, inspect `sudo systemctl is-active tailscaled quantmesh-staging.service`, `tailscale status`, and `curl --fail --silent http://127.0.0.1:8765/health`.
- [ ] If the operator elects to restart after inspection, restart only the existing service and repeat loopback health. Do not change release, environment, firewall, Serve target or lake.
- [ ] From Windows require three successful Tailscale pings and private TCP 443 before application checks. Otherwise keep the blocker open.

### Task 3: Verify the accepted release and live read-only surface

**Files:** `docs/iterations/0036-staging-recovery.md`; existing contract `tests/test_live_smoke.py`.

- [ ] Check `https://quantmesh-staging.tail99d23c.ts.net/health` and require build `76203e03476b120e149a0c06d9932849bb4d8e14`, `runtime_mode=live`, `paper_mode=true`, and `live_trading=false`.
- [ ] Run `python tools/live_smoke.py --url https://quantmesh-staging.tail99d23c.ts.net --watchlist BTC,ETH,SOL --timeout 10` with `PYTHONPATH=src`; require `LIVE SMOKE PASSED` and read-only GETs only.
- [ ] Inspect `/live/status` and `/live/state`; record real/delayed/stale/unavailable labels and source times honestly.

### Task 4: Verify charts and close recovery

**Files:** `docs/iterations/0036-staging-recovery.md`, `docs/goals/ACTIVE.md`.

- [ ] Open Markets and Watchlist → BTC, ETH and SOL with `range=1d&mode=line`; confirm Hyperliquid, real classification, advancing source time and freshness.
- [ ] Observe a short recovery window and reload; require two advancing source timestamps per symbol and retained points. Do not call this a new ten-minute witness.
- [ ] Run `python -m pytest tests/test_live_smoke.py -q`, `ruff check src tests tools`, and `git diff --check`.
- [ ] Open a reviewed documentation/evidence PR from `origin/main`; wait for required CI. No deployment follows docs-only changes.

### Task 5: Start Moomoo/OpenD readiness after recovery

**Files:** `docs/ITERATION_PLAN.md`, `docs/iterations/0036-staging-recovery.md`; inspect `src/quantmesh/settings.py`, `src/quantmesh/moomoo/opend.py`, `src/quantmesh/live/moomoo.py`, and `docs/adr/0004-moomoo-opend-adapter-boundary.md`.

- [ ] Capture only the existing OpenD private host, port, market-session and entitlement state; never request password or OTP.
- [ ] Verify private reachability and run the typed probe. A failed probe remains `unavailable`, never fixture data.
- [ ] Only after reachability is proven, write the exact-file test-first plan and issue. The exit metric is two distinct source timestamps for AAPL and NVDA during an open session, with truthful delayed/closed/unavailable labels.
