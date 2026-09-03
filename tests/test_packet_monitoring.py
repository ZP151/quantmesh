from __future__ import annotations

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


def test_entry_zone_arms_then_triggers_only_on_outside_to_inside_crossing(tmp_path: Path) -> None:
    packets = DecisionPacketStore(tmp_path / "packets")
    packet = packets.record(_packet())
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


def test_invalidation_requires_equality_or_above_then_strictly_below_and_preserves_event(
    tmp_path: Path,
) -> None:
    packets = DecisionPacketStore(tmp_path / "packets")
    packet = packets.record(_packet())
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
    packet = packets.record(_packet())
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
    packet = packets.record(_packet())
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


def test_initial_or_continued_in_band_price_never_backfills_entry_trigger(tmp_path: Path) -> None:
    packets = DecisionPacketStore(tmp_path / "packets")
    packet = packets.record(_packet())
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
    packet = packets.record(_packet())
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


def test_registration_conflict_and_corrupt_replay_fail_closed(tmp_path: Path) -> None:
    root = tmp_path / "monitoring"
    packets = DecisionPacketStore(tmp_path / "packets")
    packet = packets.record(_packet())
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
    packet = packets.record(_packet_with_history_generated_at(reference))
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
    target = NOW + timedelta(days=30)
    point = SimpleNamespace(timestamp=target, p50=p50)
    return SimpleNamespace(
        id=artifact_id,
        instrument=packet.instrument,
        generated_at=generated_at,
        model_name="median-log-drift-conformal",
        model_version="1",
        config_digest="a" * 64,
        target="unadjusted-close",
        paths=(SimpleNamespace(sessions=30, points=(point,)),),
    )


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
    packet = packets.record(packet)
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
    packet = packets.record(packet)
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
