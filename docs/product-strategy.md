# QuantMesh Product Strategy

Status: north-star strategy for the local prototype and its first usable
release. English is authoritative; the Chinese summary is included for the
operator handoff.

## 1. Vision

QuantMesh is a local-first, evidence-driven market research workstation for a
solo quantitative researcher. It unifies equities, crypto and prediction
markets into one inspectable loop: observe data, validate provenance and
freshness, test a hypothesis, rehearse a paper trade, and audit the result.

The product optimizes for trust and reproducibility, not for maximum venue
count or autonomous activity.

## 2. First users and jobs to be done

1. **Solo quant researcher** — compare heterogeneous markets, run reusable
   experiments, inspect walk-forward evidence and retain the full lineage.
2. **Paper trader / systematic learner** — rehearse signals and portfolio
   decisions without credentials or real-money risk.
3. **Advanced operator** — connect read-only live feeds and optional broker
   paper surfaces while preserving local control and fail-closed states.

The first segment is the solo researcher who needs a trustworthy local loop;
team collaboration, SaaS hosting and social trading are later possibilities,
not current requirements.

## 3. Cost and operating position

QuantMesh is deliberately local-first and reuse-first. It uses open-source
components and existing venue SDKs behind adapters, stores data locally, and
avoids mandatory cloud infrastructure. The trade-off is that the operator owns
runtime setup, credentials and data availability. The value is lower recurring
cost, privacy and reproducibility.

## 4. Value proposition

**Before:** evidence is split across broker terminals, crypto dashboards,
prediction-market pages, notebooks and scripts; freshness and provenance are
easy to lose.

**How:** QuantMesh normalizes source data, experiments, forecasts, risk state
and paper orders behind local APIs and a coherent workstation. Every displayed
live value is labeled with venue/source/time/age and every order is recorded in
the deterministic paper kernel and audit trail.

**After:** the operator can move from market evidence to a defensible paper
decision and reproduce what happened after restart or replay.

**Alternatives:** separate broker terminals, TradingView, exchange dashboards,
Jupyter notebooks, OpenBB, Qlib, Freqtrade, Hummingbot and ad-hoc scripts.
QuantMesh integrates selected strengths; it does not attempt to replace every
specialist tool.

## 5. Non-negotiable trade-offs

QuantMesh will not initially:

- become a multi-tenant cloud broker or social-trading network;
- support unlimited venues or unbounded symbol discovery;
- promise profitable predictions or hide costs/look-ahead risk;
- let an LLM directly sign, submit, cancel or resize orders;
- enable mainnet wallet signing or real-money execution in the prototype;
- treat synthetic/demo data as live data;
- replace mature open-source data, backtest or chart components without a
  measurable reason.

The product may eventually support guarded live execution, but only behind
explicit operator approval, venue limits, idempotency, reconciliation, kill
switches and a separate release gate.

## 6. Success metrics

**North Star:** reproducible decision loops completed — a session in which the
operator inspects sourced evidence, records a strategy/forecast decision,
executes a paper order or rejects it, and can replay the evidence and audit
result from a clean restart.

Supporting metrics:

- live-data surfaces with truthful source/age/sequence states;
- percentage of paper decisions with dataset/model/parameter lineage;
- deterministic replay equality rate;
- acceptance-flow completion rate on a clean checkout;
- stale/degraded states detected instead of silently rendered as fresh;
- zero safety violations in kill-switch and quote-fence drills.

Near-term OMTM: complete one venue-aware instrument decision loop in which the
operator can inspect sourced historical/live prices, compare probabilistic
forecast evidence, accept or reject a paper proposal, and replay the entire
lineage without changing pages or re-entering context.

## 7. Growth and distribution

The first growth motion is product-led and open-source: a deterministic demo,
clear README, reusable connectors and reproducible research artifacts should
let another technical user evaluate the product locally. No paid acquisition or
hosted service is needed before the local workflow is credible.

## 8. Capabilities and reuse boundaries

Build and own the normalized contracts, provenance/freshness semantics, paper
kernel, risk gates, replay evidence, acceptance drills and product workflow.

Reuse behind adapters:

- FastAPI, React/TypeScript/Vite and selected shadcn/ui components;
- DuckDB/Parquet and existing data-quality primitives;
- a coherent FinRL-X research/allocation workflow if the iteration-0020
  evidence gate passes, with QuantMesh retaining provenance, risk and paper
  authority;
- a process-isolated NautilusTrader execution boundary only after an explicit
  LGPL/license and process-architecture ADR;
- official or maintained Hyperliquid, Moomoo OpenD, Polymarket and Kalshi
  transports where licensing and read-only boundaries are clear;
- Qlib, Darts, LightGBM and similar research components after license,
  point-in-time and cost-model review; Commons-Clause VectorBT remains
  excluded from the runtime;
- local/OpenAI-compatible model gateways for advisory analysis.

## 9. Defensibility

The defensible asset is not a secret indicator. It is the local evidence graph:
normalized multi-market data, replayable experiments, calibrated forecasts,
decision lineage, paper outcomes and explicit risk outcomes collected in one
consistent model. Trustworthy failure states and reproducible operator drills
create switching costs for a researcher whose history lives in the workstation.

## Final product shape

The end state is a local desktop web application with:

- React/TypeScript frontend and FastAPI/Python backend;
- DuckDB/Parquet research lake plus append-only audit/decision ledgers;
- read-only live connectors for Hyperliquid, Polymarket, Kalshi and optional
  Moomoo OpenD;
- market cockpit, watchlists, probability board, experiments, forecasts,
  paper orders, positions, P&L, risk and audit;
- an integrated instrument workspace combining historical/live charts,
  comparison series, forecast intervals, confidence evidence, position/risk
  context and operator-confirmed paper actions;
- English/简体中文 language setting and system/light/dark theme;
- local AI analyst/critic/risk assistant with citations and structured output;
- deterministic paper kernel as the only order authority;
- optional future guarded execution, never unconstrained AI execution.

## Chinese handoff summary

QuantMesh 最终不是“让 AI 自动炒股”的黑箱，而是一个本地部署的多市场量化研究与模拟交易工作站：统一股票、加密货币和预测市场的数据来源、实时状态、量化实验、预测报告、风险和审计。AI 负责分析、解释、质疑和生成候选方案；数据新鲜度、风险规则、熔断开关和纸面交易内核保留最终控制权。真实交易必须另行审批，不能从模拟盘直接越级。
