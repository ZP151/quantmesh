# Exact Forecast Outcome Scorecard

Iteration 0033 follows the operator's authorization to merge #137 and develop
the next important planned product capability. M14's learning loop currently
freezes forecast points and realized daily bars, but review renders thresholds
and R metrics without comparing the forecast with those realized prices.

## User action and acceptance

Open one saved AAPL/NVDA action packet's review, compare its original selected
7/30-session P10/P50/P90 with the exact realized closes, and save/reopen the
existing review within 120 seconds on a deterministic local acceptance station.
The saved comparison must remain identical after current history changes and
review-store restart. Legacy packets use 30 sessions.

## Bounded design

Add a pure derived `ForecastOutcomeComparison` to the existing review response
as `forecast_comparison`, computed from `review.outcome` when saved, otherwise
`outcome`. Do not add fields to persisted outcomes, packets or review records.
The response identifies its policy version, outcome ID, selected horizon,
status, matched session count, and original forecast artifact ID. Rows preserve
every forecast timestamp with P10/P50/P90 and an optional exact close, absolute
median error and inclusive interval hit. Join timestamps, never row positions;
do not interpolate gaps, include live tails, or fetch newer forecasts.

Complete paths expose mean absolute median error, last-price benchmark MAE
(constant root market-state latest close), P10/P90 hit count/fraction, and
signed terminal error (actual minus P50). Pending, partial and unavailable
paths keep all aggregate scores null; matched observations may remain visible.
No observed rows is unavailable performance, never zero. Missing exact forecast
or mismatched expected timestamps refuses comparison. These are descriptive
errors for one path, not independent evaluation samples, model calibration,
scenario probabilities, net return, or promotion/risk authority.

The existing review panel gets an in-place comparison section before detailed
attribution: status/count, observed-versus-frozen-forecast plot, compact metrics,
and a keyboard-accessible disclosure containing all dated rows and provenance.
Reuse the existing Lightweight Charts adapter, tokens and bilingual copy.
The plot must not bridge missing actual sessions. Preserve draft save-first,
loading/error and stale-response protection. Saved review wins over newer preview.
No new route, global dashboard, model, dataset, provider or dependency.

## Non-goals and gates

No cloud, deployment, Scheduler/OpenD, trusted-root writes, notifications,
soak/#124/#127/#132/#135, broker execution, review revisions, aggregate model
rankings or new order lifecycle. Existing Paper risk and second confirmation
stay authoritative. Existing snapshot bytes/IDs and legacy replay are unchanged.
Targeted feedback commands <=300s; coherent local validation <=600s. No local
full pytest/domain/release/soak. One independent Standards/Spec review and one
batched desktop/390px EN/zh acceptance, with at most one correction/confirmation.
