# doublema_daily_overlay_candidate_v1 — proposed contract

Date: 2026-10-27 SGT. Status: PROPOSED_FOR_APPROVAL; no implementation, financial run or promotion. All numerical choices below are engineering proposals, not recovered proprietary rules or evidence of profitability. Keep paper=true/live=false; the research path has no order authority.

## 1. Scope and reuse

One operator action in the eventual first slice: inspect one deterministic synthetic **policy** trace comparing the same trend with overlay off/on. Success: each signal, requested/permitted quantity, constraint reason and transition following an explicitly supplied fill event is explainable and reproducible. Account/fill snapshots are stated synthetic inputs; this first slice neither generates financial fills nor computes P&L or a new cash ledger. Fee/cash formulas constrain proposed quantities, not an assertion that accounting integration already exists.

Reuse QuantMesh's existing SPY cashbook and reconciliation semantics through a **new opt-in strategy/protocol version**. Do not alter the existing `prepare_signals/run_cashbook/metrics/calculate` functions, old protocol hashes, reports or v1 parsers. A bounded extension of this engine needs an implementation plan and review; it is not possible just by changing a current parameter. No new engine, package/runtime, factor DSL, uploaded Python, provider, account, cloud resource or paid data. If satisfying this contract needs a second independent ledger/matcher framework or a generic strategy platform, stop and reduce scope.

Implementation stages are deliberately unequal: first deliver the pure policy only, in a new module, with `on_close` -> research action, `size_at_open` -> bounded permitted quantity, and `on_fill` -> campaign transition from an externally supplied synthetic fill. No API/order type gives it trading authority. Existing SPY engine file bytes stay unchanged. Later full accounting integration is an explicit unresolved extension, not part of first-slice approval: existing protocols pin complete source files, so even appending a function changes source identity. The implementer must propose the exact version/profile migration and reuse boundary before touching the cashbook; preserving old function ASTs alone is insufficient. Do not duplicate its ledger loop in another module to evade that decision. Sections2–6 define the target economic semantics against which that later integration would be reviewed.

Use the publicly documented/pinned-in-repo DoubleMA10/20 idea for the signal only. Native vn.py is not executed here, nor is its installed hash newly certified. Its original strategy can reverse short and sends limit orders; this proposal intentionally defines a daily long/cash version with next-open proxies. The prior `trend_v1`20/10 breakout proposal and `position_overlay_v1` stay separate, unchanged artifacts. This candidate does not implement that breakout proposal. A name such as Livermore, Buffett or the pictured trader must not appear as an exact strategy attribution.

## 2. Signal function: no sizing or cash access

Universe fixed to one identified SPY venue/feed, raw unadjusted USD daily bars. Let F_t=mean(C[t-9:t]) and S_t=mean(C[t-19:t]), including the completed t close. At least 100 prior completed warmup sessions, as an engineering convention matching current sample shape; at least 21 closes are mathematically needed to compare both averages on two consecutive sessions. Warmup contributes zero evaluation opportunities or P&L and cannot submit a pre-period decision.

At an eligible evaluation close:

- `enter_long` iff F_t>S_t AND F_(t-1)<S_(t-1).
- `exit_long` iff F_t<S_t AND F_(t-1)>S_(t-1).
- Otherwise `hold`; equality on either compared day does not cross. This preserves the strict reference rule, including its equality edge case.
- Emit only event, session, feature cutoff, availability cutoff, F/S and source/protocol digests. Do not inspect t+1 open, future revised prices, volume at execution or account cash to decide the event.

Start flat. Only a new enter event while flat can start a campaign. An enter while already long does not resize. Exit while flat is a no-op. After overlay flattens, a persistent positive F-S does not permit immediate reentry: a later fresh strict enter is required. This is explicit and may skip long positive-trend periods; no outcome-driven fix is allowed.

## 3. Independent campaign overlay

The trend-only control and overlay variant use identical entry allocation, upper bound and fees. Initial NAV USD100000; integral shares; no debt/short/margin; interest assumed zero. At the actual initial fill lock P0=unfrictioned proxy price and Q0=filled initial shares. Do not set anchors on a zero fill, recalculate P0 after averaging down, or round Q0 upward.

Initial entry budget, including its friction, is 50% of execution-time pretrade NAV. A buy must also satisfy the 75% post-friction NAV concentration bound and settled spendable cash below. These are research sizing proposals, not a drawdown tolerance or live allocation authority.

At completed close t use r=C_t/P0-1, only for a campaign that exists before this close:

| Threshold | One-time quantity request, anchored to Q0 |
|---|---|
| -5%, +5%, +15% | No event |
| r<=-15%, r<=-25% | Buy floor(.10 Q0), floor(.25 Q0), respectively |
| r>=+25%, +35%, +45%, +60% | Sell floor(.10 Q0), floor(.20 Q0), floor(.30 Q0), floor(.40 Q0), respectively |
| r>=+100% | Sell all shares remaining |

Every eligible unconsumed level is considered. If the close leaps across several levels, add the separately rounded quantities and send one net same-side request. No inference of intraday path from high/low; each level fires at most once per campaign. A level that becomes true again after a previous consumption does not refire. Normal sales cannot exceed owned shares. With additional shares, the four ordinary profit stages need not flatten the position; only trend exit, +100% or terminal closeout necessarily requests all remaining shares.

Priority: invalid/unavailable input blocks the affected step; terminal scheduled closeout > trend full exit > +100% full exit > regular sells > adds > new initial entry. Resolve once per decision; at most one instrument action per execution session. No sell proceeds are recycled into another same-session buy. Full flatten resets anchors and levels only after the fill; never reset to hide a failed exit.

Each stage has one execution opportunity. Data invalid before a decision means no stage consumption. A valid decision reserves triggered levels; the next scheduled open's successful/zero/clipped/cancelled attempt permanently records those levels as consumed, with requested/filled/cancelled quantities and reason. No retry merely because a later price improves. An execution-data failure yields an incomplete/failed trace, not a successful zero-cost run. A failed mandatory terminal exit cannot be published as complete.

Full exits have an explicit `pending_full_exit` state distinct from once-only stages. A trend exit or +100% event latches its cause and original decision identity until actual flat. If its valid open attempt is volume-clipped, cancel that order's remainder but retain pending_full_exit. At each subsequent valid completed close, request the remaining shares for the following open regardless of a hold/new-enter signal; suppress all adds and fresh entries. Zero cap likewise keeps pending state. Do not retry intraday, execute on stale data, or extend the sealed terminal window. Only a fully filled exit clears this latch/campaign. This is risk completion under one persistent exit decision, not a new crossover or a refired profit stage.

## 4. Clock, proxy execution and cashbook

Use the pinned exchange calendar, early closes and timezone. Research decision cutoff is actual session close +30 minutes; historical simulated availability is explicitly assumed unless supported by a contemporaneous receipt/vintage. At that cutoff require a completed bar whose documented availability is no later than cutoff. A genuinely late bar is skipped, never backfilled into an earlier signal. Unknown availability blocks causal/PIT claims, even when a retrospective engineering trace can be constructed.

Decisions at t fill at the next regular session's documented OPEN, never at C_t. A next-open daily-bar proxy is not an actual executable quote or a 09:35 price. The daily close has no role in that morning's sizing except information already known from earlier sessions. There is no daily-bar stop matching.

For each execution session in the later cashbook integration: carry shares from preceding close; recognize ex-date dividend entitlement on those carried shares (before an ex-date open sale/buy); credit only dated paid entitlements; determine proxy open, validate liquidity and then execute the single action. NAV=settled cash+shares*mark+unpaid receivables. Receivables are not spendable. Same-day sale proceeds cannot fund a second buy. That later integration assumes immediate availability of dated dividend cash at the simulation session start and no same-session reinvestment of sale proceeds; actual settlement/intraday credit is unqualified. Real trading needs appropriate settled-cash evidence and its own policy, not this assumption.

At price O, fee rate f=bps/10000, pretrade E=cash+Q*O+receivables and H=Q*O, a proposed buy n must satisfy all of:

`n>=0 integer; n*O*(1+f)<=cash; H+n*O<=.75*(E-n*O*f)`.

Thus clamp n by `floor(cash/(O*(1+f)))` and `max(0,floor((.75*E-H)/(O*(1+.75*f))))`. On initial entry also clamp by `floor(.50*E/(O*(1+f)))`. Use bounded numeric tolerance consistent with existing cashbook reconciliation; do not use tolerance to buy an extra unaffordable share. Market appreciation above75% does not itself cause a sale; the rule constrains new buys. Report such passive concentration separately.

Retain the existing conservative proxy cap: floor(1% of median volume of the prior20 completed sessions), excluding the current session, in proven share units. Apply to both directions. A stage remainder cancels. If mandatory terminal liquidation exceeds the cap, lacks an open or cannot reconcile, produce failure/no successful numerical report, not a fictitious full liquidation. Do not infer actual market capacity from this lagged-volume rule.

Evaluation is flat at start. Its final session OPEN is a precommitted liquidation boundary; do not form a signal from the final close or use final-day high/low. Benchmark and candidate use this same economic endpoint. It is a scheduled exogenous boundary, not evidence of profitable exit timing. Shares must be zero at completion; cash plus outstanding receivables is final wealth. Unpaid dividends remain explicitly identified receivables, not cash. The initial engineering trace retains 100warmup+21observations for integration compatibility; it is not an adequate profitability horizon.

V1 **refuses any split or other unsupported noncash action in the warmup/evaluation scope** rather than adding a split engine. Full applicable event coverage must prove that supported scope. Use raw cash-price OHLC for DoubleMA; dividends do not retrospectively adjust these features. Consequently its signals can change at ex-dividend gaps, unlike old total-return-index SMA100. This is a disclosed rule choice, not a data correction. A future split/total-return version would require a new candidate and protocol.

## 5. Friction and comparisons

Charge `abs(filled_shares)*O*f` exactly once on every fill, including entry, stages, exit and terminal liquidation. Fixed engineering scenarios5bps and10bps are one-way all-in proxies; do not additionally charge native vn.py half-spread/slippage. They are not calibrated real execution costs. ETF management expense already embedded in observed prices is not charged again. Real R2 needs commission/minima, spread, opening impact, fees, settlement and executable-size evidence.

Prespecified arms, both cost scenarios retained: T=DoubleMA with overlay off and50% initial sizing; TO=same signal with overlay on; B50=buy initially up to50% NAV then hold; B100=buy initially up to100% NAV then hold; C=cash. B100 explicitly has a100% benchmark concentration exception, otherwise the same spendable-cash, cap, fee, dividend and terminal rules; no daily rebalance. B50 initial integer shares likewise stay fixed. Benchmarks enter at first evaluation OPEN without using that day's close; T/TO wait for first eligible new enter signal. Report delayed entry/average exposure so differing invested time is visible.

Primary descriptive contrast is TO minus T, isolating overlay effects; B50/B100/C supply exposure context. Display paired net return/terminal equity, drawdown, mean exposure, turnover, fees, entry/campaign/threshold counts and cancelled quantities. Profit, smaller drawdown or more fills alone does not give PASS. Undefined ratios stay null with reason. Primary investment objective, minimum benefit, risk budget and inferential error budget are unapproved/null: economic acceptance cannot be computed from this design.

## 6. Non-leaking development, validation, freeze and trial registration

No fitted model or parameter optimization in this version: 10/20, all overlay thresholds, budgets and5/10bps are locked before any new outcome inspection. No training phase is falsely claimed; warmup only computes causal rolling values. Any later learned quantity must be trained only on completed past data, with interval-aware purging when labels overlap a later fold. Fixed daily lookback context may cross a chronological boundary using past bars; that does not grant use of future labels or validation returns.

Available historical SPY through the previously exposed/consumed periods, including old final2025-01-02–2026-10-16 and the once-consumed recent capture, cannot become new blind OOS through new source/hash/strategy/version. Existing R1/R2/R3 stage views remain exposed historical diagnostics. This task does not run any of them. No new unseen test set exists in this delivery.

Future sequence: qualified development-only data for engineering and complete past trial reconstruction; chronology-fixed validation diagnostics with every arm retained; freeze code/protocol/objective/costs/data semantics and all choices; independently identify actually unviewed future observations and their lawful capture authority; seal and open exactly once after a prespecified horizon. Dates/required effective N are presently unallocated, so data/run admission remains closed. If history is already seen, label it diagnostic and use later genuinely unviewed time; do not promise unseen status simply because it is later than a named file. No automatic collection or daily scheduler is authorized.

Register one planned study group `doublema_daily_overlay_candidate_v1` before any execution. Every arm/cost setting, failed/aborted attempt, parameter/rule amendment and outcome access gets a linked immutable record; arms are correlated comparisons, not independent trials. Minimum fields: study/candidate/version, status, reason, preregistered_at, code/protocol/parameter hashes, source/data/action hashes, window roles, exposure/first-viewed history, fit/feature cutoffs, planned contrasts, cost/benchmark definitions, all tried alternatives, parent study, attempts/outcomes/release count. Prior search/trial count is null with reason until reconstructed; do not set total trial count=1 because this is one proposed study. Planned status is not an executed trial.

The existing professional acceptance matrix remains authoritative. If future inference is authorized, predeclare a paired dependent-return method and its block length/error budget using development data only; sparse campaign/threshold events may leave it INSUFFICIENT. Do not add a bootstrap or DSR implementation in this slice. DSR needs trial/search and dependence information, not just a Sharpe number. No repeated peeking, best-window selection, cost switching or replacement benchmark after results. No economic PASS, R3 paper promotion or live authority follows from the synthetic trace.

## 7. Slice acceptance and stop

First-slice policy acceptance requires the affected policy/state boundary oracles in COUNTEREXAMPLES, unchanged legacy source/contract hashes, no future-input sensitivity and explicit supplied-versus-computed evidence labels. Counterexamples for ex/pay/marking/terminal reconciliation are future accounting-integration oracles, not claims that the policy performs those operations. That later full integration additionally requires independent cash/share/receivable/fee reconciliation and original artifact identities retained. Each slice requires targeted TDD only on new affected paths, at most two independent review rounds and the one applicable final CI after review. Existing financial suites and consumed jobs are not rerun. A third structural issue returns the slice to planning.

Implementation must receive a concrete approved design and bounded GitHub issue first. Data gaps do not prevent synthetic software work once that scope is approved, but prevent a real research run or profitability claim. Missing applicable volume/venue semantics are not remedied by dropping the cap or assuming them. This research session stops at these documents; no source changes, trials, market data, SDK import, host access, model calls or external messages occur.
