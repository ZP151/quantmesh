"""Fresh delivery never renews executable source time."""

from datetime import timedelta

import pytest

from quantmesh.live.fence import QuoteFence
from tests.test_live_fence import BTC, T0, _snapshot, _view


@pytest.mark.parametrize(
    "source",
    [
        None,
        "bad",
        "2026-08-09T10:00:00",
        (T0 + timedelta(seconds=1)).isoformat(),
        (T0 - timedelta(hours=1)).isoformat(),
    ],
)
def test_invalid_or_old_source_is_refused(source):
    view = _view()
    view["data_time"] = source
    assert not QuoteFence().evaluate(view, instrument=BTC, now=T0).allowed


@pytest.mark.parametrize(
    "receipt",
    [
        None,
        "bad",
        "2026-08-09T10:00:00",
        (T0 + timedelta(seconds=1)).isoformat(),
        (T0 - timedelta(seconds=31)).isoformat(),
    ],
)
def test_invalid_or_old_receipt_is_refused(receipt):
    view = _view()
    view["received_at"] = receipt
    assert not QuoteFence().evaluate(view, instrument=BTC, now=T0).allowed


def test_source_horizon_boundary_and_quote_timestamp():
    view = _view()
    view["data_time"] = (T0 - timedelta(seconds=30)).isoformat()
    decision = QuoteFence().evaluate(view, instrument=BTC, now=T0)
    assert decision.allowed and decision.quote.timestamp == T0 - timedelta(seconds=30)
    view["data_time"] = (T0 - timedelta(seconds=30, microseconds=1)).isoformat()
    assert not QuoteFence().evaluate(view, instrument=BTC, now=T0).allowed


def test_resolve_preserves_source_clock():
    snapshot = _snapshot(_view())
    assert QuoteFence().resolve(snapshot, instrument=BTC, now=T0).allowed
