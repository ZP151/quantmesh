# Moomoo quote-only live polling follow-up

Status: next bounded slice after the readiness repair checkpoint; not implemented.
Issue: [#156](https://github.com/ZP151/quantmesh/issues/156).

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

1. Add red tests through the real client/transport: connecting must use
   `probe_market_data()`, never construct a trade context or call account APIs.
2. Add TICKER subscription/order/denial/malformed-status/context-close tests.
   Preserve typed errors and source rows; reuse existing strict SDK helpers.
3. Switch only the polling capability path and implement the missing SDK
   subscription with Python push disabled. Update test clients explicitly;
   never fall back to the general trade probe for legacy clients.
4. Verify `tests/test_live_moomoo.py`, provider boundary tests, polling
   reconnect/stale tests, and the existing no-fabricated-bid/ask invariant.
5. Independent review (maximum two rounds), iteration checkpoint, broad gates
   at the commit boundary. CI remains paused; no push, merge or deployment.

## Non-goals and later acceptance

No provider UI redesign, public ports, paid subscriptions, secrets, order
placement, broader watchlist, persistent-process rewrite or Hyperliquid changes.
Do not infer tick-push from TICKER registration: the application still polls.
Before real acceptance, verify the configured private OpenD route and actual
rights, at least two progressing source timestamps per equity, chart updates
and truthful unavailable/delayed/closed states. Preserve the independent
8 GB observation and rollback/reboot checklist for later operational review.
