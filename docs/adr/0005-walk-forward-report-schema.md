# ADR-0005: Walk-forward report schema and cost-model ownership

Status: accepted (2026-08-08)

## Context

M4 Phase C (iteration 0006, issue #27) adds research baselines: momentum,
mean-reversion, and risk-parity strategies evaluated with walk-forward
windows over pinned lake datasets, with explicit cost assumptions and
generated artifacts. M3 established the reproducibility discipline the
experiment registry (issue #18) embodies: a run is identified by its
setup, never its results, and pins are validated through the lake's
manifest gate. Phase C must give every baseline the same discipline, and
must answer who owns the cost model, how windows are split, and which
metrics are comparable across strategies.

VectorBT and Qlib are named as optional accelerators in the iteration
plan. This ADR decides that QuantMesh owns the report schema outright and
treats accelerators as out-of-scope for Phase C: a schema owned by a
vendor changes when the vendor changes, and the baselines are deliberately
simple enough that a pure, dependency-free backtester over lake bars is
the transparent ground truth.

## Decision

1. **StrategyReport pins the full setup, hashed into a deterministic ID.**
   The report records dataset name, manifest revision, code commit,
   strategy, interval, universe, window spec, and cost model; the 16-hex
   ID is the SHA-256 of the canonical JSON of those fields (setup only,
   never results). The same setup always yields the same ID — "reproduce
   report X" is well-defined, mirroring `experiment_id` (issue #18).
2. **Universe order-independence.** Universe members are
   `(venue, symbol)` pairs; identity hashes over the sorted member list,
   so adding a member in a different order does not change the report.
3. **Windows are count-based over the observed bar grid.** A
   `WalkForwardSpec(train_bars, test_bars, step_bars)` splits the grid by
   bar counts — no trading calendar, no date arithmetic, fully
   deterministic over a pinned dataset. `train_bars >= 2` (a one-bar
   train cannot estimate returns or volatility) and `step_bars >=
   test_bars` (evaluation segments never overlap, so the report's equity
   curve concatenates cleanly without double counting; walk-forward in
   this contract evaluates disjoint test segments). Each test segment
   follows its train segment; weights are computed from train bars only —
   no lookahead by construction.
4. **One cost model, owned by QuantMesh, applied uniformly.**
   `CostModel(fee_bps, half_spread_bps, slippage_bps)` is the only cost
   input to every baseline: the one-way rate is the sum over 10_000 and
   is charged on each unit of one-way turnover
   (turnover = sum of absolute weight changes at a rebalance). Baselines
   are compared under identical costs, so differences are strategy, not
   cost-model, differences. Non-finite costs are rejected at the model
   boundary.
5. **Fixed metrics schema, decimal fractions, documented units.**
   Report metrics: `total_return`, `annualized_return`, `sharpe`,
   `max_drawdown`, `win_rate` (fraction of positive windows), `n_windows`,
   `avg_turnover`, `total_cost`. Annualization assumes 252 trading days ×
   bars per day (from the canonical interval); `sharpe` is `None` when
   volatility is zero (honest absence, not a fabricated number);
   `annualized_return` is `None` when the product goes non-positive (a
   collapse is reported through `total_return` instead). Per-window
   results carry `window_return`, `turnover`, `cost`, and `n_trades`
   (weight changes per symbol at the rebalance, each counting once).
6. **Baselines are pure functions of bars — no RNG anywhere.**
   Momentum goes long the top half of the universe by train-period
   return, mean-reversion the bottom half, risk-parity weights
   proportional to inverse train volatility (zero-volatility symbols
   excluded; all-zero volatility fails closed); ties break on symbol so
   ranks are deterministic. All are long-only, equal-weight within their
   set, rebalanced once per window start. The pipeline itself imports no
   random generator, so byte-identical runs are the rule, not a
   coincidence of seeds.
7. **Artifacts are deterministic functions of the report ID.**
   Artifacts live at `reports_root/<id>/{report.json,equity_curve.csv,
   trades.csv}`. `report.json` is the full report minus `created_at`
   (which is bookkeeping, not setup or result), written byte-stable;
   regenerating a report rewrites identical bytes. A rerun with the same
   setup reproduces the ID, the metrics, and the artifact bytes — the
   Phase C reproducibility acceptance, tested end-to-end.
8. **ReportRegistry is JSONL with the experiment-registry discipline.**
   Records append atomically (unique temp file + rename) under
   `reports.jsonl`; reads fail closed with file/line attribution;
   duplicate IDs are refused on write and read; the pin (dataset +
   manifest revision) is validated through the lake's manifest gate
   before anything is recorded, so the registry never holds a dangling
   pin. `resolve(id)` re-checks the gate and refuses when the manifest
   has moved past the pinned revision.
9. **VectorBT/Qlib are optional future accelerators.** They may later
   sit behind adapters that emit this report schema from their own
   backtests; the schema and the pure baselines remain the owned ground
   truth. Nothing in Phase C depends on either project.

## Consequences

- Every baseline report is reproducible from dataset + revision +
  commit + setup, matching the M4 exit criterion ("at least three
  baseline strategies have walk-forward, cost-aware reports").
- Baseline comparisons are apples-to-apples: same windows, same costs,
  same metrics, same artifact layout.
- The cost model is deliberately coarse (bps on notional, one-way
  turnover); execution-level detail (fills, fees by venue) belongs to
  the Phase D simulated-execution reconciliation, not to research
  reports.
- Count-based windows sidestep calendar data (holidays, partial days)
  entirely; the cost is that a window spec means "N bars", not "N
  weeks", and is dataset-relative — recorded verbatim, so the meaning
  is pinned with the setup.
- Overlapping evaluation segments and one-bar trains are rejected, so a
  report that exists is one whose equity curve and win rate are
  well-defined.
