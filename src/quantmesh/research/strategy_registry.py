"""Allowlisted existing baselines and read-only, explicitly fixture-only v1 gate."""

import hashlib
import inspect
import json
import math
from datetime import UTC, datetime
from pathlib import Path

from quantmesh.data._fixture_read_scope import current_reader
from quantmesh.data.lake import Lake
from quantmesh.data.layout import shards_in, validate_dataset_name
from quantmesh.domain.market_data import interval_to_timedelta, monotonic_violations
from quantmesh.research import baselines
from quantmesh.research.jobs import DatasetRef, DatasetRejected, ResearchJobRequest, StrategySpec

_BASELINES = {
    "momentum": baselines.momentum_weights,
    "mean_reversion": baselines.mean_reversion_weights,
    "risk_parity": baselines.risk_parity_weights,
}


def get_strategy(strategy_id: str, version: str) -> StrategySpec:
    if strategy_id not in _BASELINES or version != "1":
        raise ValueError("unknown registered strategy/version")
    # Pin the engine and costs as well as the selected strategy's function.
    code = Path(inspect.getfile(baselines)).read_bytes()
    from quantmesh.research import reports

    code += Path(inspect.getfile(reports)).read_bytes()
    digest = hashlib.sha256(strategy_id.encode() + b"\0" + code).hexdigest()
    return StrategySpec(
        strategy_id=strategy_id,
        version=version,
        family=strategy_id,
        parameters_schema={"type": "object", "properties": {}, "additionalProperties": False},
        supported_markets=["moomoo", "internal"],
        supported_intervals=["1m", "5m", "15m", "30m", "1h", "1d"],
        dataset_requirements={
            "bars": "aligned-positive-chronological",
            "permission": "fixture",
            "manifest_schema": 1,
            "minimum": "train_bars+test_bars",
        },
        cost_policy_id="baseline-bps-v1",
        implementation_digest=digest,
    )


def _fixture_pin(root: Path, name: str) -> tuple[DatasetRef, object]:
    reader = current_reader(root, name)
    if reader is not None:
        return reader.pin()
    try:
        validate_dataset_name(name)
        manifest_path = root / name / "manifest.json"
        if manifest_path.is_symlink():
            raise DatasetRejected("manifest_invalid")
        declared = json.loads(manifest_path.read_bytes())
        if not isinstance(declared, dict):
            raise DatasetRejected("manifest_invalid")
        if declared.get("schema_version", 1) != 1:
            raise DatasetRejected("manifest_schema_unsupported")
        if declared.get("source") != "fixture" or declared.get("license") != "test":
            raise DatasetRejected("permission_unsupported")
        dataset = Lake(root).dataset(name)
        manifest = dataset.manifest
        # Legacy manifests have no rights object. Only explicit test declarations are admitted.
        if manifest.source != "fixture" or manifest.license != "test":
            raise DatasetRejected("permission_unsupported")
        entries = []
        for coverage in manifest.coverage:
            partition = root / name / coverage.interval / coverage.venue.value / coverage.symbol
            for shard in shards_in(partition):
                if shard.is_symlink():
                    raise DatasetRejected("export_invalid")
                entries.append(
                    (
                        shard.relative_to(root / name).as_posix(),
                        hashlib.sha256(shard.read_bytes()).hexdigest(),
                    )
                )
        export = json.dumps(sorted(entries), separators=(",", ":"), ensure_ascii=False).encode()
        return DatasetRef(
            dataset_id=name,
            revision=manifest.revision,
            manifest_digest=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            permission_class="fixture",
            export_digest=hashlib.sha256(export).hexdigest(),
        ), dataset
    except DatasetRejected:
        raise
    except (ValueError, OSError) as exc:
        raise DatasetRejected("manifest_or_export_invalid") from exc


def pin_fixture_dataset(root: Path, dataset_id: str) -> DatasetRef:
    """Explicit local fixture helper, with no export, write or network operation."""
    return _fixture_pin(root, dataset_id)[0]


def validate_dataset(request: ResearchJobRequest, root: Path, now: datetime) -> None:
    if request.dataset.permission_class != "fixture":
        raise DatasetRejected("permission_unsupported")
    actual, dataset = _fixture_pin(root, request.dataset.dataset_id)
    if actual != request.dataset:
        raise DatasetRejected("pin_mismatch")
    try:
        grid = None
        for member in request.universe:
            bars = dataset.read_bars(
                interval=request.interval, venue=member.venue, symbol=member.symbol
            )
            current = [b.timestamp for b in bars]
            if not current or monotonic_violations(current):
                raise DatasetRejected("chronology_invalid")
            if len(set(current)) != len(current):
                raise DatasetRejected("chronology_invalid")
            duration = interval_to_timedelta(request.interval)
            if any(b.timestamp.astimezone(UTC) + duration > now or b.close <= 0 for b in bars):
                raise DatasetRejected("future_or_nonpositive_data")
            if any(
                not math.isfinite(getattr(b, field))
                for b in bars
                for field in ("open", "high", "low", "close", "volume")
            ):
                raise DatasetRejected("nonfinite_data")
            if grid is not None and grid != current:
                raise DatasetRejected("universe_grid_mismatch")
            grid = current
        request.window_spec.test_starts(len(grid))
        # Re-pin after reading: a changed shard/manifest cannot be silently admitted.
        if _fixture_pin(root, request.dataset.dataset_id)[0] != actual:
            raise DatasetRejected("pin_changed_during_admission")
    except DatasetRejected:
        raise
    except (ValueError, OSError) as exc:
        raise DatasetRejected("coverage_or_window_invalid") from exc
