"""Ensemble combination and uncertainty calibration (M7 Phase C, issue #41).

An ensemble is a setup-only ``EnsembleSpec``: member model specs (each
already a deterministic setup digest) plus a weight method and a
validation budget. Every walk-forward window splits its train segment
into a fit slice and a validation tail: members fit on the fit slice,
member weights derive from validation errors only (inverse error or
nonnegative least squares via scipy), and the test segment is
evaluated once. Test observations never touch the weights — the
weight functions receive only validation rows, proven by test (the
tests flip the test closes and demand every weight stay identical).

Ensemble predictions carry disagreement-based epistemic uncertainty:
the per-bar weighted variance of member probabilities (identical
members produce zero disagreement by construction). Calibration pools
the ensemble's out-of-sample probability-vs-outcome pairs across
windows under the M6 ``brier_by_bin`` discipline (half-open bins,
empty-bin ``None``); the newest unresolved bars carry no label and are
excluded, never fabricated. Reports follow the M6 forecast report
idiom — setup-only ids, byte-stable artifacts, an append-only JSONL
registry — with the M5 lake-pin gate at record.
"""

import csv
import hashlib
import importlib
import json
import math
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field, ValidationError, model_validator

from quantmesh.data.lake import Dataset, Lake
from quantmesh.domain.market_data import Bar
from quantmesh.events.calibration import CalibrationBin, brier_by_bin
from quantmesh.research.baselines import validate_universe
from quantmesh.research.features import FeatureRegistry, FeatureSpec, compute_feature
from quantmesh.research.models import ModelSpec
from quantmesh.research.pipelines import (
    PipelineUnavailableError,
    _pipeline_for,
    direction_labels,
    normalize_hyperparameters,
)
from quantmesh.research.reports import UniverseMember, WalkForwardSpec, current_commit
from quantmesh.settings import settings

ENSEMBLES_FILE = "ensembles.jsonl"
ID_PATTERN = "^[0-9a-f]{16}$"
COMMIT_PATTERN = "^[0-9a-f]{7,64}$"
# Ensemble members must be probabilistic classifiers: the calibration
# evidence is probability-vs-outcome pairs, so regime signals (hmm /
# garch) and regression outputs (linear) are refused like ``fit_model``
# refuses them.
_CLASSIFIER_KINDS = ("logistic", "lightgbm")
_N_BINS_MIN = 1
_N_BINS_MAX = 100

Parameter = str | int | float | bool | None


def _require_scipy():
    """Lazy scipy accessor (ADR-0009 decision 6): the ensemble module
    imports nothing from the research stack until a weighted method
    needs it."""
    try:
        return importlib.import_module("scipy")
    except ImportError as error:
        raise PipelineUnavailableError(
            "scipy is not installed; install quantmesh[research] to derive "
            "ensemble weights with nnls"
        ) from error


def inverse_error_weights(errors: list[float]) -> list[float]:
    """Validation-error-weighted member weights: w_i = (1/e_i)/sum(1/e_j).

    A zero error is perfect on the validation slice — that member gets
    weight 1.0 and the rest 0.0 (deterministic, no division by zero).
    Errors must be finite and non-negative; all-zero errors are refused
    (no information to weight on). Weights are rounded to 6 dp: they are
    results, stored byte-stable, and never enter any identity.
    """
    if not errors:
        raise ValueError("inverse-error weighting needs at least one member error")
    if not all(math.isfinite(error) and error >= 0.0 for error in errors):
        raise ValueError(f"member errors must be finite and non-negative, got {errors}")
    if all(error == 0.0 for error in errors):
        raise ValueError("all member validation errors are zero; no signal to weight on")
    if any(error == 0.0 for error in errors):
        return [1.0 if error == 0.0 else 0.0 for error in errors]
    total = sum(1.0 / error for error in errors)
    return [round((1.0 / error) / total, 6) for error in errors]


def nnls_weights(
    member_predictions: np.ndarray, outcomes: np.ndarray
) -> list[float]:
    """Nonnegative least squares member weights (scipy.optimize.nnls).

    Solves min ||X w - y||2 subject to w >= 0 over the validation
    observations, then normalizes to a unit sum. The system is only
    well-posed with at least as many observations as members — fewer
    fails closed. scipy loads lazily (ADR-0009 decision 6).
    """
    predictions = np.asarray(member_predictions, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    if predictions.ndim != 2:
        raise ValueError(
            f"member predictions must be a 2-D matrix (observations x members), "
            f"got shape {predictions.shape}"
        )
    n_observations, n_members = predictions.shape
    if n_observations < n_members:
        raise ValueError(
            f"nnls weighting needs at least as many validation observations as "
            f"members ({n_observations} < {n_members}); grow validation_bars "
            "or drop members"
        )
    if y.shape != (n_observations,):
        raise ValueError(
            f"outcomes must match the prediction rows ({y.shape} vs "
            f"{predictions.shape})"
        )
    if not np.isfinite(predictions).all() or not np.isfinite(y).all():
        raise ValueError("nnls weighting needs finite inputs")
    solution, _residual = _require_scipy().optimize.nnls(predictions, y)
    total = float(solution.sum())
    if not math.isfinite(total) or total <= 0.0:
        raise ValueError("nnls weighting collapsed to a zero weight vector")
    return [round(float(weight) / total, 6) for weight in solution]


def ensemble_predict(
    member_predictions: np.ndarray, weights: list[float]
) -> tuple[float, float]:
    """Weighted mean and weighted-variance disagreement of one row.

    Identical members produce zero disagreement by construction —
    every p_m equals the shared mean. Weights must be non-negative and
    sum to one (within 1e-6, since results round to 6 dp).
    """
    predictions = np.asarray(member_predictions, dtype=float)
    if predictions.ndim != 1 or predictions.shape[0] != len(weights):
        raise ValueError(
            f"one prediction per member: got {predictions.shape[0]} predictions "
            f"for {len(weights)} weights"
        )
    if not np.isfinite(predictions).all():
        raise ValueError("member predictions must be finite")
    if any(weight < 0.0 for weight in weights):
        raise ValueError(f"weights must be non-negative, got {weights}")
    if not math.isclose(sum(weights), 1.0, abs_tol=1e-6):
        raise ValueError(f"weights must sum to one, got {sum(weights)}")
    mean = float(np.dot(predictions, weights))
    variance = float(np.dot(weights, (predictions - mean) ** 2))
    return round(mean, 6), round(variance, 6)


def ensemble_id(
    *,
    members: list[ModelSpec],
    weight_method: str,
    validation_bars: int,
) -> str:
    """Deterministic identity of an ensemble spec: setup only, never results.

    Member ids (themselves setup digests) hash over sorted order, so
    member order never changes the identity (ADR-0005 decision 2).
    Weights, metrics and disagreements are results and never enter the
    id.
    """
    setup = {
        "members": sorted(member.id for member in members),
        "weight_method": weight_method,
        "validation_bars": validation_bars,
    }
    canonical = json.dumps(setup, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"ensemble\0{canonical}".encode()).hexdigest()[:16]


class EnsembleSpec(BaseModel):
    """Setup-only record of one ensemble: members, weight method, validation budget."""

    members: list[ModelSpec] = Field(min_length=2)
    weight_method: str = Field(pattern="inverse_error|nnls")
    validation_bars: int = Field(ge=1)
    id: str = Field(pattern=ID_PATTERN)

    @model_validator(mode="after")
    def spec_is_consistent(self) -> "EnsembleSpec":
        ids = [member.id for member in self.members]
        if len(set(ids)) != len(ids):
            raise ValueError(f"ensemble members must be unique, got {ids}")
        for member in self.members:
            if member.model_type not in _CLASSIFIER_KINDS:
                raise ValueError(
                    f"ensemble member {member.id!r} is a {member.model_type!r} "
                    "pipeline; only probabilistic classifiers (logistic, "
                    "lightgbm) qualify — calibration needs "
                    "probability-vs-outcome pairs"
                )
        expected = ensemble_id(
            members=self.members,
            weight_method=self.weight_method,
            validation_bars=self.validation_bars,
        )
        if self.id != expected:
            raise ValueError(
                f"ensemble spec id {self.id!r} does not match its setup "
                f"(expected {expected!r})"
            )
        return self


def ensemble_report_id(
    *,
    commit: str,
    spec: EnsembleSpec,
    dataset: str,
    revision: int,
    interval: str,
    universe: list[UniverseMember],
    window_spec: WalkForwardSpec,
    n_bins: int,
) -> str:
    """Deterministic identity of an ensemble report: setup only, never results.

    The universe hashes over sorted member identities and the spec's
    member ids over sorted order, so ordering never changes identity.
    """
    setup = {
        "commit": commit,
        "spec": spec.id,
        "dataset": dataset,
        "revision": revision,
        "interval": interval,
        "universe": sorted((member.venue.value, member.symbol) for member in universe),
        "window_spec": window_spec.model_dump(),
        "n_bins": n_bins,
    }
    canonical = json.dumps(setup, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"ensemble-report\0{canonical}".encode()).hexdigest()[:16]


class EnsembleWindowResult(BaseModel):
    """Per-window results: validation-derived weights and OOS test evidence.

    Weights are results (ADR-0005 decision 2): they never enter the
    report id. ``brier`` is None when the window's newest bar has no
    resolved outcome (mirroring the M6 forecast reports); such windows
    contribute no calibration pairs.
    """

    index: int = Field(ge=0)
    train_end: datetime
    weights: list[float]
    n_fit_observations: int = Field(ge=0)
    n_validation_observations: int = Field(ge=0)
    n_test_observations: int = Field(ge=0)
    mean_disagreement: float
    brier: float | None


class EnsembleReport(BaseModel):
    """One ensemble evaluation report over a pinned lake and universe.

    The id covers setup only — commit, spec, dataset pin, universe,
    window spec, bins — so a rerun with identical evidence is the same
    report. Calibration is out-of-sample by construction: every pair
    pools from a test segment the members never fit or weighted on.
    """

    id: str = Field(pattern=ID_PATTERN)
    commit: str = Field(pattern=COMMIT_PATTERN)
    spec: EnsembleSpec
    dataset: str
    revision: int = Field(ge=1)
    interval: str
    universe: list[UniverseMember]
    window_spec: WalkForwardSpec
    n_bins: int = Field(ge=_N_BINS_MIN, le=_N_BINS_MAX)
    created_at: datetime
    metrics: dict[str, Parameter]
    windows: list[EnsembleWindowResult]
    calibration: list[CalibrationBin]

    @model_validator(mode="after")
    def report_is_consistent(self) -> "EnsembleReport":
        expected = ensemble_report_id(
            commit=self.commit,
            spec=self.spec,
            dataset=self.dataset,
            revision=self.revision,
            interval=self.interval,
            universe=self.universe,
            window_spec=self.window_spec,
            n_bins=self.n_bins,
        )
        if self.id != expected:
            raise ValueError(
                f"ensemble report id {self.id!r} does not match its setup "
                f"(expected {expected!r})"
            )
        return self


def ensemble_artifact_paths(root: Path, report: EnsembleReport) -> dict[str, Path]:
    """Deterministic artifact locations (ADR-0005 decision 7, applied)."""
    directory = root / report.id
    return {
        "report.json": directory / "report.json",
        "windows.csv": directory / "windows.csv",
        "calibration.csv": directory / "calibration.csv",
    }


def _write_artifacts(root: Path, report: EnsembleReport) -> None:
    """Write byte-stable artifacts; ``created_at`` is excluded so the
    same setup reproduces identical bytes across registry roots."""
    paths = ensemble_artifact_paths(root, report)
    directory = paths["report.json"].parent
    directory.mkdir(parents=True, exist_ok=True)
    payload = report.model_dump(mode="json", exclude={"created_at"})
    paths["report.json"].write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with paths["windows.csv"].open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            [
                "window_index",
                "train_end",
                "weights",
                "n_fit_observations",
                "n_validation_observations",
                "n_test_observations",
                "mean_disagreement",
                "brier",
            ]
        )
        for window in report.windows:
            writer.writerow(
                [
                    window.index,
                    window.train_end.isoformat(),
                    json.dumps(window.weights, separators=(",", ":")),
                    window.n_fit_observations,
                    window.n_validation_observations,
                    window.n_test_observations,
                    window.mean_disagreement,
                    "" if window.brier is None else window.brier,
                ]
            )
    with paths["calibration.csv"].open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            [
                "bin",
                "lo",
                "hi",
                "count",
                "mean_prediction",
                "observed_frequency",
                "brier",
            ]
        )
        for bin_row in report.calibration:
            writer.writerow(
                [
                    bin_row.bin,
                    bin_row.lo,
                    bin_row.hi,
                    bin_row.count,
                    (
                        ""
                        if bin_row.mean_prediction is None
                        else bin_row.mean_prediction
                    ),
                    (
                        ""
                        if bin_row.observed_frequency is None
                        else bin_row.observed_frequency
                    ),
                    "" if bin_row.brier is None else bin_row.brier,
                ]
            )


class EnsembleReportRegistry:
    """Append-only store of ensemble reports under one registry root.

    Same discipline as the M5 ``ReportRegistry`` — atomic temp+replace
    appends, fail-closed reads with line attribution, duplicate ids
    refused — plus the lake pin: a recorded report's dataset must pass
    the manifest gate at the pinned revision, so the registry never
    holds a report over a dangling pin.
    """

    def __init__(self, root: Path | None = None, lake_root: Path | None = None) -> None:
        self.root = root if root is not None else settings.reports_dir
        self.lake_root = lake_root if lake_root is not None else settings.lake_root

    def record(self, report: EnsembleReport) -> EnsembleReport:
        """Record a report; the pin is validated before anything is written.

        Refuses duplicate IDs — the same setup is the same report, and a
        rerun regenerates identical artifacts instead of recording again.
        """
        existing = self.all()
        if any(record.id == report.id for record in existing):
            raise ValueError(f"ensemble report {report.id!r} already recorded")
        self._require_pin(report)
        self._append(report, existing)
        return report

    def get(self, report_id_value: str) -> EnsembleReport:
        for report in self.all():
            if report.id == report_id_value:
                return report
        raise ValueError(f"no ensemble report recorded with id {report_id_value!r}")

    def all(self) -> list[EnsembleReport]:
        return self._read()

    def resolve_pin(self, dataset: str, revision: int) -> Dataset:
        """The dataset at a pinned revision, through the lake's manifest gate."""
        dataset_handle = Lake(self.lake_root).dataset(dataset)
        if dataset_handle.manifest.revision != revision:
            raise ValueError(
                f"dataset {dataset!r} is now revision {dataset_handle.manifest.revision}, "
                f"but the pin asks for revision {revision}"
            )
        return dataset_handle

    def _require_pin(self, report: EnsembleReport) -> None:
        self.resolve_pin(report.dataset, report.revision)

    def _append(
        self, report: EnsembleReport, existing: list[EnsembleReport]
    ) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / ENSEMBLES_FILE
        descriptor, temp_name = tempfile.mkstemp(
            dir=self.root, prefix=f".{ENSEMBLES_FILE}.", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                for record in existing + [report]:
                    handle.write(record.model_dump_json())
                    handle.write("\n")
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def _read(self) -> list[EnsembleReport]:
        if not self.root.exists():
            return []
        if not self.root.is_dir():
            raise ValueError(f"ensemble registry root {self.root} is not a directory")
        path = self.root / ENSEMBLES_FILE
        if not path.exists():
            return []
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise ValueError(f"ensemble registry {path} is unreadable") from error
        records = []
        seen: dict[str, int] = {}
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                record = EnsembleReport.model_validate_json(line)
            except ValidationError as error:
                raise ValueError(
                    f"ensemble registry {path} line {line_number} is invalid"
                ) from error
            if record.id in seen:
                raise ValueError(
                    f"ensemble registry {path} lines {seen[record.id]} and "
                    f"{line_number} share a report id"
                )
            seen[record.id] = line_number
            records.append(record)
        return records


def run_ensemble_report(
    *,
    spec: EnsembleSpec,
    dataset: str,
    revision: int,
    interval: str,
    universe: list[UniverseMember],
    window_spec: WalkForwardSpec,
    n_bins: int = 10,
    commit: str | None = None,
    registry: EnsembleReportRegistry | None = None,
    feature_registry: FeatureRegistry | None = None,
) -> EnsembleReport:
    """Fit the ensemble walk-forward over a pinned lake; evaluate out of sample.

    Every window splits its train segment into a fit slice and a
    validation tail: each member fits on the fit slice only, validation
    errors on the tail derive the member weights (inverse error or
    nnls), and the test segment is evaluated once. Test observations
    never touch the weights — the weight functions receive only
    validation rows, which the tests prove by flipping the test closes
    and demanding every weight stay identical. Calibration pools the
    ensemble's out-of-sample probability-vs-outcome pairs across
    windows under the M6 ``brier_by_bin`` discipline; the newest
    unresolved bars carry no label and are excluded, never fabricated.
    """
    registry = registry if registry is not None else EnsembleReportRegistry()
    if commit is None:
        commit = current_commit()
    members = validate_universe(universe)
    feature_registry = (
        feature_registry if feature_registry is not None else FeatureRegistry()
    )
    if window_spec.train_bars < spec.validation_bars + 2:
        raise ValueError(
            f"the {window_spec.train_bars}-bar train window must exceed the "
            f"{spec.validation_bars}-bar validation slice by at least 2 bars "
            "(one fit bar and one leading label)"
        )
    dataset_handle = registry.resolve_pin(dataset, revision)

    # Resolve every member's featureset through the Phase A registry —
    # a member pins its featureset by digest, so an unrecorded set is a
    # dangling setup and is refused before any computation.
    features_by_member: dict[str, list[FeatureSpec]] = {}
    for member in spec.members:
        feature_set = feature_registry.get_set(member.featureset_id)
        features_by_member[member.id] = [
            feature_registry.get_spec(feature_id_value)
            for feature_id_value in feature_set.feature_ids
        ]

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

    # Per-member, per-symbol feature matrices (one column per feature
    # id, rows on the bar grid after warm-up). Members must align on
    # the same grid per symbol: the ensemble combines per-bar
    # probabilities, so a member whose features cannot produce a bar
    # makes the disagreement vector undefined — refuse instead.
    universe_keys = {(member.venue, member.symbol) for member in members}
    matrices: dict[str, dict[str, pd.DataFrame]] = {}
    for member in spec.members:
        specs_by_key: dict[tuple, list[FeatureSpec]] = {}
        for feature_spec in features_by_member[member.id]:
            specs_by_key.setdefault((feature_spec.venue, feature_spec.symbol), []).append(
                feature_spec
            )
        outside = set(specs_by_key) - universe_keys
        if outside:
            raise ValueError(
                "features reference symbols outside the universe: "
                f"{sorted((venue.value, symbol) for venue, symbol in outside)}"
            )
        missing = sorted(
            (member_entry.venue.value, member_entry.symbol)
            for member_entry in members
            if (member_entry.venue, member_entry.symbol) not in specs_by_key
        )
        if missing:
            raise ValueError(
                f"ensemble member {member.id!r} features must cover the whole "
                f"universe; missing {missing}"
            )
        per_symbol: dict[str, pd.DataFrame] = {}
        for member_entry in members:
            frames = [
                compute_feature(feature_spec, dataset_handle).rename(feature_spec.id)
                for feature_spec in specs_by_key[(member_entry.venue, member_entry.symbol)]
            ]
            joined = pd.concat(frames, axis=1).dropna()
            if joined.empty:
                raise ValueError(
                    f"no bar row carries every feature of the member's set for "
                    f"{member_entry.symbol!r}; the grid is too short for the "
                    "feature windows"
                )
            per_symbol[member_entry.symbol] = joined
        matrices[member.id] = per_symbol
    member_ids = sorted(matrices)
    for symbol in sorted(matrices[member_ids[0]]):
        indices = [matrices[member_id][symbol].index for member_id in member_ids]
        if any(not indices[0].equals(index) for index in indices[1:]):
            raise ValueError(
                f"ensemble member featuresets must align on the same bar grid "
                f"per symbol ({symbol!r} warms up differently across members); "
                "use matching feature windows across members"
            )

    closes = {
        symbol: [bar.close for bar in bars] for symbol, bars in bars_by_symbol.items()
    }
    labels = {
        symbol: direction_labels(pd.Series(closes[symbol], index=grid))
        for symbol in closes
    }

    windows: list[EnsembleWindowResult] = []
    calibration_predictions: list[float] = []
    calibration_outcomes: list[float] = []
    disagreement_rows: list[float] = []
    for index, test_start in enumerate(window_spec.test_starts(len(grid))):
        train_start = test_start - window_spec.train_bars
        # The train segment covers rows [train_start, test_start - 2]
        # (the last label compares close[test_start - 1], known at
        # rebalance); its tail of validation_bars rows is held out for
        # the weights, and the members fit on the rest.
        fit_rows = grid[train_start : test_start - 1 - spec.validation_bars]
        validation_rows = grid[test_start - 1 - spec.validation_bars : test_start - 1]
        test_rows = grid[test_start : test_start + window_spec.test_bars]

        # The row partition is built once from the first member's
        # matrices; the setup check above guarantees every member's
        # matrix shares the same index, so the pooled blocks line up
        # positionally across members.
        first = matrices[member_ids[0]]
        fit_frames: dict[str, pd.DataFrame] = {}
        validation_frames: dict[str, pd.DataFrame] = {}
        test_frames: dict[str, pd.DataFrame] = {}
        for symbol in sorted(first):
            fit_frame = first[symbol].reindex(fit_rows).dropna()
            if fit_frame.empty:
                raise ValueError(
                    f"feature warm-up for {symbol!r} exceeds the "
                    f"{window_spec.train_bars}-bar train window "
                    f"({spec.validation_bars} validation bars held out); "
                    "grow train_bars, shrink validation_bars, or drop "
                    "deeper-window features"
                )
            validation_frame = first[symbol].reindex(validation_rows).dropna()
            if validation_frame.empty:
                raise ValueError(
                    f"the {spec.validation_bars}-bar validation slice for "
                    f"{symbol!r} falls inside the feature warm-up; grow "
                    "train_bars or shrink validation_bars"
                )
            test_frame = first[symbol].reindex(test_rows).dropna()
            if test_frame.empty:
                raise ValueError(
                    f"the test segment for {symbol!r} has no rows on the "
                    "feature grid; the grid is too short"
                )
            fit_frames[symbol] = fit_frame
            validation_frames[symbol] = validation_frame
            test_frames[symbol] = test_frame
        y_fit = np.concatenate(
            [
                labels[symbol].reindex(fit_frames[symbol].index).astype(float).to_numpy()
                for symbol in sorted(first)
            ]
        )
        y_validation = np.concatenate(
            [
                labels[symbol]
                .reindex(validation_frames[symbol].index)
                .astype(float)
                .to_numpy()
                for symbol in sorted(first)
            ]
        )
        if not np.isfinite(y_fit).all() or not np.isfinite(y_validation).all():
            raise ValueError("labels do not cover the window's fit and validation slices")
        y_test = np.concatenate(
            [
                labels[symbol].reindex(test_frames[symbol].index).astype(float).to_numpy()
                for symbol in sorted(first)
            ]
        )
        # The newest test bar has no resolved outcome (no next close) —
        # its label is NaN and its pair must not enter the evidence.
        labeled = np.isfinite(y_test)

        validation_predictions: dict[str, np.ndarray] = {}
        test_predictions: dict[str, np.ndarray] = {}
        members_by_id = {member.id: member for member in spec.members}
        for member_id in member_ids:
            frames = matrices[member_id]
            x_fit = np.concatenate(
                [
                    frames[symbol].loc[fit_frames[symbol].index].to_numpy(dtype=float)
                    for symbol in sorted(first)
                ],
                axis=0,
            )
            x_validation = np.concatenate(
                [
                    frames[symbol]
                    .loc[validation_frames[symbol].index]
                    .to_numpy(dtype=float)
                    for symbol in sorted(first)
                ],
                axis=0,
            )
            x_test = np.concatenate(
                [
                    frames[symbol].loc[test_frames[symbol].index].to_numpy(dtype=float)
                    for symbol in sorted(first)
                ],
                axis=0,
            )
            member = members_by_id[member_id]
            params = normalize_hyperparameters(member.model_type, member.hyperparameters)
            model = _pipeline_for(member.model_type, params)
            model.fit(pd.DataFrame(x_fit), pd.Series(y_fit))
            # The pipeline codecs return the positive-class probability
            # directly (1-D), not sklearn's two-column matrix.
            validation_predictions[member_id] = model.predict_proba(
                pd.DataFrame(x_validation)
            )
            test_predictions[member_id] = model.predict_proba(pd.DataFrame(x_test))

        errors = [
            float(
                np.mean((validation_predictions[member_id] - y_validation) ** 2)
            )
            for member_id in member_ids
        ]
        if spec.weight_method == "inverse_error":
            weights = inverse_error_weights(errors)
        else:
            weights = nnls_weights(
                np.stack(
                    [validation_predictions[member_id] for member_id in member_ids],
                    axis=1,
                ),
                y_validation,
            )
        test_matrix = np.stack(
            [test_predictions[member_id] for member_id in member_ids], axis=1
        )
        weights_array = np.asarray(weights, dtype=float)
        ensemble_mean = test_matrix @ weights_array
        # Weighted variance per row: sum_m w_m (p_m - mean)^2. Identical
        # members give zero disagreement by construction.
        disagreement = ((test_matrix - ensemble_mean[:, None]) ** 2) @ weights_array
        disagreement_rows.extend(disagreement.tolist())
        labeled_mean = ensemble_mean[labeled]
        labeled_outcomes = y_test[labeled]
        if labeled_outcomes.size:
            brier = round(
                float(np.mean((labeled_mean - labeled_outcomes) ** 2)), 6
            )
            calibration_predictions.extend(labeled_mean.tolist())
            calibration_outcomes.extend(labeled_outcomes.tolist())
        else:
            # The newest bar's outcome has not resolved; the window
            # contributes no calibration pairs (M6 precedent).
            brier = None
        windows.append(
            EnsembleWindowResult(
                index=index,
                train_end=grid[test_start - 1],
                weights=weights,
                n_fit_observations=int(y_fit.size),
                n_validation_observations=int(y_validation.size),
                n_test_observations=int(labeled_outcomes.size),
                mean_disagreement=round(float(np.mean(disagreement)), 6),
                brier=brier,
            )
        )

    if not calibration_predictions:
        raise ValueError(
            "the ensemble evaluated no out-of-sample observations; nothing to "
            "calibrate (extend the grid or grow test_bars)"
        )
    calibration = brier_by_bin(calibration_predictions, calibration_outcomes, n_bins)
    metrics: dict[str, Parameter] = {
        "n_windows": len(windows),
        "n_calibration_pairs": len(calibration_predictions),
        "mean_brier": round(
            float(
                np.mean(
                    (np.asarray(calibration_predictions) - np.asarray(calibration_outcomes))
                    ** 2
                )
            ),
            6,
        ),
        "mean_disagreement": round(float(np.mean(disagreement_rows)), 6),
    }
    report = EnsembleReport(
        id=ensemble_report_id(
            commit=commit,
            spec=spec,
            dataset=dataset,
            revision=revision,
            interval=interval,
            universe=members,
            window_spec=window_spec,
            n_bins=n_bins,
        ),
        commit=commit,
        spec=spec,
        dataset=dataset,
        revision=revision,
        interval=interval,
        universe=members,
        window_spec=window_spec,
        n_bins=n_bins,
        created_at=datetime.now(UTC),
        metrics=metrics,
        windows=windows,
        calibration=calibration,
    )
    _write_artifacts(registry.root, report)
    registry.record(report)
    return report


__all__ = [
    "ENSEMBLES_FILE",
    "EnsembleReport",
    "EnsembleReportRegistry",
    "EnsembleSpec",
    "EnsembleWindowResult",
    "ensemble_artifact_paths",
    "ensemble_id",
    "ensemble_predict",
    "ensemble_report_id",
    "inverse_error_weights",
    "nnls_weights",
    "run_ensemble_report",
]
