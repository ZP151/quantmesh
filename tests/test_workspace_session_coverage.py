from datetime import UTC, datetime

from quantmesh.domain.models import Venue
from quantmesh.instruments.contracts import WorkspaceLiveEvidence
from quantmesh.live.contract import UpdateKind
from quantmesh.live.session_freshness import SessionFreshness
from tests.test_live_session_consumers import stock_feed


def test_exact_instrument_coverage_matches_global_policy_without_quote_authority():
    feed = stock_feed()
    now = datetime(2026, 10, 11, 12, tzinfo=UTC)
    global_policy = feed.latest_state(now=now)["instruments"]["moomoo:AAPL"]["session_freshness"]
    assert hasattr(feed, "session_coverage"), "workspace needs exact shared coverage access"
    exact = feed.session_coverage(Venue.MOOMOO, "AAPL", now=now)
    assert exact.model_dump(mode="json") == global_policy
    assert exact.data_state == "latest_session"
    assert exact.evaluated_at == now
    assert feed.session_coverage(Venue.MOOMOO, "NVDA", now=now).data_state == "unknown"
    assert feed.snapshot_exact(Venue.MOOMOO, "AAPL", UpdateKind.QUOTE, as_of=now) is None


def test_workspace_coverage_is_read_only_and_cannot_make_a_quote_available():
    now = datetime(2026, 10, 11, 12, tzinfo=UTC)
    policy = SessionFreshness.model_validate(
        stock_feed().latest_state(now=now)["instruments"]["moomoo:AAPL"]["session_freshness"]
    )
    evidence = WorkspaceLiveEvidence(
        status="degraded", reason="no bid/ask", session_freshness=policy
    )
    assert evidence.status == "degraded"
    assert evidence.bid is None and evidence.ask is None
    assert evidence.session_freshness.data_state == "latest_session"
