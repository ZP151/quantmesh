"""Model registry: versioned models with setup-only identity (issue #39).

(``from __future__ import annotations`` keeps the pipeline type hints in
``fit_model`` lazy like the imports themselves — the codecs are optional
runtime surface, ADR-0009 decision 6.)

A ``ModelSpec`` pins everything that defines a training run — code
commit, model type, hyperparameters, feature-set digest, lake dataset
and revision, and the training window bounds — under a deterministic
16-hex ID. Metrics and the artifact hash are results, never identity:
the same setup always produces the same ID, so "reproduce model X"
means resolving the pin through the lake's manifest gate and refitting
with the recorded setup.

Artifacts are byte-addressed: ``ModelRegistry.record`` writes the
artifact bytes under ``root/<id>/model.bin`` (atomic temp + replace),
records the sha256 on the record, and ``load`` re-verifies the hash —
a missing or tampered artifact fails closed. Models of the Phase A
``linear`` type are pure numpy (deterministic least squares, canonical
JSON serialization with round-trip-exact floats); the LightGBM /
logistic / HMM / GARCH codecs land with their pipelines (Phase B) as
registered types. Records persist as JSONL with the experiment-registry
discipline: atomic appends, fail-closed reads with line attribution,
duplicate refusal, pin validated before anything is written.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from quantmesh.research.pipelines import LightGBMPipeline, LogisticPipeline

import numpy as np
import pandas as pd
from pydantic import (
    BaseModel,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from quantmesh._fs import atomic_replace
from quantmesh.data.lake import Dataset, Lake
from quantmesh.data.layout import validate_dataset_name
from quantmesh.settings import settings

MODELS_FILE = "models.jsonl"
ARTIFACT_NAME = "model.bin"

ID_PATTERN = "^[0-9a-f]{16}$"
SHA256_PATTERN = "^[0-9a-f]{64}$"
COMMIT_PATTERN = "^[0-9a-f]{7,64}$"

Parameter = str | int | float | bool | None

# Model types with a registered artifact codec. Phase A ships the pure
# numpy linear codec; Phase B (issue #40) registers the pipeline types
# (logistic / lightgbm as classifier codecs via
# ``quantmesh.research.pipelines``; hmm / garch as return-based codecs
# that fit through their pipelines, never through ``fit_model(X, y)``).
MODEL_TYPES = ("linear", "logistic", "lightgbm", "hmm", "garch")

LINEAR_FORMAT = "quantmesh-linear-v1"


class LinearModel:
    """A pure-numpy linear model: deterministic fit, byte-stable bytes.

    The fit is ordinary least squares via ``numpy.linalg.lstsq`` with
    an intercept column — no random generator, deterministic on the CI
    platform for identical inputs. Serialization is canonical JSON with
    round-trip-exact float reprs, so identical inputs produce identical
    bytes.
    """

    def __init__(self, weights: np.ndarray, intercept: float, feature_names: tuple[str, ...]):
        if weights.ndim != 1 or weights.shape[0] != len(feature_names):
            raise ValueError(
                f"weights shape {weights.shape} does not match {len(feature_names)} features"
            )
        if not np.isfinite(weights).all() or not math.isfinite(intercept):
            raise ValueError("linear model coefficients must be finite")
        self.weights = np.asarray(weights, dtype=np.float64)
        self.intercept = float(intercept)
        self.feature_names = tuple(feature_names)

    @classmethod
    def fit(
        cls,
        X: pd.DataFrame,
        y: pd.Series,
        *,
        train_mask: pd.Series | None = None,
    ) -> LinearModel:
        """Fit on ``X``/``y``, optionally restricted by an aligned boolean mask.

        Fails closed on non-finite values, empty training sets,
        mismatched indexes, duplicate or missing columns. The mask, when
        given, must carry exactly ``X.index`` and boolean dtype.
        """
        if X.empty or X.shape[1] == 0:
            raise ValueError("cannot fit a linear model without features")
        if len(X.columns) != len(set(X.columns)):
            raise ValueError(f"duplicate feature columns: {list(X.columns)}")
        if not X.index.equals(y.index):
            raise ValueError("feature frame and target must share exactly the same index")
        if train_mask is not None:
            if not train_mask.index.equals(X.index):
                raise ValueError("train mask must carry exactly the feature index")
            if not train_mask.dtype == bool:
                raise ValueError(f"train mask must be boolean, got {train_mask.dtype}")
            rows = train_mask.to_numpy()
        else:
            rows = np.ones(len(X), dtype=bool)
        if not rows.any():
            raise ValueError("train mask selects no rows")
        if not np.isfinite(X.to_numpy()).all():
            raise ValueError("feature matrix contains non-finite values")
        if not np.isfinite(y.to_numpy()).all():
            raise ValueError("target contains non-finite values")
        design = np.column_stack(
            [X.to_numpy()[rows], np.ones(rows.sum(), dtype=np.float64)]
        )
        target = y.to_numpy(dtype=np.float64)[rows]
        coefficients, _, _, _ = np.linalg.lstsq(design, target, rcond=None)
        return cls(
            weights=coefficients[:-1],
            intercept=float(coefficients[-1]),
            feature_names=tuple(str(column) for column in X.columns),
        )

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if list(X.columns) != list(self.feature_names):
            raise ValueError(
                f"prediction columns {list(X.columns)} do not match trained "
                f"order {list(self.feature_names)}"
            )
        if not np.isfinite(X.to_numpy()).all():
            raise ValueError("feature matrix contains non-finite values")
        return X.to_numpy() @ self.weights + self.intercept

    def to_bytes(self) -> bytes:
        payload = {
            "format": LINEAR_FORMAT,
            "features": list(self.feature_names),
            "weights": [float(weight) for weight in self.weights],
            "intercept": self.intercept,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    @classmethod
    def from_bytes(cls, data: bytes) -> LinearModel:
        try:
            payload = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("linear model artifact is not valid JSON") from error
        if payload.get("format") != LINEAR_FORMAT:
            raise ValueError(
                f"linear model artifact has unknown format {payload.get('format')!r}"
            )
        features = payload.get("features")
        weights = payload.get("weights")
        intercept = payload.get("intercept")
        if not isinstance(features, list) or not isinstance(weights, list):
            raise ValueError("linear model artifact is missing features or weights")
        if len(features) != len(weights):
            raise ValueError(
                f"linear model artifact has {len(features)} features but {len(weights)} weights"
            )
        if not isinstance(intercept, (int, float)) or isinstance(intercept, bool):
            raise ValueError("linear model artifact has an invalid intercept")
        return cls(
            weights=np.asarray(weights, dtype=np.float64),
            intercept=float(intercept),
            feature_names=tuple(str(feature) for feature in features),
        )


def model_id(
    dataset: str,
    revision: int,
    commit: str,
    model_type: str,
    hyperparameters: dict[str, Parameter],
    featureset_id_value: str,
    train_start: datetime,
    train_end: datetime,
) -> str:
    """Deterministic identity of a training run: setup only, never results."""
    setup = {
        "commit": commit,
        "model_type": model_type,
        "hyperparameters": hyperparameters,
        "featureset": featureset_id_value,
        "dataset": dataset,
        "revision": revision,
        "train_start": train_start.astimezone(UTC).isoformat(),
        "train_end": train_end.astimezone(UTC).isoformat(),
    }
    canonical = json.dumps(setup, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"model\0{canonical}".encode()).hexdigest()[:16]


class ModelSpec(BaseModel):
    """One recorded training run's pinned setup."""

    id: str = Field(pattern=ID_PATTERN)
    model_type: str
    hyperparameters: dict[str, Parameter] = Field(default_factory=dict)
    featureset_id: str = Field(pattern=ID_PATTERN)
    dataset: str
    revision: int = Field(ge=1)
    commit: str = Field(pattern=COMMIT_PATTERN)
    train_start: datetime
    train_end: datetime

    @field_validator("hyperparameters")
    @classmethod
    def values_are_finite(cls, values: dict[str, Parameter]) -> dict[str, Parameter]:
        for name, value in values.items():
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(f"hyperparameter {name!r} is not finite ({value})")
        return values

    @model_validator(mode="after")
    def spec_is_consistent(self) -> ModelSpec:
        validate_dataset_name(self.dataset)
        if self.model_type not in MODEL_TYPES:
            raise ValueError(
                f"unknown model type {self.model_type!r} "
                f"(expected one of {MODEL_TYPES})"
            )
        for name in ("train_start", "train_end"):
            if getattr(self, name).tzinfo is None:
                raise ValueError(f"{name} must be timezone-aware")
        if self.train_start >= self.train_end:
            raise ValueError(
                f"training window must have train_start < train_end, got "
                f"{self.train_start} >= {self.train_end}"
            )
        expected = model_id(
            dataset=self.dataset,
            revision=self.revision,
            commit=self.commit,
            model_type=self.model_type,
            hyperparameters=self.hyperparameters,
            featureset_id_value=self.featureset_id,
            train_start=self.train_start,
            train_end=self.train_end,
        )
        if self.id != expected:
            raise ValueError(
                f"model id {self.id!r} does not match its pinned setup (expected {expected!r})"
            )
        return self


def fit_model(
    spec: ModelSpec,
    X: pd.DataFrame,
    y: pd.Series,
    *,
    train_mask: pd.Series | None = None,
) -> LinearModel | LogisticPipeline | LightGBMPipeline:
    """Fit a model of the spec's type over the given feature frame and target.

    Phase A implements the ``linear`` type; Phase B (issue #40) dispatches
    the classifier pipelines (logistic / lightgbm) to their lazy
    import-guarded codecs. The return-based pipeline types (hmm / garch)
    fit on per-symbol returns through their pipelines, never here —
    ``fit_model`` refuses them rather than fabricating a classifier out
    of a series fit. The caller supplies frames computed from the spec's
    feature set (the spec pins the feature-set digest; ``fit_model`` is
    deliberately registry-free).
    """
    if spec.model_type not in MODEL_TYPES:
        raise ValueError(
            f"model type {spec.model_type!r} is not implemented "
            f"(expected one of {MODEL_TYPES})"
        )
    if spec.model_type == "linear":
        return LinearModel.fit(X, y, train_mask=train_mask)
    if spec.model_type == "logistic":
        # Lazy import: the pipelines module is import-guarded on the
        # research extra, which is optional runtime surface (ADR-0009).
        from quantmesh.research.pipelines import LogisticPipeline

        return LogisticPipeline(spec.hyperparameters).fit(X, y)
    if spec.model_type == "lightgbm":
        from quantmesh.research.pipelines import LightGBMPipeline

        return LightGBMPipeline(spec.hyperparameters).fit(X, y)
    raise ValueError(
        f"model type {spec.model_type!r} fits on returns through its pipeline "
        "(HMMPipeline / GARCHPipeline in quantmesh.research.pipelines), "
        "not fit_model(X, y)"
    )


class ModelRecord(BaseModel):
    """One recorded model: pinned setup plus observed results."""

    id: str = Field(pattern=ID_PATTERN)
    spec: ModelSpec
    metrics: dict[str, Parameter] = Field(default_factory=dict)
    artifact_sha256: str = Field(pattern=SHA256_PATTERN)
    created_at: datetime

    @field_validator("metrics")
    @classmethod
    def metrics_are_finite(cls, values: dict[str, Parameter]) -> dict[str, Parameter]:
        for name, value in values.items():
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(f"metric {name!r} is not finite ({value})")
        return values

    @model_validator(mode="after")
    def record_is_consistent(self) -> ModelRecord:
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        self.created_at = self.created_at.astimezone(UTC)
        if self.id != self.spec.id:
            raise ValueError(
                f"record id {self.id!r} does not match its spec id {self.spec.id!r}"
            )
        return self


def artifact_path(root: Path, model_id_value: str) -> Path:
    """Deterministic artifact location for a model (registry discipline)."""
    return root / model_id_value / ARTIFACT_NAME


class ModelRegistry:
    """Append-only store of models and their byte-addressed artifacts."""

    def __init__(self, root: Path | None = None, lake_root: Path | None = None) -> None:
        self.root = root if root is not None else settings.models_dir
        self.lake_root = lake_root if lake_root is not None else settings.lake_root

    def record(
        self,
        *,
        spec: ModelSpec,
        metrics: dict[str, Parameter] | None = None,
        artifact_bytes: bytes,
    ) -> ModelRecord:
        """Record a model; the pin is validated before anything is written.

        The artifact is written first (atomic temp + replace) and the
        sha256 recorded on the record; the record append happens last, so
        a crash leaves at worst an unreferenced orphan artifact, never a
        record whose bytes are missing. Duplicate IDs are refused — the
        same setup is the same model.
        """
        existing = self.all()
        if any(record.id == spec.id for record in existing):
            raise ValueError(f"model {spec.id!r} already recorded")
        self._require_pin(spec)
        digest = hashlib.sha256(artifact_bytes).hexdigest()
        record = ModelRecord(
            id=spec.id,
            spec=spec,
            metrics=metrics or {},
            artifact_sha256=digest,
            created_at=datetime.now(UTC),
        )
        self._write_artifact(spec.id, artifact_bytes)
        _append_records(self.root, MODELS_FILE, existing + [record])
        return record

    def load(self, model_id_value: str) -> tuple[ModelRecord, bytes]:
        """The record and its artifact, with the sha256 re-verified.

        A missing, unreadable or tampered artifact fails closed — the
        record's identity pins the bytes.
        """
        record = self.get(model_id_value)
        path = artifact_path(self.root, model_id_value)
        try:
            data = path.read_bytes()
        except OSError as error:
            raise ValueError(f"model artifact {path} is unreadable") from error
        digest = hashlib.sha256(data).hexdigest()
        if digest != record.artifact_sha256:
            raise ValueError(
                f"model artifact {path} does not match the recorded sha256 "
                f"(recorded {record.artifact_sha256}, found {digest})"
            )
        return record, data

    def get(self, model_id_value: str) -> ModelRecord:
        for record in self.all():
            if record.id == model_id_value:
                return record
        raise ValueError(f"no model recorded with id {model_id_value!r}")

    def all(self) -> list[ModelRecord]:
        return _read_records(self.root, MODELS_FILE, ModelRecord)

    def resolve(self, model_id_value: str) -> Dataset:
        """Re-open the model's dataset, pinned to its revision (lake gate)."""
        record = self.get(model_id_value)
        self._require_pin(record.spec)
        return Lake(self.lake_root).dataset(record.spec.dataset)

    def _require_pin(self, spec: ModelSpec) -> None:
        dataset = Lake(self.lake_root).dataset(spec.dataset)
        if dataset.manifest.revision != spec.revision:
            raise ValueError(
                f"model {spec.id!r} pins manifest revision {spec.revision}, "
                f"but dataset {spec.dataset!r} is now revision "
                f"{dataset.manifest.revision}"
            )

    def _write_artifact(self, model_id_value: str, data: bytes) -> None:
        directory = self.root / model_id_value
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / ARTIFACT_NAME
        descriptor, temp_name = tempfile.mkstemp(
            dir=directory, prefix=f".{ARTIFACT_NAME}.", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
            atomic_replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)


def _append_records(root: Path, filename: str, records: list[BaseModel]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    path = root / filename
    descriptor, temp_name = tempfile.mkstemp(
        dir=root, prefix=f".{filename}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            for record in records:
                handle.write(record.model_dump_json())
                handle.write("\n")
        atomic_replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _read_records(root: Path, filename: str, model: type[BaseModel]) -> list[BaseModel]:
    if not root.exists():
        return []
    if not root.is_dir():
        raise ValueError(f"registry root {root} is not a directory")
    path = root / filename
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError(f"registry {path} is unreadable") from error
    records: list[BaseModel] = []
    seen: dict[str, int] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = model.model_validate_json(line)
        except ValidationError as error:
            raise ValueError(f"registry {path} line {line_number} is invalid") from error
        if record.id in seen:
            raise ValueError(
                f"registry {path} lines {seen[record.id]} and {line_number} "
                f"share an id"
            )
        seen[record.id] = line_number
        records.append(record)
    return records


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
