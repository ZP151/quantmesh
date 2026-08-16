"""Feature registry: named versioned features, setup-only identity (issue #39).

A ``FeatureSpec`` pins everything that defines one computed feature —
code commit, name, kind, venue, symbol, interval, lake dataset and
revision, parameters — under a deterministic 16-hex ID; a ``FeatureSet``
groups ordered member specs under its own digest, which model identity
folds in. The same setup always produces the same ID, so "reproduce
feature X" is well-defined: resolve the pin through the lake's manifest
gate and recompute.

Computation is deterministic by construction: the builtin feature
functions are pure pandas operations over the pinned dataset's bars
(no random generator, no look-ahead), and every computed frame is
trimmed of its leading window warm-up and validated to be finite and
non-empty. The registry persists specs and sets as JSONL with the
experiment-registry discipline (atomic appends, fail-closed reads with
line attribution, duplicate refusal, pin validated before anything is
written). Kinds beyond bar-derived features (orderbook, event) are
documented extensions that land with their pin contracts and
consumers; ``compute_feature`` fails closed on them.
"""

import hashlib
import json
import math
import re
import subprocess
from collections.abc import Callable
from datetime import UTC
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

import pandas as pd
from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
)

from quantmesh.data.artifacts import ArtifactLayer
from quantmesh.data.capabilities import DataKind
from quantmesh.data.lake import Lake
from quantmesh.data.layout import validate_dataset_name, validate_symbol
from quantmesh.domain.market_data import interval_to_timedelta
from quantmesh.domain.models import Venue
from quantmesh.persistence.jsonl import JsonlStore
from quantmesh.settings import settings


class TrustedResearchCatalog(Protocol):
    def open_research_dataset(
        self,
        manifest_id: str,
        *,
        evaluation_id: str,
        dataset_id: str,
        compatibility_revision: int,
    ) -> Any: ...

FEATURES_FILE = "features.jsonl"
FEATURE_SETS_FILE = "feature_sets.jsonl"

ID_PATTERN = "^[0-9a-f]{16}$"
COMMIT_PATTERN = "^[0-9a-f]{7,64}$"

Parameter = str | int | float | bool | None


class FeatureKind(StrEnum):
    """What a feature is computed from. Bar-derived features are the
    Phase A surface; orderbook/event kinds are documented extensions
    that land with their pin contracts and consumers."""

    BAR = "bar"


# Builtin feature functions: name -> (function, parameter contract).
# A spec records against a builtin by name, so its parameter contract
# is validated at record time AND at compute time (a spec recorded
# elsewhere must still compute).
def _require_window(parameters: dict[str, Parameter], name: str) -> int:
    if "window" not in parameters:
        raise ValueError(f"feature {name!r} requires parameter 'window'")
    window = parameters["window"]
    if not isinstance(window, int) or isinstance(window, bool):
        raise ValueError(f"feature {name!r} parameter 'window' must be an int, got {window!r}")
    if window < 2:
        raise ValueError(f"feature {name!r} parameter 'window' must be >= 2, got {window}")
    if set(parameters) != {"window"}:
        raise ValueError(
            f"feature {name!r} accepts only parameter 'window', got {sorted(parameters)}"
        )
    return window


def _momentum(closes: pd.Series, parameters: dict[str, Parameter]) -> pd.Series:
    """``close[t] / close[t - window] - 1`` — the window-bar momentum."""
    window = _require_window(parameters, "momentum")
    return closes / closes.shift(window) - 1.0


def _log_return(closes: pd.Series, parameters: dict[str, Parameter]) -> pd.Series:
    """``log(close[t]) - log(close[t - window])`` — the window-bar log return."""
    window = _require_window(parameters, "log_return")
    return closes.apply(math.log).diff(window)


def _rolling_mean(closes: pd.Series, parameters: dict[str, Parameter]) -> pd.Series:
    window = _require_window(parameters, "rolling_mean")
    return closes.rolling(window).mean()


def _rolling_std(closes: pd.Series, parameters: dict[str, Parameter]) -> pd.Series:
    window = _require_window(parameters, "rolling_std")
    return closes.rolling(window).std(ddof=0)


def _realized_vol(closes: pd.Series, parameters: dict[str, Parameter]) -> pd.Series:
    """Population std of per-bar log returns over the window."""
    window = _require_window(parameters, "realized_vol")
    returns = closes.apply(math.log).diff()
    return returns.rolling(window).std(ddof=0)


FEATURES: dict[str, Callable[[pd.Series, dict[str, Parameter]], pd.Series]] = {
    "momentum": _momentum,
    "log_return": _log_return,
    "rolling_mean": _rolling_mean,
    "rolling_std": _rolling_std,
    "realized_vol": _realized_vol,
}


def _validate_builtin(name: str, parameters: dict[str, Parameter]) -> None:
    if name not in FEATURES:
        raise ValueError(
            f"unknown feature {name!r} (expected one of {sorted(FEATURES)})"
        )
    _require_window(parameters, name)


def feature_id(
    dataset: str,
    revision: int,
    commit: str,
    name: str,
    kind: FeatureKind,
    venue: Venue,
    symbol: str,
    interval: str,
    parameters: dict[str, Parameter],
    manifest_id: str | None = None,
    quality_evaluation_id: str | None = None,
) -> str:
    """Deterministic identity of a feature: setup only, never results."""
    if (manifest_id is None) != (quality_evaluation_id is None):
        raise ValueError(
            "manifest_id and quality_evaluation_id must be present together"
        )
    setup = {
        "commit": commit,
        "name": name,
        "kind": kind.value,
        "venue": venue.value,
        "symbol": symbol,
        "interval": interval,
        "dataset": dataset,
        "revision": revision,
        "parameters": parameters,
    }
    if manifest_id is not None:
        setup["manifest_id"] = manifest_id
        setup["quality_evaluation_id"] = quality_evaluation_id
    canonical = json.dumps(setup, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"feature\0{canonical}".encode()).hexdigest()[:16]


class FeatureSpec(BaseModel):
    """One recorded feature: pinned setup defining a deterministic computation."""

    id: str = Field(pattern=ID_PATTERN)
    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    kind: FeatureKind
    venue: Venue
    symbol: str
    interval: str
    dataset: str
    revision: int = Field(ge=1)
    manifest_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    quality_evaluation_id: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    commit: str = Field(pattern=COMMIT_PATTERN)
    parameters: dict[str, Parameter] = Field(default_factory=dict)

    @field_validator("parameters")
    @classmethod
    def values_are_finite(cls, values: dict[str, Parameter]) -> dict[str, Parameter]:
        for param, value in values.items():
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(f"parameter {param!r} is not finite ({value})")
        return values

    @model_validator(mode="after")
    def spec_is_consistent(self) -> "FeatureSpec":
        if (self.manifest_id is None) != (self.quality_evaluation_id is None):
            raise ValueError(
                "manifest_id and quality_evaluation_id must be present together"
            )
        validate_dataset_name(self.dataset)
        interval_to_timedelta(self.interval)
        validate_symbol(self.symbol)
        _validate_builtin(self.name, self.parameters)
        expected = feature_id(
            dataset=self.dataset,
            revision=self.revision,
            commit=self.commit,
            name=self.name,
            kind=self.kind,
            venue=self.venue,
            symbol=self.symbol,
            interval=self.interval,
            parameters=self.parameters,
            manifest_id=self.manifest_id,
            quality_evaluation_id=self.quality_evaluation_id,
        )
        if self.id != expected:
            raise ValueError(
                f"feature id {self.id!r} does not match its pinned setup (expected {expected!r})"
            )
        return self


def featureset_id(name: str, feature_ids: list[str]) -> str:
    """Deterministic identity of a feature set over its sorted member ids.

    The ids are sorted inside the function, so member order never
    changes the identity.
    """
    ordered = sorted(feature_ids)
    ordered_json = json.dumps(ordered, separators=(",", ":"))
    payload = f"feature-set\0{name}\0{ordered_json}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


class FeatureSet(BaseModel):
    """A named, ordered group of features whose digest model identity folds in.

    Member ids are stored sorted ascending, so member order never
    changes the identity; the canonical model feature order is the
    sorted member id order.
    """

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    feature_ids: list[str] = Field(min_length=1)
    id: str = Field(pattern=ID_PATTERN)

    @model_validator(mode="after")
    def set_is_consistent(self) -> "FeatureSet":
        for feature_id_value in self.feature_ids:
            if not re.match(ID_PATTERN, feature_id_value):
                raise ValueError(f"feature set member {feature_id_value!r} is not a feature id")
        if self.feature_ids != sorted(self.feature_ids):
            raise ValueError(
                f"feature set members must be sorted ascending, got {self.feature_ids}"
            )
        if len(set(self.feature_ids)) != len(self.feature_ids):
            raise ValueError(f"feature set members must be unique, got {self.feature_ids}")
        expected = featureset_id(self.name, self.feature_ids)
        if self.id != expected:
            raise ValueError(
                f"feature set id {self.id!r} does not match its members (expected {expected!r})"
            )
        return self


def _trim_leading_nan(series: pd.Series) -> pd.Series:
    """Drop the leading warm-up prefix; a later NaN is a fail-closed error."""
    first_valid = series.notna().idxmax() if series.notna().any() else None
    if first_valid is None:
        return series.iloc[0:0]
    return series.loc[first_valid:]


def compute_feature(spec: FeatureSpec, dataset: Any) -> pd.Series:
    """Compute one registered feature over a manifest-gated dataset.

    Bar-derived features read the spec's partition, validate the bars
    (non-empty, strictly ascending timestamps, spec-consistent interval,
    finite prices), apply the builtin, trim the window warm-up and
    verify the frame is finite. Fails closed on every violation.
    """
    if spec.kind is not FeatureKind.BAR:
        raise ValueError(
            f"feature kind {spec.kind.value!r} is not computable yet "
            "(documented extension; only bar-derived features land in Phase A)"
        )
    if spec.manifest_id is not None:
        bars = dataset.read_bars()
    else:
        bars = dataset.read_bars(
            interval=spec.interval,
            venue=spec.venue,
            symbol=spec.symbol,
        )
    if not bars:
        raise ValueError(
            f"feature {spec.name!r} has no bars for {spec.venue.value}/{spec.symbol} "
            f"at {spec.interval} in dataset {spec.dataset!r}"
        )
    if spec.manifest_id is not None and any(
        bar.instrument.venue is not spec.venue
        or bar.instrument.symbol != spec.symbol
        for bar in bars
    ):
        raise ValueError(
            f"feature {spec.name!r} trusted manifest instrument does not match "
            f"{spec.venue.value}/{spec.symbol}"
        )
    timestamps = [bar.timestamp for bar in bars]
    if timestamps != sorted(timestamps) or len(set(timestamps)) != len(timestamps):
        raise ValueError(f"feature {spec.name!r} bars are not strictly ascending")
    if any(bar.interval != spec.interval for bar in bars):
        raise ValueError(f"feature {spec.name!r} bars mix intervals")
    closes = pd.Series([bar.close for bar in bars], index=timestamps, dtype=float)
    if not closes.notna().all() or not math.isfinite(float(closes.min())) or not math.isfinite(
        float(closes.max())
    ):
        raise ValueError(f"feature {spec.name!r} closes contain non-finite values")
    _validate_builtin(spec.name, spec.parameters)
    frame = FEATURES[spec.name](closes, spec.parameters)
    frame = _trim_leading_nan(frame)
    if frame.empty:
        raise ValueError(
            f"feature {spec.name!r} computes an empty frame (grid too short "
            f"for window {spec.parameters})"
        )
    if not frame.notna().all():
        raise ValueError(f"feature {spec.name!r} frame contains NaN beyond the warm-up")
    return frame


def _require_trusted_feature_input(spec: FeatureSpec, dataset: Any) -> Any:
    manifest = getattr(dataset, "manifest", None)
    if (
        getattr(manifest, "layer", None) is not ArtifactLayer.ADJUSTED
        or getattr(manifest, "data_kind", None) is not DataKind.BARS
        or getattr(manifest, "interval", None) != spec.interval
    ):
        raise ValueError(
            "trusted feature input must be an adjusted bar manifest at the spec interval"
        )
    return dataset


def compute_features(
    specs: list[FeatureSpec],
    *,
    lake_root: Path,
    trusted_catalog: TrustedResearchCatalog | None = None,
) -> dict[str, pd.Series]:
    """Compute every spec's frame; the result is keyed by spec name.

    Datasets are opened once per (dataset, revision) through the lake's
    manifest gate and the pinned revision is enforced, mirroring the
    registry's resolve discipline. Fails closed on empty spec lists and
    duplicate names.
    """
    if not specs:
        raise ValueError("no feature specs given")
    names = [spec.name for spec in specs]
    if len(set(names)) != len(names):
        raise ValueError(f"duplicate feature names in spec list: {names}")
    lake = Lake(lake_root)
    by_pin: dict[tuple[str, int, str | None, str | None], Any] = {}
    frames: dict[str, pd.Series] = {}
    for spec in specs:
        pin = (
            spec.dataset,
            spec.revision,
            spec.manifest_id,
            spec.quality_evaluation_id,
        )
        if pin not in by_pin:
            if spec.manifest_id is not None:
                if trusted_catalog is None or spec.quality_evaluation_id is None:
                    raise ValueError("trusted feature lineage requires a data catalog")
                dataset = trusted_catalog.open_research_dataset(
                    spec.manifest_id,
                    evaluation_id=spec.quality_evaluation_id,
                    dataset_id=spec.dataset,
                    compatibility_revision=spec.revision,
                )
                _require_trusted_feature_input(spec, dataset)
            else:
                dataset = lake.dataset(spec.dataset)
                if dataset.manifest.revision != spec.revision:
                    raise ValueError(
                        f"feature {spec.name!r} pins manifest revision {spec.revision}, "
                        f"but dataset {spec.dataset!r} is now revision "
                        f"{dataset.manifest.revision}"
                    )
            by_pin[pin] = dataset
        frames[spec.name] = compute_feature(spec, by_pin[pin])
    return frames


def frame_digest(frames: dict[str, pd.Series]) -> str:
    """Deterministic content hash of computed frames (setup of the input).

    Floats serialize via ``repr`` (round-trip exact), timestamps as UTC
    ISO-8601; the payload is sorted and keyed by feature name, so frame
    order never changes the digest. Used by the drill to pin
    reproducibility and by Phase E drift detection as the reference
    frame.
    """
    payload = {
        name: [
            [ts.astimezone(UTC).isoformat(), repr(float(value))]
            for ts, value in frame.items()
        ]
        for name, frame in sorted(frames.items())
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"frames\0{canonical}".encode()).hexdigest()[:16]


class FeatureRegistry:
    """Append-only store of feature specs and sets under one registry root."""

    def __init__(
        self,
        root: Path | None = None,
        lake_root: Path | None = None,
        *,
        trusted_catalog: TrustedResearchCatalog | None = None,
    ) -> None:
        self.root = root if root is not None else settings.features_dir
        self.lake_root = lake_root if lake_root is not None else settings.lake_root
        self.trusted_catalog = trusted_catalog
        self._specs_store = JsonlStore(
            self.root,
            filename=FEATURES_FILE,
            model=FeatureSpec,
            label="registry",
            id_label="id",
            article="an",
            record_label="feature",
            key=lambda spec: spec.id,
        )
        self._sets_store = JsonlStore(
            self.root,
            filename=FEATURE_SETS_FILE,
            model=FeatureSet,
            label="registry",
            id_label="id",
            article="an",
            record_label="feature set",
            key=lambda feature_set: feature_set.id,
        )

    def record_spec(
        self,
        *,
        name: str,
        kind: FeatureKind,
        venue: Venue,
        symbol: str,
        interval: str,
        dataset: str,
        revision: int,
        manifest_id: str | None = None,
        quality_evaluation_id: str | None = None,
        commit: str | None = None,
        parameters: dict[str, Parameter] | None = None,
    ) -> FeatureSpec:
        """Record a feature spec; ``commit`` defaults to the current git HEAD.

        The pin is validated before anything is written: the dataset
        must pass the lake's manifest gate at the pinned revision, so
        the registry never holds a dangling pin.
        """
        if commit is None:
            commit = current_commit()
        spec = FeatureSpec(
            id=feature_id(
                dataset=dataset,
                revision=revision,
                commit=commit,
                name=name,
                kind=kind,
                venue=venue,
                symbol=symbol,
                interval=interval,
                parameters=parameters or {},
                manifest_id=manifest_id,
                quality_evaluation_id=quality_evaluation_id,
            ),
            name=name,
            kind=kind,
            venue=venue,
            symbol=symbol,
            interval=interval,
            dataset=dataset,
            revision=revision,
            manifest_id=manifest_id,
            quality_evaluation_id=quality_evaluation_id,
            commit=commit,
            parameters=parameters or {},
        )
        existing = self._specs_store.read()
        self._specs_store.check_absent(spec, existing)
        self._require_pin(spec)
        self._specs_store.write([*existing, spec])
        return spec

    def record_set(self, *, name: str, feature_ids: list[str]) -> FeatureSet:
        """Record a feature set; every member spec must already be recorded."""
        known = {record.id for record in self.all_specs()}
        missing = [
            feature_id_value
            for feature_id_value in feature_ids
            if feature_id_value not in known
        ]
        if missing:
            raise ValueError(
                f"feature set {name!r} references unrecorded features: {missing}"
            )
        feature_set = FeatureSet(
            name=name,
            feature_ids=sorted(feature_ids),
            id=featureset_id(name, sorted(feature_ids)),
        )
        existing = self._sets_store.read()
        self._sets_store.check_absent(feature_set, existing)
        self._sets_store.write([*existing, feature_set])
        return feature_set

    def all_specs(self) -> list[FeatureSpec]:
        return self._specs_store.read()

    def all_sets(self) -> list[FeatureSet]:
        return self._sets_store.read()

    def get_spec(self, feature_id_value: str) -> FeatureSpec:
        for spec in self._specs_store.read():
            if spec.id == feature_id_value:
                return spec
        raise ValueError(f"no feature recorded with id {feature_id_value!r}")

    def get_set(self, featureset_id_value: str) -> FeatureSet:
        for feature_set in self._sets_store.read():
            if feature_set.id == featureset_id_value:
                return feature_set
        raise ValueError(f"no feature set recorded with id {featureset_id_value!r}")

    def resolve(self, feature_id_value: str) -> Any:
        """Re-open the feature's dataset, pinned to its revision (lake gate)."""
        spec = self.get_spec(feature_id_value)
        return self._require_pin(spec)

    def _require_pin(self, spec: FeatureSpec) -> Any:
        if spec.manifest_id is not None:
            if self.trusted_catalog is None or spec.quality_evaluation_id is None:
                raise ValueError("trusted feature lineage requires a data catalog")
            dataset = self.trusted_catalog.open_research_dataset(
                spec.manifest_id,
                evaluation_id=spec.quality_evaluation_id,
                dataset_id=spec.dataset,
                compatibility_revision=spec.revision,
            )
            return _require_trusted_feature_input(spec, dataset)
        dataset = Lake(self.lake_root).dataset(spec.dataset)
        if dataset.manifest.revision != spec.revision:
            raise ValueError(
                f"feature {spec.id!r} pins manifest revision {spec.revision}, "
                f"but dataset {spec.dataset!r} is now revision {dataset.manifest.revision}"
            )
        return dataset


def current_commit() -> str:
    """HEAD of the git repository the registry runs in; else fail closed."""
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as error:
        raise ValueError("cannot resolve the code commit; pass commit explicitly") from error
    if not head:
        raise ValueError("cannot resolve the code commit; pass commit explicitly")
    return head
