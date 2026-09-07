"""Explicit, local-only re-evaluation of existing decision watches."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal

from pydantic import Field, field_validator

from quantmesh.instruments.contracts import StrictContract
from quantmesh.instruments.decision_packets import DecisionPacketNotFoundError
from quantmesh.instruments.watch_observations import build_watch_observation


class DecisionSessionError(ValueError):
    """Stored session inputs cannot be replayed as a complete local session."""


class DecisionSessionRefreshItem(StrictContract):
    packet_id: str = Field(pattern=r"^packet-[0-9a-f]{24}$")
    registration_id: str = Field(pattern=r"^registration-[0-9a-f]{24}$")
    evaluation_id: str | None = Field(default=None, pattern=r"^evaluation-[0-9a-f]{24}$")
    status: Literal["evaluated", "failed"]
    triggered: bool = False
    not_comparable_codes: tuple[str, ...] = ()
    reason_code: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,63}$")
    reason: str | None = Field(default=None, min_length=1, max_length=300)


class DecisionSessionRefreshResult(StrictContract):
    started_at: datetime
    completed_at: datetime
    status: Literal["complete", "partial", "no_registered_watches"]
    registered_count: int = Field(ge=0)
    evaluated_count: int = Field(ge=0)
    items: tuple[DecisionSessionRefreshItem, ...]

    @field_validator("started_at", "completed_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("session timestamps must be timezone-aware")
        return value.astimezone(UTC)


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise DecisionSessionError("instrument clock is invalid")
    return value.astimezone(UTC)


def _reason_code(error: Exception) -> str:
    if isinstance(error, (DecisionPacketNotFoundError, KeyError)) or (
        "not found" in str(error).lower()
    ):
        return "packet_unavailable"
    if isinstance(error, OSError):
        return "local_workspace_unavailable"
    return "local_evaluation_unavailable"


class DecisionSessionService:
    """Refresh existing local registrations from one frozen Inbox snapshot only."""

    def __init__(
        self,
        *,
        inbox: object | Callable[[], object],
        packets: object | Callable[[], object],
        watches: object | Callable[[], object],
        workspace: object | Callable[[], object],
        now: Callable[[], datetime],
    ) -> None:
        self._inbox = inbox
        self._packets = packets
        self._watches = watches
        self._workspace = workspace
        self._now = now

    @staticmethod
    def _current(value: object | Callable[[], object]) -> object:
        return value() if callable(value) else value

    def refresh(self) -> DecisionSessionRefreshResult:
        started_at = _utc(self._now())
        try:
            inbox = self._current(self._inbox)
            snapshot = inbox.snapshot(at=started_at)
            entries = tuple(snapshot.entries)
        except (AttributeError, OSError, ValueError, TypeError) as error:
            raise DecisionSessionError("Decision Inbox replay is unavailable") from error

        watches = self._current(self._watches)
        packets = self._current(self._packets)
        workspace = self._current(self._workspace)
        selected: list[tuple[object, object]] = []
        try:
            # Replay the durable registration ledger even if Inbox selects no
            # packet.  An empty projection cannot make corrupt local state true.
            watches.validate_replay()
            for entry in entries:
                packet_id = entry.packet_id
                if packet_id is None:
                    continue
                registration, _ = watches.state(packet_id)
                if registration is not None:
                    selected.append((entry, registration))
            selected.sort(
                key=lambda item: self._sort_key(packets, item[0].packet_id),
            )
        except (AttributeError, OSError, ValueError, TypeError) as error:
            raise DecisionSessionError("decision watch registrations cannot be replayed") from error

        items: list[DecisionSessionRefreshItem] = []
        for entry, registration in selected:
            try:
                packet = packets.get(entry.packet_id)
                rendered = workspace.render(
                    packet.instrument.venue,
                    packet.instrument.symbol,
                    packet.selected_range,
                )
                evaluation = watches.check(
                    registration.registration_id,
                    build_watch_observation(
                        packet=packet,
                        workspace=rendered,
                        evaluated_at=started_at,
                    ),
                )
                results = tuple(evaluation.results)
                items.append(
                    DecisionSessionRefreshItem(
                        packet_id=packet.packet_id,
                        registration_id=registration.registration_id,
                        evaluation_id=evaluation.evaluation_id,
                        status="evaluated",
                        triggered=any(result.state == "triggered" for result in results),
                        not_comparable_codes=tuple(
                            result.facts.code
                            for result in results
                            if result.state == "not_comparable" and hasattr(result.facts, "code")
                        ),
                    )
                )
            except (DecisionPacketNotFoundError, KeyError, OSError, ValueError) as error:
                items.append(
                    DecisionSessionRefreshItem(
                        packet_id=entry.packet_id,
                        registration_id=registration.registration_id,
                        status="failed",
                        reason_code=_reason_code(error),
                        reason="This local watch could not be evaluated.",
                    )
                )

        completed_at = _utc(self._now())
        if completed_at < started_at:
            raise DecisionSessionError("instrument clock moved backwards during refresh")
        evaluated_count = sum(item.status == "evaluated" for item in items)
        return DecisionSessionRefreshResult(
            started_at=started_at,
            completed_at=completed_at,
            status=(
                "no_registered_watches"
                if not selected
                else "partial"
                if evaluated_count != len(selected)
                else "complete"
            ),
            registered_count=len(selected),
            evaluated_count=evaluated_count,
            items=tuple(items),
        )

    @staticmethod
    def _sort_key(packets: object, packet_id: str) -> tuple[str, str, str]:
        try:
            packet = packets.get(packet_id)
        except (DecisionPacketNotFoundError, KeyError):
            return ("", "", packet_id)
        return (packet.instrument.venue.value, packet.instrument.symbol, packet.packet_id)
