"""Restart-safe acceptance for the local Decision Readiness Session."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from quantmesh.demo.manifest import DemoScenario
from quantmesh.demo.runtime import create_demo_app
from quantmesh.instruments.decision_packets import DecisionPacketStore
from quantmesh.instruments.monitoring import (
    DecisionWatchService,
    DecisionWatchStore,
    PriceFacts,
    StaleFacts,
    WatchConditionKind,
)
from quantmesh.instruments.readiness import DecisionReadinessService
from quantmesh.instruments.session import DecisionSessionService
from tests.test_decision_readiness import EVALUATION, MANIFEST, ExactCatalog, _lineage, _real_packet
from tests.test_decision_session import _DurableRenderer, _record_action_packet

SCENARIO = DemoScenario()


def _root_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.name.endswith(".lock")
    }


def _save_watch(
    client: TestClient,
    symbol: str,
    *,
    venue: str = "moomoo",
) -> dict[str, object]:
    workspace = client.get(f"/api/instruments/{venue}/{symbol}/workspace?range=6m")
    assert workspace.status_code == 200
    draft = workspace.json()["decision"]["draft"]
    saved = client.post(
        "/api/decision-packets",
        json={
            "venue": venue,
            "symbol": symbol,
            "selected_range": "6m",
            "expected_packet_id": draft["packet_id"],
        },
    )
    assert saved.status_code == 200
    action = client.post(
        f"/api/decision-packets/{saved.json()['packet_id']}/actions",
        json={
            "disposition": "watch",
            "operator_reason": f"Keep the exact {symbol} packet under local watch.",
            "side": None,
            "quantity": None,
            "limit_price": None,
        },
    )
    assert action.status_code == 200
    return action.json()["packet"]


def _entry(payload: dict[str, object], symbol: str) -> dict[str, object]:
    return next(item for item in payload["entries"] if item["symbol"] == symbol)


def _durable_ids(payload: dict[str, object]) -> dict[str, tuple[object, ...]]:
    result: dict[str, tuple[object, ...]] = {}
    for symbol in ("NVDA", "AAPL"):
        item = _entry(payload, symbol)
        monitoring = item["monitoring"]
        review = item["review"]
        result[symbol] = (
            item["packet_id"],
            monitoring["registration_id"],
            monitoring["latest_evaluation_id"],
            tuple(monitoring["event_ids"]),
            item["outcome_id"],
            None if review is None else review["review_id"],
        )
    return result


class _Entries:
    def __init__(self, packet_ids: tuple[str, ...]) -> None:
        self._entries = tuple(SimpleNamespace(packet_id=packet_id) for packet_id in packet_ids)

    def snapshot(self, *, at: datetime):
        return SimpleNamespace(entries=self._entries, generated_at=at)


class _PerSymbolWorkspace:
    def __init__(self, *, at: datetime, sequence: int, quote: float | None) -> None:
        self._at = at
        self._sequence = sequence
        self._quote = quote

    def render(self, venue, symbol, selected_range):
        return _DurableRenderer(
            at=self._at,
            sequence=self._sequence,
            quote=self._quote,
            source=f"task4a-{symbol.lower()}",
        ).render(venue, symbol, selected_range)


def test_nvda_aapl_refresh_is_bounded_and_exact_results_survive_reconstruction(
    tmp_path: Path,
) -> None:
    """Catch in-memory IDs, Inbox writes, or refresh writes outside its evaluation ledger."""
    root = tmp_path / "demo"
    app = create_demo_app(root=root, seed=SCENARIO.seed, host="127.0.0.1")

    with TestClient(app) as client:
        packets = [_save_watch(client, symbol) for symbol in ("NVDA", "AAPL")]
        degraded_packets = [
            _save_watch(client, symbol, venue="hyperliquid") for symbol in ("BTC-USD", "SOL-USD")
        ]
        registrations = [
            app.state.packet_monitoring.register(
                packet["packet_id"],
                (WatchConditionKind.ENTRY_ZONE, WatchConditionKind.DATA_STALE),
            )
            for packet in packets
        ]

        before_get = _root_bytes(root)
        initial_inbox = client.get("/api/decision-packets")
        assert initial_inbox.status_code == 200
        assert _root_bytes(root) == before_get

        before_refresh = _root_bytes(root)
        refreshed = client.post("/api/decision-session/refresh")
        assert refreshed.status_code == 200
        after_refresh = _root_bytes(root)
        changed = {
            path
            for path in before_refresh.keys() | after_refresh.keys()
            if before_refresh.get(path) != after_refresh.get(path)
        }
        assert changed == {"decisions/monitoring/watch-evaluations.jsonl"}

        result = refreshed.json()
        assert result["status"] == "complete"
        assert result["registered_count"] == 2
        assert result["evaluated_count"] == 2
        started_at = datetime.fromisoformat(result["started_at"].replace("Z", "+00:00"))
        completed_at = datetime.fromisoformat(result["completed_at"].replace("Z", "+00:00"))
        assert completed_at >= started_at
        assert [item["packet_id"] for item in result["items"]] == [
            packet["packet_id"] for packet in reversed(packets)
        ]

        before_inbox_response = client.get("/api/decision-packets")
        assert before_inbox_response.status_code == 200
        before_inbox = before_inbox_response.json()
        assert {item["registration_id"]: item["evaluation_id"] for item in result["items"]} == {
            registration.registration_id: app.state.packet_monitoring.store.evaluations(
                registration.registration_id
            )[-1].evaluation_id
            for registration in registrations
        }
        for registration in registrations:
            evaluation = app.state.packet_monitoring.store.evaluations(
                registration.registration_id
            )[-1]
            assert evaluation.observation.evaluated_at == started_at

        for packet in degraded_packets:
            assert packet["paper_capability"]["allowed"] is False
            assert any(
                blocker["code"] == "forecast-missing"
                for blocker in packet["paper_capability"]["blockers"]
            )
            degraded = _entry(before_inbox, packet["instrument"]["symbol"])
            assert degraded["packet_id"] == packet["packet_id"]
            assert degraded["readiness"]["status"] == "demo"
            assert degraded["readiness"]["reason_code"] == "demo_evidence"

        for packet in (*packets, *degraded_packets):
            assert [scenario["kind"] for scenario in packet["scenarios"]] == [
                "bull",
                "base",
                "bear",
            ]
            assert all(scenario["probability"] is None for scenario in packet["scenarios"])
            assert all(scenario["confidence"] == "qualitative" for scenario in packet["scenarios"])
            costs = packet["evidence"]["costs"]
            assert costs["fee_bps"] >= 0
            assert costs["slippage_bps"] >= 0
            assert costs["half_spread_bps"] is None
            assert costs["spread_status"] == "confirmation-quote-required"

    restarted = create_demo_app(root=root, seed=SCENARIO.seed, host="127.0.0.1")
    with TestClient(restarted) as client:
        after_inbox_response = client.get("/api/decision-packets")
    assert after_inbox_response.status_code == 200
    assert _durable_ids(after_inbox_response.json()) == _durable_ids(before_inbox)
    for packet in degraded_packets:
        restarted_entry = _entry(after_inbox_response.json(), packet["instrument"]["symbol"])
        assert restarted_entry["packet_id"] == packet["packet_id"]
        assert restarted_entry["readiness"]["status"] == "demo"


def test_exact_real_catalog_absence_and_manifest_mismatch_stay_packet_bound() -> None:
    """Catch catalog fallback or substitution of another manifest/evaluation identity."""
    packet = _real_packet()
    checked_at = packet.as_of + timedelta(minutes=5)

    absent = DecisionReadinessService(catalog_provider=lambda: None).evaluate(
        packet,
        checked_at=checked_at,
    )
    assert absent.status == "unavailable"
    assert absent.reason_code == "catalog_unavailable"
    assert absent.history is None

    catalog = ExactCatalog({MANIFEST: _lineage(manifest_id="9" * 64)})
    mismatch = DecisionReadinessService(catalog_provider=lambda: catalog).evaluate(
        packet,
        checked_at=checked_at,
    )
    assert mismatch.status == "unavailable"
    assert mismatch.reason_code == "history_manifest_mismatch"
    assert mismatch.history is None
    assert catalog.requested == [MANIFEST]
    assert packet.evidence.history_manifest_id == MANIFEST
    assert packet.evidence.history_quality_evaluation_id == EVALUATION


def test_newer_sequence_stale_no_quote_and_partial_failure_preserve_durable_success(
    tmp_path: Path,
) -> None:
    """Catch lost cursors/events, fabricated stale quotes, or all-or-nothing refresh rollback."""
    packet_root = tmp_path / "packets"
    monitoring_root = tmp_path / "monitoring"
    packets = DecisionPacketStore(packet_root)
    nvda = _record_action_packet(packets, symbol="NVDA")
    aapl = _record_action_packet(packets, symbol="AAPL")
    watches = DecisionWatchService(
        packet_store=packets,
        store=DecisionWatchStore(monitoring_root),
    )
    registrations = {
        nvda.packet_id: watches.register(
            nvda.packet_id,
            (WatchConditionKind.ENTRY_ZONE,),
        ),
        aapl.packet_id: watches.register(
            aapl.packet_id,
            (WatchConditionKind.DATA_STALE,),
        ),
    }
    inbox = _Entries((nvda.packet_id, aapl.packet_id))
    first_at = max(nvda.as_of, aapl.as_of) + timedelta(minutes=2)

    first = DecisionSessionService(
        inbox=inbox,
        packets=packets,
        watches=watches,
        workspace=_PerSymbolWorkspace(at=first_at, sequence=0, quote=None),
        now=lambda: first_at,
    ).refresh()
    assert first.status == "complete"
    assert first.registered_count == first.evaluated_count == 2
    nvda_first = watches.store.evaluations(registrations[nvda.packet_id].registration_id)[-1]
    assert nvda_first.observation.price is None
    assert nvda_first.results[0].state == "not_comparable"

    armed_at = first_at + timedelta(minutes=2)
    armed_packets = DecisionPacketStore(packet_root)
    armed_watches = DecisionWatchService(
        packet_store=armed_packets,
        store=DecisionWatchStore(monitoring_root),
    )
    armed = DecisionSessionService(
        inbox=inbox,
        packets=armed_packets,
        watches=armed_watches,
        workspace=_PerSymbolWorkspace(at=armed_at, sequence=1, quote=101.0),
        now=lambda: armed_at,
    ).refresh()
    assert armed.status == "complete"
    nvda_armed = armed_watches.store.evaluations(registrations[nvda.packet_id].registration_id)[-1]
    assert nvda_armed.results[0].state == "armed"

    crossed_at = armed_at + timedelta(minutes=2)
    restarted_packets = DecisionPacketStore(packet_root)
    restarted_watches = DecisionWatchService(
        packet_store=restarted_packets,
        store=DecisionWatchStore(monitoring_root),
    )
    crossed = DecisionSessionService(
        inbox=inbox,
        packets=restarted_packets,
        watches=restarted_watches,
        workspace=_PerSymbolWorkspace(at=crossed_at, sequence=2, quote=99.0),
        now=lambda: crossed_at,
    ).refresh()
    assert crossed.status == "complete"
    assert next(item for item in crossed.items if item.packet_id == nvda.packet_id).triggered

    nvda_evaluations = restarted_watches.store.evaluations(
        registrations[nvda.packet_id].registration_id
    )
    assert [evaluation.observation.sequence for evaluation in nvda_evaluations] == [None, 1, 2]
    price = nvda_evaluations[-1].results[0]
    assert price.state == "triggered"
    assert isinstance(price.facts, PriceFacts)
    assert price.facts.previous_price == 101.0
    assert price.facts.current_price == 99.0
    assert price.event_id is not None
    nvda_event_id = price.event_id
    assert nvda.as_of < nvda_evaluations[-1].observation.data_time
    assert (
        nvda_evaluations[-1].observation.received_at
        <= nvda_evaluations[-1].observation.evaluated_at
    )

    stale_at = crossed_at + timedelta(days=4)
    stale = DecisionSessionService(
        inbox=inbox,
        packets=restarted_packets,
        watches=restarted_watches,
        workspace=_PerSymbolWorkspace(at=stale_at, sequence=0, quote=None),
        now=lambda: stale_at,
    ).refresh()
    assert stale.status == "complete"
    nvda_stale = restarted_watches.store.evaluations(registrations[nvda.packet_id].registration_id)[
        -1
    ]
    assert nvda_stale.observation.price is None
    assert nvda_stale.observation.instrument is None
    assert nvda_stale.observation.sequence is None
    assert nvda_stale.results[0].state == "triggered"
    assert nvda_stale.results[0].event_id == nvda_event_id

    aapl_stale = restarted_watches.store.evaluations(registrations[aapl.packet_id].registration_id)[
        -1
    ]
    assert aapl_stale.observation.price is None
    assert aapl_stale.observation.instrument is None
    assert aapl_stale.observation.sequence is None
    assert aapl_stale.results[0].state == "triggered"
    assert isinstance(aapl_stale.results[0].facts, StaleFacts)

    packet_path = packet_root / "decision-packets.jsonl"
    packet_path.write_text(
        "\n".join(
            line
            for line in packet_path.read_text(encoding="utf-8").splitlines()
            if json.loads(line)["packet_id"] != aapl.packet_id
        )
        + "\n",
        encoding="utf-8",
    )
    successful_count = len(
        restarted_watches.store.evaluations(registrations[nvda.packet_id].registration_id)
    )
    partial_at = stale_at + timedelta(minutes=2)
    partial_packets = DecisionPacketStore(packet_root)
    partial_watches = DecisionWatchService(
        packet_store=partial_packets,
        store=DecisionWatchStore(monitoring_root),
    )
    partial = DecisionSessionService(
        inbox=inbox,
        packets=partial_packets,
        watches=partial_watches,
        workspace=_PerSymbolWorkspace(at=partial_at, sequence=0, quote=None),
        now=lambda: partial_at,
    ).refresh()
    assert partial.status == "partial"
    assert partial.registered_count == 2
    assert partial.evaluated_count == 1
    failed = next(item for item in partial.items if item.status == "failed")
    assert failed.packet_id == aapl.packet_id
    assert failed.evaluation_id is None
    assert failed.reason_code == "packet_unavailable"
    assert (
        len(partial_watches.store.evaluations(registrations[nvda.packet_id].registration_id))
        == successful_count + 1
    )
