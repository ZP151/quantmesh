"""Server-owned local observations shared by packet and session watch checks."""

from __future__ import annotations

from datetime import UTC, datetime

from quantmesh.domain.models import Instrument
from quantmesh.instruments.contracts import DecisionPacket, InstrumentWorkspace
from quantmesh.instruments.monitoring import DecisionWatchObservation


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("instrument clock is invalid")
    return value.astimezone(UTC)


def build_watch_observation(
    *,
    packet: DecisionPacket,
    workspace: InstrumentWorkspace,
    evaluated_at: datetime,
) -> DecisionWatchObservation:
    """Map a rendered local workspace into the durable watch input exactly once."""
    live = workspace.live
    return DecisionWatchObservation(
        evaluated_at=_utc(evaluated_at),
        price=live.last,
        # DecisionPacket keeps its instrument snapshot deeply immutable.  Copy
        # it into the durable observation's base contract so its mappingproxy
        # metadata cannot leak into JSONL serialization.
        instrument=(
            Instrument(
                symbol=packet.instrument.symbol,
                venue=packet.instrument.venue,
                instrument_type=packet.instrument.instrument_type,
                currency=packet.instrument.currency,
                metadata=dict(packet.instrument.metadata),
            )
            if live.last is not None
            else None
        ),
        source=live.source,
        provenance=live.provenance,
        data_time=live.data_time,
        received_at=live.received_at,
        sequence=live.sequence,
        sequence_gap=live.sequence_gap,
        candidate_forecast_artifact_id=(
            workspace.forecast.artifact_id if workspace.forecast is not None else None
        ),
    )
