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
  the research extra pins (scipy/arch) and the CI install
  change.
- Out of scope: any execution path — M7 computes, records and alerts;
  it places nothing (the M2 paper kernel remains the only execution
  surface, and the promotion/kill-switch wiring is report-only here —
  enforcement is M10); M8-M10; the M4/M5/M6 external gates (already
  recorded and deferred).
- Reuse: lightgbm (>=4.5,<5) and scikit-learn (>=1.5,<2) already
  pinned in the research extra; new pins scipy (>=1.13,<2, used
  directly so pinned) and arch (>=7,<8) in the research extra —
  hmmlearn is deliberately not added, because the HMM codec ended up
  pure numpy (ADR-0009 decision 7: its EM is numerically unfit on
  variance-regime data); the M3 experiment-registry discipline (setup-only
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

1. [x] Feature and model registries follow the M3 discipline: setup-only
      identity (commit + name + parameters + dataset pins — never
      metrics), lake-pin validation at record AND resolve, JSONL with
      atomic temp+replace appends, fail-closed reads with line
      attribution, duplicate refusal, byte-stable artifacts; a pinned
      feature set reproduces identical frames on a clean checkout. —
      Phase A (issue #39).
2. [x] LightGBM, logistic, HMM and GARCH baseline pipelines each
      produce cost-aware walk-forward reports (M5 report stack) with
      benchmark, ablation and out-of-sample evidence; every window
      trains on its own train slice only (no-lookahead proven by test);
      runs are deterministic on pinned fixtures. — Phase B (issue #40).
3. [x] Ensemble weights derive from validation windows only (proven by
      test); ensemble predictions carry calibrated uncertainty, with
      calibration evidence computed under the M6 Brier/reliability
      discipline. — Phase C (issue #41).
4. [x] Portfolio construction respects venue, asset and event-risk
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

`quantmesh.research.features`: `FeatureSpec` (name, kind — bar-derived
recorded; orderbook/event kinds are documented extensions that land
with their pin contracts and consumers, never recordable-but-
uncomputable, source venue and universe, parameters, setup-only 16-hex
`feature_id` over commit + name + kind + parameters + dataset pins),
`FeatureSet` (sorted member ids + its own digest — member order never
changes identity — folding into model identity), `compute_features`
(deterministic frames from pinned M3 lake datasets; fail-closed on
missing pins, empty outputs, mixed grids). `quantmesh.research.models`: `ModelSpec` (type — lightgbm /
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
SDK-transport idiom) for lightgbm, scikit-learn and arch with typed
errors; `LightGBMPipeline` / `LogisticPipeline` (binary
classifier on feature frames), `HMMPipeline` (regime signal), `GARCHPipeline`
(volatility forecast signal); each exposes fit-on-train / predict-on-test
and registers as a `run_walk_forward` strategy branch (the M5 Phase D
`STRATEGIES` extension mechanism), producing cost-aware walk-forward
reports with benchmark (incumbent baselines from M4/M5) + ablation
(feature-drop sets with metric deltas) + out-of-sample (test windows by
construction) evidence recorded as `StrategyReport`s; deterministic
seeds and same-version byte determinism pinned by test; the fixture
drill runs the M3 lake fixture universe (equity + crypto bars) plus M6
implied probabilities as event-derived features. Classifier windows
pool the per-symbol feature blocks positionally into one fit (each
symbol's matrix carries its own feature ids, so a name-wise concat
would union the columns into NaN holes); return pipelines fit per
window on train returns only. Dependency decisions recorded in
ADR-0009: research extra gains scipy/arch pins (hmmlearn is *not*
added — its EM numerically diverges on variance-regime data, so the
HMM codec is a pure-numpy deterministic method-of-moments estimator
with no hyperparameters; ADR-0009 decision 7 records the evidence and
the amendment); CI installs `.[dev,research]` (deliberate, documented
deviation from the M3 duckdb-promotion precedent: the ML stack is
genuinely optional runtime surface and the paper kernel core stays
lean). Tests: per-pipeline walk-forward reports, ablation deltas,
no-lookahead proof, typed errors without the extra, determinism,
fail-closed HMM guards (no variance contrast, non-empty
hyperparameters), pooled-fit NaN freedom.

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

- ADR-0009 **recorded** (issue #39 Phase A): the feature and model
  registries follow the M3 experiment-registry discipline — setup-only
  16-hex identity over commit + name/type + parameters + dataset pins
  (metrics and artifacts are results, never identity), lake-pin
  validation at record AND resolve, JSONL with atomic temp+replace
  appends, fail-closed reads with line attribution, duplicate refusal;
  model artifacts are byte-stable per type with the sha256 recorded on
  the record; Phase A ships the pure-numpy `linear` codec
  (`quantmesh-linear-v1` canonical JSON); feature kinds beyond bars are
  documented extensions, refused at construction and compute. Dependency
  decision: the research extra gains scipy/arch pins (hmmlearn is
  *not* added — decision 7 records why), and CI installs
  `.[dev,research]` — a deliberate, documented extension of the
  dependency contract (a first-class, CI-tested extra because M7 makes
  the research surface one), contrasted with the M3 duckdb-promotion
  precedent (an infra necessity); the paper kernel core stays lean and
  Phase B codecs are lazy import-guarded.
- ADR-0009 extension **to record** (issue #40 Phase B): baseline
  pipelines are lazy import-guarded with typed errors (the M5
  SDK-transport idiom); every pipeline fits on its window's train slice
  only and registers as a `run_walk_forward` strategy branch; reports
  carry benchmark + ablation + OOS evidence; determinism is pinned at
  fixed versions/seeds with cross-platform float differences documented
  (identity never includes weights).
- ADR-0009 extension **recorded** (issue #41 Phase C): ensemble weights
  derive from validation windows only (the flip test proves it);
  epistemic uncertainty is the between-member disagreement (identical
  members → 0.0); calibration uses the M6 Brier/reliability discipline;
  membership is classifier-only (hmm/garch/linear refused — calibration
  needs probability-vs-outcome pairs); member featuresets resolve
  through the Phase A registry and must align on the same bar grid per
  symbol; the ensemble report registry rides the M5 stack with the
  lake-pin gate at record; the flip writes perturbed bars under the
  same dataset name so all setup ids stay identical (the column-order
  confound).
- ADR-0009 extension **recorded** (issue #42 Phase D): portfolio
  construction is risk-budget via scipy SLSQP (documented starting
  points, analytic jacobian, post-solve re-verification at 1e-6 on
  unrounded weights with returned checks re-measured on the 6 dp
  rounded weights); the constraint surface is four typed caps —
  venue, asset-class, event-risk (weight × (1 − M6 held probability)),
  leverage (M5 max_leverage linkage); structural infeasibility is
  refused pre-solve only when venue caps cover every universe venue
  and sum below 1; shocks (gap, funding, single-sweep liquidation,
  event mis-resolution) replay deterministically through the M2 kernel
  (funding charged before step orders; event sleeves marked-only);
  scenario reports run on the M5 stack with setup-only ids (scenario
  id over the timeline, shocks/orders canonical within a step) and no
  lake pin (the recorded universe IS the setup — the M6 precedent).
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
- 2026-08-08 (issue #39, Phase A): implemented `features.py` and
  `models.py`. Feature side: `FeatureSpec`/`FeatureSet`/`FeatureRegistry`
  with setup-only ids, five bar builtins (momentum, log_return,
  rolling_mean, rolling_std, realized_vol) validated at record AND
  compute, `compute_features` opening datasets once per pin through the
  lake's manifest gate, `frame_digest` (sorted canonical JSON, UTC ISO
  timestamps, repr floats) as the reproducibility reference. Model side:
  `MODEL_TYPES=("linear",)` — the pure-numpy `LinearModel` codec with
  canonical `quantmesh-linear-v1` JSON bytes; `ModelSpec`/`ModelRecord`/
  `ModelRegistry` with byte-addressed artifacts (sha256 recorded, load
  re-verifies; record append last so a crash leaves at worst an
  unreferenced orphan). Settings gained `features_dir`/`models_dir`.
  ADR-0009 recorded. During review the test file's first run exposed
  six real defects, all fixed: non-hex `COMMIT` fixture (pattern
  mismatch), id-clobbering test helper (explicit wrong ids must pass
  through), `window=` overrides not folded into `parameters`, closed-
  form comparisons including the NaN warm-up prefix, the
  duplicate-timestamps premise broken by write_bars' day-shard
  replacement (duplicates only possible within one call), and
  `.loc[list]` frame alignment (reindex onto the feature index
  instead). 60 new tests, full suite 1041 passed / 3 skipped, ruff
  clean, `git diff --check` and `git submodule status` clean. Committed
  as `M7-1 (#39): feature and model registries` and pushed.
- 2026-08-08 (issue #40, Phase B): implemented `pipelines.py` (~780
  lines) — the four codecs, `run_pipeline_report`, and the
  `window_signal_provider` hook in `run_walk_forward`. Logistic and
  LightGBM codecs round-trip canonically (the booster serializes as a
  model string — the sklearn wrapper's fitted state does not
  rehydrate from bytes); the LightGBM test suite caught that raw
  single-feature XOR data grows no tree, so the fixture is a step
  threshold and prediction goes through `Booster.predict(raw_score)`
  with a sigmoid. HMM and GARCH went through probe-driven diagnosis:
  GARCH's `fix()` wires parameters positionally, so the codec rebuilds
  them in `_all_parameter_names()` order (`parameter_names()` returns
  the mean model only and would drop the variance terms). The HMM
  consumed the most probing: hmmlearn 0.3.3's EM numerically diverges
  on variance-regime data even from the true parameters (its
  log-likelihood *decreases*, violating EM monotonicity — reproduced
  for covariance_type full and diag), and scikit-learn's
  GaussianMixture collapses into degenerate spike components on skewed
  squared returns — so the codec is a deterministic method-of-moments
  estimator (sample-mean threshold on squared returns, emission
  moments + Laplace-smoothed transition counts from the path, forward
  filter with log-sum-exp stabilization) and hmmlearn was dropped
  from the research extra (ADR-0009 decision 7 amendment). The report
  harness fixes: pooled classifier fits stack per-symbol blocks
  positionally (per-symbol feature ids would union into NaN columns),
  warm-up rows are dropped with an empty-overlap fail-closed guard,
  ablations and universe coverage validate before any work. 45
  pipeline tests green; affected research suites (models/baselines/
  reports/features) 128 passed.
- 2026-08-08 (issue #41, Phase C): implemented `ensemble.py` (~800
  lines) — `EnsembleSpec` (members ≥ 2, classifier-only,
  inverse_error|nnls), per-window validation holdouts between fit and
  test rows, weight functions (inverse error with zero-error
  domination; scipy nnls with n_obs ≥ n_members), disagreement =
  weighted variance (identical members → 0.0), M6 `brier_by_bin`
  calibration pooling across windows, `EnsembleReport` on the M5 stack
  (setup-only id + self-consistency validator, byte-stable artifacts,
  JSONL registry with duplicate refusal → lake-pin gate → atomic
  append). Probing caught two subtle defects before they could ship:
  the pipeline codecs return 1-D positive-class probabilities (no
  `[:, 1]`), and the flip test's original design — registering the
  perturbed lake under a different dataset name — changed the sorted
  featureset order (feature ids encode the dataset name), so run B was
  a different ensemble entirely: the instrumented probe showed 6
  distinct fit-input digests per run with identical y digests, proving
  the weight divergence was a setup difference, not lookahead. The
  flip now writes perturbed bars under the same dataset name in a
  separate lake root, so all setup ids (featureset/member/spec/report)
  stay identical and only the test-segment bytes differ; the test
  additionally asserts `report_a.id == report_b.id`. The dangling-pin
  registry test probes with a hand-built second report (the recorded
  report's duplicate refusal fires before the pin check) and asserts
  the ledger is byte-unchanged after the refusal. 39 ensemble tests
  green; full suite 1125 passed / 3 skipped; ruff clean.
- 2026-08-08 (issue #42, Phase D): implemented the full
  `quantmesh.portfolio` package — `constraints.py` (four typed caps
  incl. event-risk Σ w(1−p) from the M6 implied probabilities and the
  M5 `leverage_cap_from_risk_limits` linkage), `exposure.py`
  (decomposition by venue/asset class/event with the paired
  probability⇔event-key validator), `optimizer.py` (risk-budget SLSQP:
  Σ(RC − budget)² with analytic jacobian, documented inverse-vol/equal
  starting points, structural-infeasibility refusal, post-solve
  re-verification), `scenarios.py` (gap/funding/liquidation/event-
  misresolution shocks replayed through the M2 kernel), `reports.py`
  (scenario reports on the M5 stack, no lake pin — the M6 precedent),
  plus the `PaperAccount.apply_funding`/`total_funding` kernel
  extension. The first test run surfaced three real defects: the
  report artifact writer called `model_dump()` without `mode="json"`,
  so `json.dumps` choked on the datetime fields (the M6 idiom fixed
  it); the structural-infeasibility check fired on an EMPTY venue-cap
  surface (sum of zero caps = 0 < 1) — it now refuses only when the
  caps cover every venue in the universe, the partition argument; and
  the liquidation-cascade design was rewritten to a single sweep
  before testing (a round-loop could never succeed: closing converts
  mark to cash minus fees, so post-sweep < pre-sweep equity and the
  floor condition `pre < floor ≤ post` is unreachable — success
  requires the closeable bid to sit above the triggering mark). The
  fixture arithmetic is pinned by test: buy 8000 AAA at the 105 ask
  → cash 159,160; 20% gap-down marks equity at 751,160; a 0.76 floor
  sweeps at the 76 bid → cash 766,552, and a 0.8 floor fails closed.
  The optimizer's binding tests needed multi-venue universes (a
  single-venue universe with its only venue capped below 1 is
  *structurally* infeasible — the check working as intended). 82
  portfolio tests green; full suite 1207 passed / 3 skipped; ruff
  clean.

## Verification evidence

- Phase A slice (issue #39): `tests/test_research_features.py` (29
  tests) + `tests/test_research_models.py` (31 tests) — 60 passed.
  Identity: 9 field variations each change the feature id; featureset
  id order-insensitive; model id sensitive to every setup field.
  Pin discipline: record refused before any write when the lake
  manifest is missing or the revision differs (registry directory
  absent afterwards); `resolve` re-opens through the manifest gate.
  Fail-closed reads: corrupted line reported with line number,
  duplicate ids refused, registry root being a file refused. Artifacts:
  record/load round-trip with sha re-verification; tampered and
  missing artifacts fail closed. Acceptance drills: two pinned lakes +
  two registries → identical feature frames (`frame_digest` equality)
  and byte-identical model artifacts (sha256, id and metrics equal
  across roots; the artifact loaded from one root predicts exactly on
  the other's frame). Full suite: 1041 passed, 3 skipped (pre-existing
  skips); ruff, `git diff --check`, `git submodule status` all clean.
- Phase B slice (issue #40): `tests/test_research_pipelines.py` — 45
  passed, zero warnings. LightGBM: step-threshold accuracy 1.0,
  probabilities {0, 1}, byte-exact round-trip and refit (maxdiff 0.0).
  GARCH: signal separation q0 0.5409 / volatile 0.1065 / q1 0.4898 on
  the sine fixture with round-trip allclose; param re-wiring in
  `_all_parameter_names()` order verified by probe. HMM: moment
  estimator on the Gaussian regime fixture separates blocks with
  margins ≈ 1.0 (test threshold +0.3); determinism (byte-exact refits)
  and forward-filter causality (prefix invariant to appended
  observations) proven by test; the log-sum-exp stabilization removes
  the NaN underflow on extreme observations; hyperparameters refused,
  no-variance-contrast fails closed, and the pure-numpy estimator fits
  under the fully faked import guard. Report harness: 3 windows × 3
  symbols with per-window provider calls [(0,30),(10,40),(20,50)],
  turnover [1.0, 0.0, 0.0] (open then hold), 5 recorded reports with
  benchmark + ablation evidence, report id changes with
  hyperparameters, warm-up/ablation/universe fail-closed paths, and
  the cross-root acceptance drill with byte-identical artifacts and
  equal ids. Affected suites (models/baselines/reports/features): 128
  passed.
- Phase C slice (issue #41): `tests/test_research_ensemble.py` — 39
  passed. Weight functions: inverse-error arithmetic ([0.1, 0.3] →
  [0.75, 0.25]), zero-error domination, refusals (non-finite,
  negative, all-zero, empty); nnls known case (y == a member column →
  [0.0, 1.0]), sum-to-one on seeded RNG, too-few-observations and
  non-finite refusals, `PipelineUnavailableError` under faked imports.
  Predict: weighted mean + weighted-variance arithmetic, non-negative
  and sum-to-one refusals, one-prediction-per-member guard. Spec: id
  changes with every setup field, member-order invariance, classifier-
  only kinds refused, duplicates refused, min-2 enforced, wrong id
  refused. Report: 3 windows, n_test [30, 30, 27] (final window drops
  the newest unresolved bar per symbol — M6 precedent), n_validation
  15/window, weights sum to 1, nnls report, the flip test (identical
  weights across the test-bytes flip, `report_a.id == report_b.id`,
  window 0 byte-identical, flipped windows' Briers and calibration
  differ), identical members → [0.5, 0.5] weights and 0.0
  disagreement, report-id setup sensitivity, train-window and
  warm-up guards, unrecorded-featureset refusal, grid-alignment
  refusal, calibration discipline (half-open bins, empty-bin None),
  registry duplicate/dangling-pin/fail-closed/root-not-dir, and the
  cross-root acceptance drill with byte-identical artifacts. Full
  suite: 1125 passed, 3 skipped; ruff clean; `git diff --check` clean.
- Phase D slice (issue #42): `tests/test_portfolio_constraints.py`
  (17) + `tests/test_portfolio_optimizer.py` (14) +
  `tests/test_portfolio_scenarios.py` (38) +
  `tests/test_portfolio_reports.py` (13) — 82 passed. Constraints:
  paired probability⇔event-key validator, cap bounds and uniqueness,
  M5 `leverage_cap_from_risk_limits` linkage, event-risk
  Σ w(1−p) arithmetic (0.3 × 0.95 on a 5%-probability outcome),
  typed violations, duplicate-holding refusal. Exposure: decomposition
  by venue/class/event with both FED-SEP markets aggregating under one
  key. Optimizer: uncorrelated closed form (diag(4,1) → weights
  (1/3, 2/3), RC 4/9 each from the equal start), correlated parity
  ([[4, 1.5],[1.5, 1]] → (1/3, 2/3), RC 7/9 — two-asset parity is
  inverse-vol regardless of correlation), each cap class binding at
  its limit (venue 0.25, class 0.5, event-risk 0.15 on p=0.5 →
  weight 0.3, leverage 0.25), checks re-measuring the returned rounded
  weights, determinism, structural infeasibility (full-coverage caps
  summing < 1), covariance refusals (ndim/shape/non-finite/asymmetry/
  non-PSD), zero-variance and unknown-start refusals, n < 2 and
  duplicate holdings, scipy-missing → `PipelineUnavailableError` via a
  monkeypatched importlib. Scenarios: kernel funding extension
  (charge/receive/multi-position/unknown/non-finite/over-cash), gap
  up/down arithmetic (95/105/92.5 ↔ 76/84/74 at −20%), the pinned
  liquidation drill (159,160 → gap → 751,160 → sweep at 76 →
  766,552, n_liquidation_rounds 1, drawdown 0.233448; 0.8 floor fails
  closed; sub-floor no-trigger; no-bid refusal), funding replay
  (8,400 charged then 4,200 received; short marks at the bid and
  receives; unknown-position and over-cash refusals; funding charged
  before step orders), event mis-resolution (0.05 sleeve zeroed;
  both markets on one key zeroed; unknown event refused), kill-switch
  rejection, missing quote/mark fail-closed paths, scenario-id
  sensitivity to timeline order and shock parameters with invariance
  to within-step ordering, step-advance and id-match validators.
  Reports: full drill (id/registry/artifacts/metrics), report.json
  excluding `created_at`, windows.csv exact rows, byte-identical
  artifacts across two roots, registry duplicate/corrupted-line
  (line 2 attributed)/shared-id/root-not-a-directory (failing closed
  before any artifact write), id-setup sensitivity, setup-mismatch
  validator, kernel account_config snapshot. Full suite: 1207 passed,
  3 skipped; ruff clean; `git diff --check` clean.
- Phase E slice (issue #43): pending.

## Risks and gates

- Library determinism across platforms (lightgbm/arch) —
  determinism is pinned at fixed versions and seeds on the CI platform;
  cross-platform float differences are documented; identity never
  includes weights, so a rebuilt artifact with identical evidence is
  the same model. The HMM is immune by construction (pure numpy,
  no RNG).
- HMM estimator scope — method-of-moments assumes a clean variance
  threshold split of squared returns (well-separated regimes); weakly
  separated regimes (low scale ratios) degrade the signal rather than
  fail. Documented at the codec and in ADR-0009 decision 7; the M8
  research layer is the venue to revisit estimators with real-data
  evidence.
- ML dependency weight — the research extra keeps the paper kernel
  core lean; CI installs the extra so the pipelines are first-class
  tested surface.
- Portfolio optimizer sensitivity — scipy SLSQP with documented
  starting points; constraints re-verified by projection after
  optimization; infeasible systems fail closed.
- Feature ids encode the dataset name — a featureset's sorted member
  order (and thus per-symbol matrix column layout) changes when the
  same features are registered against a differently named dataset.
  The ensemble flip test is pinned to same-name flips; anything that
  re-registers features under a new dataset name must rebuild the
  featureset (a different set is a different setup by design).
- nnls weight conditioning — requires validation observations ≥ member
  count; below that budget the method refuses (fail-closed) and the
  inverse-error method remains the no-scipy default; scipy itself is
  lazy import-guarded with a typed `PipelineUnavailableError`.
- Structural-infeasibility coverage — the partition refusal covers
  venue caps only; a system blocked solely by a leverage cap (a
  single-venue universe capped below 1) surfaces as a typed solver
  refusal ("SLSQP did not converge") rather than a structural one.
  Both are fail-closed; the asymmetry is documented in ADR-0009
  decision 9.
- Boundary rounding at binding caps — returned checks re-measure the
  6 dp rounded weights, so a binding cap can sit at limit ± 5e-7 of
  rounding; refusals use the unrounded point at 1e-6 and the returned
  checks' violation tolerance is 1e-9 on the rounded values. The
  binding tests assert observed ≤ limit + 1e-6, never exact equality
  to the last float.
- Liquidation single-sweep semantics — closing converts mark to cash
  (minus fees), so a floor the flush cannot reach fails closed by
  design; a multi-round cascade was mathematically impossible (post-
  sweep < pre-sweep) and was removed during design review. A
  liquidation shock on a market without a bid fails closed.
- Funding charges precede step orders — a funding shock in the same
  step as the position-opening order refuses (the position does not
  exist yet at charge time); scenarios express this as separate
  steps. The paper kernel has no margin: any charge beyond cash fails
  closed.
- Data drift between fixture universes and live research — fixture
  universes are the pinned contract; drift detection (Phase E) exists
  precisely to flag the divergence when live data arrives (M8/M10).
- No external gates: M7 carries no human gate (local computation, no
  credentials, no new execution path). The only dependency is the
  stacked M4 → M5 → M6 PR chain.
