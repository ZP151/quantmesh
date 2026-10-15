"""Desired safety contracts from the local repository audit dated 2026-09-20.

Sources: output/technical-evidence-20260920/security_probes.py and
quote_freshness_probe.py in the original audited checkout (c74ea03f).
These fixtures reproduce audit inputs, not live attacks, venue observations,
or measurements of real model quality. REAL below is a synthetic provenance
label used to exercise the production fence. Current defects must fail these
assertions; neither xfail nor assertions that a vulnerability exists count as
successful task completion. All state is in memory and all model replies are
scripted. No credentials, external model, network, or account files are used.
"""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest

from quantmesh.ai.gateway import ModelGateway
from quantmesh.ai.roles import ResearchPipeline
from quantmesh.ai.transport import ScriptedModelTransport
from quantmesh.api import workstation
from quantmesh.domain.models import Instrument, InstrumentType, OrderRequest, Side, Venue
from quantmesh.domain.orders import OrderStatus
from quantmesh.execution.accounting import PaperAccount
from quantmesh.live.contract import MarketUpdate, Provenance, UpdateKind
from quantmesh.live.feed import LiveFeed
from quantmesh.live.fence import QuoteFence


def test_disguised_loopback_origin_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """An attacker-controlled DNS hostname is not a loopback IP literal."""
    monkeypatch.setattr(
        workstation, "settings", SimpleNamespace(environment="local", staging_origin=None)
    )
    origin = "https://127.attacker.example"
    assert urlsplit(origin).hostname == "127.attacker.example"
    assert workstation._is_allowed_browser_origin("http://127.0.0.1:8000")
    assert not workstation._is_allowed_browser_origin("https://evil.example")

    assert not workstation._is_allowed_browser_origin(origin), (
        "A DNS hostname beginning with 127. must not pass the browser-origin guard"
    )


def test_generic_pipeline_refuses_fabricated_citation() -> None:
    """A cooperative critic cannot confer evidence authority on an unknown id."""
    citation = "document:does-not-exist"
    context = {"document:fixture-source": "Synthetic research source, not market evidence."}
    outputs = [
        {
            "claims": [
                {
                    "statement": "Synthetic unsupported claim",
                    "confidence": 0.9,
                    "direction": "long",
                    "evidence_citations": [citation],
                }
            ]
        },
        {"verdict": "pass", "flagged_claims": []},
        {"posture": "aligned", "referenced_verdicts": ["risk-fixture"], "findings": []},
        {
            "posture": "within_constraints",
            "referenced_inputs": ["portfolio-fixture"],
            "suggestions": [],
        },
    ]
    assert citation not in context
    assert outputs[1] == {"verdict": "pass", "flagged_claims": []}
    transport = ScriptedModelTransport([{"content": json.dumps(item)} for item in outputs])
    pipeline = ResearchPipeline(
        ModelGateway(transport, model_name="offline-benchmark-script"),
        context=context,
        risk_verdicts={"risk-fixture": "Synthetic approved risk verdict"},
        portfolio_inputs={"portfolio-fixture": "Synthetic bounded portfolio"},
    )

    result = pipeline.run()
    assert len(transport.seen_bodies) == 4
    assert len(result.analyst_report.claims) == 1
    assert result.analyst_report.claims[0].evidence_citations == [citation]
    assert not result.critic.allowed, (
        "Unresolvable citations must be blocked even when the scripted critic says pass"
    )


def test_old_source_quote_never_fills_paper_order() -> None:
    """Fresh local delivery must not refresh the age of stale source evidence."""
    now = datetime(2026, 9, 20, 12, tzinfo=UTC)
    instrument = Instrument(
        symbol="BTC", venue=Venue.HYPERLIQUID, instrument_type=InstrumentType.PERPETUAL
    )
    feed = LiveFeed()
    updates = [
        MarketUpdate(
            venue=instrument.venue,
            instrument=instrument.symbol,
            kind=UpdateKind.QUOTE,
            provenance=Provenance.REAL,
            data_time=now - timedelta(hours=1) + timedelta(seconds=index),
            received_at=now - timedelta(seconds=1 - index),
            sequence=index + 1,
            source_event_id=f"audit-stale-quote-{index}",
            payload={"bid": 100.0, "ask": 101.0, "bid_size": 2.0, "ask_size": 2.0},
        )
        for index in range(2)
    ]
    assert len({update.source_event_id for update in updates}) == 2
    feed.ingest(updates)
    snapshot = feed.snapshot_exact(instrument.venue, instrument.symbol, UpdateKind.QUOTE, as_of=now)
    assert snapshot is not None
    assert snapshot.provenance is Provenance.REAL
    assert snapshot.continuity_proven and not snapshot.sequence_gap
    assert snapshot.data_time == now - timedelta(seconds=3599)
    assert snapshot.received_at == now
    assert snapshot.freshness_label == "stale"
    account = PaperAccount(cash=1000)
    request = OrderRequest(instrument=instrument, side=Side.BUY, quantity=1, paper=True)
    assert request.paper

    result = account.submit(request, now=now, quote_fence=QuoteFence(), snapshot=snapshot)
    assert (result.order.status, len(result.fills)) == (OrderStatus.REJECTED, 0), (
        "A quote whose source is one hour old must be refused without fills, "
        "even with a fresh receipt, valid depth, and proven continuity"
    )
