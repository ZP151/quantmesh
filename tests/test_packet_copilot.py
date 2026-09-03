from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from quantmesh.ai.decisions import DecisionLog, ModelMeta
from quantmesh.ai.gateway import ModelGateway
from quantmesh.ai.retrieval import Citation, DecisionPacketSource, resolve_citation
from quantmesh.ai.transport import ModelTransport, ScriptedModelTransport
from quantmesh.api.workstation import create_workstation_app
from quantmesh.demo.manifest import DemoScenario
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
from quantmesh.instruments.copilot import (
    PacketCopilotCritic,
    PacketCopilotDraft,
    PacketCopilotItem,
    PacketCopilotRecord,
    PacketCopilotService,
    PacketCopilotStore,
)
from quantmesh.instruments.decision_packets import DecisionPacketStore, decision_packet_id
from quantmesh.settings import settings

NOW = datetime(2026, 9, 3, 10, 0, tzinfo=UTC)
MODEL = ModelMeta(name="fixture-copilot", version="v1", endpoint_kind="scripted")


def _packet(*, history_source: str = "demo-synthetic") -> DecisionPacket:
    provisional = DecisionPacket(
        packet_id="packet-" + "0" * 24,
        version=1,
        parent_packet_id=None,
        instrument=Instrument(
            venue=Venue.MOOMOO,
            symbol="NVDA",
            instrument_type=InstrumentType.EQUITY,
            currency="USD",
        ),
        selected_range=HistoryRange.SIX_MONTHS,
        as_of=NOW,
        created_at=NOW,
        market_state=DecisionMarketState(
            trend="bullish",
            latest_close=184.0,
            sma20=182.0,
            sma50=178.0,
            support=176.0,
            resistance=190.0,
            invalidation=174.0,
            observed_drawdown=0.04,
            observed_volatility=0.22,
            key_level_bar_times=(NOW - timedelta(days=1), NOW),
        ),
        scenarios=(
            DecisionScenario(
                kind="bull",
                thesis="resistance breaks",
                trigger="close above 190",
                invalidation=174.0,
                target=205.0,
                confidence_reason="qualitative only",
            ),
            DecisionScenario(
                kind="base",
                thesis="range holds",
                trigger="support remains intact",
                invalidation=174.0,
                target=194.0,
                confidence_reason="qualitative only",
            ),
            DecisionScenario(
                kind="bear",
                thesis="support fails",
                trigger="close below 176",
                invalidation=190.0,
                target=165.0,
                confidence_reason="qualitative only",
            ),
        ),
        risk_plan=DecisionRiskPlan(
            entry_price=184.0,
            stop_price=174.0,
            target_price=194.0,
            risk_per_unit=10.0,
            reward_per_unit=10.0,
            reward_to_risk=1.0,
            suggested_quantity=5.0,
            suggested_notional=920.0,
        ),
        evidence=DecisionEvidence(
            history_dataset_id="nvda-demo",
            history_dataset_revision=1,
            history_source=history_source,
            history_generated_at=NOW,
            history_limitations=("Synthetic evidence is not live evidence.",),
            costs=DecisionCostEvidence(
                fee_bps=1.5,
                slippage_bps=2.5,
                spread_status="confirmation-quote-required",
            ),
        ),
        paper_capability=DecisionPaperCapability(allowed=True),
        disposition=DecisionDisposition.DRAFT,
    )
    return provisional.model_copy(update={"packet_id": decision_packet_id(provisional)})


def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _citation(packet: DecisionPacket, pointer: str, value: object) -> dict[str, object]:
    return {
        "source_kind": "packet",
        "source_id": packet.packet_id,
        "span": None,
        "json_pointer": pointer,
        "value_digest": _digest(value),
    }


def _draft_payload(packet: DecisionPacket) -> dict[str, object]:
    items = {
        "base_explanation": (
            "The stored market structure is bullish.",
            "/market_state/trend",
            packet.market_state.trend,
        ),
        "bull_challenge": (
            "The bull case requires a close above resistance.",
            "/scenarios/0/trigger",
            packet.scenarios[0].trigger,
        ),
        "bear_challenge": (
            "The bear case starts if support fails.",
            "/scenarios/2/thesis",
            packet.scenarios[2].thesis,
        ),
    }
    payload: dict[str, object] = {"packet_id": packet.packet_id}
    for name, (text, pointer, value) in items.items():
        payload[name] = {
            "text": text,
            "citations": [_citation(packet, pointer, value)],
        }
    payload["evidence_gaps_or_contradictions"] = [
        {
            "text": "The evidence is explicitly synthetic.",
            "citations": [
                _citation(
                    packet,
                    "/evidence/history_limitations",
                    list(packet.evidence.history_limitations),
                )
            ],
        }
    ]
    payload["limitations"] = [
        {
            "text": "Scenario confidence is qualitative.",
            "citations": [
                _citation(packet, "/scenarios/1/confidence", packet.scenarios[1].confidence)
            ],
        }
    ]
    payload["operator_questions"] = [
        {
            "text": "Will price hold above the stored support?",
            "citations": [
                _citation(packet, "/market_state/support", packet.market_state.support)
            ],
        }
    ]
    return payload


def _critic_payload(packet: DecisionPacket, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "packet_id": packet.packet_id,
        "verdict": "pass",
        "flagged_items": [],
    }
    payload.update(overrides)
    return payload


def _service(
    root: Path,
    packet: DecisionPacket,
    analyst_records: list[dict] | None,
    critic_records: list[dict] | None,
    *,
    analyst_transport: ModelTransport | None = None,
) -> tuple[
    PacketCopilotService,
    ScriptedModelTransport | ModelTransport | None,
    ScriptedModelTransport | None,
]:
    packets = DecisionPacketStore(root / "packets")
    packets.record(packet)
    analyst = analyst_transport or (
        ScriptedModelTransport(analyst_records) if analyst_records is not None else None
    )
    critic = ScriptedModelTransport(critic_records) if critic_records is not None else None
    service = PacketCopilotService(
        packet_store=packets,
        store=PacketCopilotStore(root / "copilot"),
        decision_log=DecisionLog(root / "decisions"),
        analyst_gateway=(
            ModelGateway(analyst, model_name=MODEL.name) if analyst is not None else None
        ),
        critic_gateway=(
            ModelGateway(critic, model_name=MODEL.name) if critic is not None else None
        ),
        analyst_model=MODEL,
        critic_model=MODEL,
        now=lambda: NOW,
    )
    return service, analyst, critic


def _script(content: object) -> list[dict]:
    return [{"content": json.dumps(content, sort_keys=True)}]


class TimeoutTransport(ModelTransport):
    def complete(self, body: dict) -> object:
        raise TimeoutError("fixture model timed out")


def test_legacy_citation_serialization_is_byte_compatible() -> None:
    citation = Citation(source_kind="document", source_id="doc-1", span=(2, 7))

    assert citation.model_dump() == {
        "source_kind": "document",
        "source_id": "doc-1",
        "span": (2, 7),
    }
    assert citation.model_dump_json() == (
        '{"source_kind":"document","source_id":"doc-1","span":[2,7]}'
    )


def test_openapi_citation_contract_exposes_typed_fields() -> None:
    app = create_workstation_app(account=PaperAccount(cash=100_000.0), host="127.0.0.1")

    citation = app.openapi()["components"]["schemas"]["Citation"]

    assert citation["type"] == "object"
    assert citation["additionalProperties"] is False
    assert set(citation["properties"]) == {
        "source_kind",
        "source_id",
        "span",
        "json_pointer",
        "value_digest",
    }
    assert set(citation["required"]) == {"source_kind", "source_id"}


def test_packet_source_resolves_exact_scalar_and_scalar_list_values(tmp_path: Path) -> None:
    packet = _packet()
    store = DecisionPacketStore(tmp_path / "packets")
    store.record(packet)
    sources = {"packet": DecisionPacketSource(store)}

    scalar = resolve_citation(
        Citation.model_validate(_citation(packet, "/market_state/support", 176.0)),
        sources,
    )
    scalar_list = resolve_citation(
        Citation.model_validate(
            _citation(
                packet,
                "/evidence/history_limitations",
                ["Synthetic evidence is not live evidence."],
            )
        ),
        sources,
    )

    assert scalar.record == packet
    assert scalar.text == "176.0"
    assert scalar_list.text == '["Synthetic evidence is not live evidence."]'


@pytest.mark.parametrize(
    ("pointer", "value", "message"),
    [
        ("/market_state/missing", None, "does not exist"),
        ("/market_state", None, "container"),
        ("/scenarios/~0/trigger", None, "escaped"),
        ("/scenarios/01/trigger", None, "array index"),
        ("/market_state/support", 175.0, "digest"),
    ],
)
def test_packet_source_refuses_bad_pointer_or_digest(
    tmp_path: Path,
    pointer: str,
    value: object,
    message: str,
) -> None:
    packet = _packet()
    store = DecisionPacketStore(tmp_path / "packets")
    store.record(packet)
    citation = Citation.model_validate(_citation(packet, pointer, value))

    with pytest.raises(ValueError, match=message):
        resolve_citation(citation, {"packet": DecisionPacketSource(store)})


def test_citation_contract_keeps_packet_and_legacy_fields_disjoint() -> None:
    with pytest.raises(ValidationError, match="span"):
        Citation(
            source_kind="packet",
            source_id="packet-" + "a" * 24,
            span=(0, 1),
            json_pointer="/market_state/trend",
            value_digest="b" * 64,
        )
    with pytest.raises(ValidationError, match="json_pointer"):
        Citation(
            source_kind="document",
            source_id="doc-1",
            json_pointer="/content",
            value_digest="b" * 64,
        )
    with pytest.raises(ValidationError, match="value_digest"):
        Citation(
            source_kind="packet",
            source_id="packet-" + "a" * 24,
            json_pointer="/market_state/trend",
        )


def test_contracts_refuse_cross_packet_and_authority_shaped_output() -> None:
    packet = _packet()
    payload = _draft_payload(packet)
    with pytest.raises(ValueError, match="packet_id"):
        PacketCopilotDraft.model_validate(
            payload | {"packet_id": "packet-" + "f" * 24}
        ).validate_for_packet(packet.packet_id)
    with pytest.raises(ValidationError):
        PacketCopilotDraft.model_validate(payload | {"direction": "buy"})
    with pytest.raises(ValidationError):
        PacketCopilotItem.model_validate(
            payload["base_explanation"] | {"approval": True}
        )


def test_valid_request_records_both_stages_and_reopens_idempotently(tmp_path: Path) -> None:
    packet = _packet()
    analyst_script = _script(_draft_payload(packet))
    critic_script = _script(_critic_payload(packet))
    service, analyst, critic = _service(tmp_path, packet, analyst_script, critic_script)

    state = service.request(packet.packet_id)
    again = service.request(packet.packet_id)
    reopened = PacketCopilotService(
        packet_store=DecisionPacketStore(tmp_path / "packets"),
        store=PacketCopilotStore(tmp_path / "copilot"),
        decision_log=DecisionLog(tmp_path / "decisions"),
        analyst_gateway=None,
        critic_gateway=None,
        analyst_model=MODEL,
        critic_model=MODEL,
        now=lambda: NOW + timedelta(days=1),
    ).latest(packet.packet_id)

    assert state.status == "ready"
    assert state.record is not None
    assert state.record.packet_id == packet.packet_id
    assert state.record.report.base_explanation.text.startswith("The stored")
    assert len(DecisionLog(tmp_path / "decisions").all()) == 2
    assert again == state
    assert reopened == state
    assert len(analyst.seen_bodies) == 1
    assert len(critic.seen_bodies) == 1


@pytest.mark.parametrize(
    "case",
    [
        "missing-gateway",
        "unavailable",
        "timeout",
        "non-json",
        "authority-field",
        "cross-packet-draft",
        "bad-citation",
        "malformed-critic",
        "critic-flag",
    ],
)
def test_failures_degrade_without_persisting_or_mutating_packet(
    tmp_path: Path,
    case: str,
) -> None:
    packet = _packet()
    draft = _draft_payload(packet)
    critic = _critic_payload(packet)
    analyst_records: list[dict] | None = _script(draft)
    critic_records: list[dict] | None = _script(critic)
    analyst_transport: ModelTransport | None = None
    if case == "missing-gateway":
        analyst_records = None
        critic_records = None
    elif case == "unavailable":
        analyst_records = []
    elif case == "timeout":
        analyst_transport = TimeoutTransport()
    elif case == "non-json":
        analyst_records = [{"content": "not-json"}]
    elif case == "authority-field":
        analyst_records = _script(draft | {"approval": "approved"})
    elif case == "cross-packet-draft":
        analyst_records = _script(draft | {"packet_id": "packet-" + "f" * 24})
    elif case == "bad-citation":
        changed = json.loads(json.dumps(draft))
        changed["base_explanation"]["citations"][0]["value_digest"] = "f" * 64
        analyst_records = _script(changed)
    elif case == "malformed-critic":
        critic_records = _script(critic | {"risk_approval": True})
    elif case == "critic-flag":
        critic_records = _script(
            _critic_payload(
                packet,
                verdict="flag",
                flagged_items=[
                    {"item_path": "base_explanation", "reason": "Unsupported wording."}
                ],
            )
        )

    service, _, _ = _service(
        tmp_path,
        packet,
        analyst_records,
        critic_records,
        analyst_transport=analyst_transport,
    )
    packet_path = DecisionPacketStore(tmp_path / "packets").path
    packet_bytes = packet_path.read_bytes()

    state = service.request(packet.packet_id)

    assert state.status == "degraded"
    assert state.packet_id == packet.packet_id
    assert state.record is None
    assert state.reason_code == "copilot-unavailable"
    assert packet_path.read_bytes() == packet_bytes
    assert DecisionPacketStore(tmp_path / "packets").get(packet.packet_id) == packet
    assert DecisionLog(tmp_path / "decisions").all() == []
    assert PacketCopilotStore(tmp_path / "copilot").latest(packet.packet_id) is None


def test_secret_is_redacted_before_analyst_and_critic_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "sk-supersecretfixturevalue123456789"
    monkeypatch.setenv("QUANTMESH_RESEARCH_TOKEN", secret)
    packet = _packet(history_source=f"demo source {secret}")
    service, analyst, critic = _service(
        tmp_path,
        packet,
        _script(_draft_payload(packet)),
        _script(_critic_payload(packet)),
    )

    state = service.request(packet.packet_id)
    bodies = [*analyst.seen_bodies, *critic.seen_bodies]

    assert state.status == "ready"
    assert len(bodies) == 2
    assert all(secret not in json.dumps(body) for body in bodies)
    assert all("[REDACTED" in json.dumps(body) for body in bodies)


def test_store_rejects_tampered_or_duplicate_record_identity(tmp_path: Path) -> None:
    packet = _packet()
    service, _, _ = _service(
        tmp_path,
        packet,
        _script(_draft_payload(packet)),
        _script(_critic_payload(packet)),
    )
    record = service.request(packet.packet_id).record
    assert record is not None
    store = PacketCopilotStore(tmp_path / "copilot")

    with pytest.raises(ValueError, match="already recorded"):
        store.record(record)
    with pytest.raises(ValidationError, match="record_id"):
        PacketCopilotRecord.model_validate(
            record.model_dump() | {"record_id": "copilot-" + "f" * 24}
        )


def test_accepted_record_refuses_naive_timestamp() -> None:
    packet = _packet()
    report = PacketCopilotDraft.model_validate(_draft_payload(packet))

    with pytest.raises(ValueError, match="recorded_at must be timezone-aware"):
        PacketCopilotRecord.accepted(
            packet_id=packet.packet_id,
            report=report,
            analyst_decision_id="a" * 16,
            critic_decision_id="b" * 16,
            analyst_model=MODEL,
            critic_model=MODEL,
            recorded_at=NOW.replace(tzinfo=None),
        )


def test_critic_contract_requires_flags_only_for_flag_verdict() -> None:
    packet = _packet()
    with pytest.raises(ValidationError, match="flagged_items"):
        PacketCopilotCritic(
            packet_id=packet.packet_id,
            verdict="pass",
            flagged_items=[
                {"item_path": "base_explanation", "reason": "Unexpected flag."}
            ],
        )
    with pytest.raises(ValidationError, match="flagged_items"):
        PacketCopilotCritic(
            packet_id=packet.packet_id,
            verdict="flag",
            flagged_items=[],
        )


def _persist_demo_packet(client: TestClient) -> dict[str, object]:
    workspace = client.get("/api/instruments/moomoo/NVDA/workspace?range=6m")
    assert workspace.status_code == 200
    draft = workspace.json()["decision"]["draft"]
    saved = client.post(
        "/api/decision-packets",
        json={
            "venue": "moomoo",
            "symbol": "NVDA",
            "selected_range": "6m",
            "expected_packet_id": draft["packet_id"],
        },
    )
    assert saved.status_code == 200
    return saved.json()


def _bind_scripted_service(app, packet: DecisionPacket, root: Path) -> None:
    analyst = ScriptedModelTransport(_script(_draft_payload(packet)))
    critic = ScriptedModelTransport(_script(_critic_payload(packet)))
    app.state.packet_copilot = PacketCopilotService(
        packet_store=app.state.decision_packets,
        store=PacketCopilotStore(root / "decisions" / "copilot"),
        decision_log=app.state.page_context.decisions,
        analyst_gateway=ModelGateway(analyst, model_name=MODEL.name),
        critic_gateway=ModelGateway(critic, model_name=MODEL.name),
        analyst_model=MODEL,
        critic_model=MODEL,
        now=lambda: NOW,
    )


def test_copilot_api_idle_ready_and_restart_reopen(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    app = create_demo_app(root=root, seed=DemoScenario().seed, host="127.0.0.1")
    with TestClient(app) as client:
        saved = _persist_demo_packet(client)
        packet_id = saved["packet_id"]
        idle = client.get(f"/api/decision-packets/{packet_id}/copilot")
        packet = app.state.decision_packets.get(packet_id)
        _bind_scripted_service(app, packet, root)
        ready = client.post(f"/api/decision-packets/{packet_id}/copilot")

    restarted = create_demo_app(root=root, seed=DemoScenario().seed, host="127.0.0.1")
    with TestClient(restarted) as client:
        reopened = client.get(f"/api/decision-packets/{packet_id}/copilot")

    assert idle.status_code == 200
    assert idle.json() == {
        "status": "idle",
        "packet_id": packet_id,
        "record": None,
        "reason_code": None,
    }
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    assert ready.json()["record"]["packet_id"] == packet_id
    assert reopened.status_code == 200
    assert reopened.json() == ready.json()


def test_copilot_api_model_unavailable_degrades_only_advisory_state(
    tmp_path: Path,
) -> None:
    root = tmp_path / "demo"
    app = create_demo_app(root=root, seed=DemoScenario().seed, host="127.0.0.1")
    with TestClient(app) as client:
        saved = _persist_demo_packet(client)
        packet_id = saved["packet_id"]
        packet_path = app.state.decision_packets.path
        packet_bytes = packet_path.read_bytes()
        proposal_count = len(app.state.paper_decisions.ledger.all())
        order_count = len(app.state.page_context.journal.all())

        unavailable = client.post(f"/api/decision-packets/{packet_id}/copilot")

    assert unavailable.status_code == 200
    assert unavailable.json() == {
        "status": "degraded",
        "packet_id": packet_id,
        "record": None,
        "reason_code": "copilot-unavailable",
    }
    assert packet_path.read_bytes() == packet_bytes
    assert len(app.state.paper_decisions.ledger.all()) == proposal_count
    assert len(app.state.page_context.journal.all()) == order_count


def test_normal_workstation_reopens_accepted_record_without_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = _packet()
    service, _, _ = _service(
        tmp_path,
        packet,
        _script(_draft_payload(packet)),
        _script(_critic_payload(packet)),
    )
    accepted = service.request(packet.packet_id)
    packets = DecisionPacketStore(tmp_path / "packets")
    copilot_records = PacketCopilotStore(tmp_path / "copilot")
    packet_bytes = packets.path.read_bytes()
    copilot_bytes = copilot_records.path.read_bytes()
    monkeypatch.setattr(settings, "model_name", "")
    reconstructed = create_workstation_app(
        account=PaperAccount(cash=100_000.0),
        decision_packets=packets,
        packet_copilot_store=copilot_records,
        packet_copilot=None,
        host="127.0.0.1",
    )

    with TestClient(reconstructed) as client:
        reopened = client.get(f"/api/decision-packets/{packet.packet_id}/copilot")
        unavailable = client.post(f"/api/decision-packets/{packet.packet_id}/copilot")

    assert reopened.status_code == 200
    assert reopened.json() == accepted.model_dump(mode="json")
    assert unavailable.status_code == 200
    assert unavailable.json() == {
        "status": "degraded",
        "packet_id": packet.packet_id,
        "record": None,
        "reason_code": "copilot-unavailable",
    }
    assert packets.path.read_bytes() == packet_bytes
    assert copilot_records.path.read_bytes() == copilot_bytes


def test_copilot_api_preserves_packet_lookup_and_same_origin_failures(
    tmp_path: Path,
) -> None:
    root = tmp_path / "demo"
    app = create_demo_app(root=root, seed=DemoScenario().seed, host="127.0.0.1")
    with TestClient(app) as client:
        saved = _persist_demo_packet(client)
        packet_id = saved["packet_id"]
        unknown = client.get(
            "/api/decision-packets/packet-ffffffffffffffffffffffff/copilot"
        )
        cross_origin = client.post(
            f"/api/decision-packets/{packet_id}/copilot",
            headers={"Origin": "https://example.com"},
        )
        app.state.decision_packets.path.write_text("{broken-json\n", encoding="utf-8")
        corrupt = client.get(f"/api/decision-packets/{packet_id}/copilot")

    assert unknown.status_code == 404
    assert cross_origin.status_code == 403
    assert corrupt.status_code == 409
