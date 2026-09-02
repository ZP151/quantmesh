from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.execution.accounting import PaperAccount, RiskLimits
from quantmesh.instruments.contracts import (
    CoverageSnapshot,
    DecisionBlocker,
    DecisionCostEvidence,
    DecisionDisposition,
    DecisionEvidence,
    DecisionMarketState,
    DecisionPacket,
    DecisionPaperCapability,
    DecisionRiskPlan,
    DecisionScenario,
    DecisionWorkspaceState,
    ForecastMetrics,
    ForecastPath,
    ForecastPoint,
    HistoricalBar,
    HistoricalSeries,
    HistoryRange,
    InstrumentWorkspace,
    ProposalCapability,
    WorkspaceForecast,
    WorkspaceLiveEvidence,
    WorkspaceRisk,
)
from quantmesh.instruments.decision_analysis import compose_decision_packet
from quantmesh.instruments.decision_packets import DecisionPacketStore, decision_packet_id

NOW = datetime(2026, 9, 2, 20, 0, tzinfo=UTC)
LATER = NOW + timedelta(days=1)
NVDA = Instrument(
    venue=Venue.MOOMOO,
    symbol="NVDA",
    instrument_type=InstrumentType.EQUITY,
    currency="USD",
)


def packet(*, created_at: datetime = NOW, as_of: datetime = NOW) -> DecisionPacket:
    provisional = DecisionPacket(
        packet_id="packet-" + "0" * 24,
        version=1,
        parent_packet_id=None,
        instrument=NVDA,
        selected_range=HistoryRange.SIX_MONTHS,
        as_of=as_of,
        created_at=created_at,
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
                thesis="trend holds",
                trigger="closes above resistance",
                invalidation=94.0,
                target=110.0,
                confidence_reason="forecast quantiles are not calibrated probabilities",
            ),
            DecisionScenario(
                kind="base",
                thesis="trend persists",
                trigger="holds above support",
                invalidation=94.0,
                target=105.0,
                confidence_reason="forecast quantiles are not calibrated probabilities",
            ),
            DecisionScenario(
                kind="bear",
                thesis="support fails",
                trigger="closes below support",
                invalidation=94.0,
                target=90.0,
                confidence_reason="forecast quantiles are not calibrated probabilities",
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


def test_packet_identity_ignores_only_created_at() -> None:
    first = packet(created_at=NOW)
    later = packet(created_at=NOW + timedelta(seconds=1))

    assert decision_packet_id(first) == decision_packet_id(later)
    assert decision_packet_id(first) != decision_packet_id(
        first.model_copy(update={"as_of": LATER})
    )


def watch_child(parent: DecisionPacket) -> DecisionPacket:
    payload = parent.model_dump()
    payload.update(
        packet_id="packet-" + "0" * 24,
        version=2,
        parent_packet_id=parent.packet_id,
        disposition=DecisionDisposition.WATCH,
        operator_reason="Wait for a close above resistance.",
    )
    provisional = DecisionPacket.model_validate(payload)
    return provisional.model_copy(update={"packet_id": decision_packet_id(provisional)})


def test_packet_contract_rejects_scenario_order_and_action_mismatch() -> None:
    draft = packet()

    with pytest.raises(ValidationError, match="scenarios must be ordered bull, base, bear"):
        DecisionPacket.model_validate(
            draft.model_dump() | {"scenarios": draft.scenarios[::-1]}
        )
    with pytest.raises(ValidationError, match="requires an operator reason"):
        DecisionPacket.model_validate(
            draft.model_dump()
            | {
                "packet_id": "packet-" + "2" * 24,
                "version": 2,
                "parent_packet_id": draft.packet_id,
                "disposition": DecisionDisposition.WATCH,
            }
        )


def test_store_rejects_missing_parent_or_wrong_next_version(tmp_path: Path) -> None:
    store = DecisionPacketStore(tmp_path / "packets")

    provisional = packet().model_copy(
        update={"version": 2, "parent_packet_id": "packet-" + "1" * 24}
    )
    forged = provisional.model_copy(update={"packet_id": decision_packet_id(provisional)})
    with pytest.raises(ValueError, match="parent"):
        store.record(forged)


def test_store_reopens_exact_lineage_after_new_instance(tmp_path: Path) -> None:
    root = tmp_path / "packets"
    first = DecisionPacketStore(root).record(packet())
    child = DecisionPacketStore(root).record(watch_child(first))

    assert DecisionPacketStore(root).lineage(child.packet_id) == (first, child)


def test_store_refuses_identity_drift_and_sibling_transition(tmp_path: Path) -> None:
    store = DecisionPacketStore(tmp_path / "packets")
    first = store.record(packet())
    store.record(watch_child(first))

    forged = first.model_copy(update={"packet_id": "packet-" + "f" * 24})
    with pytest.raises(ValueError, match="identity"):
        store.record(forged)
    sibling = watch_child(first)
    sibling_payload = sibling.model_dump() | {"operator_reason": "Wait for an orderly pullback."}
    sibling_provisional = DecisionPacket.model_validate(
        sibling_payload | {"packet_id": "packet-" + "0" * 24}
    )
    sibling = sibling_provisional.model_copy(
        update={"packet_id": decision_packet_id(sibling_provisional)}
    )
    with pytest.raises(ValueError, match="child"):
        store.record(sibling)


def _history_for_composition() -> HistoricalSeries:
    timestamps = tuple(NOW - timedelta(days=59 - index) for index in range(60))
    bars = tuple(
        HistoricalBar(
            instrument=NVDA,
            timestamp=timestamp,
            interval="1d",
            open=100.0 + index,
            high=101.0 + index,
            low=99.0 + index,
            close=100.0 + index,
            volume=1_000.0 + index,
        )
        for index, timestamp in enumerate(timestamps)
    )
    return HistoricalSeries(
        instrument=NVDA,
        range=HistoryRange.SIX_MONTHS,
        as_of=NOW,
        bars=bars,
        dataset_id="nvda-demo",
        dataset_revision=1,
        source="demo-synthetic",
        license="fixture",
        generated_at=NOW,
        interval="1d",
        calendar="24/7",
        adjustment="unadjusted",
        coverage=CoverageSnapshot(
            interval="1d",
            venue=Venue.MOOMOO,
            symbol="NVDA",
            start=timestamps[0],
            end=timestamps[-1],
            rows=len(timestamps),
        ),
    )


def _workspace_forecast() -> WorkspaceForecast:
    points = tuple(
        ForecastPoint(
            session=index,
            timestamp=NOW + timedelta(days=index),
            p025=150.0 + index,
            p10=152.0 + index,
            p25=155.0 + index,
            p50=160.0 + index,
            p75=165.0 + index,
            p90=168.0 + index,
            p975=170.0 + index,
        )
        for index in range(1, 31)
    )
    return WorkspaceForecast(
        artifact_id="forecast-" + "a" * 24,
        generated_at=NOW,
        target="unadjusted-close",
        train_start=NOW - timedelta(days=59),
        train_end=NOW,
        model_name="median-log-drift-conformal",
        model_version="fixture-v1",
        config_digest="a" * 64,
        dataset_id="nvda-demo",
        dataset_revision=1,
        history_digest="b" * 64,
        benchmark_name="last-price-random-walk",
        synthetic=True,
        eligible=True,
        blockers=(),
        limitations=(),
        paths=(ForecastPath(sessions=30, points=points),),
        metrics=(
            ForecastMetrics(
                sessions=30,
                residual_count=0,
                interval_test_count=0,
                mae=1.0,
                rmse=2.0,
                benchmark_mae=3.0,
                coverage_50=0.5,
                coverage_80=0.8,
                coverage_95=0.95,
            ),
        ),
    )


def test_composer_uses_observed_history_and_qualitative_30_session_quantiles() -> None:
    history = _history_for_composition()
    account = PaperAccount(
        cash=10_000.0,
        risk_limits=RiskLimits(
            max_order_quantity=5.0,
            max_notional=1_000.0,
            max_position_quantity=5.0,
        ),
    )
    packet_value = compose_decision_packet(
        history=history,
        forecast=_workspace_forecast(),
        live=WorkspaceLiveEvidence(status="unavailable", reason="fixture"),
        risk=WorkspaceRisk(
            cash=10_000.0,
            equity=10_000.0,
            starting_cash=10_000.0,
            max_order_quantity=5.0,
            max_notional=1_000.0,
            max_position_quantity=5.0,
            global_kill_switch=False,
            venue_kill_switch=False,
            mark_available=True,
            valuation_complete=True,
        ),
        proposal=ProposalCapability(allowed=True, blockers=(), proposals=()),
        account=account,
        selected_range=HistoryRange.SIX_MONTHS,
        as_of=NOW,
    )

    assert packet_value.packet_id == decision_packet_id(packet_value)
    assert [scenario.kind for scenario in packet_value.scenarios] == ["bull", "base", "bear"]
    assert [scenario.target for scenario in packet_value.scenarios] == [195.0, 190.0, 185.0]
    assert all(scenario.probability is None for scenario in packet_value.scenarios)
    assert packet_value.evidence.forecast_metrics[0].coverage_80 == 0.8
    assert packet_value.evidence.costs.fee_bps == account.fee_model.fee_bps
    assert packet_value.evidence.costs.slippage_bps == account.matcher.slippage_bps
    assert packet_value.evidence.costs.half_spread_bps is None
    assert packet_value.risk_plan.suggested_quantity == 5.0


def test_packet_boundary_is_available_from_instruments_package() -> None:
    from quantmesh.instruments import DecisionPacketStore as ExportedStore
    from quantmesh.instruments import compose_decision_packet as exported_composer

    assert ExportedStore is DecisionPacketStore
    assert exported_composer is compose_decision_packet


def test_paper_proposal_child_requires_allowed_unblocked_capability() -> None:
    parent = packet()
    blocked = DecisionPaperCapability(
        allowed=False,
        blockers=(
            DecisionBlocker(
                code="valuation", message="valuation is incomplete", evidence_ref="risk:valuation"
            ),
        ),
    )
    payload = parent.model_dump() | {
        "packet_id": "packet-" + "d" * 24,
        "version": 2,
        "parent_packet_id": parent.packet_id,
        "paper_capability": blocked,
        "disposition": DecisionDisposition.PAPER_PROPOSAL,
        "proposal_id": "proposal-" + "a" * 24,
    }

    with pytest.raises(ValidationError, match="allowed unblocked paper capability"):
        DecisionPacket.model_validate(payload)


def test_composer_preserves_exact_real_forecast_evidence_and_role_chronology() -> None:
    history = _history_for_composition().model_copy(
        update={
            "source": "trusted-provider",
            "manifest_id": "1" * 64,
            "quality_evaluation_id": "2" * 64,
        }
    )
    forecast = _workspace_forecast().model_copy(
        update={
            "dataset_revision": 7,
            "manifest_id": "3" * 64,
            "quality_evaluation_id": "4" * 64,
            "synthetic": False,
            "limitations": ("fixture limitation",),
        }
    )
    composed = compose_decision_packet(
        history=history,
        forecast=forecast,
        live=WorkspaceLiveEvidence(status="unavailable", reason="fixture"),
        risk=_ready_risk(),
        proposal=ProposalCapability(allowed=True, blockers=(), proposals=()),
        account=PaperAccount(cash=10_000.0),
        selected_range=HistoryRange.SIX_MONTHS,
        as_of=NOW,
    )

    assert composed.evidence.forecast_dataset_revision == 7
    assert composed.evidence.forecast_manifest_id == "3" * 64
    assert composed.evidence.forecast_quality_evaluation_id == "4" * 64
    assert composed.evidence.forecast_synthetic is False
    assert composed.evidence.forecast_limitations == ("fixture limitation",)
    assert composed.evidence.forecast_chronology.train_end == NOW
    assert composed.evidence.forecast_chronology.test_end is None


def test_composer_blocks_future_source_times_and_deduplicates_valuation() -> None:
    history = _history_for_composition().model_copy(
        update={"generated_at": NOW + timedelta(seconds=1)}
    )
    forecast = _workspace_forecast().model_copy(
        update={"generated_at": NOW + timedelta(seconds=1)}
    )
    composed = compose_decision_packet(
        history=history,
        forecast=forecast,
        live=WorkspaceLiveEvidence(status="unavailable", reason="fixture"),
        risk=WorkspaceRisk(
            cash=0.0,
            equity=None,
            starting_cash=0.0,
            max_order_quantity=None,
            max_notional=None,
            max_position_quantity=None,
            global_kill_switch=False,
            venue_kill_switch=False,
            mark_available=False,
            valuation_complete=False,
            valuation_reason="mark is absent",
        ),
        proposal=ProposalCapability(allowed=True, blockers=(), proposals=()),
        account=PaperAccount(cash=0.0),
        selected_range=HistoryRange.SIX_MONTHS,
        as_of=NOW,
    )

    assert composed.paper_capability.allowed is False
    assert [item.code for item in composed.paper_capability.blockers] == [
        "history-freshness",
        "chronology",
        "valuation",
    ]


def _ready_risk() -> WorkspaceRisk:
    return WorkspaceRisk(
        cash=10_000.0,
        equity=10_000.0,
        starting_cash=10_000.0,
        max_order_quantity=None,
        max_notional=None,
        max_position_quantity=None,
        global_kill_switch=False,
        venue_kill_switch=False,
        mark_available=True,
        valuation_complete=True,
    )


def test_store_rejects_changed_analysis_on_child_and_duplicate_root_scope(tmp_path: Path) -> None:
    store = DecisionPacketStore(tmp_path / "packets")
    first = store.record(packet())
    child = watch_child(first)
    changed = child.model_copy(
        update={"market_state": child.market_state.model_copy(update={"support": 93.0})}
    )
    changed = changed.model_copy(update={"packet_id": decision_packet_id(changed)})
    with pytest.raises(ValueError, match="semantic facts"):
        store.record(changed)

    root = packet().model_copy(
        update={"market_state": first.market_state.model_copy(update={"support": 93.0})}
    )
    root = root.model_copy(update={"packet_id": decision_packet_id(root)})
    with pytest.raises(ValueError, match="root"):
        store.record(root)


def test_store_serializes_concurrent_roots_without_lost_updates(tmp_path: Path) -> None:
    root = tmp_path / "packets"
    packets = tuple(
        packet(as_of=NOW + timedelta(seconds=index)) for index in range(8)
    )

    with ThreadPoolExecutor(max_workers=len(packets)) as executor:
        recorded = tuple(executor.map(lambda item: DecisionPacketStore(root).record(item), packets))

    reopened = DecisionPacketStore(root)
    assert {item.packet_id for item in recorded} == {
        reopened.get(item.packet_id).packet_id for item in packets
    }


def test_workspace_latest_packet_must_match_history_as_of() -> None:
    history = _history_for_composition()
    latest = packet(as_of=NOW + timedelta(seconds=1))
    with pytest.raises(ValidationError, match="latest decision as_of"):
        InstrumentWorkspace(
            generated_at=NOW,
            instrument=NVDA,
            history=history,
            live=WorkspaceLiveEvidence(status="unavailable", reason="fixture"),
            forecast=None,
            forecast_unavailable_reason="fixture",
            risk=_ready_risk(),
            proposal=ProposalCapability(allowed=True, blockers=(), proposals=()),
            decision=DecisionWorkspaceState(draft=packet(), latest=latest),
        )
