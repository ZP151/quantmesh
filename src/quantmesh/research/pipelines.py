"""ML baseline pipelines: lazy-import-guarded codecs and report harness (issue #40).

Phase B of M7 ships four baseline pipelines: logistic regression and
LightGBM (binary classifiers over feature frames) and a two-state HMM
and GARCH (regime and volatility signals over per-symbol returns).
Each registers as a ``run_walk_forward`` strategy (the ``MODEL_STRATEGIES``
branch): per window the harness fits the pipeline on the train segment
only and weights the test segment by the top half of the train
window's mean signal (``signal_top_half_weights``).

No-lookahead is structural. Classifier labels lead by one bar — ``y[t]``
is the direction of ``close[t+1]`` vs ``close[t]`` — so the train slice
ends at ``test_start - 2`` and the last label compares closes up to
``test_start - 1``, known at rebalance. The HMM signal is a manual
forward filter (smoothing both directions would leak the future), and
GARCH's conditional variance at bar ``t`` uses observations up to
``t - 1``.

The research stack (scikit-learn, lightgbm, arch) is an
optional extra (ADR-0009 decision 6): accessors import lazily and raise
``PipelineUnavailableError`` with a typed message, so the paper kernel
core imports and runs without it. Determinism is a pinned contract
(ADR-0009): fixed seeds, ``deterministic=True`` with ``num_threads=1``
for lightgbm, method-of-moments estimation for the HMM, and
same-version byte-identical codecs.
"""

import hashlib
import importlib
import json
import math
import re
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from quantmesh.domain.market_data import Bar
from quantmesh.research.baselines import (
    run_baseline_report,
    run_walk_forward,
    validate_universe,
    write_artifacts,
)
from quantmesh.research.features import FeatureSpec, compute_feature, featureset_id
from quantmesh.research.reports import (
    ID_PATTERN,
    CostModel,
    Parameter,
    ReportRegistry,
    StrategyReport,
    UniverseMember,
    WalkForwardSpec,
    current_commit,
    report_id,
)

PIPELINE_KINDS = ("logistic", "lightgbm", "hmm", "garch")
_CLASSIFIER_KINDS = ("logistic", "lightgbm")

# Default hyperparameters per pipeline kind; explicit values override
# defaults, and the merged dict is what ``pipeline_digest`` covers, so an
# explicitly-defaulted setup is the same pipeline as a bare one. Unknown
# keys pass through to the underlying library as constructor kwargs.
DEFAULT_HYPERPARAMETERS: dict[str, dict[str, Parameter]] = {
    "logistic": {},
    "lightgbm": {
        "n_estimators": 20,
        "num_leaves": 7,
        "learning_rate": 0.05,
        "min_child_samples": 3,
        "deterministic": True,
        "num_threads": 1,
        "seed": 42,
        "verbosity": -1,  # keep library chatter out of fitted runs
    },
    # The HMM estimator is parameter-free: deterministic
    # method-of-moments on a variance-threshold state path (no EM —
    # hmmlearn 0.3.3's EM numerically diverges on variance-regime data
    # and scikit-learn's GaussianMixture collapses into degenerate
    # spike components), so any user-supplied hyperparameter would be
    # inert. HMMPipeline rejects them loudly instead of letting them
    # silently drift the digest.
    "hmm": {},
    "garch": {"p": 1, "q": 1},
}


class PipelineUnavailableError(RuntimeError):
    """The research extra is not installed (ADR-0009 decision 6)."""


def _require_sklearn():
    try:
        return importlib.import_module("sklearn")
    except ImportError as error:
        raise PipelineUnavailableError(
            "pipeline kind 'logistic' needs scikit-learn; install quantmesh[research]"
        ) from error


def _require_lightgbm():
    try:
        return importlib.import_module("lightgbm")
    except ImportError as error:
        raise PipelineUnavailableError(
            "pipeline kind 'lightgbm' needs lightgbm; install quantmesh[research]"
        ) from error


def _require_arch():
    try:
        return importlib.import_module("arch")
    except ImportError as error:
        raise PipelineUnavailableError(
            "pipeline kind 'garch' needs arch; install quantmesh[research]"
        ) from error


def normalize_hyperparameters(
    kind: str, hyperparameters: dict[str, Parameter] | None
) -> dict[str, Parameter]:
    """Validate and normalize a pipeline's hyperparameters.

    Defaults merge under explicit overrides; the merged dict feeds both
    the fit and ``pipeline_digest``, so the digest always covers exactly
    what the fit consumed. Names must be identifiers (they become
    library kwargs) and float values must be finite.
    """
    if kind not in DEFAULT_HYPERPARAMETERS:
        raise ValueError(f"unknown pipeline kind {kind!r} (expected {PIPELINE_KINDS})")
    merged = dict(DEFAULT_HYPERPARAMETERS[kind])
    for name, value in (hyperparameters or {}).items():
        if not isinstance(name, str) or not name.isidentifier():
            raise ValueError(f"hyperparameter name {name!r} is not a valid identifier")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"hyperparameter {name!r} must be finite, got {value}")
        merged[name] = value
    return merged


def pipeline_digest(
    kind: str, hyperparameters: dict[str, Parameter], featureset_id_value: str
) -> str:
    """Setup-only identity of a pipeline strategy (issue #40).

    Covers the kind, the normalized hyperparameters (defaults merged
    under explicit overrides, so an explicitly-defaulted setup is the
    same pipeline as a bare one) and the feature set's id; ``report_id``
    folds the digest in, so a different pipeline setup is a different
    report. Never covers results — the report's metrics and evidence
    stay outside the identity (ADR-0005 decision 2).
    """
    if not re.fullmatch(ID_PATTERN, featureset_id_value):
        raise ValueError(f"featureset id {featureset_id_value!r} is not a featureset id")
    normalized = normalize_hyperparameters(kind, hyperparameters)
    canonical = json.dumps(
        {"kind": kind, "hyperparameters": normalized, "featureset": featureset_id_value},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(f"pipeline\0{canonical}".encode()).hexdigest()[:16]


def direction_labels(closes: pd.Series) -> pd.Series:
    """Leading one-bar direction labels: y[t] = direction of close[t+1].

    One label per bar except the last, which has no next close to
    compare against (it is dropped, not fabricated). A train slice cut
    at ``test_start - 1`` keeps every label computable from train bars
    only — the last label compares ``close[test_start - 1]`` against
    ``close[test_start - 2]``, both known at rebalance. Equal closes
    label 0, deterministically.
    """
    shifted = closes.shift(-1)
    labels = pd.Series(np.where(shifted > closes, 1.0, 0.0), index=closes.index)
    # The shifted last bar is NaN, and NaN comparisons are False — drop
    # it explicitly rather than letting a fabricated 0.0 label through.
    return labels[shifted.notna()]


def _require_binary_labels(y: pd.Series) -> np.ndarray:
    """Classifier pipelines are binary: both 0 and 1 must be present."""
    labels = y.to_numpy()
    classes = np.unique(labels)
    if set(classes.tolist()) != {0.0, 1.0}:
        raise ValueError(
            "binary pipelines need both 0/1 classes in the train slice; "
            f"got {sorted(classes.tolist())}"
        )
    return labels


def _decode_payload(raw: bytes, expected: str) -> dict:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("pipeline artifact is not valid JSON") from error
    if not isinstance(payload, dict) or payload.get("format") != expected:
        raise ValueError(f"pipeline artifact format is not {expected!r}")
    return payload


class LogisticPipeline:
    """Binary logistic regression over feature frames (issue #40).

    sklearn's lbfgs solver is deterministic (no random generator); the
    codec is the canonical ``quantmesh-logistic-v1`` JSON — coefficients,
    intercept, classes and the hyperparameters that produced the fit — and
    rehydrates without refitting (``from_bytes``), matching the Phase A
    registry's byte-addressed artifact contract.
    """

    FORMAT = "quantmesh-logistic-v1"

    def __init__(self, hyperparameters: dict[str, Parameter] | None = None) -> None:
        self.hyperparameters = dict(hyperparameters or {})
        self._model = None

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "LogisticPipeline":
        sklearn = _require_sklearn()
        labels = _require_binary_labels(y)
        model = sklearn.linear_model.LogisticRegression(
            max_iter=1000, solver="lbfgs", **self.hyperparameters
        )
        self._model = model.fit(X.to_numpy(), labels)
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """P(positive) per row."""
        self._require_fitted()
        return self._model.predict_proba(X.to_numpy())[:, 1]

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return np.where(self.predict_proba(X) >= 0.5, 1.0, 0.0)

    def to_bytes(self) -> bytes:
        self._require_fitted()
        payload = {
            "format": self.FORMAT,
            "hyperparameters": self.hyperparameters,
            "coef": [float(value) for value in self._model.coef_[0]],
            "intercept": float(self._model.intercept_[0]),
            "classes": [int(value) for value in self._model.classes_],
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()

    @classmethod
    def from_bytes(cls, raw: bytes) -> "LogisticPipeline":
        payload = _decode_payload(raw, cls.FORMAT)
        pipeline = cls(payload["hyperparameters"])
        sklearn = _require_sklearn()
        model = sklearn.linear_model.LogisticRegression(
            max_iter=1000, solver="lbfgs", **pipeline.hyperparameters
        )
        model.coef_ = np.asarray([payload["coef"]], dtype=float)
        model.intercept_ = np.asarray([payload["intercept"]], dtype=float)
        model.classes_ = np.asarray(payload["classes"], dtype=int)
        pipeline._model = model
        return pipeline

    def _require_fitted(self) -> None:
        if self._model is None:
            raise ValueError("fit() before predicting or serializing")


class LightGBMPipeline:
    """LightGBM gradient boosting over feature frames (issue #40).

    Deterministic by contract (ADR-0009): ``deterministic=True`` with a
    fixed seed and ``num_threads=1``, so identical data at pinned
    versions produce byte-identical boosters. The codec is the canonical
    ``quantmesh-lightgbm-v1`` JSON — the booster's model string plus the
    hyperparameters that produced it; ``from_bytes`` rehydrates the
    booster, so predictions reproduce without refitting.
    """

    FORMAT = "quantmesh-lightgbm-v1"

    def __init__(self, hyperparameters: dict[str, Parameter] | None = None) -> None:
        self.hyperparameters = dict(hyperparameters or {})
        self._booster = None

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "LightGBMPipeline":
        lightgbm = _require_lightgbm()
        labels = _require_binary_labels(y)
        model = lightgbm.LGBMClassifier(**self.hyperparameters)
        self._booster = model.fit(X.to_numpy(), labels).booster_
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """P(positive) per row: sigmoid of the booster's raw score.

        Prediction goes through the raw booster, not the sklearn wrapper
        (whose fitted-state attributes ``from_bytes`` does not rehydrate),
        so the rehydrated pipeline predicts identically to the fitted one.
        """
        self._require_fitted()
        raw = self._booster.predict(X.to_numpy(), raw_score=True)
        return 1.0 / (1.0 + np.exp(-raw))

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return np.where(self.predict_proba(X) >= 0.5, 1.0, 0.0)

    def to_bytes(self) -> bytes:
        self._require_fitted()
        payload = {
            "format": self.FORMAT,
            "hyperparameters": self.hyperparameters,
            "booster": self._booster.model_to_string(),
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()

    @classmethod
    def from_bytes(cls, raw: bytes) -> "LightGBMPipeline":
        payload = _decode_payload(raw, cls.FORMAT)
        lightgbm = _require_lightgbm()
        pipeline = cls(payload["hyperparameters"])
        pipeline._booster = lightgbm.Booster(model_str=payload["booster"])
        return pipeline

    def _require_fitted(self) -> None:
        if self._booster is None:
            raise ValueError("fit() before predicting or serializing")


def _forward_filter(
    values: np.ndarray,
    means: np.ndarray,
    variances: np.ndarray,
    transmat: np.ndarray,
    startprob: np.ndarray,
) -> np.ndarray:
    """Normalized forward pass: P(state | observations up to t) for every t.

    Each step normalizes, so the filter never underflows; at bar ``t``
    only observations up to ``t`` have been consumed — the property that
    makes the HMM signal lookahead-free (issue #40). The emission
    likelihoods are log-sum-exp stabilized (the per-bar maximum is
    subtracted before exponentiating), so an extreme observation scores
    the nearest state with probability 1 instead of underflowing every
    weight to zero and dividing by a zero sum.
    """
    if len(values) == 0:
        raise ValueError("cannot filter an empty return series")
    x = values.reshape(-1, 1)
    log_likelihood = -0.5 * (
        np.log(2.0 * np.pi * variances).reshape(1, -1)
        + (x - means.reshape(1, -1)) ** 2 / variances.reshape(1, -1)
    )
    alphas = np.empty((len(values), len(means)))
    weights = np.exp(log_likelihood - log_likelihood.max(axis=1, keepdims=True))
    alpha = startprob * weights[0]
    alpha = alpha / alpha.sum()
    alphas[0] = alpha
    for t in range(1, len(values)):
        alpha = (alpha @ transmat) * weights[t]
        alpha = alpha / alpha.sum()
        alphas[t] = alpha
    return alphas


class HMMPipeline:
    """Two-state Gaussian HMM regime signal over per-symbol returns (issue #40).

    Emissions are squared returns (variance units), so each state is a
    volatility regime. Parameters are estimated by deterministic
    method-of-moments: the state path is seeded by the sample-mean
    threshold of the train slice's squared returns, and the emission
    means/variances, transition counts and start frequencies of that
    path are the model parameters — there is no EM to seed or iterate.
    That choice is a numerical necessity: hmmlearn 0.3.3's EM diverges
    on variance-regime data (its log-likelihood decreases, violating EM
    monotonicity) and scikit-learn's GaussianMixture collapses into
    degenerate spike components on skewed squared returns, so no
    off-the-shelf EM is fit to serve as the codec. State ordering is
    fixed — state 0 is the calm regime, state 1 the volatile regime —
    so no fitted convention needs to be stored. A train slice without
    enough bars on both sides of the threshold fails closed.

    The signal is the filtered probability of the volatile state at
    each bar, computed by hand (``_forward_filter``); smoothing both
    directions would leak the last bars' observations into early
    probabilities. The codec is the canonical ``quantmesh-hmm-v1``
    JSON: the per-symbol fitted parameters only, so a rehydrated
    pipeline reproduces the signal without refitting.
    """

    FORMAT = "quantmesh-hmm-v1"
    MIN_STATE_MEMBERS = 5  # fewer bars in either regime = no contrast; fail closed

    def __init__(self, hyperparameters: dict[str, Parameter] | None = None) -> None:
        unknown = set(hyperparameters or {}) - set(DEFAULT_HYPERPARAMETERS["hmm"])
        if unknown:
            raise ValueError(
                f"hmm pipelines take no hyperparameters (got {sorted(unknown)}); "
                "the estimator is deterministic method-of-moments"
            )
        self.hyperparameters: dict[str, Parameter] = {}
        self._states: dict[str, dict[str, list]] = {}

    def fit(self, returns_by_symbol: dict[str, pd.Series]) -> "HMMPipeline":
        self._states = {}
        for symbol, series in returns_by_symbol.items():
            self._states[symbol] = self._estimate(series.to_numpy())
        return self

    @classmethod
    def _estimate(cls, values: np.ndarray) -> dict[str, list]:
        """Method-of-moments parameters for a two-state HMM on squared returns.

        The path seed (``squared > mean(squared)``) is a standard
        variance-regime indicator: above-mean squared return marks the
        volatile state. The emission moments are the per-state mean and
        variance of the squared returns; transitions and start
        probabilities are Laplace-smoothed counts of the path, so a
        state observed only at the sample edges still normalizes.
        """
        squared = np.square(values)
        path = (squared > float(np.mean(squared))).astype(int)  # 1 = above the mean
        counts = np.bincount(path, minlength=2)
        if counts.min() < cls.MIN_STATE_MEMBERS:
            raise ValueError(
                f"no variance contrast in the train slice: only {counts.min()} "
                "bars fall into one regime; a two-state HMM needs both states "
                "populated (grow the train window)"
            )
        means = np.asarray([squared[path == 0].mean(), squared[path == 1].mean()])
        variances = np.asarray([squared[path == 0].var(), squared[path == 1].var()])
        if not np.all(variances > 0.0):
            raise ValueError("a regime state has zero variance; cannot fit a two-state HMM")
        transmat = np.full((2, 2), 1.0)
        np.add.at(transmat, (path[:-1], path[1:]), 1.0)
        transmat /= transmat.sum(axis=1, keepdims=True)
        startprob = counts.astype(float) + 1.0
        startprob /= startprob.sum()
        return {
            "means": [float(value) for value in means],
            "variances": [float(value) for value in variances],
            "transmat": [[float(value) for value in row] for row in transmat],
            "startprob": [float(value) for value in startprob],
        }

    def signals(self, returns_by_symbol: dict[str, pd.Series]) -> dict[str, np.ndarray]:
        """Filtered volatile-state probability per bar, per symbol.

        The forward pass at bar ``t`` consumes observations up to ``t``
        only — no lookahead (a future observation would raise early
        probabilities, exactly the leak two-directional smoothing has).
        """
        if not self._states:
            raise ValueError("fit() before signals()")
        out: dict[str, np.ndarray] = {}
        for symbol, series in returns_by_symbol.items():
            state = self._states[symbol]
            alphas = _forward_filter(
                np.square(series.to_numpy()),
                np.asarray(state["means"], dtype=float),
                np.asarray(state["variances"], dtype=float),
                np.asarray(state["transmat"], dtype=float),
                np.asarray(state["startprob"], dtype=float),
            )
            out[symbol] = alphas[:, 1]  # state 1 is the volatile regime by construction
        return out

    def to_bytes(self) -> bytes:
        if not self._states:
            raise ValueError("fit() before serializing")
        payload = {
            "format": self.FORMAT,
            "hyperparameters": self.hyperparameters,
            "symbols": self._states,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()

    @classmethod
    def from_bytes(cls, raw: bytes) -> "HMMPipeline":
        payload = _decode_payload(raw, cls.FORMAT)
        pipeline = cls(payload["hyperparameters"])
        pipeline._states = {
            str(symbol): state for symbol, state in payload["symbols"].items()
        }
        return pipeline


class GARCHPipeline:
    """GARCH(p, q) volatility signal over per-symbol returns (issue #40).

    The signal is ``1 / (1 + conditional_variance)`` — calm periods
    carry high weight. Returns are scaled by ``SCALE = 100`` for the
    fit (stable MLE on decimal returns); the scale is part of the
    pipeline contract, so the signal is deterministic. arch's
    conditional volatility at bar ``t`` uses observations up to ``t -
    1``, so the in-sample signal has no lookahead. The codec is the
    canonical ``quantmesh-garch-v1`` JSON — the fitted parameters only,
    replayed through ``fix`` so a rehydrated pipeline reproduces the
    signal without refitting.
    """

    FORMAT = "quantmesh-garch-v1"
    SCALE = 100.0

    def __init__(self, hyperparameters: dict[str, Parameter] | None = None) -> None:
        self.hyperparameters = dict(DEFAULT_HYPERPARAMETERS["garch"]) | dict(
            hyperparameters or {}
        )
        self._params: dict[str, dict[str, float]] = {}

    def fit(self, returns_by_symbol: dict[str, pd.Series]) -> "GARCHPipeline":
        arch = _require_arch()
        self._params = {}
        for symbol, series in returns_by_symbol.items():
            result = self._model_for(arch, series).fit(disp="off", show_warning=False)
            self._params[symbol] = {
                name: float(value) for name, value in result.params.items()
            }
        return self

    def signals(self, returns_by_symbol: dict[str, pd.Series]) -> dict[str, np.ndarray]:
        if not self._params:
            raise ValueError("fit() before signals()")
        arch = _require_arch()
        out: dict[str, np.ndarray] = {}
        for symbol, series in returns_by_symbol.items():
            model = self._model_for(arch, series)
            # Rebuild the params in the model's canonical name order:
            # the codec stores sorted keys (canonical JSON), and arch's
            # ``fix`` wires parameters positionally, so an unsorted
            # Series would silently mis-wire the values. The canonical
            # order is ``_all_parameter_names()`` — mean + volatility +
            # distribution; ``parameter_names()`` is an abstract method
            # returning only the mean model's names (``['mu']``) and
            # would silently drop the variance terms.
            ordered = pd.Series(
                {
                    name: self._params[symbol][name]
                    for name in model._all_parameter_names()
                }
            )
            result = model.fix(ordered)
            variance = result.conditional_volatility**2
            out[symbol] = 1.0 / (1.0 + variance)
        return out

    def to_bytes(self) -> bytes:
        if not self._params:
            raise ValueError("fit() before serializing")
        payload = {
            "format": self.FORMAT,
            "hyperparameters": self.hyperparameters,
            "symbols": self._params,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()

    @classmethod
    def from_bytes(cls, raw: bytes) -> "GARCHPipeline":
        payload = _decode_payload(raw, cls.FORMAT)
        pipeline = cls(payload["hyperparameters"])
        pipeline._params = {
            str(symbol): {str(name): float(value) for name, value in params.items()}
            for symbol, params in payload["symbols"].items()
        }
        return pipeline

    def _model_for(self, arch, series: pd.Series):
        return arch.arch_model(
            series.to_numpy() * self.SCALE,
            mean="Constant",
            vol="GARCH",
            p=int(self.hyperparameters["p"]),
            q=int(self.hyperparameters["q"]),
        )


def _pipeline_for(kind: str, hyperparameters: dict[str, Parameter]):
    """A pipeline object for the kind, over the merged hyperparameters."""
    if kind == "logistic":
        return LogisticPipeline(hyperparameters)
    if kind == "lightgbm":
        return LightGBMPipeline(hyperparameters)
    if kind == "hmm":
        return HMMPipeline(hyperparameters)
    return GARCHPipeline(hyperparameters)


def _validate_kind(kind: str) -> str:
    if kind not in PIPELINE_KINDS:
        raise ValueError(f"unknown pipeline kind {kind!r} (expected {PIPELINE_KINDS})")
    return kind


def _validate_featureset(featureset: list[FeatureSpec]) -> None:
    if not featureset:
        raise ValueError("a pipeline report needs at least one feature spec")
    ids = [spec.id for spec in featureset]
    if len(set(ids)) != len(ids):
        raise ValueError(f"duplicate feature ids in the pipeline set: {ids}")


def run_pipeline_report(
    *,
    pipeline: str,
    hyperparameters: dict[str, Parameter] | None = None,
    featureset: list[FeatureSpec],
    dataset: str,
    revision: int,
    interval: str,
    universe: list[UniverseMember],
    window_spec: WalkForwardSpec,
    costs: CostModel,
    benchmark_strategies: tuple[str, ...] = ("momentum", "risk_parity", "low_volatility"),
    ablations: tuple[str, ...] = (),
    commit: str | None = None,
    registry: ReportRegistry | None = None,
) -> StrategyReport:
    """Full pipeline report: benchmarks, ablations, and the main report.

    The harness pins everything through the lake's manifest gate, builds
    the per-symbol feature matrices (one column per feature id, aligned
    on the bar grid, warm-up rows dropped — a window whose train slice
    starts before the warm-up fails closed), and backtests the pipeline
    as a walk-forward strategy through ``window_signal_provider``, which
    fits the pipeline on each window's train segment only.

    Evidence is recorded as results (never identity, ADR-0005 decision
    2) on the main report: ``benchmark:<name>`` ids of the incumbent
    baselines, ``ablation:drop:<name>`` ids of the feature-drop variants,
    and ``windows_oos`` (test windows are out-of-sample by construction).
    Ablation variants are full pipeline reports over the reduced feature
    set — their metric deltas against the main report are the ablation
    evidence.
    """
    kind = _validate_kind(pipeline)
    params = normalize_hyperparameters(kind, hyperparameters)
    _validate_featureset(featureset)
    # Ablations are validated before any work: a drop that matches no
    # feature would silently re-run the full report under a mislabeled
    # evidence key, and an empty remainder is a degenerate report.
    for dropped in ablations:
        if not any(spec.name == dropped for spec in featureset):
            raise ValueError(f"ablation drop {dropped!r} matches no feature in the set")
        if all(spec.name == dropped for spec in featureset):
            raise ValueError(f"ablation drop {dropped!r} would leave no features")
    featureset_id_value = featureset_id(f"pipeline_{kind}", [spec.id for spec in featureset])
    digest = pipeline_digest(kind, params, featureset_id_value)

    registry = registry if registry is not None else ReportRegistry()
    if commit is None:
        commit = current_commit()
    members = validate_universe(universe)
    dataset_handle = registry.resolve_pin(dataset, revision)

    bars_by_symbol: dict[str, list[Bar]] = {}
    for member in members:
        bars = dataset_handle.read_bars(
            interval=interval, venue=member.venue, symbol=member.symbol
        )
        if not bars:
            raise ValueError(
                f"universe member {member.venue.value}.{member.symbol} has no "
                f"{interval} bars in dataset {dataset!r}"
            )
        bars_by_symbol[member.symbol] = bars
    grid = [bar.timestamp for bar in bars_by_symbol[members[0].symbol]]

    # Per-symbol feature matrices: one column per feature id, rows on
    # the bar grid after warm-up. Features outside the universe would
    # silently never enter the matrix — refuse instead.
    universe_keys = {(member.venue, member.symbol) for member in members}
    specs_by_key: dict[tuple, list[FeatureSpec]] = {}
    for spec in featureset:
        specs_by_key.setdefault((spec.venue, spec.symbol), []).append(spec)
    outside = set(specs_by_key) - universe_keys
    if outside:
        raise ValueError(
            "features reference symbols outside the universe: "
            f"{sorted((venue.value, symbol) for venue, symbol in outside)}"
        )
    missing = sorted(
        (member.venue.value, member.symbol)
        for member in members
        if (member.venue, member.symbol) not in specs_by_key
    )
    if missing:
        raise ValueError(f"features must cover the whole universe; missing {missing}")
    matrices: dict[str, pd.DataFrame] = {}
    for member in members:
        frames = [
            compute_feature(spec, dataset_handle).rename(spec.id)
            for spec in specs_by_key[(member.venue, member.symbol)]
        ]
        joined = pd.concat(frames, axis=1).dropna()
        if joined.empty:
            raise ValueError(
                f"no bar row carries every feature of the pipeline set for "
                f"{member.symbol!r}; the grid is too short for the feature windows"
            )
        matrices[member.symbol] = joined

    closes = {symbol: [bar.close for bar in bars] for symbol, bars in bars_by_symbol.items()}
    labels = {
        symbol: direction_labels(pd.Series(closes[symbol], index=grid))
        for symbol in closes
    }
    returns = {
        symbol: pd.Series(
            [0.0]
            + [
                closes[symbol][position] / closes[symbol][position - 1] - 1.0
                for position in range(1, len(closes[symbol]))
            ],
            index=grid,
        )
        for symbol in closes
    }

    def _provider(train_start: int, test_start: int) -> dict[str, float]:
        """Fit on the window's train slice; return mean train signals."""
        if kind in _CLASSIFIER_KINDS:
            # Rows up to test_start - 2: the last row's leading label
            # compares close[test_start - 1] vs close[test_start - 2],
            # both known at rebalance. Rows before the feature warm-up
            # do not exist in the matrix (warm-up was dropped), so
            # window 0's train slice simply starts at the warm-up
            # boundary; an empty overlap means the warm-up itself
            # exceeds the train window — fail closed.
            train_rows = grid[train_start : test_start - 1]
            x_train: dict[str, pd.DataFrame] = {}
            for symbol, matrix in matrices.items():
                rows = matrix.reindex(train_rows).dropna()
                if rows.empty:
                    raise ValueError(
                        f"feature warm-up for {symbol!r} exceeds the "
                        f"{window_spec.train_bars}-bar train window; grow "
                        "train_bars or drop deeper-window features"
                    )
                x_train[symbol] = rows
            y_train = {
                symbol: labels[symbol].reindex(x_train[symbol].index).astype(float)
                for symbol in x_train
            }
            if any(series.isna().any() for series in y_train.values()):
                raise ValueError("labels do not cover the train slice")
            order = sorted(x_train)
            # Each symbol's matrix columns are its own feature ids, so a
            # pd.concat across symbols would union the column names and
            # fill the gaps with NaN — the pooled fit must stack the
            # numeric blocks positionally, one block per symbol in
            # ``order`` (deterministic per window).
            x_pool = pd.DataFrame(
                np.concatenate(
                    [x_train[symbol].to_numpy(dtype=float) for symbol in order], axis=0
                )
            )
            y_pool = pd.Series(
                np.concatenate(
                    [y_train[symbol].to_numpy(dtype=float) for symbol in order], axis=0
                )
            )
            model = _pipeline_for(kind, params)
            model.fit(x_pool, y_pool)
            return {
                symbol: float(np.mean(model.predict_proba(x_train[symbol])))
                for symbol in order
            }
        # Return-based pipelines (hmm / garch): the return of bar
        # test_start - 1 is known at rebalance, so the train slice may
        # include it.
        train_returns = {
            symbol: returns[symbol].iloc[train_start:test_start] for symbol in returns
        }
        model = _pipeline_for(kind, params)
        model.fit(train_returns)
        signals = model.signals(train_returns)
        return {symbol: float(np.mean(signals[symbol])) for symbol in sorted(signals)}

    evidence: dict[str, Parameter] = {}
    for name in benchmark_strategies:
        report = run_baseline_report(
            dataset=dataset,
            revision=revision,
            strategy=name,
            interval=interval,
            universe=members,
            window_spec=window_spec,
            costs=costs,
            commit=commit,
            registry=registry,
        )
        evidence[f"benchmark:{name}"] = report.id
    for dropped in ablations:
        remaining = [spec for spec in featureset if spec.name != dropped]
        if not remaining:
            raise ValueError(f"ablation drop {dropped!r} would leave no features")
        ablation = run_pipeline_report(
            pipeline=kind,
            hyperparameters=params,
            featureset=remaining,
            dataset=dataset,
            revision=revision,
            interval=interval,
            universe=universe,
            window_spec=window_spec,
            costs=costs,
            benchmark_strategies=(),
            ablations=(),
            commit=commit,
            registry=registry,
        )
        evidence[f"ablation:drop:{dropped}"] = ablation.id
    evidence["windows_oos"] = True

    result = run_walk_forward(
        bars_by_symbol,
        strategy=kind,
        window_spec=window_spec,
        costs=costs,
        window_signal_provider=_provider,
    )
    report = StrategyReport(
        id=report_id(
            dataset=dataset,
            revision=revision,
            commit=commit,
            strategy=kind,
            interval=interval,
            universe=members,
            window_spec=window_spec,
            costs=costs,
            pipeline_digest=digest,
        ),
        dataset=dataset,
        revision=revision,
        commit=commit,
        strategy=kind,
        interval=interval,
        universe=members,
        window_spec=window_spec,
        costs=costs,
        pipeline_digest=digest,
        created_at=datetime.now(UTC),
        metrics=result.metrics,
        evidence=evidence,
        windows=result.windows,
    )
    write_artifacts(registry.root, report, result)
    registry.record(report)
    return report
