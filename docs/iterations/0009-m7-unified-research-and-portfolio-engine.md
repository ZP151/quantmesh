# Iteration 0009 — M7 unified research and portfolio engine

- Status: active
- Started: 2026-08-08
- Completed:
- Owner: Claude (solo delivery lane)
- GitHub issue: #39-#43 (Phases A-E)
- Pull request: (opened after acceptance criteria complete; base = `feat/m6-prediction-market-intelligence`, stacked — merges after the M6 PR #38, which awaits the M5 PR, which awaits the M5 operator drill)
- Roadmap milestone: M7 (`LATER` → `ACTIVE`)

## Outcome

Combine equity (M4), crypto (M5) and event (M6) signals under one risk
budget: versioned feature and model registries, LightGBM/logistic/HMM/
GARCH baseline pipelines, ensemble predictions with calibrated
uncertainty, a portfolio engine with venue/asset/event-risk constraints
and exposure decomposition, deterministic scenario tests, and
drift/failure detection with an evidence-disciplined signal promotion
ledger. Every promoted signal carries benchmark, ablation and
out-of-sample evidence; portfolio construction respects venue, asset
and event-risk constraints.

## Scope and boundaries

- In scope: `quantmesh.research.features` (feature registry) and
  `quantmesh.research.models` (model registry) on the M3
  experiment-registry discipline; `quantmesh.research.pipelines`
  (LightGBM, logistic, HMM, GARCH baselines, lazy import-guarded with
  typed errors — the M5 SDK-transport idiom); `quantmesh.research.ensemble`
  (validation-only weight derivation, disagreement uncertainty,
  M6-discipline calibration); `quantmesh.portfolio` (risk-budget
  construction, constraints, exposure decomposition, scenario tests);
  `quantmesh.research.drift` (PSI/KS drift, staleness, failure
  detection, alert ledger, promotion ledger); extension of the M5
  walk-forward report stack and the M5 `STRATEGIES` branch mechanism;
  the research extra pins (scipy/hmmlearn/arch) and the CI install
  change.
- Out of scope: any execution path — M7 computes, records and alerts;
  it places nothing (the M2 paper kernel remains the only execution
  surface, and the promotion/kill-switch wiring is report-only here —
  enforcement is M10); M8-M10; the M4/M5/M6 external gates (already
  recorded and deferred).
- Reuse: lightgbm (>=4.5,<5) and scikit-learn (>=1.5,<2) already
  pinned in the research extra; new pins scipy (>=1.13,<2, used
  directly so pinned), hmmlearn (>=0.3,<1), arch (>=7,<8) in the
  research extra; the M3 experiment-registry discipline (setup-only
  identity, lake-pin gate at record and resolve, JSONL with atomic
  appends and fail-closed reads) for the model/feature registries; the
  M5 report stack (`run_walk_forward`, `STRATEGIES` branches, `report_id`,
  `ReportRegistry`, byte-stable artifacts) for pipeline reports; the M5
  signal-digest discipline for feature-set digests; the M6 Brier/
  reliability-binning discipline for ensemble calibration; the M5 risk
  checks (leverage/liquidation/stale-data) and M6 implied probabilities
  as portfolio-constraint inputs; the M2 kernel replay for scenario
  tests. Reference projects (not vendored): Qlib and MLflow for model
  registry concepts, PyPortfolioOpt for portfolio reference, Alphalens
  for factor/ablation reference — all behind the established local-first
  JSONL discipline.
- Stacking: `feat/m7-unified-research-and-portfolio-engine` branches
  from the M6 tip (`7c4a0d1`) because M7 reuses the M5 report stack,
  the M3 lake/registry discipline and the M6 calibration machinery. The
  M4 and M5 final PRs await their human drill gates; the M6 PR #38
  stacks on the M5 PR; the M7 PR stacks on the M6 PR. M7 itself has no
  human gate: everything is local computation over pinned fixtures.

## Acceptance criteria

1. [ ] Feature and model registries follow the M3 discipline: setup-only
      identity (commit + name + parameters + dataset pins — never
      metrics), lake-pin validation at record AND resolve, JSONL with
      atomic temp+replace appends, fail-closed reads with line
      attribution, duplicate refusal, byte-stable artifacts; a pinned
      feature set reproduces identical frames on a clean checkout. —
      Phase A (issue #39).
2. [ ] LightGBM, logistic, HMM and GARCH baseline pipelines each
      produce cost-aware walk-forward reports (M5 report stack) with
      benchmark, ablation and out-of-sample evidence; every window
      trains on its own train slice only (no-lookahead proven by test);
      runs are deterministic on pinned fixtures. — Phase B (issue #40).
3. [ ] Ensemble weights derive from validation windows only (proven by
      test); ensemble predictions carry calibrated uncertainty, with
      calibration evidence computed under the M6 Brier/reliability
      discipline. — Phase C (issue #41).
4. [ ] Portfolio construction respects venue, asset and event-risk
      constraints (proven by test on fixture universes); exposure
      decomposes by venue, asset class and event; deterministic
      scenario tests (gap moves, liquidation cascade, funding spike,
      event mis-resolution) run on fixture universes through the M2
      kernel replay. — Phase D (issue #42).
5. [ ] Every promoted signal carries a promotion record linking
      benchmark, ablation and out-of-sample evidence (exit criterion
      1); injected drift and stale data are detected and alerted. —
      Phase E (issue #43).

## Plan and role assignments

- Planner: Claude
- Quant researcher: Claude
- Implementer: Claude
- Reviewer: Claude (adversarial self-review before every commit)
- Verifier: Claude (fixture drills, full suite, ruff, diff, submodules)

### Phase A — feature and model registries (issue #39)

`quantmesh.research.features`: `FeatureSpec` (name, kind — bar-derived /
orderbook-derived / event-derived, source venue and universe, parameters,
setup-only 16-hex `feature_id` over commit + name + kind + parameters +
dataset pins), `FeatureSet` (ordered specs + its own digest, folding into
model identity), `compute_features` (deterministic frames from pinned M3
lake datasets; fail-closed on missing pins, empty outputs, mixed
grids). `quantmesh.research.models`: `ModelSpec` (type — lightgbm /
logistic / hmm / garch, hyperparameters, `features_digest`, dataset
pins, setup-only 16-hex `model_id`), `ModelRecord` (spec + metrics as
results + artifact sha256 + train-window bounds), `ModelRegistry`
(JSONL under `settings.models_dir`, atomic temp+replace appends,
fail-closed reads with line attribution, duplicate refusal, lake-pin
gate at record AND resolve — the `ExperimentRegistry` pattern verbatim),
byte-stable artifact serialization per model type with the sha256
recorded on the record (identity never includes metrics or weights).
Settings additions (`features_dir`, `models_dir`). ADR-0009 recorded
(registry decisions + the research-extra/CI dependency decision).
Tests: pin validation both directions; duplicate refusal; corrupted
reads; clean-checkout reproducibility; artifact byte-stability across
registry roots.

### Phase B — baseline pipelines (issue #40)

`quantmesh.research.pipelines`: lazy import-guarded accessors (the M5
SDK-transport idiom) for lightgbm, scikit-learn, hmmlearn and arch with
typed errors; `LightGBMPipeline` / `LogisticPipeline` (binary
classifier on feature frames), `HMMPipeline` (regime signal), `GARCHPipeline`
(volatility forecast signal); each exposes fit-on-train / predict-on-test
and registers as a `run_walk_forward` strategy branch (the M5 Phase D
`STRATEGIES` extension mechanism), producing cost-aware walk-forward
reports with benchmark (incumbent baselines from M4/M5) + ablation
(feature-drop sets with metric deltas) + out-of-sample (test windows by
construction) evidence recorded as `StrategyReport`s; deterministic
seeds and same-version byte determinism pinned by test; the fixture
drill runs the M3 lake fixture universe (equity + crypto bars) plus M6
implied probabilities as event-derived features. Dependency decisions
recorded in ADR-0009: research extra gains scipy/hmmlearn/arch pins;
CI installs `.[dev,research]` (deliberate, documented deviation from
the M3 duckdb-promotion precedent: the ML stack is genuinely optional
runtime surface and the paper kernel core stays lean). Tests:
per-pipeline walk-forward reports, ablation deltas, no-lookahead proof,
typed errors without the extra, determinism.

### Phase C — ensemble and uncertainty calibration (issue #41)

`quantmesh.research.ensemble`: `EnsembleSpec` (member model ids +
weight method), weights derived on validation windows only —
inverse-error or nonnegative least squares via scipy, never on test
windows (proven by test); ensemble predictions with disagreement-based
epistemic uncertainty (identical members → zero disagreement); ensemble
calibration curves via the M6 `brier_by_bin` discipline (half-open
bins, empty-bin `None`); ensemble reports on the M5 stack. ADR-0009
extension recorded. Tests: validation-only weight derivation;
determinism; calibration binning reuse; disagreement arithmetic.

### Phase D — portfolio engine (issue #42)

`quantmesh.portfolio`: risk-budget construction via `scipy.optimize`
(SLSQP, documented starting points, fail-closed on infeasible
systems); constraint surface — per-venue caps, asset-class caps,
event-risk exposure caps computed from M6 implied probabilities,
per-venue leverage limits drawn from the M5 risk checks; exposure
decomposition by venue, asset class and event; deterministic scenario
tests — gap moves, liquidation cascade, funding spike, event
mis-resolution — applied as shocks to fixture universes and replayed
through the M2 kernel; scenario reports on the M5 report stack (scenario
ids setup-only over shocks + universe). ADR-0009 extension recorded.
Tests: constraint enforcement (each constraint class violated then
refused), decomposition arithmetic, scenario outcomes, report-stack
reuse.

### Phase E — drift/failure detection + signal promotion (issue #43)

`quantmesh.research.drift`: feature drift (population-stability index
and KS tests on feature frames, fail-closed on short samples), prediction
drift (score distributions vs the training window), data-staleness
(the M5 stale-data discipline applied to feature inputs), failure
detection (missing features, NaN, coverage collapse); `AlertRecord`
ledger JSONL (atomic appends, fail-closed reads, duplicate refusal);
`PromotionRecord` ledger — a signal is promoted only with the full
evidence bundle (benchmark report id + ablation report ids + OOS
report id), identity pins the evidence, never the outcome; report-only
kill-switch tie-in (enforcement is M10). ADR-0009 extension recorded.
Tests: injected drift detected (shifted features, stale inputs, NaN
rows), alert ledger discipline, promotion requires the full bundle,
the acceptance drill over fixture universes (M7 exit criteria 1-2).

## Delivery protocol

Solo fast lane: one branch `feat/m7-unified-research-and-portfolio-engine`,
one tested/reviewed/issue-linked commit per issue, push each checkpoint,
one final M7 PR after acceptance criteria complete, squash-merge under
the standing merge authority when CI is green, close #39-#43, checkpoint
ACTIVE.md/0009/ROADMAP.md. There is no human gate in M7: all surfaces
are local computation over pinned fixtures with no credentials and no
new execution path. The only stacking constraint: the M7 PR merges
after the M6 PR #38 (which stacks on the M5 PR, which awaits the M5
operator drill).

## Durable decisions to record when reached

- ADR-0009 **to record** (issue #39 Phase A): the feature and model
  registries follow the M3 experiment-registry discipline — setup-only
  16-hex identity over commit + name/type + parameters + dataset pins
  (metrics and artifacts are results, never identity), lake-pin
  validation at record AND resolve, JSONL with atomic temp+replace
  appends, fail-closed reads with line attribution, duplicate refusal;
  model artifacts are byte-stable per type with the sha256 recorded on
  the record. Dependency decision: the research extra gains
  scipy/hmmlearn/arch pins, and CI installs `.[dev,research]` — a
  deliberate, documented deviation from the M3 duckdb-promotion
  precedent (the ML stack is optional runtime surface; the paper
  kernel core stays lean; the research extra is a first-class,
  CI-tested surface because M7 makes it one).
- ADR-0009 extension **to record** (issue #40 Phase B): baseline
  pipelines are lazy import-guarded with typed errors (the M5
  SDK-transport idiom); every pipeline fits on its window's train slice
  only and registers as a `run_walk_forward` strategy branch; reports
  carry benchmark + ablation + OOS evidence; determinism is pinned at
  fixed versions/seeds with cross-platform float differences documented
  (identity never includes weights).
- ADR-0009 extension **to record** (issue #41 Phase C): ensemble weights
  derive from validation windows only; epistemic uncertainty is the
  between-member disagreement; calibration uses the M6 Brier/reliability
  discipline.
- ADR-0009 extension **to record** (issue #42 Phase D): portfolio
  construction is risk-budget via scipy SLSQP with a documented
  constraint surface (venue, asset-class, event-risk, leverage); shocks
  are deterministic and scenario reports run on the M5 report stack;
  infeasible systems fail closed.
- ADR-0009 extension **to record** (issue #43 Phase E): drift and
  failure detection are evidence-producing with an alert ledger; signal
  promotion requires the full benchmark/ablation/OOS evidence bundle
  and identity pins the evidence, never the outcome; kill-switch
  integration is report-only until M10.

## Work log

- 2026-08-08: M7 planned and opened — iteration 0009 recorded; issues
  #39-#43 created with the M7 label; branch
  `feat/m7-unified-research-and-portfolio-engine` branched from the M6
  tip `7c4a0d1` (stacked delivery). Reuse survey done: lightgbm
  (>=4.5,<5) and scikit-learn (>=1.5,<2) already pinned in the research
  extra; scipy/hmmlearn/arch need new pins; the local venv has none of
  the ML stack installed and CI installs `.[dev]` only, so the CI
  install line and the extra pins move together in Phase B; the M5
  `run_walk_forward`/`STRATEGIES` extension mechanism and the M3
  `ExperimentRegistry` pattern are the direct integration points. No
  external gates: M7 is local computation over pinned fixtures end to
  end (the stacked M4/M5/M6 PR chain is the only dependency).

## Verification evidence

- Phase A slice (issue #39): pending.
- Phase B slice (issue #40): pending.
- Phase C slice (issue #41): pending.
- Phase D slice (issue #42): pending.
- Phase E slice (issue #43): pending.

## Risks and gates

- Library determinism across platforms (lightgbm/hmmlearn/arch) —
  determinism is pinned at fixed versions and seeds on the CI platform;
  cross-platform float differences are documented; identity never
  includes weights, so a rebuilt artifact with identical evidence is
  the same model.
- ML dependency weight — the research extra keeps the paper kernel
  core lean; CI installs the extra so the pipelines are first-class
  tested surface.
- Portfolio optimizer sensitivity — scipy SLSQP with documented
  starting points; constraints re-verified by projection after
  optimization; infeasible systems fail closed.
- Data drift between fixture universes and live research — fixture
  universes are the pinned contract; drift detection (Phase E) exists
  precisely to flag the divergence when live data arrives (M8/M10).
- No external gates: M7 carries no human gate (local computation, no
  credentials, no new execution path). The only dependency is the
  stacked M4 → M5 → M6 PR chain.
