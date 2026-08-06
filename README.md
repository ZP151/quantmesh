# QuantMesh

QuantMesh is a local-first cross-market quantitative research and trading workstation. It is designed to combine equities, crypto assets, prediction markets, local quantitative models, AI-assisted research, paper trading and guarded execution in one auditable workflow.

The project is currently in the MVP infrastructure stage. The implementation strategy is to reuse mature open-source components behind stable QuantMesh adapters instead of rebuilding every data provider, backtester, exchange SDK and AI workflow from scratch.

## Product scope

QuantMesh is intended to support:

- Moomoo market data and paper trading
- Hyperliquid perpetual and spot market data, testnet execution and risk controls
- Polymarket, Kalshi and other prediction-market data providers
- Factor models, technical strategies, machine learning and event-probability models
- Local AI research, news analysis and decision explanations
- Unified backtesting, paper trading, portfolio risk and audit logs

The language model is not an unrestricted trader. AI may propose research, explain signals, generate experiments and identify anomalies. Orders must pass deterministic risk checks, position limits, liquidity checks and execution controls.

## Quick start

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev,research]"
uvicorn quantmesh.api.app:app --reload
```

Open `http://127.0.0.1:8000/health` after startup.

## Repository layout

```text
QuantMesh/
├── src/quantmesh/
│   ├── api/                 # Local API
│   ├── connectors/          # Broker, crypto and prediction-market adapters
│   ├── domain/              # Shared instrument, quote, order and signal models
│   ├── research/            # Research and backtesting integration points
│   └── settings.py          # Local configuration
├── tests/                   # Regression tests
├── docs/                    # Reuse matrix and iteration plan
├── vendor/                  # Pinned open-source Git submodules
├── configs/                 # Example configuration without secrets
├── data/                    # Local data directory, ignored by Git
└── pyproject.toml
```

## Open-source reuse strategy

QuantMesh owns the normalized domain models, connector contracts, risk engine, orchestration, audit trail and product UI. Mature capabilities are reused through packages, adapters, Git submodules or isolated local services.

Direct integration candidates:

- Qlib for factor research, datasets, machine learning workflows and backtesting
- VectorBT for fast vectorized experiments and parameter sweeps
- Official Hyperliquid Python SDK for REST, WebSocket and signed actions
- Current Polymarket CLOB SDK for prediction-market connectivity
- Moomoo OpenAPI Python SDK for broker quotes and paper trading

Reference and companion projects:

- Hummingbot for connector contracts, order tracking, reconnects and Hyperliquid support
- Freqtrade for dry-run, simulated wallets, strategy lifecycle, persistence and risk controls
- OpenBB for provider registration, data routing and local AI/data-tool patterns
- VeighNa/vn.py for gateway/application separation, CTA, portfolio and ML research modules
- TradingAgents for analyst, trader, risk and portfolio-manager agent orchestration

See [`docs/REUSE_MATRIX.md`](docs/REUSE_MATRIX.md) and [`docs/REFERENCE_PROJECTS.md`](docs/REFERENCE_PROJECTS.md) for licenses, integration modes and adaptation estimates.

## Agent collaboration and roadmap

Codex and Claude share the repository contract in [`AGENTS.md`](AGENTS.md). Platform resources and project-scoped skills live in `.codex/` and `.claude/`. The delivery path is tracked in [`docs/roadmap/ROADMAP.md`](docs/roadmap/ROADMAP.md), with append-only iteration records under `docs/iterations/`.

Create the next writable iteration record with:

```powershell
quantmesh-iteration "Paper Trading Kernel" --owner "your-name" --status active
```

In Claude Code, start or resume the long-running project goal with:

```text
/goal
```

Or replace the objective explicitly:

```text
/goal Advance M2 deterministic paper-trading kernel through issue #1
```

## Security defaults

- Paper trading and testnet mode are enabled by default.
- Live trading requires an explicit configuration change.
- Secrets must be loaded from local environment variables or an OS secret store.
- Private keys, signatures and raw account credentials must never be sent to an AI model.
- Every signal and order should retain its input data, model version, risk checks and execution result.

## Iteration plan

1. Establish domain models, local configuration, health checks and the internal paper connector.
2. Build deterministic internal paper matching with fees, spread, slippage, cash, positions and audit records.
3. Add the Moomoo quote and paper-trading adapter.
4. Add Hyperliquid market data and testnet execution.
5. Add Polymarket and Kalshi probability data.
6. Add Qlib/VectorBT experiments and initial momentum, mean-reversion and risk-parity strategies.
7. Add probability calibration, portfolio risk and model-failure detection.
8. Add a local AI research assistant.
9. Enable guarded live execution only after paper-trading promotion gates pass.

## Disclaimer

QuantMesh is a software engineering and quantitative research project. It is not investment, legal or tax advice. Backtest results do not guarantee future performance, and live trading can result in partial or total loss of capital.

For the Chinese project overview, see [`README.zh-CN.md`](README.zh-CN.md).
