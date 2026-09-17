# Iteration 0036 — Private staging recovery and equity readiness

- Status: ACTIVE, 2026-09-17. The private recovery gate closed after the existing Lightsail node was cold-started and its service was made healthy. This iteration remains active for the lake-retention guard and the separate Moomoo/OpenD readiness slice.
- Linked issue: [#135 — Private AWS staging workstation](https://github.com/ZP151/quantmesh/issues/135).
- Review PR: [#154 — private staging recovery](https://github.com/ZP151/quantmesh/pull/154).
- Plan: [2026-09-17 staging recovery plan](../superpowers/plans/2026-09-17-staging-recovery.md).
- Runbook: [AWS private staging](../runbooks/aws-private-staging.md).

## User action and measurable outcome

Open the existing private AWS workstation and see the accepted exact build
`76203e03476b120e149a0c06d9932849bb4d8e14`, live Hyperliquid BTC/ETH/SOL
observations and paper-only safety state. Moomoo/OpenD host and entitlement
readiness is tracked by a separate follow-up and is not part of this outcome.

## Initial diagnosis — 2026-09-17 00:29 SGT (historical)

The Windows Tailscale client is healthy: backend `Running`, local node online,
UDP/IPv4 available and Singapore DERP latency 6 ms. DNS resolves
`quantmesh-staging.tail99d23c.ts.net` to `100.90.189.16`. The peer is offline,
last seen 2026-09-14 22:32 SGT, with no handshake. Tailscale ping and TCP 443
fail, so HTTPS `/health` times out before an application response. This is a
node/network boundary failure, not evidence of an application regression.

## Control-plane cross-check — 2026-09-17

The Tailscale Machines console independently shows `quantmesh-staging` as
**Machine not connected**, with the same last-seen time (2026-09-14 22:32
GMT+8). Its SSH entry warns that the machine appears offline, so starting an
SSH session cannot provide loopback evidence. The console login itself is
healthy but does not start the AWS instance or `tailscaled`; recovery still
requires the existing Lightsail instance to be started or inspected from its
AWS/authorized host console.

The public AWS address was also checked read-only: TCP 22 and 443 timed out and
an HTTPS `/health` request produced no response. No public ingress is being
opened; this only confirms that the current outage is below the application
layer.

## Operator recovery attempt — 2026-09-17 02:08 SGT

The existing Lightsail console showed `quantmesh-staging` as **Running**. A
reboot of that same instance completed, but the browser-based SSH client
returned `UPSTREAM_ERROR [515]` before and after the reboot. A compatible SSH
attempt to the displayed public address (`47.128.230.51`) then timed out at
TCP/22. The Lightsail Networking page confirms that TCP/22 is already allowed
to Any IPv4/IPv6 address and to Lightsail browser SSH, so no firewall rule was
changed.

After the reboot, the Tailscale client still reports `quantmesh-staging` as
offline and the control plane still reports **Machine not connected** with
Last seen 2026-09-14 22:32 GMT+8. The instance is therefore not operationally
reachable for the required in-host `tailscaled`, application health or Serve
checks; the recovery gate remains blocked below the application layer.

## Recovery completion and live-data evidence — 2026-09-17 02:12–02:23 SGT

The existing instance was then stopped and started from the Lightsail console.
Its dynamic public address changed, and the same instance became reachable over
SSH. No new instance or ingress rule was created. In-host checks showed
`tailscaled` enabled and active, `tailscale serve status` exposing only the
tailnet HTTPS origin and proxying to `http://127.0.0.1:8765`, and the Tailscale
peer online at `100.90.189.16`.

The first application start exposed the actual service failure: the 1.9 GiB
host had no swap, while `live/updates.duckdb` contained about 3,699,148 rows
(about 2.4 GiB on disk) from BTC/ETH/SOL. The kernel repeatedly killed the
`quantmesh-workstation` process during startup while DuckDB migrated/indexed the
lake. This explains the earlier browser `UPSTREAM_ERROR [515]`; it was an
instance memory failure, not fabricated chart data or a Tailscale Serve error.

As an operational recovery measure on the existing disk, a 2 GiB `/swapfile`
was created with mode `0600` and persisted in `/etc/fstab`. After the service
restart, the process completed lake startup and remained active. The health
response was:

```json
{"status":"ok","project":"QuantMesh","version":"0.1.1rc1","paper_mode":true,"live_trading":false,"deployment":{"environment":"staging","build_ref":"76203e03476b120e149a0c06d9932849bb4d8e14"},"runtime_mode":"live"}
```

The private route then passed `tailscale ping`, TCP 443 and the read-only
`Invoke-RestMethod .../health` check. The read-only live smoke command passed
all 13 checks in 0.9 seconds for BTC, ETH and SOL. `/live/state` showed real
Hyperliquid quote, trade, metrics, L2 and 1-minute candle observations with
current receipt times; `/live/status` reported the three sources connected.

The browser acceptance was performed against the deployed URL after the API
checks. The BTC `range=1d&mode=line` workspace rendered `Live proven`, live
source `hyperliquid`, classification `real · real`, `WebSocket` stream and a
roughly 3-second age. The observed OHLC table advanced through the current
minutes and the 1D/Line controls were selected. The already accepted 0035
five-minute witness also recorded two current-minute candle revisions followed
by a later-minute candle append for BTC, ETH and SOL; this recovery check
re-established the same real-data path without claiming a new sustained
witness. Status rows may age independently while the live market kinds stay
fresh.

The swap is a host mitigation, not the durable fix. `LiveBuffer.prune()` exists
but production startup has no bounded-lake sweep, and the current service
constructs the buffer with its default retention. A follow-up implementation
slice must make retention configurable, invoke it on a safe cadence, and prove
startup behavior against a growing lake before this iteration can be closed.

Issue #135 remains open for the operator-deferred Lightsail firewall acceptance
recorded in its existing ledger. This recovery did not inspect, remove or add
public HTTP/SSH rules, and closing the service/reachability gate must not be
read as closing that issue.

## Recovery exit criteria

- The existing peer is online, responds to three pings and accepts private TCP 443.
- `/health` reports build `76203e03476b120e149a0c06d9932849bb4d8e14`, live runtime, paper enabled and live trading disabled, with visible staging environment and exact build metadata.
- The instance's `tailscale serve status` shows private HTTPS proxying only to `127.0.0.1:8765`.
- `tools/live_smoke.py --watchlist BTC,ETH,SOL` passes with read-only GETs.
- Markets and Watchlist 1D/Line pages show real Hyperliquid data times and retain points after reload.
- No new AWS resource, public ingress, credential, order or live-execution change occurs.
- Existing public firewall acceptance for issue #135 remains an explicit open
  operator item; no firewall rule was changed by this recovery.

## Explicit non-goals

Do not redeploy a new build, change the lake, repair the 168-hour soak, expose
OpenD, add prediction credentials, claim all-market coverage, or repeat the full
601.662-second 0035 witness unless a later evidence decision requires it.

## Current stop condition

The AWS/Tailscale recovery gate is closed, but iteration closeout is held by the
unbounded-lake risk identified during recovery. The next bounded slice must
ship the retention guard and repeat the health, live-smoke and browser gates
without relying on another OOM recovery. The separate Moomoo/OpenD route and
quote-entitlement work remains deferred as described below. No credentials are
needed in chat; only connection results and redacted host/status evidence are
needed.

## OpenD preflight evidence — deferred follow-up, 2026-09-17

This evidence is preparatory only and does not advance the AWS recovery slice;
the recovery gate above must close before a separate Moomoo/OpenD issue and
test-first plan starts.

The existing Windows `moomoo_OpenD.exe` is running as PID 40028 and listens on
`127.0.0.1:11111`; port 11112 is not listening. The read-only
`quantmesh-moomoo probe` completed successfully and reported
`quote=True`, `history_kline=True`, `auth_required=False`. The probe opened and
closed the vendor contexts cleanly; no order or account operation was issued.
This proves local OpenD capability only. It does not prove that AWS can reach
Windows localhost, so the approved private route or an AWS-side OpenD placement
remains the next readiness dependency.

A read-only `stock_quote(["US.AAPL", "US.NVDA"])` attempt then failed closed with
the vendor response: `Before calling the Get Real-time Quotes interface, please
subscribe to Basic data first.` No quote values were accepted, persisted or
shown as real. The local OpenD process is therefore reachable, but the required
AAPL/NVDA quote entitlement is not yet ready.

After installing the repository-declared `moomoo-api==10.10.7008` package in
the local development environment, the same probe was rerun on 2026-09-17
00:52 SGT and passed with `quote=True`, `history_kline=True`,
`auth_required=False`; the read-only AAPL/NVDA request still failed closed with
the same Basic-data entitlement message. Targeted regression checks then passed
`82 passed, 1 skipped` (`test_moomoo_cli.py`, `test_moomoo_opend.py` and
`test_live_smoke.py`), and Ruff passed. This remains local capability evidence;
it does not establish an AWS route or accept fixture data as real.

## Local verification checkpoint — 2026-09-17

The exact focused commands and outcomes are:

```text
python -m pytest -q --basetemp=output/pytest-temp-0036-2 tests/test_moomoo_cli.py tests/test_moomoo_opend.py tests/test_live_smoke.py
82 passed, 1 skipped in 1.02s (exit 0)
ruff check src tests tools
All checks passed! (exit 0)
git diff --check
exit 0
git diff --exit-code origin/main -- src frontend deploy tests tools
exit 0 (APPLICATION_TREE_UNCHANGED)
```

The eight changed tracked Markdown/document files decoded as UTF-8. The remote
recovery checks above are now green; the remaining verification gap is the
source-level retention guard and its deployment witness. The local OpenD
preflight remains separate from AWS acceptance.

## Review checkpoint — 2026-09-17

The two-axis review of `git diff origin/main...HEAD` found that the first
version mixed a deferred OpenD preflight into the recovery slice, omitted the
Serve loopback and visible metadata gates, and did not state exact command
outcomes. The plan and ledger now classify OpenD as a separate follow-up,
require `tailscale serve status` to target only `127.0.0.1:8765`, require
environment/build metadata, and record the focused command exit codes. The
AWS recovery itself is accepted by the evidence above. This review still does
not close the iteration because the swap mitigation must be replaced by a
bounded-lake implementation and the OpenD follow-up remains outstanding.

## Retention startup correction checkpoint — 2026-09-17

The first retention deployment from PR [#155](https://github.com/ZP151/quantmesh/pull/155)
activated `ab90f92` but failed closed during `LiveFeed` startup. The retained
`market_updates` lake made the prior `latest()` window query exhaust the
1.4 GiB process limit before the health gate could answer. The service was
stopped, and the previously accepted `76203e0` release was restored with its
private Tailscale Serve path; no failed release is counted as deployed.

Issue [#157](https://github.com/ZP151/quantmesh/issues/157) records the failure
and acceptance criteria. The follow-up PR
[#158](https://github.com/ZP151/quantmesh/pull/158) changes latest-state
selection to a bounded grouped `MAX(local_seq)` lookup, adds a 100,000-row
regression under a 32 MiB DuckDB limit, and makes the 420-attempt health gate a
seven-minute elapsed deadline. Focused local tests are green; the exact merged
head still requires full CI and a fresh AWS health, read-only live-smoke and
browser chart witness before this checkpoint can close.
