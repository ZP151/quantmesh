# Evidence-backed Decision Copilot Design

- Status: proposed for operator review
- Date: 2026-09-02
- Iteration: 0027
- Tracking issue: [#122](https://github.com/ZP151/quantmesh/issues/122)
- Product surface: Instrument Workspace

## 1. Problem and wedge

QuantMesh already exposes venue-aware history, live evidence, forecast lineage,
paper position/risk, proposal blockers and operator-confirmed paper actions in
Instrument Workspace. The remaining product problem is compression: the user
must still infer market structure, assemble scenarios, translate evidence into
risk levels and recover the result across separate concepts.

Iteration 0027 makes one promise:

> A research-minded individual active trader can turn one ticker into a
> verifiable, risk-first DecisionPacket in no more than two minutes, save
> Reject, Watch or Paper proposal, and later replay its evidence, paper outcome
> and review.

The comparison lesson from KairoTrend is its short workflow, not its AI signal
or pattern-recognition breadth. QuantMesh differentiates through owned evidence,
point-in-time replay, explicit degraded states and deterministic risk.

## 2. Product principles

1. **One page, one context.** Ticker selection, market state, scenarios, risk,
   evidence and action stay inside Instrument Workspace.
2. **Deterministic foundation.** The packet exists without an AI service. AI
   can explain and challenge facts but cannot create or alter authoritative
   facts.
3. **Risk before action.** Entry, invalidation, stop, target, R multiple and
   paper size appear before Paper proposal. Evidence and risk blockers sit next
   to the action.
4. **Immutable as-of history.** The original analysis is never rewritten.
   Operator, paper and review transitions create immutable versions or linked
   records.
5. **Fail closed for paper, remain useful for research.** Stale, low-quality,
   leakage-affected or missing evidence disables Paper proposal but keeps
   Reject and Watch available with reasons.
6. **Measure the user loop.** Framework count, model count, test count and code
   volume are not product outcomes.

## 3. Existing boundaries to reuse

Iteration 0027 extends rather than replaces these owned contracts:

- `InstrumentWorkspaceService` composes one explicit clock over history, live
  evidence, forecast, paper account, valuation, risk and proposal state.
- `HistoricalSeries` already binds dataset revision, manifest, quality
  evaluation, coverage, gaps, limitations and as-of time.
- `WorkspaceForecast` already exposes model/config/history identity, benchmark,
  train/validation/test chronology, eligibility, blockers, paths and metrics.
- `PaperDecisionService` and `ProposalLedger` own immutable forecast-to-paper
  intent, freshness checks, risk evaluation and explicit confirmation.
- `DecisionLog`, citation resolution and the structured model gateway provide
  advisory AI and audit boundaries with no order-sending surface.
- The shared JSONL persistence module supplies atomic append, fail-closed read
  and duplicate-identity behavior.
- The React Instrument Workspace already owns `MarketCanvas`,
  `ForecastEvidence`, `DecisionRail`, proposal confirmation and generated
  OpenAPI access.

No Qlib, Darts, FinRL-X, NautilusTrader or new chart runtime is required for the
first product slice.

## 4. DecisionPacket contract

### 4.1 Immutable version record

`DecisionPacket` is a frozen, strict record. Each version contains:

- `packet_id`: content identity over every semantic field except bookkeeping
  time;
- `version`: positive integer within one decision lineage;
- `parent_packet_id`: absent only for the initial analysis version;
- `instrument`, `selected_range`, `as_of` and `created_at`;
- `market_state`: trend state, structure summary, support/resistance and the
  exact bar times used to derive them;
- `scenarios`: exactly Bull, Base and Bear, each with thesis, trigger,
  invalidation, target and either calibrated probability or explicitly
  qualitative confidence;
- `risk_plan`: entry zone, stop, target, risk per unit, R multiple and suggested
  paper quantity/notional with the assumptions used;
- `evidence`: exact history/manifest/quality/forecast/model/config/benchmark/
  chronology/cost/leakage references and limitations;
- `paper_capability`: allowed flag plus ordered, typed blockers;
- optional `copilot_record_id` referencing schema-valid, cited advisory output;
- `disposition`: Draft, Reject, Watch or Paper proposal;
- optional immutable references to watch conditions, proposal/risk/order result
  and review records.

The packet ID is derived from canonical JSON. Bookkeeping time is recorded but
excluded from identity only where an existing QuantMesh content-addressed
precedent does the same. A new ADR in Slice 1 must fix the exact identity fields
before code is written.

### 4.2 Version transitions

- Creating analysis writes version 1 with disposition Draft.
- Reject writes a child version with operator reason.
- Watch writes a child version and immutable references to local watch
  conditions.
- Paper proposal writes a child version referencing the existing proposal
  record. It does not place an order.
- Paper confirmation remains in `PaperDecisionService`; a later packet version
  references its proposal/risk/order result without copying or overriding it.
- Review writes a child version referencing the realized-path attribution and
  operator notes.

A transition validates the parent identity and refuses forks that claim the
same lineage/version. Existing historical versions remain readable.

### 4.3 Store and replay

`DecisionPacketStore` uses the shared durable JSONL module under a dedicated
local runtime root. It supports append, exact get, lineage listing and latest
version resolution. Reads revalidate content identity, parent continuity and
referenced-record shape. Corruption, duplicate identity, a missing parent or a
future version fails closed with file/line attribution.

Replay reopens the exact packet version and its referenced evidence. It never
re-runs current analysis and labels it as the historical decision. A separate
refresh action creates a new lineage/version at a new `as_of`; it cannot mutate
the old packet.

## 5. Deterministic analysis

Slice 1 uses transparent native calculations over the exact
`HistoricalSeries` and existing forecast artifact:

- market trend and realized state derive from chronological observed closes and
  the existing bounded moving-average/volatility/drawdown primitives;
- support/resistance and invalidation derive from a documented bounded lookback
  over observed bars only, with stable tie-breaking and exact source bar times;
- Bull/Base/Bear scenarios compose observed structure and forecast quantile
  paths. If calibrated probabilities are unavailable, the field is absent and
  confidence is labeled qualitative; three arbitrary percentages are never
  fabricated;
- the risk plan derives from entry/invalidation/target levels, current paper
  account limits and an explicit paper risk budget. It is a proposal input, not
  an approval;
- data freshness, quality, forecast eligibility, leakage, chronology,
  benchmark/cost and lineage limitations become typed packet blockers.

Every calculation is pure over pinned inputs and one injected UTC clock. It
performs no provider, model or execution call.

## 6. Paper action boundary

Reject and Watch are local research decisions. They remain available when
Paper proposal is blocked.

Paper proposal requires all of the following:

- trusted or explicitly demo-labeled history at the packet clock;
- complete manifest/quality binding where the path claims trusted evidence;
- eligible, sufficiently fresh forecast evidence;
- no leakage, chronology, quality or lineage blocker;
- usable paper valuation and mark according to existing demo/live semantics;
- kill switches clear;
- the existing `PaperDecisionService` accepting the proposed quantity/price and
  risk inputs.

The first action creates an immutable proposal only. The existing second
confirmation performs the deterministic risk check and paper-order transition.
The browser cannot bypass or reimplement either gate.

## 7. Structured Copilot boundary

The Copilot consumes a redacted canonical rendering of one persisted packet
version and resolvable evidence text. Its output schema contains:

- packet ID and cited fact references;
- concise explanation of the Base scenario;
- strongest Bull and Bear challenge;
- evidence gaps or contradictions;
- limitations and questions for the operator.

It contains no order, side, quantity override, risk approval or confidence
field that can replace deterministic semantics. Every claim carries resolvable
citations. The existing critic gate refuses fabricated or unresolved claims.

No model configuration, timeout, protocol failure, invalid schema or citation
failure changes the packet's deterministic analysis or actions. The UI renders
an explicit unavailable/degraded Copilot state and continues.

## 8. Local monitoring

A `DecisionWatchCondition` is an immutable local rule bound to a packet version.
Iteration 0027 supports exactly four condition kinds:

- observed price enters the packet entry zone;
- observed price crosses the invalidation level;
- a referenced data/forecast freshness threshold is exceeded;
- a newer forecast exceeds a documented drift threshold relative to the packet
  forecast.

Evaluation is deterministic over injected observations and clocks. It writes a
typed local event and never contacts a provider, notification service or order
surface. Duplicate observations are idempotent. Restart reloads active
conditions and emitted events from durable local state.

## 9. Outcome attribution and review

The review composer compares the original as-of packet with:

- realized observed path over the packet horizon;
- which Bull/Base/Bear triggers and invalidations occurred, using exact times;
- proposal, risk, order, fill, P&L and refusal records when present;
- planned versus realized R and execution-cost difference when the required
  evidence exists;
- watch-condition events and freshness/drift changes.

Missing evidence yields an explicit unavailable attribution, never a zero or a
fabricated success. Operator notes and a structured outcome classification are
appended as a new packet version/reference. The journal can replay accepted,
rejected and never-triggered Watch decisions.

## 10. API composition

Instrument Workspace remains the route and composition root. New API contracts
are generated from FastAPI OpenAPI and consumed through the typed frontend
client. The API surface must support:

- compose an unsaved deterministic packet for one workspace clock;
- persist and reopen an exact packet version;
- apply Reject, Watch or Paper proposal as an idempotent child transition;
- request optional Copilot analysis for an already persisted packet;
- list/evaluate local watch conditions;
- load outcome attribution and append review.

Write endpoints preserve the existing same-origin, demo/live, risk and
idempotency boundaries. Raw JSON routes remain diagnostics, not a required user
workflow.

## 11. Instrument Workspace experience

Desktop keeps the separator-first three-column layout:

- **Market canvas:** ticker/range, as-of/freshness, observed chart, trend state,
  support/resistance and invalidation.
- **Evidence rail:** Bull/Base/Bear scenarios, forecast uncertainty, exact
  evidence/limitations and optional cited Copilot.
- **Decision rail:** entry/stop/target/R/size, blockers, Reject/Watch/Paper
  actions, confirmation and saved packet identity.

The user does not navigate to Forecasts, Risk or Audit during the primary loop.
Evidence opens in place. Background refresh never changes a persisted packet;
it offers an explicit new analysis version. At compact width the order is
context → market → scenarios/evidence → risk/action, with no horizontal
overflow.

The visible workflow phases are Draft analysis, Evidence blocked, Ready to
decide, Watching, Paper proposed, Paper confirmed and Reviewed. Direction and
workflow state use different text/shape semantics and never rely on color
alone.

## 12. Two-minute measurement

The deterministic NVDA browser acceptance station is the authority. The timer:

- starts when the operator submits NVDA or activates its watchlist row;
- ends after the API confirms a durable Reject, Watch or Paper-proposal packet
  version and the UI displays its identity;
- excludes installation, server startup and optional AI completion;
- includes all required in-workspace interaction and second confirmation only
  when measuring a confirmed paper path separately.

The primary acceptance requires each save disposition to be reachable within
two minutes by a keyboard-capable operator. Automation records elapsed time as
regression evidence, but a passing timer cannot waive evidence, risk,
accessibility or replay failures.

## 13. Error and degraded states

- Missing/invalid history: no deterministic packet; show exact recovery action.
- Stale/failed quality or leakage: packet renders Evidence blocked; Reject and
  Watch available, Paper disabled.
- Missing forecast: deterministic market state may render, but Paper remains
  blocked unless the authoritative proposal contract explicitly permits that
  class; Slice 1 does not relax the existing forecast requirement.
- AI unavailable/invalid: neutral Copilot unavailable state; no packet/action
  change.
- Risk refusal: persist/display the refusal reference; never label it an order.
- Store corruption/reference drift: fail closed and identify the exact local
  record; do not rebuild history silently.
- Background evidence update: retain the last persisted packet and offer an
  explicit refresh/new-version action.

## 14. Verification and acceptance

Each slice uses test-first targeted backend, API and component coverage. Broad
Python/frontend/OpenAPI/bundle checks run at coherent slice commits and the
final PR boundary.

The final NVDA E2E proves:

1. ticker/watchlist to saved packet in Instrument Workspace;
2. Bull/Base/Bear, risk, evidence and action visible on one desktop view;
3. deterministic operation with model service absent;
4. stale evidence blocks Paper proposal but permits Reject/Watch;
5. risk refusal remains visible and creates no order;
6. accepted proposal requires second confirmation and links to paper outcome;
7. clean restart reopens the exact packet and review lineage;
8. English/Simplified-Chinese, keyboard, reduced-motion and 390 px behavior.

## 15. Delivery decomposition

The executable work is deliberately split into four independently demonstrable
plans: DecisionPacket foundation, Structured Copilot, Local monitoring, and
Outcome/review. Only the first plan is written after this design is approved.
Each later plan consumes the persisted packet boundary instead of expanding the
first slice.

At most two tracks run concurrently: this product track and 0021 soak
maintenance. Every prompt has one deliverable, one stop condition and explicit
forbidden actions. Side defects are recorded without expanding the active task
unless they block its user action or safety acceptance. Review is capped at two
rounds; a third structural finding returns the slice for scope reduction.

## 16. Explicit exclusions

- Qlib/Darts/framework integration or model leaderboard as product work.
- More instruments before NVDA proves the complete loop.
- Browser extensions, TradingView integration, mobile and external messaging.
- Real trading, credentials, signing, mainnet or autonomous AI authority.
- Social features and broad pattern recognition.
- Impeccable upgrade or design-sidecar regeneration; both are separate,
  non-blocking maintenance tasks.
