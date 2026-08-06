# QuantMesh Iteration Plan

## Iteration 0: Foundation

- Git repository and English identifiers
- Chinese product README
- FastAPI health endpoint
- Shared domain models
- Internal paper connector
- Upstream reuse matrix and license tracking

## Iteration 1: Internal simulation

- Account, cash, position and fill models
- Fee, spread and slippage model
- Deterministic paper matching
- Order and signal audit records
- Backtest-to-paper replay test

## Iteration 2: Stock workflow

- Moomoo quote adapter
- Moomoo paper account adapter
- Daily and intraday data persistence
- First momentum, mean-reversion and risk-parity strategies
- Qlib/VectorBT experiment runner

## Iteration 3: Crypto workflow

- Hyperliquid REST and WebSocket market data
- Testnet execution adapter
- Funding, leverage and liquidation-aware risk checks
- Order-book imbalance and volatility strategies

## Iteration 4: Prediction workflow

- Polymarket market discovery and CLOB snapshots
- Kalshi adapter behind the same interface
- Probability conversion and calibration
- Event-to-asset mapping with explicit confidence and expiry

## Iteration 5: AI research layer

- Local model gateway
- News and filing retrieval
- Factor proposal and backtest request generation
- Explanation and anomaly summaries
- No direct unrestricted order authority

## Promotion gates

Strategy promotion requires out-of-sample testing, walk-forward validation, cost and slippage assumptions, paper-trading observation and a defined rollback rule.

