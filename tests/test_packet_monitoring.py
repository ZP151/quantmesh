from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.instruments.contracts import (
    DecisionCostEvidence,
    DecisionDisposition,
    DecisionEvidence,
    DecisionMarketState,
    DecisionPacket,
    DecisionPaperCapability,
    DecisionRiskPlan,
    DecisionScenario,
    ForecastPath,
    ForecastPoint,
    HistoryRange,
)
from quantmesh.instruments.decision_packets import DecisionPacketStore, decision_packet_id
from quantmesh.instruments.monitoring import (
    DecisionWatchObservation,
    DecisionWatchService,
    DecisionWatchStore,
    WatchConditionKind,
)

NOW = datetime(2026, 9, 2, 20, 0, tzinfo=UTC)
NVDA = Instrument(
    venue=Venue.MOOMOO, symbol="NVDA", instrument_type=InstrumentType.EQUITY, currency="USD"
)


def _packet() -> DecisionPacket:
    provisional = DecisionPacket(
        packet_id="packet-" + "0" * 24,
        version=1,
        parent_packet_id=None,
        instrument=NVDA,
        selected_range=HistoryRange.SIX_MONTHS,
        as_of=NOW,
        created_at=NOW,
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
            key_level_bar_times=(NOW - timedelta(days=1), NOW),
        ),
        scenarios=(
            DecisionScenario(
                kind="bull",
                thesis="holds",
                trigger="above",
                invalidation=94.0,
                target=110.0,
                confidence_reason="qualitative",
            ),
            DecisionScenario(
                kind="base",
                thesis="holds",
                trigger="above",
                invalidation=94.0,
                target=105.0,
                confidence_reason="qualitative",
            ),
            DecisionScenario(
                kind="bear",
                thesis="fails",
                trigger="below",
                invalidation=94.0,
                target=90.0,
                confidence_reason="qualitative",
            ),
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
            history_dataset_id="nvda-demo",
            history_dataset_revision=1,
            history_manifest_id=None,
            history_quality_evaluation_id=None,
            history_source="demo-synthetic",
            history_generated_at=NOW,
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


def _record_action_packet(
    store: DecisionPacketStore, draft: DecisionPacket | None = None
) -> DecisionPacket:
    parent = store.record(draft or _packet())
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


def test_entry_zone_arms_then_triggers_only_on_outside_to_inside_crossing(tmp_path: Path) -> None:
    packets = DecisionPacketStore(tmp_path / "packets")
    packet = _record_action_packet(packets)
    service = DecisionWatchService(
        packet_store=packets, store=DecisionWatchStore(tmp_path / "monitoring")
    )
    registration = service.register(packet.packet_id, (WatchConditionKind.ENTRY_ZONE,))

    armed = service.check(
        registration.registration_id,
        DecisionWatchObservation(
            evaluated_at=NOW + timedelta(minutes=2),
            price=101.0,
            instrument=NVDA,
            source="local-workspace",
            provenance="demo-synthetic",
            data_time=NOW + timedelta(minutes=1),
            received_at=NOW + timedelta(minutes=2),
            sequence=1,
            sequence_gap=False,
        ),
    )
    triggered = service.check(
        registration.registration_id,
        DecisionWatchObservation(
            evaluated_at=NOW + timedelta(minutes=4),
            price=99.0,
            instrument=NVDA,
            source="local-workspace",
            provenance="demo-synthetic",
            data_time=NOW + timedelta(minutes=3),
            received_at=NOW + timedelta(minutes=4),
            sequence=2,
            sequence_gap=False,
        ),
    )

    assert armed.results[0].state == "armed"
    assert triggered.results[0].state == "triggered"
    assert triggered.results[0].event_id is not None


def _price_observation(*, price: float, sequence: int, minutes: int) -> DecisionWatchObservation:
    return DecisionWatchObservation(
        evaluated_at=NOW + timedelta(minutes=minutes + 1),
        price=price,
        instrument=NVDA,
        source="local-workspace",
        provenance="demo-synthetic",
        data_time=NOW + timedelta(minutes=minutes),
        received_at=NOW + timedelta(minutes=minutes + 1),
        sequence=sequence,
        sequence_gap=False,
    )


def test_registration_refuses_a_draft_packet(tmp_path: Path) -> None:
    packets = DecisionPacketStore(tmp_path / "packets")
    packet = packets.record(_packet())
    store = DecisionWatchStore(tmp_path / "monitoring")
    service = DecisionWatchService(packet_store=packets, store=store)

    with pytest.raises(ValueError, match="action packet"):
        service.register(packet.packet_id, (WatchConditionKind.ENTRY_ZONE,))

    assert store.registrations() == ()


def test_invalidation_requires_equality_or_above_then_strictly_below_and_preserves_event(
    tmp_path: Path,
) -> None:
    packets = DecisionPacketStore(tmp_path / "packets")
    packet = _record_action_packet(packets)
    service = DecisionWatchService(
        packet_store=packets,
        store=DecisionWatchStore(tmp_path / "monitoring"),
    )
    registration = service.register(packet.packet_id, (WatchConditionKind.INVALIDATION,))

    armed = service.check(
        registration.registration_id, _price_observation(price=94.0, sequence=1, minutes=1)
    )
    equality = service.check(
        registration.registration_id, _price_observation(price=94.0, sequence=2, minutes=3)
    )
    crossed = service.check(
        registration.registration_id, _price_observation(price=93.0, sequence=3, minutes=5)
    )
    later = service.check(
        registration.registration_id, _price_observation(price=92.0, sequence=4, minutes=7)
    )

    assert armed.results[0].state == "armed"
    assert equality.results[0].state == "not_triggered"
    assert crossed.results[0].state == "triggered"
    assert later.results[0] == crossed.results[0]


def test_cursor_refuses_gap_and_stale_uses_completed_xnys_sessions(tmp_path: Path) -> None:
    packets = DecisionPacketStore(tmp_path / "packets")
    packet = _record_action_packet(packets)
    service = DecisionWatchService(
        packet_store=packets,
        store=DecisionWatchStore(tmp_path / "monitoring"),
    )
    registration = service.register(
        packet.packet_id,
        (WatchConditionKind.ENTRY_ZONE, WatchConditionKind.DATA_STALE),
    )
    service.check(
        registration.registration_id, _price_observation(price=101.0, sequence=1, minutes=1)
    )
    with pytest.raises(ValueError, match="continuously advance"):
        service.check(
            registration.registration_id, _price_observation(price=99.0, sequence=3, minutes=3)
        )

    stale = service.check(
        registration.registration_id,
        DecisionWatchObservation(evaluated_at=datetime(2026, 9, 4, 21, 0, tzinfo=UTC)),
    )
    stale_result = stale.results[1]
    assert stale_result.state == "triggered"
    assert stale_result.facts.completed_sessions == 2


def test_reopens_exact_registration_and_byte_identical_observation_replays(tmp_path: Path) -> None:
    root = tmp_path / "monitoring"
    packets = DecisionPacketStore(tmp_path / "packets")
    packet = _record_action_packet(packets)
    first = DecisionWatchService(packet_store=packets, store=DecisionWatchStore(root))
    registration = first.register(packet.packet_id, (WatchConditionKind.ENTRY_ZONE,))
    observation = _price_observation(price=101.0, sequence=1, minutes=1)
    evaluation = first.check(registration.registration_id, observation)

    restarted = DecisionWatchService(
        packet_store=DecisionPacketStore(tmp_path / "packets"), store=DecisionWatchStore(root)
    )
    replay = restarted.check(registration.registration_id, observation)

    assert restarted.register(packet.packet_id, (WatchConditionKind.ENTRY_ZONE,)) == registration
    assert replay == evaluation


def test_register_and_check_is_one_durable_activation_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    packets = DecisionPacketStore(tmp_path / "packets")
    packet = _record_action_packet(packets)
    root = tmp_path / "monitoring"
    store = DecisionWatchStore(root)
    service = DecisionWatchService(packet_store=packets, store=store)

    def fail_append(_value) -> None:
        raise OSError("injected activation append failure")

    monkeypatch.setattr(store._activations, "append", fail_append)
    with pytest.raises(OSError, match="injected activation append failure"):
        service.register_and_check(
            packet.packet_id,
            (WatchConditionKind.ENTRY_ZONE,),
            _price_observation(price=101.0, sequence=1, minutes=1),
        )

    restarted = DecisionWatchStore(root)
    assert restarted.registration_for_packet(packet.packet_id) is None
    assert not (root / "watch-registrations.jsonl").exists()
    assert not (root / "watch-evaluations.jsonl").exists()


def test_replay_recomputes_terminal_event_identity(tmp_path: Path) -> None:
    packets = DecisionPacketStore(tmp_path / "packets")
    packet = _record_action_packet(packets)
    root = tmp_path / "monitoring"
    service = DecisionWatchService(packet_store=packets, store=DecisionWatchStore(root))
    registration = service.register(packet.packet_id, (WatchConditionKind.ENTRY_ZONE,))
    service.check(
        registration.registration_id, _price_observation(price=101.0, sequence=1, minutes=1)
    )
    service.check(
        registration.registration_id, _price_observation(price=99.0, sequence=2, minutes=3)
    )

    path = root / "watch-evaluations.jsonl"
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    records[1]["results"][0]["event_id"] = "watch-event-" + "f" * 24
    identity_payload = {
        "registration_id": records[1]["registration_id"],
        "observation": records[1]["observation"],
        "results": records[1]["results"],
    }
    digest = hashlib.sha256(
        json.dumps(identity_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:24]
    records[1]["evaluation_id"] = f"evaluation-{digest}"
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="event identity"):
        DecisionWatchService(packet_store=packets, store=DecisionWatchStore(root)).state(
            packet.packet_id
        )


def test_initial_or_continued_in_band_price_never_backfills_entry_trigger(tmp_path: Path) -> None:
    packets = DecisionPacketStore(tmp_path / "packets")
    packet = _record_action_packet(packets)
    service = DecisionWatchService(
        packet_store=packets,
        store=DecisionWatchStore(tmp_path / "monitoring"),
    )
    registration = service.register(packet.packet_id, (WatchConditionKind.ENTRY_ZONE,))

    initial = service.check(
        registration.registration_id,
        _price_observation(price=99.0, sequence=1, minutes=1),
    )
    continued = service.check(
        registration.registration_id,
        _price_observation(price=98.0, sequence=2, minutes=3),
    )

    assert initial.results[0].state == "armed"
    assert continued.results[0].state == "not_triggered"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.model_copy(
            update={"data_time": NOW, "received_at": NOW + timedelta(minutes=2)}
        ),
        lambda value: value.model_copy(
            update={
                "data_time": NOW + timedelta(minutes=3),
                "received_at": NOW + timedelta(minutes=2),
            }
        ),
        lambda value: value.model_copy(update={"sequence_gap": True}),
        lambda value: value.model_copy(
            update={
                "received_at": NOW + timedelta(minutes=9),
                "evaluated_at": NOW + timedelta(minutes=4),
            }
        ),
    ],
)
def test_price_causality_fail_closed_for_pre_asof_future_or_gapped_evidence(
    tmp_path: Path,
    mutate,
) -> None:
    packets = DecisionPacketStore(tmp_path / "packets")
    packet = _record_action_packet(packets)
    service = DecisionWatchService(
        packet_store=packets,
        store=DecisionWatchStore(tmp_path / "monitoring"),
    )
    registration = service.register(packet.packet_id, (WatchConditionKind.ENTRY_ZONE,))
    result = service.check(
        registration.registration_id,
        mutate(_price_observation(price=101.0, sequence=1, minutes=1)),
    )

    assert result.results[0].state == "not_comparable"
    assert result.results[0].facts.code == "unusable_price_evidence"


def test_rejected_price_evidence_never_becomes_the_durable_crossing_cursor(tmp_path: Path) -> None:
    packets = DecisionPacketStore(tmp_path / "packets")
    packet = _record_action_packet(packets)
    service = DecisionWatchService(
        packet_store=packets, store=DecisionWatchStore(tmp_path / "monitoring")
    )
    registration = service.register(packet.packet_id, (WatchConditionKind.ENTRY_ZONE,))

    rejected = service.check(
        registration.registration_id,
        _price_observation(price=101.0, sequence=1, minutes=1).model_copy(
            update={"sequence_gap": True}
        ),
    )
    accepted = service.check(
        registration.registration_id, _price_observation(price=101.0, sequence=1, minutes=3)
    )

    assert rejected.results[0].state == "not_comparable"
    assert accepted.results[0].state == "armed"


def test_registration_conflict_and_corrupt_replay_fail_closed(tmp_path: Path) -> None:
    root = tmp_path / "monitoring"
    packets = DecisionPacketStore(tmp_path / "packets")
    packet = _record_action_packet(packets)
    store = DecisionWatchStore(root)
    service = DecisionWatchService(packet_store=packets, store=store)
    service.register(packet.packet_id, (WatchConditionKind.ENTRY_ZONE,))

    with pytest.raises(ValueError, match="different watch conditions"):
        service.register(packet.packet_id, (WatchConditionKind.INVALIDATION,))

    (root / "watch-registrations.jsonl").write_text("{not-json}\n", encoding="utf-8")
    with pytest.raises(ValueError):
        DecisionWatchStore(root).registrations()


def _packet_with_history_generated_at(value: datetime) -> DecisionPacket:
    original = _packet()
    provisional = original.model_copy(
        update={
            "packet_id": "packet-" + "0" * 24,
            "evidence": original.evidence.model_copy(update={"history_generated_at": value}),
        }
    )
    return provisional.model_copy(update={"packet_id": decision_packet_id(provisional)})


def test_stale_uses_xnys_holiday_and_early_close_boundaries(tmp_path: Path) -> None:
    reference = datetime(2026, 11, 25, 21, 0, tzinfo=UTC)
    packets = DecisionPacketStore(tmp_path / "packets")
    packet = _record_action_packet(packets, _packet_with_history_generated_at(reference))
    service = DecisionWatchService(
        packet_store=packets,
        store=DecisionWatchStore(tmp_path / "monitoring"),
    )
    registration = service.register(packet.packet_id, (WatchConditionKind.DATA_STALE,))

    early_close = service.check(
        registration.registration_id,
        DecisionWatchObservation(evaluated_at=datetime(2026, 11, 27, 19, 0, tzinfo=UTC)),
    )
    monday_close = service.check(
        registration.registration_id,
        DecisionWatchObservation(evaluated_at=datetime(2026, 11, 30, 22, 0, tzinfo=UTC)),
    )

    assert early_close.results[0].facts.completed_sessions == 1
    assert early_close.results[0].state == "not_triggered"
    assert monday_close.results[0].facts.completed_sessions == 2
    assert monday_close.results[0].state == "triggered"


def test_stale_freezes_the_oldest_history_or_forecast_evidence_time(tmp_path: Path) -> None:
    history = NOW + timedelta(days=2)
    original = _forecast_packet()
    evidence = original.evidence.model_copy(update={"history_generated_at": history})
    provisional = original.model_copy(
        update={"packet_id": "packet-" + "0" * 24, "evidence": evidence}
    )
    packet = provisional.model_copy(update={"packet_id": decision_packet_id(provisional)})
    packets = DecisionPacketStore(tmp_path / "packets")
    packet = _record_action_packet(packets, packet)
    service = DecisionWatchService(
        packet_store=packets, store=DecisionWatchStore(tmp_path / "monitoring")
    )

    registration = service.register(packet.packet_id, (WatchConditionKind.DATA_STALE,))
    definition = registration.conditions[0].definition

    assert definition.reference_at == NOW + timedelta(minutes=1)
    assert definition.history_generated_at == history
    assert definition.forecast_generated_at == NOW + timedelta(minutes=1)


def test_stale_24_7_counts_completed_utc_sessions(tmp_path: Path) -> None:
    original = _packet_with_history_generated_at(NOW)
    instrument = NVDA.model_copy(update={"metadata": {"calendar": "24/7"}})
    provisional = original.model_copy(
        update={"packet_id": "packet-" + "0" * 24, "instrument": instrument}
    )
    packet = provisional.model_copy(update={"packet_id": decision_packet_id(provisional)})
    packets = DecisionPacketStore(tmp_path / "packets")
    packet = _record_action_packet(packets, packet)
    service = DecisionWatchService(
        packet_store=packets, store=DecisionWatchStore(tmp_path / "monitoring")
    )
    registration = service.register(packet.packet_id, (WatchConditionKind.DATA_STALE,))

    evaluation = service.check(
        registration.registration_id,
        DecisionWatchObservation(evaluated_at=NOW + timedelta(days=2, minutes=1)),
    )

    assert evaluation.results[0].facts.completed_sessions == 2
    assert evaluation.results[0].state == "triggered"


def test_replay_refuses_evaluation_with_missing_or_reordered_condition_results(
    tmp_path: Path,
) -> None:
    packets = DecisionPacketStore(tmp_path / "packets")
    packet = _record_action_packet(packets)
    root = tmp_path / "monitoring"
    service = DecisionWatchService(packet_store=packets, store=DecisionWatchStore(root))
    registration = service.register(
        packet.packet_id, (WatchConditionKind.ENTRY_ZONE, WatchConditionKind.INVALIDATION)
    )
    service.check(
        registration.registration_id, _price_observation(price=101.0, sequence=1, minutes=1)
    )
    payload = json.loads((root / "watch-evaluations.jsonl").read_text(encoding="utf-8"))
    payload["results"] = payload["results"][:1]
    (root / "watch-evaluations.jsonl").write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid"):
        DecisionWatchService(packet_store=packets, store=DecisionWatchStore(root)).state(
            packet.packet_id
        )


def _forecast_path(p50: float) -> ForecastPath:
    return ForecastPath(
        sessions=30,
        points=tuple(
            ForecastPoint(
                session=session,
                timestamp=NOW + timedelta(days=session),
                p025=p50 - 3.0,
                p10=p50 - 2.0,
                p25=p50 - 1.0,
                p50=p50,
                p75=p50 + 1.0,
                p90=p50 + 2.0,
                p975=p50 + 3.0,
            )
            for session in range(1, 31)
        ),
    )


def _forecast_packet() -> DecisionPacket:
    original = _packet()
    evidence = original.evidence.model_copy(
        update={
            "forecast_artifact_id": "forecast-" + "a" * 24,
            "forecast_dataset_id": "nvda-demo",
            "forecast_dataset_revision": 1,
            "forecast_synthetic": True,
            "forecast_eligible": True,
            "forecast_model_name": "median-log-drift-conformal",
            "forecast_model_version": "1",
            "forecast_config_digest": "a" * 64,
            "forecast_history_digest": "b" * 64,
            "forecast_benchmark_name": "last-price-random-walk",
            "forecast_generated_at": NOW + timedelta(minutes=1),
            "forecast_paths": (_forecast_path(100.0),),
        }
    )
    provisional = original.model_copy(
        update={"packet_id": "packet-" + "0" * 24, "evidence": evidence}
    )
    return provisional.model_copy(update={"packet_id": decision_packet_id(provisional)})


class _ForecastRegistry:
    def __init__(self, *artifacts) -> None:
        self._artifacts = {artifact.id: artifact for artifact in artifacts}

    def get(self, artifact_id: str):
        return self._artifacts[artifact_id]


def _forecast_artifact(
    packet: DecisionPacket, *, artifact_id: str, generated_at: datetime, p50: float
):
    return SimpleNamespace(
        calendar="XNYS",
        dataset_id="nvda-demo",
        dataset_revision=1,
        id=artifact_id,
        instrument=packet.instrument,
        generated_at=generated_at,
        model_name="median-log-drift-conformal",
        model_version="1",
        config_digest="a" * 64,
        target="unadjusted-close",
        paths=(_forecast_path(p50),),
    )


def test_forecast_drift_baseline_is_frozen_from_packet_not_mutable_registry(
    tmp_path: Path,
) -> None:
    packet = _forecast_packet()
    substituted = _forecast_artifact(
        packet,
        artifact_id=packet.evidence.forecast_artifact_id,
        generated_at=packet.evidence.forecast_generated_at,
        p50=130.0,
    )
    packets = DecisionPacketStore(tmp_path / "packets")
    packet = _record_action_packet(packets, packet)
    service = DecisionWatchService(
        packet_store=packets,
        store=DecisionWatchStore(tmp_path / "monitoring"),
        forecast_registry=_ForecastRegistry(substituted),
    )

    registration = service.register(packet.packet_id, (WatchConditionKind.FORECAST_DRIFT,))
    definition = registration.conditions[0].definition

    assert definition.baseline_p50 == 100.0
    assert definition.target_at == NOW + timedelta(days=30)
    assert definition.target is None
    assert definition.calendar is None


@pytest.mark.parametrize(
    ("candidate_p50", "expected"),
    [(105.0, "not_triggered"), (106.0, "not_triggered"), (107.0, "triggered")],
)
def test_forecast_drift_uses_same_absolute_target_and_strict_risk_threshold(
    tmp_path: Path,
    candidate_p50: float,
    expected: str,
) -> None:
    packet = _forecast_packet()
    baseline = _forecast_artifact(
        packet,
        artifact_id=packet.evidence.forecast_artifact_id,
        generated_at=packet.evidence.forecast_generated_at,
        p50=100.0,
    )
    candidate = _forecast_artifact(
        packet,
        artifact_id="forecast-" + "c" * 24,
        generated_at=NOW + timedelta(minutes=2),
        p50=candidate_p50,
    )
    packets = DecisionPacketStore(tmp_path / "packets")
    packet = _record_action_packet(packets, packet)
    service = DecisionWatchService(
        packet_store=packets,
        store=DecisionWatchStore(tmp_path / "monitoring"),
        forecast_registry=_ForecastRegistry(baseline, candidate),
    )
    registration = service.register(packet.packet_id, (WatchConditionKind.FORECAST_DRIFT,))
    evaluation = service.check(
        registration.registration_id,
        DecisionWatchObservation(
            evaluated_at=NOW + timedelta(minutes=3),
            candidate_forecast_artifact_id=candidate.id,
        ),
    )

    assert evaluation.results[0].state == expected


def test_forecast_drift_compares_a_newer_revision_of_the_same_dataset(
    tmp_path: Path,
) -> None:
    packet = _forecast_packet()
    baseline = _forecast_artifact(
        packet,
        artifact_id=packet.evidence.forecast_artifact_id,
        generated_at=packet.evidence.forecast_generated_at,
        p50=100.0,
    )
    candidate = _forecast_artifact(
        packet,
        artifact_id="forecast-" + "c" * 24,
        generated_at=NOW + timedelta(minutes=2),
        p50=107.0,
    )
    candidate.dataset_revision = 2
    packets = DecisionPacketStore(tmp_path / "packets")
    packet = _record_action_packet(packets, packet)
    service = DecisionWatchService(
        packet_store=packets,
        store=DecisionWatchStore(tmp_path / "monitoring"),
        forecast_registry=_ForecastRegistry(baseline, candidate),
    )
    registration = service.register(packet.packet_id, (WatchConditionKind.FORECAST_DRIFT,))

    evaluation = service.check(
        registration.registration_id,
        DecisionWatchObservation(
            evaluated_at=NOW + timedelta(minutes=3),
            candidate_forecast_artifact_id=candidate.id,
        ),
    )

    assert evaluation.results[0].state == "triggered"


def test_forecast_drift_refuses_missing_or_incompatible_candidate(tmp_path: Path) -> None:
    packet = _forecast_packet()
    baseline = _forecast_artifact(
        packet,
        artifact_id=packet.evidence.forecast_artifact_id,
        generated_at=packet.evidence.forecast_generated_at,
        p50=100.0,
    )
    candidate = _forecast_artifact(
        packet,
        artifact_id="forecast-" + "c" * 24,
        generated_at=NOW + timedelta(minutes=2),
        p50=110.0,
    )
    candidate.config_digest = "d" * 64
    packets = DecisionPacketStore(tmp_path / "packets")
    packet = _record_action_packet(packets, packet)
    service = DecisionWatchService(
        packet_store=packets,
        store=DecisionWatchStore(tmp_path / "monitoring"),
        forecast_registry=_ForecastRegistry(baseline, candidate),
    )
    registration = service.register(packet.packet_id, (WatchConditionKind.FORECAST_DRIFT,))

    missing = service.check(
        registration.registration_id,
        DecisionWatchObservation(evaluated_at=NOW + timedelta(minutes=3)),
    )
    incompatible = service.check(
        registration.registration_id,
        DecisionWatchObservation(
            evaluated_at=NOW + timedelta(minutes=3),
            candidate_forecast_artifact_id=candidate.id,
        ),
    )

    assert missing.results[0].facts.code == "missing_forecast"
    assert incompatible.results[0].facts.code == "candidate_incompatible"
