# Active Goal

Status: iteration0036 ACTIVE, 2026-09-17. The 0035 AWS real-chart acceptance
and documentation closeout are complete; this goal now resumes the next route.
The current private AWS endpoint is unreachable because its Tailscale peer is
offline. No application regression is established.

## Accepted user loop

Markets and Watchlist open BTC/ETH/SOL full charts with1D/Line defaults and
actual Hyperliquid observations. The current minute revises, new minutes append,
and reload retains recorded coverage. Source, time, age and5m->1m fallback stay
visible. This is bounded observed history, not qualified full-day history or
tick-by-tick rendering. Automatic workspace reads wait5s after completion.

- Issue: https://github.com/ZP151/quantmesh/issues/144
- PR149 merged11:20:26UTC as76203e03476b120e149a0c06d9932849bb4d8e14.
- Candidatee23ab82, CI checkoutb4b6adc and squash merge share fulltree
  6e43a7754040bd35b2cef5b8094922fd90157e14. CI34751913362 passed3524Python
  tests/56skipped/9warnings,365frontend tests and all preceding gates.
- Exact private AWS deployment exited0. PID45254 started11:24:24UTC,
  loopback8765/runtime live/papertrue/live executionfalse. User's two existing
  QuantMesh IAB tabs were reloaded. Session59488 is terminal; do not redeploy it.
- Actual paired witness passed601.662s/175samples per page, six entry paths,
  11tailminutes per coin,62/55/53 BTC/ETH/SOL DOM changes matched to earlier
  own-page real frames. Reload/settled API history, keyboard/1440/390px passed.
- 296native workspace requests completed, no errors/timeouts/pending/censored
  requests. Max latency BTC5.743/ETH6.278/SOL5.737s; p95 2.579/3.450/3.000s.
  All21health observations had exact build/papertrue/livefalse. Orders/risk
  unchanged. Independent offline raw-evidence audit has no findings.
- Longest-lived sampling document loaders show minimum response-end-to-next-read
  spacing5.002073/5.002328/5.002287s, independently recomputed by root.
- Actual session97072 exited0 at12:07:43UTC; do not poll or rerun it.
  Artifacts: output/playwright/0035-aws-76203e0/attempt-2, verifier-audit.json,
  refresh-spacing.json and screenshots. HelperSHA256:
  9a3a26014624a33855824f3ae1d29990bd70c78f827b95b159390ee51a88dcff.

## Current recovery checkpoint

- Local Tailscale is healthy: backend Running, UDP/IPv4 available, Singapore
  DERP latency 6 ms.
- `quantmesh-staging.tail99d23c.ts.net` resolves to `100.90.189.16`, but the
  peer is offline with no handshake and was last seen 2026-09-14 22:32 SGT.
- Tailscale ping, TCP 443 and HTTPS `/health` all fail from the local host.
  This is a node/network boundary result, not an application health result.
- The Tailscale Machines console independently reports `quantmesh-staging` as
  **Machine not connected** and its browser SSH entry warns that the machine is
  offline. Read-only checks of the existing AWS public address also timed out
  on TCP 22/443. Console login therefore did not restore the instance or
  `tailscaled`; no public ingress was added.
- The existing Lightsail console showed the instance as Running. Rebooting that
  same instance completed, but browser SSH returned `UPSTREAM_ERROR [515]`
  before and after reboot, and a compatible SSH attempt still timed out at
  TCP/22. Lightsail Networking already allows TCP/22 to Any IPv4/IPv6 and
  browser SSH; no firewall rule was changed. The peer remained offline after
  the reboot.
- Recovery issue: [#135](https://github.com/ZP151/quantmesh/issues/135).
- Active iteration: [0036 staging recovery](../iterations/0036-staging-recovery.md).
- Plan: [2026-09-17 staging recovery plan](../superpowers/plans/2026-09-17-staging-recovery.md).

An operator must inspect or start the existing Lightsail instance and check
`tailscaled` and `quantmesh-staging.service` from the AWS console or authorized
Tailscale SSH. The agent must not invent a healthy application response while
the peer is offline.

Local OpenD is available on Windows at `127.0.0.1:11111`; the read-only probe
reported quote/history capability and `auth_required=false`. This is local
readiness evidence only. AWS still needs an approved private route or an
AWS-side OpenD placement before AAPL/NVDA can be accepted there. A direct
read-only AAPL/NVDA quote request was rejected by the vendor because Basic data
subscription is required; no quote was accepted or persisted.

## Retention evidence and limits

Existing replay-window API reports1074523rows through12:11:55UTC, with earliest
receipt2026-09-12 10:47:14UTC; previous direct snapshot896780rows is preserved.
Chart reload retained covered observations from09:44 through12:07UTC. A new
stable file-copy attempt exhausted10tries while the lake was being written;
session90210 exited1, primary unchanged. No pause, truncation, unverified copy
read or retry followed. Current growth is proven through the existing in-process
read-only API. Last direct quarantine/index check remains09:56UTC: four old
quarantines and lookup index present; do not claim a new direct count.

Earlier failures remain in the iteration ledger. In particular76203e0 attempt1
was inconclusive for an old-document request, not a proven backend20s timeout.
Planner reset the measurement slice; native document identities,18pure controls
and two review rounds resolved it. The passing actual run censored zero requests.
A ten-minute witness does not certify indefinite availability.

## Next frontier after recovery

Current branch: `docs/135-staging-recovery` from `origin/main@c74ea03`;
review PR: [#154](https://github.com/ZP151/quantmesh/pull/154).
Complete the recovery gate with the normal reviewed PR workflow. Preserve
divergent local `main`; new branches start from `origin/main`. Retain `e185c3b`
and `4022942` rollback releases; do not change infrastructure or execution.

After recovery, the next bounded slice is Moomoo/OpenD readiness for AAPL/NVDA: identify the existing
licensed host, approved private AWS route and actual quote entitlement. The
operator connection-information question is pending; no credentials are needed
in chat. Windows localhost probes cannot establish remote absence. Only after
readiness is established, write the exact-file plan and issue. An open-session
real-data witness and truthful delayed/closed/unavailable labels are required;
existing five-second polling is not native tick push. Then prediction venues
and qualified historical evidence follow sequentially in docs/ITERATION_PLAN.md.

Keep0021soak and issues135/132/127 independent. No public OpenD exposure, paid
subscriptions, orders, strategy promotion or opportunistic maintenance changes.
Standing reviewed merge/private-deployment authority remains in the user's
request and .codex/prompts/goal.md; no further confirmation for this scope.
