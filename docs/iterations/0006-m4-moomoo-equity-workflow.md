# Iteration 0006 — M4 Moomoo Equity Workflow

- Status: active
- Started: 2026-08-07
- Completed:
- Owner: solo delivery fast lane
- GitHub issue: to be split from this plan before implementation
- Pull request: one final M4 integration PR from `feat/m4-moomoo-equity-workflow`
- Roadmap milestone: M4

## Outcome

Deliver a local US/HK equity workflow that ingests Moomoo-compatible market
data, produces reproducible cost-aware research reports, and reconciles
Moomoo simulated orders against QuantMesh's deterministic paper-account
semantics. Live trading is not part of this iteration.

## Scope and boundaries

- In scope: OpenD connectivity diagnostics, fixture-first Moomoo adapters,
  historical/daily/intraday normalization into the M3 lake, three baseline
  strategies, walk-forward reports, and simulated-order reconciliation.
- Out of scope: real-money orders, account unlock passwords, credentials in
  source control, AI order authority, mobile/frontend work, and Hyperliquid
  or prediction-market execution.
- Reuse: consume the pinned `py-moomoo-api` SDK through a thin adapter;
  borrow Qlib/VectorBT through optional research adapters rather than copying
  their engines. Do not copy GPL/AGPL reference-project code.

## Acceptance criteria

- [ ] Local OpenD health and capability status are observable without logging
      secrets.
- [ ] Historical, daily, and intraday Moomoo-shaped data normalize into the
      M3 lake with manifests and quality gates.
- [ ] Momentum, mean-reversion, and risk-parity baselines each produce a
      reproducible walk-forward, cost-aware report from a pinned dataset.
- [ ] A Moomoo simulated-order reconciliation identifies every matched,
      pending, missing, or divergent order/fill without silently accepting
      drift.
- [ ] No real-money order path is implemented or enabled.

## Implementation plan

### Phase A — contract and diagnostics

Create issue(s) for a fixture-first `MoomooOpenDClient` boundary, settings for
host/port/timeouts, capability reporting, and typed unavailable/auth-required
errors. Unit tests must run without OpenD. Probe a real local OpenD instance
only through an explicit operator command; never persist its response if it
contains account data.

### Phase B — market-data adapter

Map SDK historical-kline, quote, and ticker responses to canonical M3 `Bar`
and `TradeEvent` models. Ingest fixture data through `Lake`, manifests, and
quality checks before any live OpenD read. Add integration tests using fixtures
for US and HK symbols and daily/intraday intervals.

### Phase C — research baselines

Add a strategy-report contract with pinned dataset reference, universe,
walk-forward windows, fee/spread/slippage assumptions, metrics, and generated
artifacts. Implement momentum, mean-reversion, and risk-parity as transparent
baselines. VectorBT/Qlib adapters are optional accelerators; QuantMesh owns
the report schema and reproducibility test.

### Phase D — simulated execution reconciliation

Add a simulated-only Moomoo order/status/fill adapter and a reconciliation
service that maps broker identifiers to QuantMesh client/order IDs. Reconcile
quantities, prices, fees, status transitions, timestamps, and positions; fail
closed on missing or ambiguous mappings. Fixture replay is mandatory.

### Phase E — operator validation and milestone gate

Only after all fixture tests pass, request one human-provided local OpenD plus
Moomoo **simulated-account** validation. Run health, read-only quote/history,
then a deliberately small simulated-order reconciliation drill. Record
redacted evidence. This is the sole external-state gate for M4; never request
or log a password, secret, or real-trading confirmation.

## Delivery protocol

Use `feat/m4-moomoo-equity-workflow` as the solo integration branch. Before
coding, split Phases A-D into GitHub issues with acceptance criteria and
blocking edges. Keep one tested, reviewed, issue-linked commit and iteration
checkpoint per issue; push each checkpoint. Do not open per-slice PRs. Open
one final M4 PR only after the acceptance criteria and operator-validation
evidence are complete; CI plus the standing merge authority controls merge.

## Durable decisions to record when reached

- ADR: OpenD adapter lifecycle, error classification, and credential boundary.
- ADR: walk-forward/report schema and cost-model ownership.
- ADR: broker-paper reconciliation identity and tolerance policy.

## Risks and gates

- OpenD availability, market-data entitlements, and simulated-account access
  are external conditions; fixture development must not wait for them.
- SDK transport is synchronous/callback-oriented; isolate it from async API
  surfaces and test lifecycle/reconnect behavior.
- Moomoo symbols, timezone/session rules, corporate actions, and fee details
  must remain provider metadata and be represented in manifests/reports.
