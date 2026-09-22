# Active Goal

Status: iteration0036 ACTIVE, 2026-09-23. The 0035 AWS real-chart acceptance
and the 8 GB migration's short acceptance are complete; this goal remains
active until the new host's sustained capacity gate is closed and the separate
Moomoo/OpenD route is ready. A code-only iteration 0037 readiness slice is now
underway; it does not waive the capacity gate for deployment or merge.

## 8 GB capacity handoff — observation is a prerequisite

The authoritative private origin is now
`https://quantmesh-staging-8gb.tail99d23c.ts.net`, serving exact merged build
`33aa0521da8305001e0bd62b377c53738c85e11d`. The restored dataset passed archive
hash, WAL recovery, JSON payload validation, 13-check read-only smoke, chart
entry-path, and controlled restart checks. The host currently reports about
6.0 GiB available RAM, no swap, an active service and zero automatic restarts.
These are the completed migration facts recorded in [PR #159](https://github.com/ZP151/quantmesh/pull/159);
the PR remains open because its CI was intentionally cancelled while the
operator prepares capacity work.

The migration did not fill the old collection gap (the stopped source ends on
2026-09-17 and the new collector resumes on 2026-09-22), and it did not prove
the old 90-second shutdown behavior. A local, read-only observer started on
2026-09-22 16:21:42 UTC records five-minute smoke, quote/candle freshness,
health safety flags, service restarts, memory, swap, disk and recent journal
lines for 24 hours. The observation gate remains open until the complete log
is reviewed. No later provider or UI acceptance may treat this short sample as
indefinite availability.

The gate requires all of the following before the next provider slice:

- every sample keeps build `33aa0521`, `paper_mode=true` and
  `live_trading=false`;
- BTC, ETH and SOL quote/candle observations remain real and under the
  observer's 60-second freshness limit;
- the service stays active with no automatic restarts, OOM evidence or swap
  activity, and capacity/disk trends are reviewed;
- an operator-approved old-host rollback rehearsal and a new-host reboot test
  are separately completed or explicitly deferred with a recorded reason;
- the evidence is mirrored into iteration 0036 before its closeout.

The old origin is retained as a rollback resource and is not deleted. The
historical gap remains an explicit limitation; any backfill must use a
source-backed, lineage-preserving dataset and cannot be inferred from the
live replay.

## Iteration 0037 development checkpoint — private Moomoo/OpenD readiness

The current feature branch adds a read-only `quantmesh-moomoo readiness
--json` command for issue [#156](https://github.com/ZP151/quantmesh/issues/156).
It checks the private TCP route before SDK use, probes only quote and daily
history for `US.AAPL` and `US.NVDA`, and preserves route, SDK, auth,
entitlement and protocol failures as explicit statuses. The report never
opens an order context or persists quote/account data. Plan and acceptance
details are in [iteration 0037](../iterations/0037-moomoo-opend-readiness.md).

The AWS-to-Windows OpenD route (`100.86.41.64` to `100.91.234.68:11111`) is
currently closed, so the operational result is `route_unavailable`; no public
port is opened. Local focused verification is green (`96 passed, 1 skipped`,
Ruff and diff check passed). CI remains paused and this code work is not a
deployment, merge or real-equity acceptance claim.

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
- `quantmesh-staging.tail99d23c.ts.net` resolves to `100.90.189.16`; after a
  cold stop/start of the existing Lightsail instance, the peer is online and
  accepts private TCP 443.
- HTTPS `/health` reports build
  `76203e03476b120e149a0c06d9932849bb4d8e14`, runtime `live`, `paper_mode=true`
  and `live_trading=false`.
- The earlier Tailscale Machines snapshot and public-address checks captured the
  pre-recovery outage: the console showed **Machine not connected** and TCP
  22/443 timed out. After the cold start, local `tailscale status` shows the
  peer `active` with a direct IPv6 path; no public ingress was added.
- The instance initially looped on startup because its 1.9 GiB host had no swap
  while the 2.4 GiB live DuckDB lake held about 3.7M rows. Kernel OOM logs
  identified `quantmesh-workstation` as the killed process. A persistent 2 GiB
  swapfile on the existing disk restored startup; this is an operational
  mitigation pending a source-level retention guard.
- `tools/live_smoke.py --watchlist BTC,ETH,SOL` passed 13 read-only checks in
  0.9s. `/live/state` contains current real Hyperliquid quote/trade/metrics/L2
  and candle observations for all three instruments, and `/live/status` reports
  each source connected.
- Browser acceptance at the deployed BTC 1D/Line path showed `Live proven`,
  source `hyperliquid`, `real · real`, WebSocket stream and about 3s age while
  current-minute OHLC rows advanced.
- Recovery issue: [#135](https://github.com/ZP151/quantmesh/issues/135).
- Active iteration: [0036 staging recovery](../iterations/0036-staging-recovery.md).
- Plan: [2026-09-17 staging recovery plan](../superpowers/plans/2026-09-17-staging-recovery.md).

The recovery gate is now superseded operationally by the 8 GB host, but the
capacity observation above is still open. The agent must not treat a short
smoke, extra RAM or the former swap mitigation as a permanent stability claim.

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

The recovery found the production failure mode behind that limit: the running
service opened the full DuckDB lake before any production prune call, and the
old host had no swap. The retention setting, bounded latest-state lookup and
startup deadline are now in merged `33aa0521`; the new host's sustained
observation is the remaining evidence gate. The old swapfile remains a
reversible host mitigation and is not part of the new-host acceptance.

## Next frontier after migration

Keep the observation, rollback and reboot gates in front of new provider work.
Preserve the old release and verified backups; do not change infrastructure or
execution while the capacity evidence is incomplete. While the gate runs,
continue only code and local verification for Moomoo/OpenD readiness. After it
closes, identify the existing licensed host, approved private AWS route and
actual quote entitlement, then run the probe during an open session. The
operator connection-information question is pending; no credentials are needed
in chat. Windows localhost probes cannot establish remote absence. An
open-session real-data witness and truthful delayed/closed/unavailable labels
are required; existing five-second polling is not native tick push. Then
prediction venues and qualified historical evidence follow sequentially in
docs/ITERATION_PLAN.md.

Keep0021soak and issues135/132/127 independent. No public OpenD exposure, paid
subscriptions, orders, strategy promotion or opportunistic maintenance changes.
Standing reviewed merge/private-deployment authority remains in the user's
request and .codex/prompts/goal.md; no further confirmation for this scope.
