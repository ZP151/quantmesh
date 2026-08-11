# Framework Adoption Review — 2026-08-11

Status: evidence recorded; no framework admitted to the QuantMesh runtime

## Decision question

Can QuantMesh reuse a coherent open-source quantitative trading framework for
the next product slice instead of assembling chart, forecasting, portfolio and
execution features one library at a time?

The answer is **partly**. No reviewed project covers the full QuantMesh target:
equities, Hyperliquid, prediction markets, local evidence lineage, calibrated
forecasts, a unified web decision workspace and deterministic paper authority.
Several projects can nevertheless replace substantial internal subsystems if
they remain behind QuantMesh contracts.

## Evidence reviewed

| Candidate | What is reusable as a whole | Fit and constraint | Current disposition |
| --- | --- | --- | --- |
| [FinRL-X / FinRL-Trading](https://github.com/AI4Finance-Foundation/FinRL-Trading) | Python workflow from data and stock selection through allocation, timing, risk, backtest and paper execution | Apache-2.0 and weight-centric; closest permissive research workflow. It is young, has no integrated QuantMesh-style UI, prediction-market model or multi-venue evidence contract. | First end-to-end research-engine bake-off candidate |
| [NautilusTrader](https://github.com/nautechsystems/nautilus_trader) | One event-driven model for research, backtest, sandbox and live trading; official adapter catalogue includes [Hyperliquid, Polymarket and Interactive Brokers](https://github.com/nautechsystems/nautilus_trader/blob/develop/ADAPTERS.md) | Architecturally the closest execution core, but LGPL-3.0 conflicts with the current permissive runtime policy; it also brings a Rust/Python engine and no product UI. | Isolated replay/sandbox comparator only until a license and process-boundary ADR |
| [Hummingbot Dashboard](https://github.com/hummingbot/dashboard) and Hummingbot | Connector, strategy deployment, backtest, paper/live and monitoring workflow for crypto | Apache-2.0 and useful as a complete crypto companion, but not an equity, prediction-market or forecast workstation. | Future isolated crypto vertical or connector reference |
| [vn.py](https://github.com/vnpy/vnpy) | Gateway/app engine, paper account, charting and portfolio/risk applications | MIT and strong broker/China-market coverage; desktop/event framework does not align directly with the React/FastAPI product shell. | Future broker gateway companion/reference |
| [LEAN](https://github.com/QuantConnect/Lean) | Mature event-driven research/backtest/live engine | Apache-2.0, but introduces a C# runtime and a large operational boundary. | External parity comparator, not the next engine |
| [Freqtrade](https://github.com/freqtrade/freqtrade) | Complete crypto dry-run, strategy and operator workflow | GPL-3.0 and crypto-only. | Process-isolated reference only |

[OpenBB](https://github.com/OpenBB-finance/OpenBB) remains useful for provider
registry and research-data patterns, but its AGPL application is not copied or
linked into the permissive QuantMesh runtime.

This evidence was collected from upstream repositories and their official
documentation on 2026-08-11. Popularity is not an acceptance criterion; exact
commit pins, dependency closures and license notices must be recorded by the
bake-off before adoption.

NautilusTrader's current official installation matrix includes Windows Server
2022 x86-64, not a blanket guarantee for desktop Windows. The QuantMesh
Windows desktop checkout therefore remains an explicit install and replay gate
rather than inheriting upstream's CI support claim. FinRL-X documents a Windows
virtual-environment activation path but does not publish equivalent Windows CI
evidence, so its install gate is also empirical and pinned to this workstation.

## Recommended architecture

QuantMesh remains the product and evidence control plane:

- React/FastAPI workstation and global operator context;
- normalized instrument, market-data and forecast contracts;
- source/freshness/provenance semantics and append-only evidence;
- deterministic paper kernel, risk fences, kill switch and audit authority.

A selected upstream framework may become a replaceable engine behind an
adapter. The preferred sequence is:

1. evaluate FinRL-X as the offline research, allocation and paper-proposal
   engine;
2. evaluate a narrow NautilusTrader Hyperliquid replay-to-sandbox path as an
   execution-semantics comparator;
3. adopt neither, one or both only through an ADR that fixes the package or
   process boundary, version pin, license handling and migration cost;
4. build the integrated instrument workspace against QuantMesh contracts, not
   provider- or framework-specific response objects.

Whole-framework reuse means a pinned package, submodule, isolated checkout or
companion process. It does not mean copying an upstream repository into
`src/quantmesh` or replacing working QuantMesh safety and evidence layers.

## Iteration 0020 bake-off gate

Before feature implementation expands, the iteration must produce one bounded
vertical comparison:

1. Feed the same pinned NVDA historical dataset manifest to QuantMesh's current
   baseline and an isolated FinRL-X workflow.
2. Produce target weights, cost-aware backtest metrics and a paper proposal,
   then map those outputs to existing QuantMesh research-run, risk and audit
   identities without bypassing the paper kernel.
3. Prove clean Windows installation, deterministic reruns, chronological
   train/validation/test boundaries, no look-ahead, dependency/license closure
   and acceptable runtime/resource cost.
4. Run a smaller NautilusTrader Hyperliquid recorded-replay to sandbox-fill
   comparison with no credentials, mainnet or real order authority.
5. Score each candidate for product fit, market coverage, determinism,
   provenance, safety, license, maintenance, packaging and migration effort.
6. Record an ADR selecting or rejecting each boundary. A rejected candidate
   remains a documented reference; it is not silently reintroduced later.

No candidate becomes a release dependency merely because its example runs.
Failure of the bake-off returns iteration 0020 to the smallest native path with
the rejection evidence retained.

## Product consequence

The next prototype is still the integrated instrument decision workspace:
observed chart, forecast distribution, confidence/evidence, position/risk and
paper action on one route. The bake-off changes **how much engine code is
reused**, not the user outcome or safety boundary.
