# Iteration 0035 — Real charts from Markets and Watchlist

- Status: approved user request; implementation plan prepared, 2026-09-12.
- Issue: [#144](https://github.com/ZP151/quantmesh/issues/144).
- Branch: `codex/0035-live-instrument-charts`, from `origin/main@2a50565`.
- Plan: `docs/superpowers/plans/2026-09-12-live-instrument-charts.md`.

## User action and measurable outcome

From Markets or Watchlist on the existing private AWS workstation, open BTC,
ETH or SOL and inspect a full-size price line built from actual Hyperliquid
observations. Default to the current-day window and line mode, retain candle
switching, and show the current one-minute close update and a later candle
append without reload. Reload must retain actual recorded coverage. Observe
source times and coverage; do not imply complete-day or multi-month history.

## Planner and investigation evidence

The operator explicitly requested continued development and real streaming
charts through the previous Markets/Watchlist entry points. This existing
chart/data path is a bounded vertical slice before Moomoo readiness work.

Actual AWS `e185c3b` inspection: Markets lists BTC/ETH/SOL with empty marks and
outdated synthetic/demo descriptions. Watchlist's decision inbox is empty.
BTC click-through falls back to CockpitDetail with only a small four-close
chart instead of the existing full instrument chart.

Independent backend diagnosis: Hyperliquid subscribes 1m candles, but
LiveHistoryService permits only preferred/coarser resolution (minimum 5m for
1D), so real collected candles cannot satisfy any chart range. The default
workspace range is 6M. Existing replay/history composition and chart renderer
can be reused; no new provider, chart package or data-plane subsystem.

## Quant Researcher / design

- Permit an explicitly labelled Hyperliquid 1m replay fallback for 1D only when
  no preferred/coarser series exists. Preserve manifest preference, sequence,
  candle-open continuity, source/receipt bounds, gap/disconnect barriers and
  the minimum two-interval requirement. Other ranges retain their contract.
- Render actual candle closes (including the changing current candle), with
  line/candle controls and real coverage/interval/source labels. Short recorded
  coverage is not a full day, trusted history, forecast or promoted strategy.
- In live mode, Markets and Watchlist expose the configured feed instruments,
  actual quotes and freshness through shared existing live utilities. Keep
  registered decision watches intact and distinguish them from feed coverage;
  do not silently create favorites or paper decisions.
- No synthetic fallback, fabricated historical points or generated volume.
  Missing/collecting history has an explicit state. Existing stale/disconnect
  semantics apply to charts and source status; recovering cannot bridge a gap.

## Acceptance

- [ ] Backend RED/GREEN covers actual 1m replay through history/workspace APIs,
  preferred resolution, revisions, append, reload, gaps and unavailable ranges.
- [ ] Both Markets and Watchlist expose BTC/ETH/SOL chart entry points in live
  mode with actual quote provenance/freshness and accurate non-demo wording.
- [ ] Default live chart is 1D/line; explicit URL choices and demo behavior remain
  intact. Current candle changes without reload; a new minute appends a point.
- [ ] Keyboard, desktop/mobile and accessible chart table/attribution verified.
- [ ] Final source checks, bounded independent review and required CI pass;
  integrate through PR and verify the exact approved AWS deployment.
- [ ] Actual AWS navigation/chart update/reload witness is recorded separately
  from controlled disconnect/recovery tests. Paper true/live false; no orders.
- [ ] Update roadmap/ACTIVE and retain Moomoo/OpenD readiness as next frontier.

## Boundaries and authority

Existing user approval covers this readonly application iteration and the
existing private AWS update after review and tests. No new resources, public
access, purchased entitlement, credentials, order or trading authority. Keep
#135 firewall acceptance and the 0021 soak independent. Moomoo still needs an
existing licensed OpenD host, approved private AWS route and actual entitlement;
AAPL/NVDA real charts cannot be claimed before those observations exist.

## Role checkpoints

Planner and Quant Researcher outputs above; independent backend investigator
confirmed the production/test interval mismatch. Implementation, Reviewer and
Verifier outcomes will be appended at their demonstrable slice boundaries.
