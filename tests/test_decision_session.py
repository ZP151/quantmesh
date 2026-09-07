from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from quantmesh.api.workstation import create_workstation_app
from quantmesh.demo.runtime import create_demo_app
from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.execution.accounting import PaperAccount
from quantmesh.instruments.contracts import (
    DecisionCostEvidence,
    DecisionDisposition,
    DecisionEvidence,
    DecisionMarketState,
    DecisionPacket,
    DecisionPaperCapability,
    DecisionRiskPlan,
    DecisionScenario,
    HistoryRange,
)
from quantmesh.instruments.decision_packets import DecisionPacketStore, decision_packet_id
from quantmesh.instruments.monitoring import (
    DecisionWatchService,
    DecisionWatchStore,
    WatchConditionKind,
)
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


def _real_packet(
    *, symbol: str = "NVDA", as_of: datetime = NOW - timedelta(days=1)
) -> DecisionPacket:
    """One approved-fixture packet with all identity-bearing fields pinned."""
    instrument = Instrument(
        venue=Venue.MOOMOO,
        symbol=symbol,
        instrument_type=InstrumentType.EQUITY,
        currency="USD",
    )
    provisional = DecisionPacket(
        packet_id="packet-" + "0" * 24,
        version=1,
        parent_packet_id=None,
        instrument=instrument,
        selected_range=HistoryRange.SIX_MONTHS,
        as_of=as_of,
        created_at=as_of,
        market_state=DecisionMarketState(
            trend="bullish",
            latest_close=100.0,
            sma20=99.0,
            sma50=98.0,
            support=95.0,
            resistance=105.0,
            invalidation=94.0,
            observed_drawdown=0.04,
            observed_volatility=0.02,
            key_level_bar_times=(as_of - timedelta(days=1), as_of),
        ),
        scenarios=tuple(
            DecisionScenario(
                kind=kind,
                thesis=f"{kind} case",
                trigger="level",
                invalidation=94.0,
                target=target,
                confidence_reason="qualitative",
            )
            for kind, target in (("bull", 110.0), ("base", 105.0), ("bear", 90.0))
        ),
        risk_plan=DecisionRiskPlan(
            entry_price=100.0,
            stop_price=94.0,
            target_price=105.0,
            risk_per_unit=6.0,
            reward_per_unit=5.0,
            reward_to_risk=5.0 / 6.0,
            suggested_quantity=10.0,
            suggested_notional=1000.0,
            proposal_input_only=True,
        ),
        evidence=DecisionEvidence(
            history_dataset_id=f"{symbol.lower()}-demo",
            history_dataset_revision=1,
            history_manifest_id=None,
            history_quality_evaluation_id=None,
            history_source="demo-synthetic",
            history_generated_at=as_of,
            history_gaps=(),
            history_duplicates=(),
            history_limitations=(),
            forecast_artifact_id=None,
            forecast_model_name=None,
            forecast_model_version=None,
            forecast_config_digest=None,
            forecast_history_digest=None,
            forecast_benchmark_name=None,
            forecast_generated_at=None,
            forecast_chronology=None,
            forecast_metrics=(),
            costs=DecisionCostEvidence(
                fee_bps=10.0,
                slippage_bps=5.0,
                half_spread_bps=None,
                spread_status="confirmation-quote-required",
            ),
        ),
        paper_capability=DecisionPaperCapability(allowed=True, blockers=()),
        disposition=DecisionDisposition.DRAFT,
    )
    return provisional.model_copy(update={"packet_id": decision_packet_id(provisional)})


def _record_action_packet(store: DecisionPacketStore, *, symbol: str = "NVDA") -> DecisionPacket:
    parent = store.record(_real_packet(symbol=symbol))
    payload = parent.model_dump()
    payload.update(
        packet_id="packet-" + "0" * 24,
        version=2,
        parent_packet_id=parent.packet_id,
        disposition=DecisionDisposition.WATCH,
        operator_reason="Monitor the recorded decision.",
    )
    provisional = DecisionPacket.model_validate(payload)
    child = provisional.model_copy(update={"packet_id": decision_packet_id(provisional)})
    return store.record(child)


class _RealInbox:
    def __init__(self, entries: tuple[object, ...]) -> None:
        self._entries = entries

    def snapshot(self, *, at: datetime):
        return SimpleNamespace(entries=self._entries)


class _DurableRenderer:
    def __init__(self, *, at: datetime, sequence: int, quote: float | None = 101.0) -> None:
        self.at = at
        self.sequence = sequence
        self.quote = quote

    def render(self, _venue: Venue, _symbol: str, _selected_range: HistoryRange):
        return SimpleNamespace(
            live=SimpleNamespace(
                last=self.quote,
                source="local-workspace" if self.quote is not None else None,
                provenance="demo-synthetic" if self.quote is not None else None,
                data_time=self.at - timedelta(minutes=1) if self.quote is not None else None,
                received_at=self.at if self.quote is not None else None,
                sequence=self.sequence if self.quote is not None else None,
                sequence_gap=False if self.quote is not None else None,
            ),
            forecast=None,
        )


def _session_app(tmp_path):
    """Build the real HTTP composition while keeping facts server-owned and local."""
    packets = DecisionPacketStore(tmp_path / "packets")
    action_packet = _record_action_packet(packets)
    monitoring_root = tmp_path / "monitoring"
    watches = DecisionWatchService(
        packet_store=packets,
        store=DecisionWatchStore(monitoring_root),
    )
    registration = watches.register(action_packet.packet_id, (WatchConditionKind.ENTRY_ZONE,))
    renderer = _DurableRenderer(at=NOW, sequence=1)
    app = create_workstation_app(
        account=PaperAccount(cash=100_000.0),
        workspace_clock=lambda: NOW,
        host="127.0.0.1",
    )
    app.state.decision_packets = packets
    app.state.packet_monitoring = watches
    app.state.instrument_workspace = renderer
    app.state.decision_inbox = _RealInbox((_entry(action_packet),))
    return app, action_packet, watches, registration


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


def test_refresh_persists_canonical_replay_and_cursor_across_reconstruction(tmp_path) -> None:
    """Catch a session path that fabricates IDs, re-appends a replay, or loses its cursor."""
    packets = DecisionPacketStore(tmp_path / "packets")
    packet = _record_action_packet(packets)
    monitoring_root = tmp_path / "monitoring"
    watches = DecisionWatchService(
        packet_store=packets,
        store=DecisionWatchStore(monitoring_root),
    )
    registration = watches.register(packet.packet_id, (WatchConditionKind.ENTRY_ZONE,))
    inbox = _RealInbox((_entry(packet),))

    first = DecisionSessionService(
        inbox=inbox,
        packets=packets,
        watches=watches,
        workspace=_DurableRenderer(at=NOW, sequence=1),
        now=lambda: NOW,
    ).refresh()
    [first_item] = first.items
    assert first_item.status == "evaluated", first_item
    persisted = watches.store.evaluations(registration.registration_id)

    assert first_item.evaluation_id == persisted[-1].evaluation_id
    assert len(persisted) == 1

    replay = DecisionSessionService(
        inbox=inbox,
        packets=packets,
        watches=watches,
        workspace=_DurableRenderer(at=NOW, sequence=1),
        now=lambda: NOW,
    ).refresh()
    assert replay.items[0].evaluation_id == first_item.evaluation_id
    assert len(watches.store.evaluations(registration.registration_id)) == 1

    later = NOW + timedelta(minutes=2)
    restarted_packets = DecisionPacketStore(tmp_path / "packets")
    restarted_watches = DecisionWatchService(
        packet_store=restarted_packets,
        store=DecisionWatchStore(monitoring_root),
    )
    advanced = DecisionSessionService(
        inbox=inbox,
        packets=restarted_packets,
        watches=restarted_watches,
        workspace=_DurableRenderer(at=later, sequence=2),
        now=lambda: later,
    ).refresh()

    assert advanced.items[0].evaluation_id != first_item.evaluation_id
    durable_evaluations = restarted_watches.store.evaluations(registration.registration_id)
    assert advanced.items[0].evaluation_id == durable_evaluations[-1].evaluation_id
    assert [item.observation.sequence for item in durable_evaluations] == [1, 2]


def test_refresh_persists_a_stale_only_evaluation_without_a_quote(tmp_path) -> None:
    """Catch a refresh implementation that refuses a valid no-quote stale observation."""
    packets = DecisionPacketStore(tmp_path / "packets")
    packet = _record_action_packet(packets)
    watches = DecisionWatchService(
        packet_store=packets,
        store=DecisionWatchStore(tmp_path / "monitoring"),
    )
    registration = watches.register(packet.packet_id, (WatchConditionKind.DATA_STALE,))
    session = DecisionSessionService(
        inbox=_RealInbox((_entry(packet),)),
        packets=packets,
        watches=watches,
        workspace=_DurableRenderer(at=NOW, sequence=0, quote=None),
        now=lambda: NOW,
    )

    result = session.refresh()

    assert result.status == "complete"
    assert (
        result.items[0].evaluation_id
        == watches.store.evaluations(registration.registration_id)[-1].evaluation_id
    )
    assert result.items[0].not_comparable_codes == ()


def test_refresh_keeps_real_success_when_another_registered_packet_is_missing(tmp_path) -> None:
    """Catch a partial refresh that rolls back a successful durable evaluation."""
    packets = DecisionPacketStore(tmp_path / "packets")
    present = _record_action_packet(packets, symbol="NVDA")
    missing = _record_action_packet(packets, symbol="AAPL")
    root = tmp_path / "monitoring"
    watches = DecisionWatchService(packet_store=packets, store=DecisionWatchStore(root))
    present_registration = watches.register(present.packet_id, (WatchConditionKind.ENTRY_ZONE,))
    watches.register(missing.packet_id, (WatchConditionKind.ENTRY_ZONE,))
    packet_path = tmp_path / "packets" / "decision-packets.jsonl"
    packet_path.write_text(
        "\n".join(
            line
            for line in packet_path.read_text(encoding="utf-8").splitlines()
            if json.loads(line)["packet_id"] != missing.packet_id
        )
        + "\n",
        encoding="utf-8",
    )
    registration_count = len(watches.store.registrations())
    session = DecisionSessionService(
        inbox=_RealInbox((_entry(present), _entry(missing))),
        packets=packets,
        watches=watches,
        workspace=_DurableRenderer(at=NOW, sequence=1),
        now=lambda: NOW,
    )

    result = session.refresh()

    assert result.status == "partial"
    assert result.evaluated_count == 1
    assert {item.status for item in result.items} == {"evaluated", "failed"}
    assert (
        next(item for item in result.items if item.status == "failed").reason_code
        == "packet_unavailable"
    )
    assert len(watches.store.evaluations(present_registration.registration_id)) == 1
    assert len(watches.store.registrations()) == registration_count


def test_refresh_refuses_an_invalid_initial_or_backwards_completion_clock(tmp_path) -> None:
    """Catch removal of the guards before refresh reports a stable completion."""
    packets = DecisionPacketStore(tmp_path / "packets")
    packet = _record_action_packet(packets)
    watches = DecisionWatchService(
        packet_store=packets,
        store=DecisionWatchStore(tmp_path / "monitoring"),
    )
    registration = watches.register(packet.packet_id, (WatchConditionKind.ENTRY_ZONE,))
    renderer = _DurableRenderer(at=NOW, sequence=1)

    invalid = DecisionSessionService(
        inbox=_RealInbox((_entry(packet),)),
        packets=packets,
        watches=watches,
        workspace=renderer,
        now=lambda: datetime(2026, 9, 8, 12, 0),
    )
    with pytest.raises(DecisionSessionError, match="clock is invalid"):
        invalid.refresh()
    assert watches.store.evaluations(registration.registration_id) == ()

    moments = iter((NOW, NOW - timedelta(seconds=1)))
    backwards = DecisionSessionService(
        inbox=_RealInbox((_entry(packet),)),
        packets=packets,
        watches=watches,
        workspace=renderer,
        now=lambda: next(moments),
    )
    with pytest.raises(DecisionSessionError, match="clock moved backwards"):
        backwards.refresh()
    assert len(watches.store.evaluations(registration.registration_id)) == 1


def test_refresh_route_is_bodyless_same_origin_and_foreign_origin_writes_nothing(tmp_path) -> None:
    """Catch an accidental request body or an origin guard placed after check()."""
    app, _packet, watches, registration = _session_app(tmp_path)
    operation = app.openapi()["paths"]["/api/decision-session/refresh"]["post"]
    assert "requestBody" not in operation

    with TestClient(app) as client:
        refused = client.post(
            "/api/decision-session/refresh",
            headers={"Origin": "https://foreign.example"},
        )
        assert refused.status_code == 403
        assert watches.store.evaluations(registration.registration_id) == ()

        response = client.post(
            "/api/decision-session/refresh",
            headers={"Origin": "http://testserver"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "complete"
    assert (
        payload["items"][0]["evaluation_id"]
        == watches.store.evaluations(registration.registration_id)[-1].evaluation_id
    )


def test_refresh_route_resolves_replaced_current_app_state_services(tmp_path) -> None:
    """Catch construction-time capture of packet/watch/workspace objects after a reset swap."""
    app, original_packet, original_watches, original_registration = _session_app(tmp_path / "first")
    replacement_root = tmp_path / "replacement"
    replacement_packets = DecisionPacketStore(replacement_root / "packets")
    replacement_packet = _record_action_packet(replacement_packets, symbol="AAPL")
    replacement_watches = DecisionWatchService(
        packet_store=replacement_packets,
        store=DecisionWatchStore(replacement_root / "monitoring"),
    )
    replacement_registration = replacement_watches.register(
        replacement_packet.packet_id,
        (WatchConditionKind.ENTRY_ZONE,),
    )
    app.state.decision_packets = replacement_packets
    app.state.packet_monitoring = replacement_watches
    app.state.instrument_workspace = _DurableRenderer(at=NOW, sequence=1)
    app.state.decision_inbox = _RealInbox((_entry(replacement_packet),))

    with TestClient(app) as client:
        response = client.post("/api/decision-session/refresh")

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["packet_id"] == replacement_packet.packet_id
    assert (
        payload["items"][0]["evaluation_id"]
        == replacement_watches.store.evaluations(replacement_registration.registration_id)[
            -1
        ].evaluation_id
    )
    assert original_watches.store.evaluations(original_registration.registration_id) == ()
    assert original_packet.packet_id != replacement_packet.packet_id


def test_refresh_route_sanitizes_real_corrupt_evaluation_ledger_without_appending(tmp_path) -> None:
    """Catch raw ledger disclosure or a corrupt replay path that appends before its 409."""
    app = create_workstation_app(
        account=PaperAccount(cash=100_000.0),
        workspace_clock=lambda: NOW,
        host="127.0.0.1",
    )
    root = tmp_path / "monitoring"
    root.mkdir()
    injected = "{injected-secret-evaluation-bytes}\n"
    evaluation_path = root / "watch-evaluations.jsonl"
    evaluation_path.write_text(injected, encoding="utf-8")
    app.state.decision_packets = DecisionPacketStore(tmp_path / "packets")
    app.state.packet_monitoring = DecisionWatchService(
        packet_store=app.state.decision_packets,
        store=DecisionWatchStore(root),
    )
    app.state.instrument_workspace = _DurableRenderer(at=NOW, sequence=1)
    app.state.decision_inbox = _RealInbox(())

    with TestClient(app) as client:
        response = client.post("/api/decision-session/refresh")

    assert response.status_code == 409
    assert response.json()["detail"] == "decision session refresh is unavailable"
    assert "injected-secret-evaluation-bytes" not in response.text
    assert evaluation_path.read_text(encoding="utf-8") == injected


def test_refresh_route_is_404_when_the_session_service_is_unattached() -> None:
    """Catch a route that silently constructs a command service for an unattached app."""
    app = create_workstation_app(account=PaperAccount(cash=100_000.0), host="127.0.0.1")
    app.state.decision_session = None

    with TestClient(app) as client:
        response = client.post("/api/decision-session/refresh")

    assert response.status_code == 404
    assert response.json()["detail"] == "no decision session service is attached"


def test_refresh_after_demo_reset_reads_the_replaced_monitoring_store(tmp_path) -> None:
    """Catch reset wiring that leaves the long-lived refresh command on old durable state."""
    app = create_demo_app(
        root=tmp_path / "demo",
        seed=20260908,
        workspace_history=False,
        host="127.0.0.1",
    )
    previous_store = app.state.packet_monitoring.store

    with TestClient(app) as client:
        reset = client.post("/api/demo/reset")
        refreshed = client.post("/api/decision-session/refresh")

    assert reset.status_code == 200
    assert app.state.packet_monitoring.store is app.state.packet_monitoring_store
    assert app.state.packet_monitoring.store is not previous_store
    assert refreshed.status_code == 200
    assert refreshed.json()["status"] == "no_registered_watches"


@pytest.mark.parametrize(
    "forbidden", ["provider", "scheduler", "proposal", "confirmation", "order"]
)
def test_session_constructor_has_no_operational_or_order_collaborators(forbidden: str) -> None:
    assert forbidden not in DecisionSessionService.__init__.__annotations__
