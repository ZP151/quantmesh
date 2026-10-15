"""Read-only registered choices from construction-time Worker fixture inputs."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from quantmesh.data.lake import Lake
from quantmesh.data.layout import validate_dataset_name
from quantmesh.research.job_artifacts import _contained
from quantmesh.research.jobs import Contract, DatasetRef, ResearchJobRequest, StrategySpec
from quantmesh.research.reports import UniverseMember
from quantmesh.research.strategy_registry import get_strategy, pin_fixture_dataset, validate_dataset


class DatasetJobOption(Contract):
    dataset: DatasetRef
    interval: str
    universe: list[UniverseMember] = Field(min_length=1)
    minimum_available_bars: int = Field(ge=3)

    @model_validator(mode="after")
    def fixture_only(self):
        if self.dataset.permission_class != "fixture":
            raise ValueError("fixture inputs required")
        ResearchJobRequest(
            strategy_id="momentum",
            strategy_version="1",
            dataset=self.dataset,
            interval=self.interval,
            universe=[m.model_dump() for m in self.universe],
            costs=dict(fee_bps=1, half_spread_bps=1, slippage_bps=1),
            window_spec=dict(train_bars=2, test_bars=1, step_bars=1),
        )
        return self


class ResearchJobOptions(Contract):
    schema_version: Literal[1] = 1
    strategies: list[StrategySpec]
    datasets: list[DatasetJobOption]
    status: Literal["configured", "unavailable"]
    reason: Literal["no_qualified_inputs", "service_unavailable"] | None = None

    @model_validator(mode="after")
    def consistent_choices(self):
        for strategy in self.strategies:
            if strategy != get_strategy(strategy.strategy_id, strategy.version):
                raise ValueError("unrecognized strategy configuration")
        if self.status == "configured":
            if not self.strategies or not self.datasets or self.reason is not None:
                raise ValueError("configured options require choices")
        elif self.datasets or self.reason is None:
            raise ValueError("unavailable options cannot enable submission")
        return self


def _bounded_fixture(root: Path, name: str) -> None:
    validate_dataset_name(name)
    directory = root / name
    _contained(root, directory)
    total = 0
    count = 0
    # Inspect only explicitly configured dataset trees; refuse links before pin/read.
    pending = [directory]
    while pending:
        parent = pending.pop()
        for path in parent.iterdir():
            _contained(root, path)
            count += 1
            if count > 8192:
                raise ValueError("fixture too large")
            if path.is_dir():
                pending.append(path)
            elif path.is_file():
                total += path.stat().st_size
                if total > 256 * 1024 * 1024:
                    raise ValueError("fixture too large")
    manifest = directory / "manifest.json"
    if manifest.stat().st_size > 1024 * 1024:
        raise ValueError("manifest too large")


def job_options(lake_root: Path, configured_dataset_ids: tuple[str, ...]) -> ResearchJobOptions:
    strategies = [get_strategy(name, "1") for name in ("momentum", "mean_reversion", "risk_parity")]
    choices = []
    for name in dict.fromkeys(configured_dataset_ids[:128]):
        try:
            _bounded_fixture(lake_root, name)
            pin = pin_fixture_dataset(lake_root, name)
            manifest = Lake(lake_root).dataset(name).manifest
            intervals = sorted({coverage.interval for coverage in manifest.coverage})
            dataset_choices = []
            for interval in intervals:
                coverage = [c for c in manifest.coverage if c.interval == interval]
                members = [UniverseMember(venue=c.venue, symbol=c.symbol) for c in coverage]
                request = ResearchJobRequest(
                    strategy_id="momentum",
                    strategy_version="1",
                    dataset=pin,
                    interval=interval,
                    universe=[m.model_dump() for m in members],
                    costs=dict(fee_bps=1, half_spread_bps=1, slippage_bps=1),
                    window_spec=dict(train_bars=2, test_bars=1, step_bars=1),
                )
                validate_dataset(request, lake_root, datetime.now(UTC))
                dataset_choices.append(
                    DatasetJobOption(
                        dataset=pin,
                        interval=interval,
                        universe=members,
                        minimum_available_bars=min(c.rows for c in coverage),
                    )
                )
            if pin_fixture_dataset(lake_root, name) != pin:
                raise ValueError("pin changed")
            choices.extend(dataset_choices)
        except (ValueError, OSError):
            continue
    return ResearchJobOptions(
        strategies=strategies,
        datasets=choices,
        status="configured" if choices else "unavailable",
        reason=None if choices else "no_qualified_inputs",
    )
