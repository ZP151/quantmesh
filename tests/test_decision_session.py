from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.instruments.contracts import HistoryRange
from quantmesh.instruments.decision_packets import DecisionPacketStore
from quantmesh.instruments.monitoring import DecisionWatchService, DecisionWatchStore
from quantmesh.instruments.session import DecisionSessionError, DecisionSessionService

NOW = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)


class _Packets:
    def __init__(self, packets: dict[str, object]) -> None:
        self._packets = packets

    def get(self, packet_id: str) -> object:
        return self._packets[packet_id]


class _Watches:
    def __init__(self, registrations: dict[str, object]) -> None:
        self._registrations = registrations
        self.checked: list[tuple[str, object]] = []
        self.store = SimpleNamespace(registrations=lambda: tuple(registrations.values()))

    def state(self, packet_id: str):
        return self._registrations.get(packet_id), None

    def validate_replay(self) -> None:
        self.store.registrations()

    def check(self, registration_id: str, observation: object):
        self.checked.append((registration_id, observation))
        return SimpleNamespace(
            evaluation_id=f"evaluation-{registration_id[-24:]}",
            results=(SimpleNamespace(state="not_triggered", facts=SimpleNamespace(code="ok")),),
        )


class _Inbox:
    def __init__(self, entries: tuple[object, ...]) -> None:
        self._entries = entries
        self.snapshot_at: datetime | None = None

    def snapshot(self, *, at: datetime):
        self.snapshot_at = at
        return SimpleNamespace(entries=self._entries)


class _Renderer:
    def __init__(self) -> None:
        self.calls: list[tuple[Venue, str, HistoryRange]] = []

    def render(self, venue: Venue, symbol: str, selected_range: HistoryRange):
        self.calls.append((venue, symbol, selected_range))
        return SimpleNamespace(
            live=SimpleNamespace(
                last=100.0,
                source="local-workspace",
                provenance="demo-synthetic",
                data_time=NOW,
                received_at=NOW,
                sequence=1,
                sequence_gap=False,
            ),
            forecast=None,
        )


def _packet(symbol: str) -> object:
    identities = {"AAPL": "a" * 24, "NVDA": "b" * 24}
    return SimpleNamespace(
        packet_id=f"packet-{identities[symbol]}",
        instrument=Instrument(
            venue=Venue.MOOMOO,
            symbol=symbol,
            instrument_type=InstrumentType.EQUITY,
            currency="USD",
        ),
        selected_range=HistoryRange.SIX_MONTHS,
    )


def _entry(packet: object) -> object:
    return SimpleNamespace(packet_id=packet.packet_id)


def _registration(packet: object) -> object:
    identities = {"AAPL": "c" * 24, "NVDA": "d" * 24}
    return SimpleNamespace(registration_id=f"registration-{identities[packet.instrument.symbol]}")


def test_refresh_evaluates_registered_packets_in_deterministic_identity_order() -> None:
    nvda = _packet("NVDA")
    aapl = _packet("AAPL")
    renderer = _Renderer()
    inbox = _Inbox((_entry(nvda), _entry(aapl)))
    watches = _Watches({nvda.packet_id: _registration(nvda), aapl.packet_id: _registration(aapl)})
    service = DecisionSessionService(
        inbox=inbox,
        packets=_Packets({nvda.packet_id: nvda, aapl.packet_id: aapl}),
        watches=watches,
        workspace=renderer,
        now=lambda: NOW,
    )

    result = service.refresh()

    assert result.status == "complete"
    assert result.registered_count == 2
    assert result.evaluated_count == 2
    assert [item.packet_id for item in result.items] == [aapl.packet_id, nvda.packet_id]
    assert all(item.evaluation_id is not None for item in result.items)
    assert renderer.calls == [
        (Venue.MOOMOO, "AAPL", HistoryRange.SIX_MONTHS),
        (Venue.MOOMOO, "NVDA", HistoryRange.SIX_MONTHS),
    ]
    assert inbox.snapshot_at == NOW


def test_refresh_reports_no_registered_watches_without_rendering() -> None:
    packet = _packet("NVDA")
    renderer = _Renderer()
    service = DecisionSessionService(
        inbox=_Inbox((_entry(packet),)),
        packets=_Packets({packet.packet_id: packet}),
        watches=_Watches({}),
        workspace=renderer,
        now=lambda: NOW,
    )

    result = service.refresh()

    assert result.status == "no_registered_watches"
    assert result.registered_count == 0
    assert result.evaluated_count == 0
    assert result.items == ()
    assert renderer.calls == []


def test_refresh_refuses_corrupt_registration_replay_before_an_empty_selection() -> None:
    watches = _Watches({})
    watches.store = SimpleNamespace(
        registrations=lambda: (_ for _ in ()).throw(ValueError("corrupt registration"))
    )
    service = DecisionSessionService(
        inbox=_Inbox(()),
        packets=_Packets({}),
        watches=watches,
        workspace=_Renderer(),
        now=lambda: NOW,
    )

    with pytest.raises(DecisionSessionError, match="registrations cannot be replayed"):
        service.refresh()

    assert watches.checked == []


def test_refresh_refuses_corrupt_evaluation_replay_before_empty_selection(tmp_path) -> None:
    """Catch an empty Inbox result that skips the independent evaluation ledger."""
    root = tmp_path / "monitoring"
    root.mkdir()
    corrupt = "{corrupt-evaluation}\n"
    evaluation_path = root / "watch-evaluations.jsonl"
    evaluation_path.write_text(corrupt, encoding="utf-8")
    renderer = _Renderer()
    watches = DecisionWatchService(
        packet_store=DecisionPacketStore(tmp_path / "packets"),
        store=DecisionWatchStore(root),
    )
    service = DecisionSessionService(
        inbox=_Inbox(()),
        packets=_Packets({}),
        watches=watches,
        workspace=renderer,
        now=lambda: NOW,
    )

    with pytest.raises(DecisionSessionError, match="registrations cannot be replayed"):
        service.refresh()

    assert renderer.calls == []
    assert evaluation_path.read_text(encoding="utf-8") == corrupt


def test_refresh_marks_missing_packet_as_a_sanitized_partial_failure() -> None:
    packet = _packet("NVDA")
    service = DecisionSessionService(
        inbox=_Inbox((_entry(packet),)),
        packets=_Packets({}),
        watches=_Watches({packet.packet_id: _registration(packet)}),
        workspace=_Renderer(),
        now=lambda: NOW,
    )

    result = service.refresh()

    assert result.status == "partial"
    assert result.evaluated_count == 0
    assert result.items[0].status == "failed"
    assert result.items[0].reason_code == "packet_unavailable"


@pytest.mark.parametrize(
    "forbidden", ["provider", "scheduler", "proposal", "confirmation", "order"]
)
def test_session_constructor_has_no_operational_or_order_collaborators(forbidden: str) -> None:
    assert forbidden not in DecisionSessionService.__init__.__annotations__
