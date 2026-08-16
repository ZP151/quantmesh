"""Metric records and the metrics store (M10 Phase A, issue #58).

``Metric`` is one observation (gauge or counter) with a deterministic
record id over ``(name, measured_at)`` — an identical replay at the
same instant is refused (the ADR-0006 discipline), a later sample
appends. ``MetricsStore`` persists them as ``metrics.jsonl`` under
``settings.metrics_dir`` with the exact ADR-0006 write/read
discipline: atomic temp+replace appends, fail-closed reads with line
attribution, duplicate ids refused, root-not-dir refused, and a
missing store reading as an empty list — never an error.
"""

import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator

from quantmesh.persistence.jsonl import JsonlStore
from quantmesh.research.reports import ID_PATTERN
from quantmesh.settings import settings

METRICS_FILE = "metrics.jsonl"

MetricKind = str  # "gauge" | "counter" — kept plain to stay open-ended


class Metric(BaseModel):
    """One recorded observation."""

    id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1, max_length=64)
    kind: MetricKind = Field(pattern=r"^(gauge|counter)$")
    unit: str = Field(min_length=1, max_length=16)
    value: float
    measured_at: datetime

    @field_validator("name")
    @classmethod
    def name_is_identifier(cls, name: str) -> str:
        if not (name.replace("_", "").isalnum() and name[0].islower()):
            raise ValueError(f"metric name {name!r} is not a snake_case identifier")
        return name

    @field_validator("value")
    @classmethod
    def value_is_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError(f"metric value must be finite ({value})")
        return value

    @model_validator(mode="after")
    def metric_is_consistent(self) -> "Metric":
        if self.measured_at.tzinfo is None:
            raise ValueError("measured_at must be timezone-aware")
        self.measured_at = self.measured_at.astimezone(UTC)
        expected = metric_id(name=self.name, measured_at=self.measured_at)
        if self.id != expected:
            raise ValueError(
                f"metric id {self.id!r} does not match its setup (expected {expected!r})"
            )
        return self


def metric_id(*, name: str, measured_at: datetime) -> str:
    """Deterministic metric identity: name + measurement instant. A
    re-measurement later is a new sample; an identical replay at the
    same instant is a duplicate (refused by the store)."""
    canonical = json.dumps(
        {"name": name, "measured_at": measured_at.astimezone(UTC).isoformat()},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(f"metric\0{canonical}".encode()).hexdigest()[:16]


class MetricsStore:
    """Append-only JSONL store of metric samples (ADR-0006 discipline)."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root if root is not None else settings.metrics_dir
        self._store = JsonlStore(
            self.root,
            filename=METRICS_FILE,
            model=Metric,
            label="metrics store",
            id_label="record",
            record_label="metric",
            key=lambda metric: metric.id,
        )

    def record(self, metric: Metric) -> Metric:
        """Record a sample; a duplicate id is refused before anything
        is written."""
        return self._store.append(metric)

    def all(self) -> list[Metric]:
        return self._store.read()
