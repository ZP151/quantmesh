# Similar Open-Source Projects

These projects are not all runtime dependencies. They are reference implementations or isolated companion services that can shorten QuantMesh development.

## Priority A: coherent-framework bake-off now

### FinRL-X / FinRL-Trading

Use the complete Apache-2.0 Python workflow as the first research-engine
candidate: data, stock selection, allocation, timing, risk, backtest and paper
execution expressed through portfolio weights.

Recommended reuse: pin an isolated checkout, run the QuantMesh NVDA manifest
end to end and adapt outputs to QuantMesh research-run, target-weight, risk and
paper-proposal contracts. Admit a package/process dependency only after the
iteration-0020 determinism, leakage, Windows, resource and license gates pass.

### NautilusTrader

Use its unified research/backtest/sandbox/live event model and official
Hyperliquid, Polymarket and Interactive Brokers adapters to test whether a
mature execution engine can replace future venue-specific plumbing.

Recommended reuse: one isolated recorded Hyperliquid replay-to-sandbox
comparator. Do not link or copy it into the permissive runtime until an ADR
accepts the LGPL-3.0 and Rust/Python process boundary.

## Priority B: inspect and reuse bounded companions

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

## Priority C: AI research reference

### TradingAgents

Use it to study multi-agent research roles, decision logs, checkpointing and local-model support. QuantMesh will adapt these ideas to produce structured research artifacts and signals; the deterministic risk engine will remain the only order gate.

## Integration rule

Every copied file must keep its upstream copyright and license header. Prefer adapters, submodules and process boundaries over copying large portions of a framework into the QuantMesh core.

The complete evidence matrix and Phase-0 gate are recorded in
`docs/architecture/framework-adoption-review-2026-08-11.md`. No popularity or
successful demo run is sufficient to approve a runtime dependency.
