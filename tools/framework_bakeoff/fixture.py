"""Deterministic, explicitly synthetic lake fixture for framework bake-offs."""

import json
import math
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from quantmesh.data.lake import Lake
from quantmesh.data.manifest import DatasetManifest, ManifestWriter
from quantmesh.domain.market_data import Bar
from quantmesh.domain.models import Instrument, InstrumentType, Venue

FrameworkName = Literal["finrl-x", "nautilus-trader"]
_PIN_ADAPTER = TypeAdapter(dict[FrameworkName, "FrameworkPin"])
_ANCHOR = datetime(2025, 1, 2, 21, 0, tzinfo=UTC)
_DATASET = "bakeoff-moomoo-nvda"


class FrameworkPin(BaseModel):
    """Validated immutable repository metadata for one upstream candidate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    repository: str = Field(
        pattern=r"^https://github\.com/[^/\s]+/[^/\s]+(?:\.git)?$"
    )
    revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    license: str
    tag: str | None = None

    @field_validator("license")
    @classmethod
    def license_is_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("license must be nonblank")
        return value

    @field_validator("tag")
    @classmethod
    def tag_is_nonblank_when_present(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("tag must be nonblank when present")
        return value


def load_pins(path: Path) -> Mapping[FrameworkName, FrameworkPin]:
    """Load frozen, validated framework repository metadata from JSON."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"pins metadata {path} is unreadable") from error
    return MappingProxyType(_PIN_ADAPTER.validate_python(raw))


def build_nvda_fixture(root: Path, sessions: int = 420) -> DatasetManifest:
    """Write a reproducible 420-session synthetic NVDA dataset and manifest."""
    if sessions < 1:
        raise ValueError("sessions must be at least one")
    instrument = Instrument(
        symbol="NVDA",
        venue=Venue.MOOMOO,
        instrument_type=InstrumentType.EQUITY,
        currency="USD",
    )
    bars: list[Bar] = []
    session = _ANCHOR
    for index in range(sessions):
        close = 120 * math.exp(
            0.0004 * index + 0.018 * math.sin(2 * math.pi * index / 21)
        )
        open_price = close * (1 + 0.002 * math.sin(2 * math.pi * index / 7))
        high = max(open_price, close) * 1.003
        low = min(open_price, close) * 0.997
        bars.append(
            Bar(
                instrument=instrument,
                timestamp=session,
                interval="1d",
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=float(1_000_000 + 10_000 * (index % 31)),
            )
        )
        session += timedelta(days=1)
        while session.weekday() >= 5:
            session += timedelta(days=1)

    lake = Lake(root)
    lake.write_bars(_DATASET, bars)
    return ManifestWriter(root).generate(
        _DATASET,
        source="quantmesh-deterministic-bakeoff",
        license="QuantMesh synthetic test data",
        revision=1,
        generated_at=_ANCHOR,
    )
