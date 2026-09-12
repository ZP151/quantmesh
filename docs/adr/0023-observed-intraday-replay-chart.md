# ADR 0023 — Observed intraday replay chart

Status: accepted for iteration 0035 / issue #144, 2026-09-12.

## Context

Hyperliquid collects 1m candles into LiveBuffer. The shared chart history policy
only selects 5m-or-coarser for the 1D window, so the actual collected stream
cannot open the existing full chart. A configured period is a requested window,
not proof of complete historical coverage. Replay observations must remain
separate from manifest-qualified research history and execution authority.

## Decision

Reuse HistoricalSeries and the shared history/workspace/InstrumentChart path.
When no manifest or eligible preferred/coarser replay exists, permit exactly
Hyperliquid 1D local replay at 1m with `resolution_fallback="5m->1m"`. The
contract validates source and dataset identity against the exact instrument,
24/7 unadjusted interval, absent manifest/quality qualification, and exact
coverage rows/start/end. Other finer fallbacks remain invalid.

Use actual venue candle OHLCV and source-open timestamps. Same-minute revisions
replace a point; contiguous next minutes append. Keep source/receipt bounds,
provenance, sequence/gap checks, disconnect barriers and the two-interval
minimum. Show actual covered time and an unavailable/collecting state instead
of manufacturing a full day. Do not infer historical data from BBO marks.

Live chart navigation defaults to 1D/line, with explicit URL choices and candle
switching preserved. At the right edge, allow the pinned chart library to
follow appended observations; preserve manual historical pan/zoom and forecast
ranges. Cached quote/header freshness uses the existing monotonic aging policy.
Configured live instruments appear separately from registered decision watches.

## Consequences and rollback

No package, provider, schema field, external browser endpoint or order authority
is added. Replay coverage remains unqualified for trusted history/forecast or
strategy promotion. Broad ranges and comparisons retain existing refusal.
Removing the bounded exception returns the prior unavailable chart behavior;
the preceding tested live AWS release remains the deployment rollback target.
