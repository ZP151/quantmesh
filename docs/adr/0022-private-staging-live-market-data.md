# ADR-0022 — Read-only market data in private staging

- Status: accepted for iteration 0034 implementation, 2026-09-12
- Extends: ADR-0021 private staging boundary; preserves ADR-0014 and ADR-0020

## Decision

The operator approved replacing the deployed demo-only acceptance loop with a
bounded real-data loop after reviewing iteration 0034. Keep demo as the default
deployment profile. An explicit `--live-market-data` deployment selects public
Hyperliquid BTC/ETH/SOL observation through the existing `--live` runtime.
No broker, wallet, credential, order or live-execution authority is added.

The systemd unit supplies default demo arguments; a canonical per-release
environment selects the live profile. Live lake/order/decision roots are under
`/var/lib/quantmesh/live`, separate from the retained demo root. An old release
without a profile override still starts in demo mode through the same unit.
Activation verifies exact build, expected runtime, paper true and live trading
false. Retained activation infers the canonical saved profile, never rewrites
its environment and restores the previous release on failed health.

Private Tailscale HTTPS, exact browser-origin checks, loopback binding and
retained-release rollback remain mandatory. No public service or new AWS
resource is introduced. Installing the updated unit and releasing a new build
are explicit iteration deployment steps, not side effects of a Git merge.

## Timestamp and research semantics

Quotes, trades and book observations use the older of source time and receipt
time to measure display age. A source clock more than five seconds ahead of
receipt is unavailable, allowing small clock skew without claiming future
observations are current. Metrics lacking exchange timestamps and candle
interval identifiers retain receipt-age semantics; they cannot satisfy the
upstream-timestamp acceptance witness. Browser-cached prices age without
requiring successful polling. A fresh metric cannot freshen an old quote.

These observations do not establish trusted historical datasets, calendar
coverage, calibrated forecasts or qualified DecisionPackets. Missing history
and forecasts remain unavailable. Data-plane roots and the independent soak
are not modified. Existing risk/quote-fence authority is unchanged.

## Rollback and acceptance

Retain the original `4022942` demo release. Validate an exact candidate via
the same loopback/private HTTPS health contract, then separately record a
five-minute source/browser/replay witness. A successful merge or healthy
process is not proof of connected market data. Rollback changes the release
symlink and restarts the same service; it does not delete either data root.
