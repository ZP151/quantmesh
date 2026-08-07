# ADR-0009 — Research registries: setup-only identity, byte-addressed artifacts, and the research-dependency contract

- Status: accepted
- Date: 2026-08-08
- Deciders: solo delivery (iteration 0009, M7 Phase A, issue #39)
- Related: ADR-0006 (reconciliation discipline — the append-only JSONL
  ledger and fail-closed read idioms are carried over), ADR-0008
  (event-market data contract — the fixture-first, fail-closed
  disciplines this ADR extends), ADR-0003 (the lake's manifest gate —
  registry pins resolve through it), `docs/iterations/0009-m7-unified-research-and-portfolio-engine.md`

## Context

M7 unifies the research surface: features, models, ensembles,
portfolios and promotion decisions must all be reproducible records,
not loose artifacts. Phase A establishes the two foundational
registries (feature specs/sets and model records with byte-addressed
artifacts) on the discipline proven in the M3 experiment registry,
plus the dependency contract the Phase B pipelines need. Two facts
shape the decisions:

- **The venv has no research stack installed** (no scikit-learn,
  lightgbm, vectorbt, scipy or arch), and CI installs only
  `.[dev]` — so a Phase B pipeline that imports any of these breaks
  both local runs and CI.
- **M3 promoted duckdb to the core dependency by documented
  deviation.** For research, the roadmap pins four explicit
  pipelines (LightGBM, logistic, HMM, GARCH); those libraries are
  *user-visible research surface*, so this ADR treats the research
  extra as a first-class part of the dependency contract instead of a
  deviation to waive per-milestone.

## Decisions

### 1. Feature specs and sets are records of setup only; identity is deterministic, never a function of results

`FeatureSpec` pins everything that defines one computed feature —
code commit, name, kind, venue, symbol, interval, lake dataset and
revision, parameters — under a 16-hex id (sha256 over the canonical
sorted setup JSON). `FeatureSet` groups member ids under its own
digest, sorted ascending so member order never changes identity; the
canonical model feature order is the sorted member-id order.
Metrics, frame digests and artifact hashes are results and never
enter identity. The same setup always yields the same id, so
"reproduce feature X" is well-defined: resolve the pin through the
lake's manifest gate and recompute.

### 2. Registries validate the pin before any write and fail closed on every read

`FeatureRegistry` and `ModelRegistry` record only against datasets
that pass the lake's manifest gate at the pinned revision — a
dangling pin is refused before anything is written (asserted by the
tests: the registry directory is absent after a refused record).
Records persist as JSONL with the ADR-0006 discipline: atomic
temp+replace appends, fail-closed reads with line attribution and
duplicate-id refusal, corrupted lines reported with their line
number. `record_spec`/`record` refuse duplicates — the same setup is
the same feature/model.

### 3. Model artifacts are byte-addressed; load re-verifies the sha256

`ModelRegistry.record` writes the artifact under
`root/<id>/model.bin` (atomic temp + replace) and records its sha256
on the record; the record append happens last, so a crash leaves at
worst an unreferenced orphan artifact, never a record whose bytes
are missing. `load` re-verifies the hash — a missing, unreadable or
tampered artifact fails closed.

### 4. Phase A ships one model type — the pure-numpy `linear` codec — with a canonical byte format

`MODEL_TYPES = ("linear",)` in Phase A; the roadmap pipeline types
(lightgbm / logistic / hmm / garch) are registered by Phase B with
their pipelines. The linear codec is pure numpy (deterministic
`np.linalg.lstsq`, no random generator) and serializes to canonical
JSON (`quantmesh-linear-v1`): sorted keys, compact separators, exact
float reprs — identical inputs produce identical bytes, which the
acceptance drill pins across registry roots. This gives Phase A a
real, drill-capable model type with zero new dependencies while
Phase B lands the library-backed codecs.

### 5. Feature kinds beyond bars are documented extensions, never recordable-but-uncomputable paths

`FeatureKind` has one member (`BAR`); orderbook/event kinds are
documented extensions that land with their pin contracts and
consumers. A spec of an uncomputable kind is refused at construction
and `compute_feature` fails closed on it — the registry never holds
a spec that cannot compute.

### 6. The research extra is part of the dependency contract; CI installs `.[dev,research]`

Phase B extends `pyproject.toml`'s `research` extra with
`scipy>=1.13,<2` and `arch>=7,<8` beside the pinned
roadmap libraries (lightgbm 4.5+, scikit-learn 1.5+, vectorbt
0.27+), and CI's install step becomes `.[dev,research]` so the
pipeline codecs are installed where their tests run. This is a
*deliberate extension of the dependency contract* (a first-class
extra), documented here rather than as a per-milestone deviation —
research codecs are a promised roadmap surface, unlike the M3
duckdb promotion which was an infra necessity. Phase B code paths
use lazy import-guarded accessors (the M5 SDK idiom): importing
`quantmesh.research` never requires the research stack, so the core
test suite stays runnable without it.

### 7. Baseline pipelines are lazy import-guarded codecs with per-window train-only fits and an evidence bundle (Phase B extension, issue #40)

`quantmesh.research.pipelines` registers four strategy codecs —
`LogisticPipeline`, `LightGBMPipeline`, `HMMPipeline`,
`GARCHPipeline` — each exposing fit / predict(-proba) / signals and
canonical byte formats (`quantmesh-logistic-v1`, `quantmesh-lightgbm-v1`,
`quantmesh-hmm-v1`, `quantmesh-garch-v1`) matching the Phase A
byte-addressed artifact contract. The libraries load lazily and raise
`PipelineUnavailableError` with a typed message when the extra is
missing (the M5 SDK-transport idiom, decision 6). Three properties are
pinned by test:

- **No lookahead is structural.** Classifier labels lead by one bar
  (`y[t]` = direction of `close[t+1]`), so a window's train slice ends
  at `test_start - 2` and the last label compares closes up to
  `test_start - 1` — known at rebalance. The HMM signal is a manual
  forward filter (smoothing both directions would leak the future);
  the causality test appends observations and demands the signal
  prefix stay identical. GARCH's conditional variance at bar `t` uses
  observations up to `t - 1` by construction.
- **Determinism is a pinned contract.** Fixed seeds; lightgbm with
  `deterministic=True`, `num_threads=1`; sklearn lbfgs and arch MLE
  without RNG. The HMM is fit by deterministic method-of-moments —
  no RNG anywhere in the estimator. Same-version byte determinism is
  proven by refits on identical data and by the cross-root acceptance
  drill, which demands byte-identical report artifacts from two
  independent lakes and registries. Identity never includes weights
  or metrics, so a rebuilt artifact with identical evidence is the
  same model.
- **The HMM codec is pure numpy and takes no hyperparameters.** Its
  two-state Gaussian HMM (emissions on squared returns, state 0 =
  calm, state 1 = volatile) is estimated by method-of-moments: the
  state path is seeded by the sample-mean threshold of the train
  slice's squared returns, emission means/variances and
  Laplace-smoothed transition/start counts come from that path, and
  the signal is the log-sum-exp-stabilized forward filter's posterior
  on the volatile state. No EM: hmmlearn 0.3.3's EM numerically
  diverges on variance-regime data (its log-likelihood *decreases*,
  violating EM monotonicity — reproduced from the true parameters)
  and scikit-learn's GaussianMixture collapses into degenerate spike
  components on skewed squared returns, so neither off-the-shelf EM
  is fit to back the codec. Consequently hmmlearn is *not* a research
  dependency (an amendment to decision 6), and a non-empty
  hyperparameter dict is refused — an inert knob would silently drift
  the digest. A train slice without enough bars on both sides of the
  threshold fails closed.
- **Pipeline strategies backtest through the report stack.** Each kind
  is a `MODEL_STRATEGIES` member; `run_walk_forward` gains a
  `window_signal_provider(train_start, test_start)` hook that fits on
  the window's train slice and returns mean train signals, weighted by
  the shared top-half rule (`signal_top_half_weights`, factored out of
  the M5 `book_imbalance_weights`). `run_pipeline_report` orchestrates
  the evidence bundle: benchmark reports (the incumbent M4/M5
  baselines), ablation reports (one full pipeline report per dropped
  feature name), and the main report — all recorded as
  `StrategyReport`s whose ids pin the `pipeline_digest` (kind +
  normalized hyperparameters + feature-set id), never the outcomes.
  Evidence ids ride on the report as results (`evidence` field), so
  the evidence bundle is auditable but outside identity.

## Consequences

- Registry reads are O(records) linear scans over small JSONL files
  — fine for local research scale; the Phase B benchmarks will show
  whether a lookup index is needed (recorded as a Phase D decision
  point if so).
- The `linear` codec's byte format is versioned (`quantmesh-linear-v1`)
  and validated on load; future codecs register new formats rather
  than mutating old ones.
- Duplicate records are refused rather than appended, so a
  re-recorded setup (same commit, same pins) must intentionally
  change the setup or the code — the intended discipline for a
  local research history.
- Adding `.[dev,research]` to CI installs ~6 additional packages on
  every job; acceptable for the test surface they unlock, and the
  core suite (without research extra) still passes alone.
- Phase B registers four more codec formats (`quantmesh-logistic-v1`,
  `quantmesh-lightgbm-v1`, `quantmesh-hmm-v1`, `quantmesh-garch-v1`),
  versioned and validated on load like the linear codec; each kind is
  a `MODEL_STRATEGIES` strategy, so a new pipeline kind is code plus
  one tuple member. Cross-platform float differences in library-backed
  codecs are documented at the codec; they never change identity,
  because identity pins setup only — weights and metrics are results.
- hmmlearn is dropped from the research extra (decision 7): the HMM
  codec's estimator is pure numpy, so the extra loses a package while
  the HMM remains a registered, CI-tested pipeline kind. The
  estimator's method-of-moments assumption — a clean threshold split
  of squared returns, i.e. well-separated volatility regimes — is
  documented at the codec; weakly separated regimes degrade the
  signal rather than fail, which is a documented limitation, not a
  silent guarantee (recorded as a Phase D risk in iteration 0009).
