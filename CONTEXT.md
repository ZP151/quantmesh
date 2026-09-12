# QuantMesh Domain Context

## Product vision

QuantMesh is a local-first workstation for cross-market quantitative research, forecasting, paper trading and eventually guarded live execution. It combines equities, crypto venues and prediction markets without hiding venue-specific constraints.

## Current stage

M0 through M13 and iterations 0014–0020 are implemented and merged.
`v0.1.1-rc1` is the immutable accepted prototype baseline. It includes the
React workstation, deterministic demo and paper authority, read-only live
cockpit, venue-aware history, integrated instrument decision workspace,
reproducible research evidence, local AI boundaries and guarded execution
controls.

Iteration 0021, Trusted Data Fabric, is merged; its real 168-hour soak continues
as an independent maintenance and release-confidence track. Iteration 0027,
Evidence-backed Decision Copilot, is merged through PR #128. Iteration 0028,
Decision Inbox & Bounded Paper Shadow Portfolio, is merged through PR #130.
Iteration 0029, Decision Readiness Session, is merged through PR #133.
Iteration 0032, Probabilistic Scenario Lab, merged through PR #137 at `13743ea`.
Iteration 0033 merged through PR #139 at `6ea9a13`, adding exact
forecast-versus-outcome review. The Lab
brings a chart-first AAPL/NVDA daily workspace, exact 7/30-session
forecast evidence and saved analysis replay to the existing DecisionPacket
loop. The 0021 Scheduler/Provider/evidence data plane stays separate. AI remains
optional and advisory. Final `v0.1.1` promotion and real-money execution remain
outside this iteration.

Iteration 0034 / issue #140 delivered the first real AWS market-data loop.
PR #142 integrated private staging support and merged as `e185c3b`, deployed
on 2026-09-12 with public Hyperliquid BTC/ETH/SOL feeds, paper mode on and
live trading off. Five-minute API and browser witnesses, reload/replay and
controlled stale/reconnect tests passed; `4022942` remains the demo rollback.
This establishes those three crypto instruments only. Next: private Moomoo/
OpenD reachability and entitlements for AAPL/NVDA, followed by prediction
venues and trusted history. See `docs/ITERATION_PLAN.md` for delivery order.

## Bounded context

QuantMesh currently uses one bounded context: quantitative research and guarded execution. Split contexts only when the frontend, research runtime or execution runtime develops a genuinely independent language and lifecycle.

## Domain glossary

- **Venue**: An external or internal market endpoint such as Moomoo, Hyperliquid, Polymarket, Kalshi or the internal simulator.
- **Instrument**: A tradeable or observable market contract with a venue, symbol and instrument type.
- **Quote**: A timestamped observation of bid, ask, last price and optional volume.
- **Forecast**: A probabilistic estimate with horizon, calibration metadata and uncertainty.
- **Signal**: A model output proposing directional intent, expected return and confidence. A signal cannot place an order.
- **Strategy**: Versioned logic that transforms data into signals.
- **Experiment**: A reproducible strategy evaluation with pinned data, code, parameters and metrics.
- **Order intent**: A requested trade before risk approval.
- **Risk decision**: A deterministic approval, rejection or modification of an order intent with reasons.
- **Execution command**: An approved instruction sent to a paper or external venue adapter.
- **Fill**: A venue-confirmed or simulator-generated execution event.
- **Position**: The derived quantity, average cost and realized/unrealized P&L for an instrument.
- **Paper account**: A simulated portfolio with deterministic cash, positions, orders and fills.
- **Connector**: An adapter that isolates venue-specific market-data or execution behavior.
- **Promotion gate**: Evidence required to move a strategy from research to replay, paper trading and guarded live trading.
- **DecisionPacket**: A versioned, replayable composition of one instrument's
  as-of market state, scenarios, risk plan, evidence references and operator
  disposition, with immutable links to later paper and review records.

## Architectural boundaries

- `domain` owns venue-neutral models and invariants.
- `connectors` isolate external SDKs and protocols.
- `research` orchestrates datasets, features, experiments and backtests.
- `risk` owns deterministic pre-trade and portfolio controls.
- `execution` owns order orchestration, persistence and reconciliation; order state-transition invariants live in `domain`.
- `api` exposes local control and observability surfaces.
- `vendor` contains pinned upstream components and reference projects, not QuantMesh-owned code.

## Product invariants

1. Research results are reproducible from pinned inputs.
2. Paper and live execution share order/risk semantics.
3. Venue-specific behavior never leaks into strategy interfaces.
4. AI produces structured research artifacts, not executable authority.
5. Every order is explainable from signal through risk decision to fill.
6. Missing or stale market data fails closed for execution.

## Non-goals for the MVP

- High-frequency or latency-arbitrage execution
- Unrestricted autonomous live trading
- Custody of user funds
- Training a foundation model from scratch
- Supporting every broker or prediction market at launch
