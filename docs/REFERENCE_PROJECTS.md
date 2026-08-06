# Similar Open-Source Projects

These projects are not all runtime dependencies. They are reference implementations or isolated companion services that can shorten QuantMesh development.

## Priority A: inspect and reuse patterns now

### Hummingbot

Use it to study connector interfaces, order tracking, WebSocket reconnects, market-making strategy boundaries and Hyperliquid support. Its connector model is the closest match to QuantMesh's multi-venue execution problem.

Recommended reuse: selectively port interface patterns and tests, or run it as a separate crypto execution service.

### Freqtrade

Use it to study dry-run behavior, simulated wallets, persisted trades, strategy loading, backtesting, hyperparameter optimization and operator controls.

Recommended reuse: copy product behavior and test cases. Keep GPL code isolated unless the whole distribution is made GPL-compatible.

### OpenBB

Use it to study provider registration, data normalization, local API serving, analyst workflows and AI/data-tool boundaries.

Recommended reuse: provider registry ideas and API shapes. Treat the AGPL application as a separate process for now.

### VeighNa / vn.py

Use it to study gateway/app separation and domain modules for CTA, portfolio, spread and algorithmic trading. Its MIT license makes selected code reuse easier, but the framework is broad and should not become a second core engine inside QuantMesh.

## Priority B: AI research reference

### TradingAgents

Use it to study multi-agent research roles, decision logs, checkpointing and local-model support. QuantMesh will adapt these ideas to produce structured research artifacts and signals; the deterministic risk engine will remain the only order gate.

## Integration rule

Every copied file must keep its upstream copyright and license header. Prefer adapters, submodules and process boundaries over copying large portions of a framework into the QuantMesh core.

