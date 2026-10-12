"""Canonical baseline results and immutable job-owned publication.

Receipt times belong in the per-attempt registry, never in result identity.
Publication creates bytes only; the JobStore lease fence alone grants success.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from quantmesh.research.jobs import ArtifactRef, JobRecord, canonical_request_digest
from quantmesh.research.reports import StrategyReport


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def canonical_result(report: StrategyReport) -> bytes:
    """Revalidate numerical content, preserving setup/evidence but no receipt clock."""
    valid = StrategyReport.model_validate(report.model_dump(mode="json"))
    data = valid.model_dump(mode="json", exclude={"created_at"})
    _numerical(valid)
    return _canonical(data)


def _numerical(report: StrategyReport) -> None:
    required = {
        "total_return",
        "annualized_return",
        "sharpe",
        "max_drawdown",
        "win_rate",
        "n_windows",
        "avg_turnover",
        "total_cost",
    }
    if set(report.metrics) != required or not report.windows:
        raise ValueError("invalid baseline numerical schema")
    if any(
        isinstance(v, bool) or not isinstance(v, (int, float, type(None)))
        for v in report.metrics.values()
    ):
        raise ValueError("invalid baseline metric")
    if report.metrics["n_windows"] != len(report.windows):
        raise ValueError("inconsistent windows")
    if report.signals_digest is not None or report.pipeline_digest is not None:
        raise ValueError("registered baseline has no signal or pipeline input")
    nullable = {"annualized_return", "sharpe"}
    if any(v is None for k, v in report.metrics.items() if k not in nullable):
        raise ValueError("mandatory baseline metric missing")
    if not 0 <= report.metrics["win_rate"] <= 1 or report.metrics["max_drawdown"] > 0:
        raise ValueError("metric outside baseline domain")
    aggregates = {
        "total_cost": sum(w.cost for w in report.windows),
        "avg_turnover": sum(w.turnover for w in report.windows) / len(report.windows),
        "win_rate": sum(w.window_return > 0 for w in report.windows) / len(report.windows),
        "total_return": math.prod(1 + w.window_return for w in report.windows) - 1,
    }
    if any(
        not math.isclose(report.metrics[k], v, rel_tol=1e-9, abs_tol=1e-12)
        for k, v in aggregates.items()
    ):
        raise ValueError("inconsistent numerical aggregates")
    for i, w in enumerate(report.windows):
        if w.index != i or not w.train_end < w.test_start <= w.test_end:
            raise ValueError("invalid window chronology")
        if i and report.windows[i - 1].test_end >= w.test_start:
            raise ValueError("overlapping evaluation windows")
        if not math.isclose(w.cost, report.costs.rate() * w.turnover, rel_tol=1e-9, abs_tol=1e-12):
            raise ValueError("window costs mismatch")


def _validate_result(job: JobRecord, raw: bytes) -> dict:
    if canonical_request_digest(job.request) != job.request_digest:
        raise ValueError("request digest mismatch")
    data = json.loads(raw)
    if not isinstance(data, dict) or set(data) != set(StrategyReport.model_fields) - {"created_at"}:
        raise ValueError("invalid canonical report schema")
    report = StrategyReport.model_validate({**data, "created_at": datetime(2000, 1, 1, tzinfo=UTC)})
    _numerical(report)
    r = job.request
    expected = dict(
        dataset=r.dataset.dataset_id,
        revision=r.dataset.revision,
        commit=job.implementation_digest,
        strategy=r.strategy_id,
        interval=r.interval,
        universe=[m.model_dump(mode="json") for m in r.universe],
        window_spec=r.window_spec.model_dump(),
        costs=r.costs.model_dump(),
    )
    if any(data[k] != v for k, v in expected.items()):
        raise ValueError("report setup mismatch")
    pins = dict(
        request_digest=job.request_digest,
        manifest_digest=r.dataset.manifest_digest,
        export_digest=r.dataset.export_digest,
    )
    if any(report.evidence.get(k) != v for k, v in pins.items()):
        raise ValueError("report input lineage mismatch")
    for key in ("build_digest", "dependency_digest"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(report.evidence.get(key, ""))):
            raise ValueError("report runtime fingerprint missing")
    # Require canonical encoding; duplicate keys, extraneous fields or alternate bytes reject.
    if canonical_result(report) != raw:
        raise ValueError("noncanonical report bytes")
    return data


def _contained(root: Path, path: Path) -> None:
    if root.resolve() not in path.resolve().parents or any(
        p.is_symlink() for p in (path, *path.parents)
    ):
        raise ValueError("artifact path invalid")


def publish_result(job: JobRecord, canonical_bytes: bytes, root: Path) -> ArtifactRef:
    """Install an immutable content-addressed envelope, never overwrite a collision."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", job.job_id):
        raise ValueError("artifact job ownership invalid")
    result = _validate_result(job, canonical_bytes)
    raw = _canonical(
        dict(
            schema_version=1,
            request_digest=job.request_digest,
            implementation_digest=job.implementation_digest,
            result=result,
        )
    )
    digest = hashlib.sha256(raw).hexdigest()
    root = Path(root)
    target = root / job.job_id / (digest + ".json")
    _contained(root, target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        # Same-filesystem hard-link is atomic create-if-absent, unlike replace().
        try:
            os.link(temporary, target)
        except FileExistsError:
            if target.read_bytes() != raw:
                raise ValueError("immutable artifact collision") from None
        _contained(root, target)
        if target.read_bytes() != raw:
            raise ValueError("artifact verification failed")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return ArtifactRef(
        artifact_id=digest,
        kind="report",
        sha256=digest,
        byte_size=len(raw),
        object_key=f"{job.job_id}/{digest}.json",
    )
