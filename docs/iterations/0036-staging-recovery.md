# Iteration 0036 — Private staging recovery and equity readiness

- Status: ACTIVE, 2026-09-17. The 0035 chart acceptance remains valid historical evidence; the current private endpoint is unreachable because the Tailscale peer is offline.
- Linked issue: [#135 — Private AWS staging workstation](https://github.com/ZP151/quantmesh/issues/135).
- Review PR: [#154 — private staging recovery](https://github.com/ZP151/quantmesh/pull/154).
- Plan: [2026-09-17 staging recovery plan](../superpowers/plans/2026-09-17-staging-recovery.md).
- Runbook: [AWS private staging](../runbooks/aws-private-staging.md).

## User action and measurable outcome

Open the existing private AWS workstation and see the accepted exact build
`76203e03476b120e149a0c06d9932849bb4d8e14`, live Hyperliquid BTC/ETH/SOL
observations and paper-only safety state. After recovery, provide the existing
Moomoo OpenD private host and entitlement state so AAPL/NVDA can be tested.

## Current diagnosis — 2026-09-17 00:29 SGT

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

## Recovery exit criteria

- The existing peer is online, responds to three pings and accepts private TCP 443.
- `/health` reports build `76203e03476b120e149a0c06d9932849bb4d8e14`, live runtime, paper enabled and live trading disabled, with visible staging environment and exact build metadata.
- The instance's `tailscale serve status` shows private HTTPS proxying only to `127.0.0.1:8765`.
- `tools/live_smoke.py --watchlist BTC,ETH,SOL` passes with read-only GETs.
- Markets and Watchlist 1D/Line pages show real Hyperliquid data times and retain points after reload.
- No new AWS resource, public ingress, credential, order or live-execution change occurs.

## Explicit non-goals

Do not redeploy a new build, change the lake, repair the 168-hour soak, expose
OpenD, add prediction credentials, claim all-market coverage, or repeat the full
601.662-second 0035 witness unless a later evidence decision requires it.

## Current stop condition

The agent cannot restore an offline AWS/Tailscale peer from the local host. An
operator must inspect or start the existing Lightsail instance and its
`tailscaled`/`quantmesh-staging.service` state. No credentials are needed in
chat; only the connection result and redacted host/status evidence are needed.

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
recovery checks remain blocked at the network boundary: the peer is still
offline, Tailscale ping and TCP 443 time out, and no `/health` response exists
to inspect. The local OpenD preflight is therefore not a recovery acceptance.

## Review checkpoint — 2026-09-17

The two-axis review of `git diff origin/main...HEAD` found that the first
version mixed a deferred OpenD preflight into the recovery slice, omitted the
Serve loopback and visible metadata gates, and did not state exact command
outcomes. The plan and ledger now classify OpenD as a separate follow-up,
require `tailscale serve status` to target only `127.0.0.1:8765`, require
environment/build metadata, and record the focused command exit codes. The
AWS recovery itself remains incomplete until the operator restores the peer;
this review is not acceptance evidence.
