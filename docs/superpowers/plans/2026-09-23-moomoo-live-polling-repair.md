# Moomoo quote-only live polling follow-up

Status: implemented locally; targeted and broad verification pass; both
independent review rounds have no findings. Actual local quote/ticker progression observed
on 2026-09-23 at 15:40–15:41 UTC. AWS/browser acceptance remains separate.
Issue: [#156](https://github.com/ZP151/quantmesh/issues/156).

Release-authority update: on September 24 Singapore / September 23 UTC the
user explicitly restored CI and authorized merge/deployment to the new 8 GB
private host after all checks pass. This supersedes the initial pause clauses
below. Candle/chart acceptance remains a separate follow-up.

## User action and scope

Opening an AAPL/NVDA instrument from Markets or Watchlist should consume
read-only market observations without requiring a trading context or failing
because the adapter omitted an SDK subscription. Success metric: the real
client/transport call chain produces valid quote and ticker frames from a
subscription-enforcing fake SDK with trade-context creation forbidden, and
preserves source timestamps, five-second polling and stale/reconnect semantics.
Actual AWS/open-session observations are a separate acceptance step.

## Findings motivating this slice

- `MoomooVenueTransport.connect()` still calls the legacy general `probe()`.
  The newly repaired readiness command does not change that live path.
- `SdkTransport.rt_ticker()` calls `get_rt_ticker()` without registering a
  TICKER subscription. The official [ticker contract](https://openapi.moomoo.com/moomoo-api-doc/en/quote/get-ticker.html)
  requires this, just as quote reads require QUOTE registration.
- Synchronous live polling still runs in threads; readiness's process deadline
  does not automatically contain live-poll SDK calls. Record this distinction
  and separately scope any persistent worker/lifecycle change.

## Implementation sequence

- [x] Add red tests through the real client/transport: connecting must use
   `probe_market_data()`, never construct a trade context or call account APIs.
- [x] Add TICKER subscription/order/denial/malformed-status/context-close tests.
   Preserve typed errors and source rows; reuse existing strict SDK helpers.
- [x] Switch only the polling capability path and implement the missing SDK
   subscription with Python push disabled. Update test clients explicitly;
   never fall back to the general trade probe for legacy clients.
- [x] Verify `tests/test_live_moomoo.py`, provider boundary tests, polling
   reconnect/stale tests, and the existing no-fabricated-bid/ask invariant.
- [x] Independent review (maximum two rounds), iteration checkpoint, broad gates
   at the commit boundary. CI remains paused; no push, merge or deployment.

Exact implementation files: `src/quantmesh/live/moomoo.py` and
`src/quantmesh/moomoo/opend.py`. Tests: `tests/test_moomoo_live_sdk.py`
and the explicitly quote-only fake in `tests/test_live_moomoo.py`.
Red: `python -m pytest tests/test_moomoo_live_sdk.py -q` failed all eight
new cases at the missing subscription/trade-probe boundary. Green:
`python -m pytest tests/test_moomoo_live_sdk.py tests/test_live_moomoo.py
tests/test_moomoo_readiness_sdk.py tests/test_moomoo_opend.py -q --basetemp
output/pytest-polling-focused` passed 73, skipped 1.

### Direct AWS acceptance blockers found during execution

Ruling (Planner/Product, 2026-09-23): the user's requested AWS equity loop
also needs the Linux readiness worker and an explicit deployment profile.
These directly block this user action; add only the following bounded repairs:

- [x] `readiness_worker.py`: restore the actual OS user home when absent before
  SDK import. The subprocess environment scrubber stays unchanged. Linux SDK
  logging requires this standard value; never replace it with a task directory.
  Regression in `test_moomoo_readiness_sdk.py` failed before the fix. Repeat
  actual Linux readiness using the isolated audited SDK closure.
- [x] `deploy/aws/lightsail/deploy_release.py`: optional `--moomoo-market-data`
  requires `--live-market-data`, installs existing constrained `[moomoo]`
  extra and writes only AAPL/NVDA, US, loopback:11111 and five-second polling.
  Canonical profile comparison recognizes retained equity releases for rollback.
  Do not create a tunnel, change credentials or enable order authority here.
  Tests in `test_aws_staging_assets.py` cover install/profile, default-off,
  incompatible flags, reactivation and rollback. Four missing-feature cases
  failed before implementation; the combined deployment/readiness rerun passed
  84 after updating the existing CLI fake to assert the new flag defaults false.
- [x] Final independent second review includes both acceptance-blocking repairs;
  rerun affected files and reconcile their current case counts with the broad
  suite started before these additions. No application activation while CI is paused.

Final local gate: all 149 files covered, 3582 passed/61 skipped (3643 collected),
including the explicit 84-test rerun of changed deployment/worker files. Ruff
and diff checks pass. Evidence: `output/0037-polling-verification-final.json`.

## Non-goals and later acceptance

No provider UI redesign, public ports, paid subscriptions, secrets, order
placement, broader watchlist, persistent-process rewrite or Hyperliquid changes.
Do not infer tick-push from TICKER registration: the application still polls.
Before real acceptance, verify the configured private OpenD route and actual
rights, at least two progressing source timestamps per equity, chart updates
and truthful unavailable/delayed/closed states. Preserve the independent
8 GB observation and rollback/reboot checklist for later operational review.
