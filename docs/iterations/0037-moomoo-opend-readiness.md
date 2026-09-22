# Iteration 0037 — Private Moomoo/OpenD AAPL/NVDA readiness

- Status: ACTIVE, 2026-09-23. The code-only readiness slice is in progress while
  the 8 GB capacity observation remains open.
- Linked issue: [#156 — Private Moomoo/OpenD AAPL/NVDA readiness](https://github.com/ZP151/quantmesh/issues/156).
- Plan: [Moomoo readiness probe plan](../superpowers/plans/2026-09-23-moomoo-readiness-probe.md).
- Depends on: [iteration 0036 capacity gate](0036-staging-recovery.md), which
  remains a deployment and merge gate rather than a blocker on local code work.

## User action and measurable outcome

An operator runs `quantmesh-moomoo readiness --json` and receives a redacted,
machine-readable report for the private OpenD endpoint and `US.AAPL`/
`US.NVDA`. The command checks the TCP route before SDK use, probes only quote
and daily history, records each symbol independently and exits non-zero for a
missing route, provider, entitlement or malformed payload. It never checks or
unlocks an order session.

The code slice is complete when the report boundary and CLI tests pass, Ruff
and diff checks are clean, and the report distinguishes `route_unavailable`,
`sdk_missing`, `auth_required`, `unavailable`, `protocol_error`, `partial` and
`ready` without persisting credentials or quote data.

## Implementation checkpoint — 2026-09-23

Commit `50b2ddb` adds `ReadinessReport`, `SymbolReadiness` and
`run_readiness(...)`. It validates quote and history payloads through the
existing Moomoo adapter, requires at least one daily history row and preserves
per-symbol failures. A capability response that advertises order access is
reported but never called by this boundary.

The follow-up CLI changes are on the current feature branch and add the
private TCP preflight plus stable text/JSON output. The local focused suite
currently passes `69 passed, 1 skipped`; Ruff and `git diff --check` pass. CI
is intentionally paused, so no remote check, push, merge or deploy is claimed.

## Current operator evidence and blocker

The new AWS host is healthy for the accepted Hyperliquid BTC/ETH/SOL path, but
the read-only route from AWS `100.86.41.64` to the Windows OpenD host
`100.91.234.68:11111` currently returns `CLOSED`. This is recorded as
`route_unavailable`; no public OpenD port is opened and no quote is treated as
real. Local Windows OpenD capability and the existing Basic-data rejection for
AAPL/NVDA remain separate evidence.

After an approved private route or AWS-side licensed OpenD placement is
available, run the JSON probe during an open US session. Acceptance requires
at least two distinct source timestamps for both AAPL and NVDA, explicit
delayed/closed/unavailable labels, the existing five-second polling contract,
paper mode unchanged and live execution disabled. A last-price-only response
remains research data; it cannot bless a paper order.

## Explicit non-goals

Do not open public ingress, install credentials in the repository, enable live
trading, place an order as a connectivity test, fabricate bid/ask values, or
claim AWS equity acceptance before the route and entitlement witness exists.
The 8 GB 24-hour capacity/freshness, rollback and reboot gates remain in
iteration 0036 and are reviewed before deployment or merge.
