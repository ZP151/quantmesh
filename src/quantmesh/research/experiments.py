"""Experiment registry: reproducible research records (issue #18).

An experiment pins the inputs that define a run — dataset, manifest
revision, code commit, parameters — under a deterministic ID, and
carries the outputs (metrics). The same setup always produces the same
ID, so "reproduce experiment X" is well-defined: resolve the pin through
the lake's manifest gate and re-run with the recorded parameters (the
M3 exit criterion: manifest → lake → experiment registry on a clean
checkout).

Records persist as JSONL under the registry root. ``record`` rewrites
the file atomically (unique temp file + rename) so a crash cannot
corrupt prior records; duplicate IDs are refused because metrics do not
change an experiment's identity. Reads fail closed: a corrupt or
tampered line names the file and line instead of resolving silently,
and duplicate IDs are refused on read as well as write. Metrics are
results, not identity — an edit that only changes a metric value is
not detectable without signing (out of M3 scope). Non-finite floats
(NaN/Infinity) are rejected at the model boundary: JSON cannot carry
them portably, so a record that would serialize differently from its
identity hash must never be written. Concurrent writers are not
synchronized — the last writer wins, which suits the single-user local
workstation this registry serves.
"""

import hashlib
import json
import math
import os
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import (
    BaseModel,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from quantmesh._fs import atomic_replace
from quantmesh.data.lake import Lake
from quantmesh.data.layout import validate_dataset_name
from quantmesh.settings import settings

EXPERIMENTS_FILE = "experiments.jsonl"

ID_PATTERN = "^[0-9a-f]{16}$"
COMMIT_PATTERN = "^[0-9a-f]{7,64}$"

Parameter = str | int | float | bool | None


class TrustedResearchCatalog(Protocol):
    def open_research_dataset(
        self,
        manifest_id: str,
        *,
        evaluation_id: str,
        dataset_id: str,
        compatibility_revision: int,
    ) -> Any: ...


def experiment_id(
    dataset: str,
    revision: int,
    commit: str,
    parameters: dict[str, Parameter],
    *,
    manifest_id: str | None = None,
    quality_evaluation_id: str | None = None,
) -> str:
    """Deterministic identity of a run: setup only, never results."""
    if (manifest_id is None) != (quality_evaluation_id is None):
        raise ValueError(
            "manifest_id and quality_evaluation_id must be present together"
        )
    canonical = json.dumps(parameters, sort_keys=True, separators=(",", ":"))
    payload = f"{dataset}\0{revision}\0{commit}\0{canonical}"
    if manifest_id is not None:
        payload += f"\0{manifest_id}\0{quality_evaluation_id}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class Experiment(BaseModel):
    """One recorded run: pinned inputs plus observed results."""

    id: str = Field(pattern=ID_PATTERN)
    dataset: str
    revision: int = Field(ge=1)
    manifest_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    quality_evaluation_id: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    commit: str = Field(pattern=COMMIT_PATTERN)
    parameters: dict[str, Parameter] = Field(default_factory=dict)
    metrics: dict[str, Parameter] = Field(default_factory=dict)
    created_at: datetime

    @field_validator("parameters", "metrics")
    @classmethod
    def values_are_finite(cls, values: dict[str, Parameter]) -> dict[str, Parameter]:
        """Non-finite floats would serialize as ``null``, breaking identity."""
        for name, value in values.items():
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(f"value for {name!r} is not finite ({value})")
        return values

    @model_validator(mode="after")
    def experiment_is_consistent(self) -> "Experiment":
        if (self.manifest_id is None) != (self.quality_evaluation_id is None):
            raise ValueError(
                "manifest_id and quality_evaluation_id must be present together"
            )
        validate_dataset_name(self.dataset)
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        self.created_at = self.created_at.astimezone(UTC)
        if self.id != experiment_id(
            self.dataset,
            self.revision,
            self.commit,
            self.parameters,
            manifest_id=self.manifest_id,
            quality_evaluation_id=self.quality_evaluation_id,
        ):
            raise ValueError(
                f"experiment id {self.id!r} does not match its pinned inputs "
                "(dataset, revision, commit, parameters)"
            )
        return self


class ExperimentRegistry:
    """Append-only store of experiments under one registry root."""

    def __init__(
        self,
        root: Path | None = None,
        lake_root: Path | None = None,
        *,
        trusted_catalog: TrustedResearchCatalog | None = None,
    ) -> None:
        self.root = root if root is not None else settings.experiments_dir
        self.lake_root = lake_root if lake_root is not None else settings.lake_root
        self.trusted_catalog = trusted_catalog

    def record(
        self,
        *,
        dataset: str,
        revision: int,
        manifest_id: str | None = None,
        quality_evaluation_id: str | None = None,
        commit: str | None = None,
        parameters: dict[str, Parameter] | None = None,
        metrics: dict[str, Parameter] | None = None,
        created_at: datetime | None = None,
    ) -> Experiment:
        """Record a run; ``commit`` defaults to the current git HEAD.

        The pin is validated before anything is written: the dataset
        must pass the lake's manifest gate and the manifest revision
        must match ``revision``, so the registry never holds a dangling
        pin. ``created_at`` defaults to the current time; pin it
        explicitly when a record must be byte-reproducible (demo seed,
        replay).
        """
        if commit is None:
            commit = self._current_commit()
        experiment = Experiment(
            id=experiment_id(
                dataset,
                revision,
                commit,
                parameters or {},
                manifest_id=manifest_id,
                quality_evaluation_id=quality_evaluation_id,
            ),
            dataset=dataset,
            revision=revision,
            manifest_id=manifest_id,
            quality_evaluation_id=quality_evaluation_id,
            commit=commit,
            parameters=parameters or {},
            metrics=metrics or {},
            created_at=created_at or datetime.now(UTC),
        )
        existing = self.all()
        if any(record.id == experiment.id for record in existing):
            raise ValueError(f"experiment {experiment.id!r} already recorded")
        self._require_pin(experiment)
        self._append(experiment, existing)
        return experiment

    def get(self, experiment_id: str) -> Experiment:
        """The record with this ID; raises when absent or unreadable."""
        for experiment in self.all():
            if experiment.id == experiment_id:
                return experiment
        raise ValueError(f"no experiment recorded with id {experiment_id!r}")

    def all(self) -> list[Experiment]:
        """Every record, in recording order."""
        return self._read()

    def resolve(self, experiment_id: str) -> Any:
        """Re-open the experiment's dataset, pinned to its revision.

        The lake's manifest gate checks the bytes match the declaration
        before anything is read; this additionally refuses when the
        manifest has moved on to a newer revision — the pinned
        experiment no longer describes the data on disk.
        """
        experiment = self.get(experiment_id)
        return self._require_pin(experiment)

    def _require_pin(self, experiment: Experiment) -> Any:
        if experiment.manifest_id is not None:
            if self.trusted_catalog is None or experiment.quality_evaluation_id is None:
                raise ValueError("trusted experiment lineage requires a data catalog")
            return self.trusted_catalog.open_research_dataset(
                experiment.manifest_id,
                evaluation_id=experiment.quality_evaluation_id,
                dataset_id=experiment.dataset,
                compatibility_revision=experiment.revision,
            )
        dataset = Lake(self.lake_root).dataset(experiment.dataset)
        if dataset.manifest.revision != experiment.revision:
            raise ValueError(
                f"experiment {experiment.id!r} pins manifest revision "
                f"{experiment.revision}, but dataset {experiment.dataset!r} is now "
                f"revision {dataset.manifest.revision}"
            )
        return dataset

    def _append(self, experiment: Experiment, existing: list[Experiment]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / EXPERIMENTS_FILE
        descriptor, temp_name = tempfile.mkstemp(
            dir=self.root, prefix=f".{EXPERIMENTS_FILE}.", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                for record in existing + [experiment]:
                    excluded = (
                        {"manifest_id", "quality_evaluation_id"}
                        if record.manifest_id is None
                        else set()
                    )
                    handle.write(record.model_dump_json(exclude=excluded))
                    handle.write("\n")
            atomic_replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def _read(self) -> list[Experiment]:
        if not self.root.exists():
            return []
        if not self.root.is_dir():
            raise ValueError(f"experiment registry root {self.root} is not a directory")
        path = self.root / EXPERIMENTS_FILE
        if not path.exists():
            return []
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise ValueError(f"experiment registry {path} is unreadable") from error
        records = []
        seen: dict[str, int] = {}
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                record = Experiment.model_validate_json(line)
            except ValidationError as error:
                raise ValueError(
                    f"experiment registry {path} line {line_number} is invalid"
                ) from error
            if record.id in seen:
                raise ValueError(
                    f"experiment registry {path} lines {seen[record.id]} and "
                    f"{line_number} share an experiment id"
                )
            seen[record.id] = line_number
            records.append(record)
        return records

    def _current_commit(self) -> str:
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
