# Probabilistic Scenario Lab design

Status: option A approved by the operator on 2026-09-11, with continuous goal-driven implementation authorized. Original requested filename retained.

## Product contract

One research-minded individual trader opens NVDA, reads a large observed daily candle chart and a clearly separated forecast, chooses 7 or 30 trading sessions, saves Watch, and reopens the same evidence. The measured entry-to-save path is at most 120 seconds, excluding installation/startup. AAPL proves the same bounded contract. This is an extension of Instrument Workspace in Operate mode, preserving the owned black/graphite/green, Geist and separator-first system.

## Composition and interaction

Home, Markets, Watchlist and the command palette offer a supported-ticker chart action. Existing exact decision links remain explicit replay actions. Ticker matching is limited to Moomoo AAPL/NVDA; unsupported input is explained, never sent to an order ticket or a new provider. Chart entry opens fresh analysis rather than silently selecting an old action packet.

The first viewport contains ticker, source and as-of/demo/freshness status, the daily-bar label, 7/30-session control, candles, volume and SMA 20/50 controls, and the observed/forecast boundary. The market canvas leads at usable width. Evidence details and the risk/action form open in place below it. Persistent material blockers remain visible before opening risk details. On 390px, context, controls, chart, concise conclusion, evidence and actions form one column; no document overflow. Native controls expose pressed states, visible focus and keyboard activation. Reduced motion disables nonessential transitions.

Observed candles have distinct filled/hollow shapes. Forecast P50 is visually distinct; P10/P90 form the empirical 80% interval band and retain distinct boundaries. The split between observed history and projected times has a textual label and a visible separator. The complete accessible table identifies observations and forecasts by series name and timestamp. Chart library access remains behind InstrumentChart, with attribution preserved. No new chart package.

## Exact evidence and persistence

An optional, versioned `scenario_lab` extension on DecisionPacket contains `selected_horizon` (7 or 30), the bounded historical chart snapshot, and a deterministic confidence assessment with policy/version and reasons. Forecast paths, metrics and provenance already belong to DecisionEvidence and are reused. Absent legacy extension serializes exactly as before, preserving legacy canonical bytes and IDs. New extension content participates in canonical identity and child immutability. Root scope distinguishes selected horizon and pinned analysis identity so both horizons may be saved at the same as-of.

Workspace query and save accept the selected horizon. The server constructs and stages the exact draft; the browser never edits packet content. A selected forecast artifact ID is pinned in the URL and resolved by exact registry lookup, never replaced by latest on failure. History used for a pinned analysis must match its declared dataset/revision/manifest and the as-of cut; mismatches refuse the forecast conclusion. Switching horizons selects paths and metrics from that same artifact. Saving and reopening uses the packet's frozen history, forecast evidence and horizon, including when current data changes. A missing legacy chart snapshot is explicitly unavailable for archived-chart replay; current data may not masquerade as archived evidence.

New lab packets use their selected horizon for scenario targets and related forecast monitoring/outcome review. Existing packets without the extension continue to use 30 sessions. Existing watch definitions, reviews, packet versions and forecasts are never rewritten. This is input selection within existing risk/monitor/review services, not new execution authority. Other venues and 126-session legacy analysis remain outside the main path and retain existing behavior.

## Quant semantics and refusal

Reuse median-log-drift-conformal, rolling chronological OOS, the last-price random-walk benchmark and immutable PriceForecastArtifact. Do not introduce a classifier, Darts or a new model framework.

Confidence is an evidence qualification, not a directional probability. Missing path/metrics, binding/chronology failure or unavailable data gives abstain. Insufficient sample counts (at least 30 resolved residuals and 30 evaluated intervals for 7/30), empirical 80% coverage outside the existing [0.60, 0.98] gate, MAE greater than or equal to random-walk MAE, or stale evidence gives low-confidence/abstain with explicit reasons and blocks Paper. Existing artifact-wide blockers, including 126-session blockers, are additional constraints and cannot be relaxed by the new selected-horizon check. Zero samples display unavailable metrics, not zero predictive error.

Bull/Base/Bear remain qualitative; probability stays null without independent calibration. Explain that residual rows overlap and are not independent observations, and intermediate path bands use a scaling approximation rather than separate per-time calibration. The interval is not a profit probability or guaranteed coverage. Fees and slippage remain pinned; spread is resolved at existing confirmation and is not shown as zero.

New XNYS forecast configuration uses the existing pinned CalendarService for future trading dates, gap and age semantics. Legacy config digests retain their weekday algorithm, limitations and validation branch so old artifact bytes/IDs reopen unchanged. New configuration/model version and limitations enter artifact identity; unsupported calendar/version fails closed. Historical synthetic fixtures remain explicitly demo-synthetic. Holiday and DST behavior receives targeted tests.

## Evidence hierarchy and authority

The concise summary exposes selected horizon/target, synthetic or real status, confidence and key blocker. An evidence disclosure carries source, as-of, dataset/revision/manifest/quality IDs, model version, configuration summary/digest, forecast vintage, OOS MAE/RMSE, random-walk MAE, coverage, sample counts, evaluation windows and limitations. All facts derive from the exact displayed packet/artifact.

Real qualification consumes only the exact trusted-data manifest/quality binding. No catalog-head substitution, provider refresh, alternate root or trusted-data write. Missing/stale real data cannot appear live. Reject and Watch remain available with reasons. Paper is gated on both existing deterministic capability and lab evidence qualification, then existing action-time freshness, risk and a second explicit confirmation. Copilot explains only persisted evidence and cannot generate probabilities or override blockers, risk or orders.

## Delivery and non-goals

One integration branch, one final reviewable PR; major architecture merge remains a separate operator boundary. Keep Planner, Quant Researcher, Implementer, Reviewer and Verifier evidence in the iteration. Spec self-review covers identity, selected-horizon consistency, calendar compatibility, real/demo authority, and all five acceptance paths.

No AWS/Lightsail/Tailscale/firewall/deployment, #124/#127/#132/#135, soak/witness/Scheduler/Provider/OpenD operations, new data provider, news/social/community data, QuantumTrading/Darts, external notification, live/mainnet/automatic order or performance promotion. Impeccable design sidecar schema/staleness is recorded only; do not run document or repair it.

TDD uses affected pytest nodes and Vitest files. Each command is bounded to approximately 300 seconds; one complete slice verification targets 600 seconds. Reuse installed environments with explicit worktree imports. A slow fixture is isolated instead of extending to 30/180 minutes. No full pytest/domain sweep/release gate/soak or multiple fresh environments. Final verification comprises scoped Ruff/Oxlint, actual TypeScript project build, generated OpenAPI and packaged bundle freshness, one Standards/Spec review and one batched desktop/mobile UI pass. At most one correction batch and one confirmation; no repeated audit loops. These operator limits supersede historical broad-gate templates.

## Acceptance mapping

1. Home or Watchlist NVDA entry reaches chart without order page, with first-viewport observed/forecast boundary and selected horizon.
2. 7/30 switching and refresh preserve one exact artifact, associated metrics, target dates and selected horizon.
3. Both equities show demo-synthetic honestly; missing/stale real evidence is blocked.
4. Benchmark equality/loss, sample/coverage failure and binding failure deterministically block Paper while Reject/Watch remain usable.
5. Saved packet reopens exact history, forecast and horizon after restart; old packet/watch/review identities stay intact, with unchanged confirmation authority.

## Self-review

No probability is derived from price quantiles. Legacy serialization and forecast validators are explicitly versioned. The 7/30 selection has a declared downstream meaning; old 30-session records remain unchanged. Source and confidence failures cannot silently fall back. All work is bounded to the stated user loop. No unresolved product interaction remains after the operator's option-A approval.
