"""Phase D drills (iteration 0015): the deterministic quote fence.

The fence is the operator-prescribed gate between the live feed and
paper-order consumption: orders may only read *locally validated
latest quotes* — provenance real, age within the fence horizon,
sequence continuous. These drills pin three surfaces:

- the pure ``evaluate`` verdicts (every rejection reason, the bless
  path and the priority order) against scripted feed views;
- ``resolve`` against venue/symbol/kind-exact snapshots;
- the full consumption path: ``PaperAccount.submit`` with the fence
  enabled — healthy quotes flow to fills, every rejection lands as an
  explicit REJECTED reason, idempotency replays bypass the fence, and
  the no-fence (demo) path is unchanged.

The real-stack drill at the bottom runs the scripted venue → live
supervisor → feed pump end to end and evaluates the fence with
explicit clocks, so the quiet-venue block is proven without sleeping
on a wall clock.
"""

from __future__ import annotations

import asyncio
import threading
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest

from quantmesh.domain.models import (
    Instrument,
    InstrumentType,
    OrderRequest,
    Quote,
    Side,
    Venue,
)
from quantmesh.domain.orders import OrderEventType, OrderStatus
from quantmesh.execution.accounting import PaperAccount
from quantmesh.execution.matcher import PaperMatcher
from quantmesh.live.contract import Provenance, UpdateKind
from quantmesh.live.feed import ExactUpdateSnapshot, LiveFeed
from quantmesh.live.fence import QuoteFence
from quantmesh.live.hyperliquid import HyperliquidVenueSupervisor, LiveHyperliquidTransport
from tests.fixture_ws_venue import ScriptedVenue

BTC = Instrument(
    symbol="BTC",
    venue=Venue.HYPERLIQUID,
    instrument_type=InstrumentType.PERPETUAL,
)

T0 = datetime(2026, 8, 9, 10, 0, 0, tzinfo=UTC)


def _view(
    *,
    provenance: str = "real",
    received_at: datetime = T0,
    sequence_gap: bool = False,
    payload: dict[str, float] | None = None,
) -> dict[str, object]:
    return {
        "kind": "quote",
        "provenance": provenance,
        "data_time": received_at.isoformat(),
        "received_at": received_at.isoformat(),
        "age_ms": 0,
        "sequence": 1,
        "sequence_gap": sequence_gap,
        "continuity_proven": not sequence_gap,
        "label": "real",
        "payload": payload
        if payload is not None
        else {"bid": 100.0, "ask": 100.5, "bid_size": 1.0, "ask_size": 2.0},
    }


def _snapshot(btc_view: dict[str, object] = _view()) -> ExactUpdateSnapshot:
    received_at = datetime.fromisoformat(str(btc_view["received_at"]))
    return ExactUpdateSnapshot(
        venue=Venue.HYPERLIQUID,
        instrument="BTC",
        kind=UpdateKind.QUOTE,
        source="hyperliquid",
        provenance=Provenance(str(btc_view["provenance"])),
        data_time=datetime.fromisoformat(str(btc_view["data_time"])),
        received_at=received_at,
        sequence=cast(int | None, btc_view["sequence"]),
        sequence_gap=bool(btc_view["sequence_gap"]),
        payload=cast(dict[str, object], btc_view["payload"]),
        continuity_proven=bool(btc_view["continuity_proven"]),
        predecessor_sequence=0,
        predecessor_data_time=received_at - timedelta(milliseconds=1),
        freshness_label="real",
        age_ms=0,
    )


def _request(quantity: float = 1.0) -> OrderRequest:
    return OrderRequest(
        instrument=BTC,
        side=Side.BUY,
        quantity=quantity,
        idempotency_key=None,
    )


def _account() -> PaperAccount:
    return PaperAccount(
        cash=100_000.0,
        matcher=PaperMatcher(slippage_bps=0.0),
    )


# -- pure evaluate -----------------------------------------------------------


def test_blesses_a_healthy_real_quote_into_a_usable_domain_quote() -> None:
    decision = QuoteFence().evaluate(_view(), instrument=BTC, now=T0 + timedelta(seconds=2))

    assert decision.allowed
    assert decision.reason is None
    quote = decision.quote
    assert quote is not None
    assert quote.bid == 100.0
    assert quote.ask == 100.5
    assert quote.last == 100.25  # mid
    assert quote.volume == 3.0  # bid + ask size, the demo route's depth convention
    assert quote.timestamp == T0  # the local receipt anchor


@pytest.mark.parametrize("view", [None, {"kind": "candle", "payload": {}}])
def test_rejects_when_there_is_no_quote_view(view: dict[str, object] | None) -> None:
    decision = QuoteFence().evaluate(view, instrument=BTC, now=T0)

    assert not decision.allowed
    assert decision.reason == "no locally validated quote for BTC"
    assert decision.quote is None


@pytest.mark.parametrize("provenance", ["delayed", "synthetic", "unavailable"])
def test_rejects_anything_that_is_not_real(provenance: str) -> None:
    decision = QuoteFence().evaluate(
        _view(provenance=provenance), instrument=BTC, now=T0
    )

    assert not decision.allowed
    assert decision.reason == (
        f"quote provenance is {provenance}; only locally validated real quotes "
        "may feed paper orders"
    )


def test_rejects_a_sequence_gapped_quote() -> None:
    decision = QuoteFence().evaluate(_view(sequence_gap=True), instrument=BTC, now=T0)

    assert not decision.allowed
    assert decision.reason == "quote sequence is discontinuous — the venue dropped updates"


def test_rejects_missing_positive_continuity_evidence() -> None:
    view = _view()
    view["continuity_proven"] = False

    decision = QuoteFence().evaluate(view, instrument=BTC, now=T0)

    assert decision.allowed is False
    assert decision.reason == (
        "quote continuity is unproven — two clean ordered venue updates are required"
    )


def test_rejects_a_stale_quote_with_the_explicit_age() -> None:
    decision = QuoteFence().evaluate(
        _view(), instrument=BTC, now=T0 + timedelta(seconds=31)
    )

    assert not decision.allowed
    assert decision.reason == "quote is 31 s old; the fence horizon is 30 s"


def test_rejects_a_quote_without_usable_depth() -> None:
    for payload in (
        {"bid": 100.0, "ask": 100.5},  # sizes missing
        {"bid": 100.0, "ask": 100.5, "bid_size": 0.0, "ask_size": 0.0},  # zero depth
        {"bid": 101.0, "ask": 100.5, "bid_size": 1.0, "ask_size": 2.0},  # crossed
    ):
        decision = QuoteFence().evaluate(
            _view(payload=payload), instrument=BTC, now=T0
        )
        assert not decision.allowed
        assert decision.reason == (
            "quote has no usable depth (bid/ask/sizes) for a paper order"
        )


def test_rejects_a_quote_without_a_receipt_anchor() -> None:
    view = _view()
    view["received_at"] = "not-a-timestamp"

    decision = QuoteFence().evaluate(view, instrument=BTC, now=T0)

    assert not decision.allowed
    assert decision.reason == "quote has no local receipt time — it cannot be age-validated"


def test_rejection_priority_is_source_then_gap_then_age() -> None:
    # A synthetic quote that is also gapped and stale reports its source.
    synthetic = QuoteFence().evaluate(
        _view(provenance="synthetic", sequence_gap=True),
        instrument=BTC,
        now=T0 + timedelta(seconds=999),
    )
    assert "provenance is synthetic" in synthetic.reason
    # A real quote that is both gapped and stale reports the gap.
    gapped = QuoteFence().evaluate(
        _view(sequence_gap=True), instrument=BTC, now=T0 + timedelta(seconds=999)
    )
    assert gapped.reason == "quote sequence is discontinuous — the venue dropped updates"


def test_max_age_must_be_positive() -> None:
    with pytest.raises(ValueError, match="max_age must be positive"):
        QuoteFence(max_age=timedelta(0))


# -- resolve against a latest_state snapshot ----------------------------------


def test_resolve_pulls_the_quote_view_from_the_snapshot() -> None:
    fence = QuoteFence()
    healthy = fence.resolve(_snapshot(), instrument=BTC, now=T0 + timedelta(seconds=2))
    assert healthy.allowed
    assert healthy.quote is not None

    wrong_symbol = _snapshot()
    wrong_symbol = ExactUpdateSnapshot(
        **{**wrong_symbol.__dict__, "instrument": "ETH"}
    )
    wrong_venue = _snapshot()
    wrong_venue = ExactUpdateSnapshot(
        **{**wrong_venue.__dict__, "venue": Venue.MOOMOO, "source": "moomoo"}
    )
    for snapshot in (None, wrong_symbol, wrong_venue):
        decision = fence.resolve(snapshot, instrument=BTC, now=T0)
        assert not decision.allowed
        assert "quote" in decision.reason


# -- the consumption path: PaperAccount.submit with the fence -----------------


def test_submit_flows_a_healthy_fenced_quote_to_fills() -> None:
    result = _account().submit(
        _request(),
        now=T0 + timedelta(seconds=2),
        quote_fence=QuoteFence(),
        snapshot=_snapshot(),
    )

    assert result.rejection is None
    assert len(result.fills) == 1
    assert result.fills[0].price == 100.5  # the ask the fence blessed, not a caller quote
    assert result.order.status is OrderStatus.FILLED
    assert result.order.events[-1].event_type is OrderEventType.FILL


def test_submit_records_the_fence_rejection_with_the_explicit_reason() -> None:
    cases = (
        (
            _view(),
            T0 + timedelta(seconds=31),
            "quote is 31 s old; the fence horizon is 30 s",
        ),
        (
            _view(provenance="delayed"),
            T0,
            "quote provenance is delayed; only locally validated real quotes "
            "may feed paper orders",
        ),
        (
            _view(sequence_gap=True),
            T0,
            "quote sequence is discontinuous — the venue dropped updates",
        ),
    )
    for view, now, expected in cases:
        result = _account().submit(
            _request(),
            now=now,
            quote_fence=QuoteFence(),
            snapshot=_snapshot(view),
        )
        assert result.rejection == expected
        assert result.order.status is OrderStatus.REJECTED
        assert result.fills == []
        assert result.account.cash == 100_000.0


def test_submit_ignores_a_caller_quote_when_the_fence_is_enabled() -> None:
    """The fence is the source of truth: the blessed quote replaces any
    caller-supplied one (orders may only read locally validated quotes)."""
    result = _account().submit(
        _request(),
        quote=None,  # the fence path does not need a caller quote
        now=T0 + timedelta(seconds=2),
        quote_fence=QuoteFence(),
        snapshot=_snapshot(),
    )
    assert result.rejection is None
    assert result.fills[0].price == 100.5


def test_idempotency_replay_bypasses_the_fence() -> None:
    """A keyed retry returns the original order even when the fence would
    now reject — replay is not a re-submission (M10 Phase B semantics)."""
    account_ = _account()
    request = OrderRequest(
        instrument=BTC, side=Side.BUY, quantity=1.0, idempotency_key="k-1"
    )
    first = account_.submit(
        request, now=T0 + timedelta(seconds=2), quote_fence=QuoteFence(), snapshot=_snapshot()
    )
    assert first.fills

    # The retry goes to the SAME account state (the replay unit is the
    # recorded order), with a clock that would reject a fresh submission.
    late = first.account.submit(
        request,
        now=T0 + timedelta(minutes=5),
        quote_fence=QuoteFence(),
        snapshot=_snapshot(),
    )
    assert late.replay_of == first.order.order_id
    assert late.order.status is first.order.status
    assert late.fills == []


def test_fence_requires_a_snapshot_and_submit_requires_a_quote_or_fence() -> None:
    with pytest.raises(ValueError, match="snapshot is required"):
        _account().submit(
            _request(), now=T0, quote_fence=QuoteFence(), snapshot=None
        )
    with pytest.raises(ValueError, match="quote or a quote_fence"):
        _account().submit(_request(), quote=None, now=T0)


def test_without_a_fence_the_caller_quote_is_used_unchanged() -> None:
    """The demo path: no fence, the caller's quote feeds the matcher
    directly (the seeded book's touch), exactly as before Phase D."""
    account_ = _account()
    result = account_.submit(
        _request(quantity=2.0),
        Quote(
            instrument=BTC,
            timestamp=T0,
            bid=99.0,
            ask=101.0,
            last=100.0,
            volume=50.0,
        ),
        now=T0,
    )

    assert result.rejection is None
    assert result.fills[0].price == 101.0  # the caller's ask, not the snapshot's


# -- real stack: scripted venue -> supervisor -> feed -> fence ----------------


def _bbo(coin: str) -> dict[str, object]:
    return {
        "channel": "bbo",
        "data": {
            "coin": coin,
            "time": 1_750_000_000_000,
            "bid": 100.0,
            "bidSz": 1.0,
            "ask": 100.5,
            "askSz": 2.0,
        },
    }


def _plan() -> list[tuple[float, object]]:
    # A burst of real bbo frames, then an hour of silence (socket open).
    return [
        (0.0, _bbo("BTC")),
        (0.0, _bbo("BTC")),
        (3600.0, {"__cmd": "close"}),
    ]


@pytest.fixture(scope="module")
def live_quote_anchor() -> tuple[LiveFeed, datetime]:
    """The scripted venue + live supervisor + feed pump on one daemon
    loop; returns the feed and the receipt anchor of the burst quote."""
    loop = asyncio.new_event_loop()
    holder: dict[str, object] = {}
    ready = threading.Event()

    def runner() -> None:
        asyncio.set_event_loop(loop)

        async def serve() -> None:
            async with ScriptedVenue(plan=_plan()) as venue:
                feed = LiveFeed(lag=timedelta(seconds=5), stale=timedelta(seconds=10))
                supervisor = HyperliquidVenueSupervisor(
                    LiveHyperliquidTransport(str(venue.url))
                )
                supervisor.subscribe(["BTC"])
                feed.attach(supervisor)
                holder["feed"] = feed
                held: asyncio.Future[None] = asyncio.get_running_loop().create_future()
                holder["held"] = held
                ready.set()
                await asyncio.gather(feed.run(), held)

        loop.run_until_complete(serve())

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    if not ready.wait(timeout=10):
        raise AssertionError("the scripted venue never came up")
    feed = cast(LiveFeed, holder["feed"])
    received_at: datetime | None = None
    for _ in range(150):
        state = feed.latest_state()
        view = (
            state.get("instruments", {})
            .get("hyperliquid:BTC", {})
            .get("kinds", {})
            .get("quote")
            if isinstance(state.get("instruments"), dict)
            else None
        )
        if isinstance(view, dict):
            anchor = view.get("received_at")
            if isinstance(anchor, str):
                received_at = datetime.fromisoformat(anchor)
                break
        threading.Event().wait(0.1)
    if received_at is None:
        raise AssertionError("the feed never delivered a quote for BTC")
    try:
        yield feed, received_at
    finally:
        held = holder.get("held")
        if held is not None:
            loop.call_soon_threadsafe(cast(asyncio.Future, held).cancel)
        thread.join(timeout=5)


def test_real_stack_healthy_quote_flows_and_a_quiet_venue_blocks(
    live_quote_anchor: tuple[LiveFeed, datetime],
) -> None:
    feed, received_at = live_quote_anchor
    fence = QuoteFence(max_age=timedelta(seconds=5))

    # Within the horizon: the fence blesses the venue's own quote and the
    # order fills against it.
    fresh = feed.snapshot_exact(
        Venue.HYPERLIQUID,
        "BTC",
        UpdateKind.QUOTE,
        as_of=received_at + timedelta(seconds=2),
    )
    result = _account().submit(
        _request(),
        now=received_at + timedelta(seconds=2),
        quote_fence=fence,
        snapshot=fresh,
    )
    assert result.rejection is None
    assert result.fills[0].price == 100.5
    assert result.order.status is OrderStatus.FILLED

    # Past the horizon (the venue went quiet): the same snapshot ages out
    # and the fence blocks with the explicit reason, before any matching.
    stale = feed.snapshot_exact(
        Venue.HYPERLIQUID,
        "BTC",
        UpdateKind.QUOTE,
        as_of=received_at + timedelta(seconds=6),
    )
    blocked = _account().submit(
        _request(),
        now=received_at + timedelta(seconds=6),
        quote_fence=fence,
        snapshot=stale,
    )
    assert blocked.rejection == "quote is 6 s old; the fence horizon is 5 s"
    assert blocked.order.status is OrderStatus.REJECTED
    assert blocked.fills == []
