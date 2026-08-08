# QuantMesh Reuse Matrix

This document records which open-source projects are reused, why they are used, and how much adaptation is expected.

| Component | Upstream | Role | Integration mode | Expected change | License note |
| --- | --- | --- | --- | --- | --- |
| Research platform | `microsoft/qlib` | Factor research, datasets, ML workflow, backtesting | Git submodule/reference implementation | Medium | MIT; preserve notices |
| Vectorized research | `polakowo/vectorbt` | Fast parameter sweeps and portfolio experiments | Optional Python dependency | Light | Apache 2.0 with Commons Clause; review before commercial distribution |
| RL research | `AI4Finance-Foundation/FinRL` | PPO/SAC/TD3 experiments after baselines | Optional reference dependency | Medium | MIT; research use only until validated |
| Stock broker | `MoomooOpen/py-moomoo-api` | Moomoo OpenAPI quote/trade transport | Git submodule or package | Medium | Apache-2.0; verify the upstream package version |
| Crypto venue | `hyperliquid-dex/hyperliquid-python-sdk` | Hyperliquid REST, WebSocket and signed actions | Git submodule/package | Light | MIT; never expose private keys to AI |
| Prediction market | `Polymarket/py-clob-client-v2` | Polymarket CLOB client | Git submodule/package | Light to medium | MIT; use the current v2 client, not the archived legacy client |
| Market-data platform | `OpenBB-finance/OpenBB` | Provider registry, research data routing, AI/data-server patterns | Reference submodule; optionally run as a separate local service | Medium | AGPLv3; keep process boundary if future distribution is planned |
| Crypto bot | `hummingbot/hummingbot` | Connector contracts, order tracking, market-data streams, Hyperliquid connector | Reference submodule; selectively port patterns | Medium | Apache-2.0 |
| Crypto bot | `freqtrade/freqtrade` | Dry-run, strategy lifecycle, persistence, backtesting and risk controls | Reference submodule or separate companion process | Medium | GPL-3.0; do not copy code into a permissively licensed core without a license decision |
| Quant trading framework | `vnpy/vnpy` | Gateway/app separation, CTA, portfolio, spread and ML research modules | Reference submodule; selectively port patterns | Medium | MIT |
| LLM trading research | `TauricResearch/TradingAgents` | Analyst/researcher/risk/portfolio agent workflow and persistent decision logs | Optional research submodule; adapter around QuantMesh signals | Medium | Apache-2.0; treat output as research, not execution authority |
| Execution engine candidate | `QuantConnect/Lean` | Event-driven simulation and future live execution | Deferred reference | Medium to high | Apache-2.0 |
| Execution engine candidate | `nautechsystems/nautilus_trader` | Deterministic multi-venue execution | Deferred reference | High | LGPL-3.0; trademark and attribution rules apply |
| UI component source | `shadcn-ui/ui` | Accessible React primitives owned and themed by QuantMesh | CLI-copy selected components; never copy the full repository | Medium | MIT; preserve generated component notices where supplied |
| Data grid candidate | `TanStack/table` | Dense positions, orders, instruments and audit tables | Package behind QuantMesh table components | Light to medium | MIT; verify selected release during ADR spike |
| Market chart candidate | `tradingview/lightweight-charts` | Candlestick and time-series market views | Package behind a chart adapter | Light | Apache-2.0; preserve notice |
| Analytics chart candidate | `apache/echarts` | P&L, exposure, calibration and scenario visualizations | Package behind a chart adapter | Light to medium | Apache-2.0; preserve notice |
| Frontend design skill | `Leonxlnx/taste-skill` @ `e988add20dab0fa97d7a76781c48961c8184288e` | Anti-template design and design-system selection | Project-scoped Codex/Claude skill; advisory outside dashboards | None | MIT; license preserved under `docs/third-party/` |
| Product UI skill | `pbakaus/impeccable` @ `aee6ce9352b842217b3f57c78296a7a4fa35a7f3` | Product context, UX shaping and bounded visual QA | Project-scoped Codex/Claude skill | None | Apache-2.0; upstream notice preserved under `docs/third-party/` |
| Frontend test runner | `vitest` 3.2.x | Unit/component test runner for the React SPA (Phase E) | Dev dependency behind `npx vitest run` | Light | MIT |
| Browser DOM for tests | `jsdom` 26.x | jsdom environment for component tests (Phase E) | Dev dependency (Vitest `environment: "jsdom"`) | None | MIT |
| React testing library | `@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event` (16/6/14) | Component queries, matchers and user-event simulation | Dev dependencies; the E2E surface stays Playwright | Light | MIT (all three) |
| Frontend linter | `oxlint` 1.x | Fast lint pass for the SPA source | Dev dependency behind `npm run lint` | Light | MIT |

## Selection rule

QuantMesh owns the normalized domain models, connector contracts, risk engine, orchestration, audit trail and product UI. Upstream projects remain isolated behind adapters whenever possible.

For the RC2 frontend, “reuse shadcn/ui” means copying selected components with
the official CLI and then owning their source and visual treatment. It does not
mean forking the full showcase application or shipping its default theme.

## Similar-project lessons

- OpenBB demonstrates a provider-registry and “connect once, consume everywhere” data layer. QuantMesh should borrow the provider contract, not the full AGPL application surface.
- Hummingbot demonstrates that a strategy should not know exchange-specific REST/WebSocket details. QuantMesh keeps this separation through `MarketConnector` and `ExecutionConnector`.
- Freqtrade demonstrates a practical dry-run promotion path, SQLite persistence, strategy file loading and explicit risk controls. These are high-value product patterns for the first paper-trading release.
- VeighNa/vn.py demonstrates a gateway/app split and reusable CTA, portfolio, spread and algorithmic-trading modules. Its `vnpy.alpha` module is also a useful reference for dataset/model/lab separation.
- TradingAgents demonstrates structured analyst, trader, risk and portfolio roles, persistent decision logs and local-model support. QuantMesh should use this as an AI research workflow while keeping order authority in deterministic code.
- Hummingbot already lists Hyperliquid spot and perpetual connectors, so it is a candidate for a future isolated crypto execution service instead of reimplementing every exchange detail in the MVP.

## Excluded from the first MVP

- LEAN and NautilusTrader are not pulled into the first runtime because they add substantial engine and deployment complexity.
- FinRL is kept optional because reinforcement learning is not the first validation path.
- Backtrader is not selected for the core because the active fork is GPLv3 and Qlib/VectorBT cover the initial research needs.
- OpenBB and Freqtrade may be checked out for reference, but their AGPL/GPL licenses make direct code embedding a deliberate later decision.

## License checklist

Before distributing QuantMesh outside personal use:

1. Pin every upstream commit and record the commit in `git submodule status`.
2. Preserve upstream license and attribution files.
3. Run a dependency license scan in CI.
4. Re-check VectorBT Commons Clause and any SDK-specific usage terms.
5. Review broker and prediction-market terms separately from open-source licenses.
