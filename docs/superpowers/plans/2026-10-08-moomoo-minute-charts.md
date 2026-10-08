# Moomoo minute charts implementation plan

> **For agentic workers:** Use test-first implementation with independent boundary review. Record evidence in iteration 0037.

**Goal:** Open AAPL/NVDA from Markets or Watchlist and see real, unadjusted regular-session 1m OHLCV, revisions, appends and retained coverage.

**Architecture:** Extend the existing quote-only OpenD client, polled venue supervisor and replay-backed Instrument Workspace. Preserve raw Eastern provider labels; this scoped US 1m adapter maps the empirically verified end label to canonical start by subtracting one minute. Keep quote/order authority distinct from a displayed last price.

**Tech stack:** Existing audited Moomoo SDK, CalendarService/XNYS, LiveFeed/DuckDB replay, React chart workspace. No new dependencies.

**Spec:** Iteration 0037 user loop and September 23 feasibility evidence, resumed under the user's continuing-development instruction.

## Constraints and review focus

- Scope only US.AAPL/US.NVDA, 1m, raw adjustment, regular session, 1D chart; no synthetic OHLC or cross-gap filling.
- Source clocks and receipt clocks remain distinct. An unchanged cached candle must not renew freshness or produce repeated events.
- Monotonic local observation sequence must be explicitly identified as local, never claimed as exchange sequence. New sessions and missing intervals break continuity.
- Private supplier license, finite coverage and source state remain visible; retained history does not certify current feed availability.
- Existing QUOTE/bid-ask fences, paper=true/live=false and private loopback ingress remain enforced.
- Preserve old deployment profiles for rollback. Self-start/login and tunnel persistence are later operational work.

## Task 1 — SDK and minute normalization

Files: `src/quantmesh/moomoo/opend.py`, new `src/quantmesh/moomoo/minute_candles.py`, new `tests/test_moomoo_minute_candles.py`.
Interface: `MoomooOpenDClient.current_kline(code, *, num=390) -> dict`, matching transport method. Plain payload has code, interval=1m, autype=None marker string, session=regular, rows. `minute_candles(instrument, payload) -> list[dict]` returns timestamp (aware UTC start), provider_time_key, provider_end (aware UTC), OHLCV; validates ordered unique rows and XNYS regular boundaries.

- [x] Write SDK call-order/strict-status/cleanup tests and invalid-symbol/size tests; run them red.
- [x] Subscribe K_1M with push disabled and explicit regular session, request raw candles with bounded num; reuse existing strict SDK error handling. No trade context.
- [x] Test Eastern DST, end-to-start mapping, regular/holiday/early-close boundaries, finite positive OHLC and volume; implement scoped adapter, leaving historical/daily mapping untouched.
- [x] Run `python -m pytest tests/test_moomoo_minute_candles.py tests/test_moomoo_live_sdk.py -q` green; record results.

## Task 2 — Polling and replay provenance

Files: `src/quantmesh/live/moomoo.py`, `src/quantmesh/settings.py`, `src/quantmesh/api/workstation.py`, `deploy/aws/lightsail/deploy_release.py`, candle-focused tests plus existing deployment tests.
Interface: `MoomooVenueTransport(..., candle_num=0)` defaults off; runtime passes `Settings.moomoo_candle_num` (0..390). Approved Moomoo deployment profile enables 390. Frame kind `current_kline` carries Task 1 payload.

- [x] Write red tests for opt-in calls, overlapping windows/revisions/appends, no unchanged replay, restart/session gaps and stale rereads.
- [x] Emit changed/new rows in order; retain a bounded current window and local sequence counter. On subsequent polls only the latest observed bar may revise; older changed rows cannot rewind the live channel.
- [x] Preserve provider labels/end, adjustment/session/license metadata and local sequence origin. Historical rows have source-backed historical age, never fresh simply because polled.
- [x] Write settings/profile tests, preserve exact old environment recognition; wire the explicit setting and enable it in the approved equity profile.
- [x] Run affected live/runtime/deployment tests green; record results.

## Task 3 — Shared history and workspace display

Files: `src/quantmesh/instruments/live_history.py`, `src/quantmesh/instruments/workspace.py`, relevant instrument tests; frontend only if the existing display cannot convey evidence truthfully.

- [x] Write red tests for Moomoo 1D 5m->1m fallback, private supplier license, revision/reload, session gaps and unchanged execution fences.
- [x] Reuse existing continuity-checked replay, retaining gaps and finite observed coverage. License is `moomoo-private-market-data`, never public data.
- [x] Display metrics last in WorkspaceLiveEvidence as degraded/non-executable when a quote is absent. Preserve source/receipt/age and fail paper confirmation. Describe regular-session scope, closed/old data honestly without claiming paid entitlement delay.
- [x] Run instrument history/workspace tests green and independent review at this user-loop boundary.

## Release and acceptance

- [x] Record role outputs and targeted red/green evidence; run whole-tree Ruff/diff and relevant broad suite once at final boundary, frontend gates if touched. Final exact-head CI: 3677 Python passed / 56 skipped; 380 frontend passed.
- [x] Independent specification/standards review, at most two rounds; create one PR, await required green CI and no unresolved actionable review.
- [x] Match-head squash, compare trees, deploy exact merged commit through reviewed release tool; keep previous c8e1813 retained for rollback. PR #163 merged/deployed 69515b7; candidate/merge tree fa470ee5d8737f6822af30df79f85cdfb3f05e37 matches.
- [x] Verify API plus all four Markets/Watchlist entry paths and reload; actual provider candles across two minute boundaries must match chart values. Verify crypto chart regression, paper=true/live=false. October 8 13:56–14:03 UTC witness passes; both browser charts advance 13:58→13:59→14:00, revise within a minute, retain 30 closed bars on reload and match the recent four closed OHLCV to source brackets. The earlier closed-session pending result remains in the ledger.

Operational follow-up: reviewed current-user OpenD startup/private tunnel recovery is installed through PR #164. Configuration acceptance passes; next actual Windows login/outage remains pending without manufacturing a restart. Never store credentials in source or prompts.
