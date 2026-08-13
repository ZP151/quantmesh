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

Iteration 0021, Trusted Data Fabric, is active under issue #110. It unifies real
Moomoo AAPL/NVDA and Hyperliquid BTC/ETH/SOL observations through a
capability-aware read-only provider registry, bitemporal raw evidence,
content-addressed manifests, normalized/adjusted/feature lineage, durable
collection checkpoints, quality SLAs and a local catalog. Completion requires
a clean-install real-data drill and at least 168 continuous hours of immutable
quality evidence. Final `v0.1.1` promotion and real-money execution remain
outside this iteration.

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
