"""Pre-submission risk gate and funding ledger (issue #31, Phase C).

The gate is pure and deterministic: every check is exercised directly
against ``evaluate_order``, and the adapter wiring is proven through a
recording transport — a refusal must consume nothing (no journal entry,
no wire call). The funding ledger is the fee-like journal entry surface:
anchors on first record, deltas after, zero-delta no-ops, per-coin
series, atomic writes, fail-closed reads with line attribution.
"""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from quantmesh.domain.models import Instrument, InstrumentType, OrderRequest, Side, Venue
from quantmesh.execution.journal import OrderJournal
from quantmesh.hyperliquid.errors import HyperliquidRiskRefusalError
from quantmesh.hyperliquid.exchange import (
    BrokerPosition,
    CancelAck,
    ExecutionSnapshot,
    HyperliquidExecutionAdapter,
    PlaceAck,
    build_snapshot,
)
from quantmesh.hyperliquid.risk import (
    FundingLedger,
    RiskContext,
    RiskKind,
    RiskLimits,
    evaluate_order,
)
from quantmesh.settings import settings

BTC = Instrument(
    symbol="BTC",
    venue=Venue.HYPERLIQUID,
    instrument_type=InstrumentType.PERPETUAL,
)

NOW = datetime(2025, 8, 8, 12, 0, 0, tzinfo=UTC)


def order(
    *,
    side: Side = Side.BUY,
    quantity: float = 1.0,
    limit_price: float | None = 100.0,
) -> OrderRequest:
    return OrderRequest(
        instrument=BTC,
        side=side,
        quantity=quantity,
        limit_price=limit_price,
    )


def position(
    *,
    coin: str = "BTC",
    size: float = 1.0,
    entry_price: float | None = 100.0,
    liquidation_price: float | None = 90.0,
) -> BrokerPosition:
    return BrokerPosition(
        coin=coin,
        size=size,
        entry_price=entry_price,
        liquidation_price=liquidation_price,
    )


def context(
    *,
    position: BrokerPosition | None = None,
    book_mid: float | None = 100.0,
    book_timestamp: datetime | None = NOW,
    funding: float | None = 0.0,
    equity: float | None = 1_000.0,
    now: datetime = NOW,
) -> RiskContext:
    return RiskContext(
        position=position,
        book_mid=book_mid,
        book_timestamp=book_timestamp,
        funding=funding,
        equity=equity,
        now=now,
    )


class StaticRiskContext:
    """A context provider returning one fixed context (test double)."""

    def __init__(self, ctx: RiskContext) -> None:
        self._ctx = ctx

    def risk_context(self) -> RiskContext:
        return self._ctx


class RecordingTransport:
    """A transport that records calls instead of wiring anything."""

    def __init__(self) -> None:
        self.placed: list[dict[str, object]] = []
        self.canceled: list[dict[str, object]] = []

    def place(self, **kwargs: object) -> PlaceAck:
        self.placed.append(kwargs)
        return PlaceAck(status="ok", oid=1000)

    def cancel(self, *, coin: str, oid: int | None, cloid: str | None) -> CancelAck:
        self.canceled.append({"coin": coin, "oid": oid, "cloid": cloid})
        return CancelAck(status="ok")

    def snapshot(self) -> ExecutionSnapshot:
        return build_snapshot(open_orders=[], fills=[], positions=[])


# --- the gate: a clean order ------------------------------------------------


def test_clean_limit_order_is_allowed() -> None:
    decision = evaluate_order(
        order(), reduce_only=False, context=context(), limits=RiskLimits()
    )
    assert decision.allowed
    assert decision.refusals == []


def test_checks_are_recorded_in_gate_order() -> None:
    decision = evaluate_order(
        order(), reduce_only=False, context=context(), limits=RiskLimits()
    )
    assert decision.checks == ["stale_data", "reduce_only", "leverage", "liquidation_distance"]


def test_non_hyperliquid_instrument_fails_closed() -> None:
    request = OrderRequest(
        instrument=Instrument(
            symbol="AAPL", venue=Venue.MOOMOO, instrument_type=InstrumentType.EQUITY
        ),
        side=Side.BUY,
        quantity=1.0,
        limit_price=100.0,
    )
    with pytest.raises(ValueError, match="not a Hyperliquid"):
        evaluate_order(request, reduce_only=False, context=context(), limits=RiskLimits())


# --- the leverage bound ------------------------------------------------------


def test_leverage_refusal_carries_observed_and_expected() -> None:
    decision = evaluate_order(
        order(quantity=2.0, limit_price=100.0),
        reduce_only=False,
        context=context(position=position(), equity=200.0),
        limits=RiskLimits(max_leverage=1.0),
    )
    assert not decision.allowed
    refusal = decision.refusals[0]
    assert refusal.kind is RiskKind.LEVERAGE
    assert refusal.observed == "1.5x"  # position 1.0 + order 2.0 = 3.0 at 100/200
    assert refusal.expected == "<= 1x"


def test_leverage_exactly_at_the_bound_is_allowed() -> None:
    decision = evaluate_order(
        order(quantity=1.0, limit_price=100.0),
        reduce_only=False,
        context=context(position=position(), equity=200.0),
        limits=RiskLimits(max_leverage=1.0),
    )
    assert decision.allowed


def test_missing_equity_fails_closed() -> None:
    decision = evaluate_order(
        order(), reduce_only=False, context=context(equity=None), limits=RiskLimits()
    )
    assert not decision.allowed
    assert decision.refusals[0].kind is RiskKind.MISSING_DATA
    assert "equity" in decision.refusals[0].message


def test_full_close_skips_the_leverage_check() -> None:
    decision = evaluate_order(
        order(side=Side.SELL, quantity=1.0),
        reduce_only=False,
        context=context(position=position(), equity=None),
        limits=RiskLimits(),
    )
    assert decision.allowed


def test_market_order_without_a_mark_fails_closed() -> None:
    decision = evaluate_order(
        order(limit_price=None),
        reduce_only=False,
        context=context(book_mid=None),
        limits=RiskLimits(),
    )
    assert not decision.allowed
    assert decision.refusals[0].kind is RiskKind.MISSING_DATA
    assert "no entry price" in decision.refusals[0].message


# --- the liquidation-distance floor -------------------------------------------


def test_distance_below_the_floor_refuses() -> None:
    decision = evaluate_order(
        order(quantity=1.0, limit_price=82.0),
        reduce_only=False,
        context=context(position=position(), book_mid=82.0, equity=200.0),
        limits=RiskLimits(),
    )
    assert not decision.allowed
    refusal = decision.refusals[0]
    assert refusal.kind is RiskKind.LIQUIDATION_DISTANCE
    # resulting entry (100 + 82)/2 = 91 → liquidation estimate 81.9;
    # distance at mark 82 is 0.1/82 = 12.2 bps < the 500 bps floor.
    assert float(refusal.observed.removesuffix("bps")) == pytest.approx(
        0.1 / 82 * 10_000, abs=0.01
    )
    assert refusal.expected == ">= 500 bps"


def test_no_floor_allows_the_same_position() -> None:
    decision = evaluate_order(
        order(quantity=1.0, limit_price=82.0),
        reduce_only=False,
        context=context(position=position(), book_mid=82.0, equity=200.0),
        limits=RiskLimits(min_liquidation_distance_bps=0),
    )
    assert decision.allowed


def test_already_at_or_beyond_liquidation_refuses() -> None:
    decision = evaluate_order(
        order(quantity=1.0, limit_price=77.0),
        reduce_only=False,
        context=context(position=position(), book_mid=77.0, equity=200.0),
        limits=RiskLimits(),
    )
    assert not decision.allowed
    assert decision.refusals[0].kind is RiskKind.LIQUIDATION_DISTANCE
    assert "already at or beyond" in decision.refusals[0].message


def test_flip_direction_rebases_the_entry_estimate() -> None:
    # Short -1.0 @ 100, buying 2.0 flips to +1.0: the estimate must use
    # the NEW entry (95), not a size-weighted blend — a blend would
    # estimate 81 and pass, the rebased estimate is 85.5 and refuses.
    decision = evaluate_order(
        order(quantity=2.0, limit_price=95.0),
        reduce_only=False,
        context=context(
            position=position(size=-1.0), book_mid=88.0, equity=200.0
        ),
        limits=RiskLimits(),
    )
    assert not decision.allowed
    assert decision.refusals[0].kind is RiskKind.LIQUIDATION_DISTANCE


def test_funding_correction_shrinks_the_distance() -> None:
    paid = evaluate_order(
        order(quantity=1.0, limit_price=92.0),
        reduce_only=False,
        context=context(position=position(), book_mid=92.0, equity=200.0, funding=6.0),
        limits=RiskLimits(),
    )
    assert not paid.allowed  # paid funding moved the estimate 86.4 → 89.1
    unpaid = evaluate_order(
        order(quantity=1.0, limit_price=92.0),
        reduce_only=False,
        context=context(position=position(), book_mid=92.0, equity=200.0, funding=0.0),
        limits=RiskLimits(),
    )
    assert unpaid.allowed


def test_short_position_distance_uses_the_short_direction() -> None:
    decision = evaluate_order(
        order(side=Side.SELL, quantity=0.5, limit_price=105.0),
        reduce_only=False,
        context=context(
            position=position(size=-1.0, entry_price=100.0, liquidation_price=110.0),
            book_mid=113.0,
            equity=200.0,
        ),
        limits=RiskLimits(),
    )
    assert not decision.allowed
    assert decision.refusals[0].kind is RiskKind.LIQUIDATION_DISTANCE
    assert "already at or beyond" in decision.refusals[0].message


def test_missing_position_liquidation_price_fails_closed() -> None:
    decision = evaluate_order(
        order(quantity=1.0, limit_price=92.0),
        reduce_only=False,
        context=context(
            position=position(liquidation_price=None), book_mid=92.0, equity=200.0
        ),
        limits=RiskLimits(),
    )
    assert not decision.allowed
    assert decision.refusals[0].kind is RiskKind.MISSING_DATA
    assert "no liquidation price" in decision.refusals[0].message


def test_missing_position_entry_price_fails_closed() -> None:
    decision = evaluate_order(
        order(quantity=1.0, limit_price=92.0),
        reduce_only=False,
        context=context(
            position=position(entry_price=None), book_mid=92.0, equity=200.0
        ),
        limits=RiskLimits(),
    )
    assert not decision.allowed
    assert decision.refusals[0].kind is RiskKind.MISSING_DATA
    assert "no entry price" in decision.refusals[0].message


def test_missing_funding_fails_closed() -> None:
    decision = evaluate_order(
        order(quantity=1.0, limit_price=92.0),
        reduce_only=False,
        context=context(position=position(), book_mid=92.0, funding=None, equity=200.0),
        limits=RiskLimits(),
    )
    assert not decision.allowed
    assert decision.refusals[0].kind is RiskKind.MISSING_DATA
    assert "no cumulative funding" in decision.refusals[0].message


def test_missing_mark_fails_closed_for_the_distance_estimate() -> None:
    decision = evaluate_order(
        order(quantity=1.0, limit_price=92.0),
        reduce_only=False,
        context=context(position=position(), book_mid=None, equity=200.0),
        limits=RiskLimits(),
    )
    assert not decision.allowed
    assert decision.refusals[0].kind is RiskKind.MISSING_DATA
    assert "no book mid" in decision.refusals[0].message


def test_no_position_skips_the_distance_estimate() -> None:
    decision = evaluate_order(
        order(),
        reduce_only=False,
        context=context(position=None, book_mid=None, funding=None),
        limits=RiskLimits(),
    )
    assert decision.allowed


def test_reducing_order_skips_the_distance_estimate() -> None:
    decision = evaluate_order(
        order(side=Side.SELL, quantity=0.5),
        reduce_only=False,
        context=context(position=position(), book_mid=None, funding=None),
        limits=RiskLimits(),
    )
    assert decision.allowed


# --- the reduce-only posture ---------------------------------------------------


def test_reduce_only_posture_refuses_non_reductions() -> None:
    decision = evaluate_order(
        order(),
        reduce_only=False,
        context=context(),
        limits=RiskLimits(reduce_only=True),
    )
    assert not decision.allowed
    assert decision.refusals[0].kind is RiskKind.REDUCE_ONLY


def test_reduce_only_posture_allows_reductions() -> None:
    decision = evaluate_order(
        order(),
        reduce_only=True,
        context=context(),
        limits=RiskLimits(reduce_only=True),
    )
    assert decision.allowed


# --- the stale-data window ------------------------------------------------------


def test_stale_book_refuses() -> None:
    decision = evaluate_order(
        order(),
        reduce_only=False,
        context=context(book_timestamp=NOW - timedelta(seconds=40)),
        limits=RiskLimits(),
    )
    assert not decision.allowed
    refusal = decision.refusals[0]
    assert refusal.kind is RiskKind.STALE_DATA
    assert refusal.observed == "40s"


def test_future_book_timestamp_refuses() -> None:
    decision = evaluate_order(
        order(),
        reduce_only=False,
        context=context(book_timestamp=NOW + timedelta(minutes=1)),
        limits=RiskLimits(),
    )
    assert not decision.allowed
    assert decision.refusals[0].kind is RiskKind.STALE_DATA
    assert "future" in decision.refusals[0].message


def test_missing_book_timestamp_refuses() -> None:
    decision = evaluate_order(
        order(),
        reduce_only=False,
        context=context(book_timestamp=None),
        limits=RiskLimits(),
    )
    assert not decision.allowed
    assert decision.refusals[0].kind is RiskKind.STALE_DATA


def test_fresh_book_within_the_window_is_allowed() -> None:
    decision = evaluate_order(
        order(),
        reduce_only=False,
        context=context(book_timestamp=NOW - timedelta(seconds=10)),
        limits=RiskLimits(),
    )
    assert decision.allowed


# --- aggregation and the context model ------------------------------------------


def test_refusals_accumulate_across_checks() -> None:
    decision = evaluate_order(
        order(quantity=40.0, limit_price=100.0),
        reduce_only=False,
        context=context(book_timestamp=NOW - timedelta(seconds=40), equity=1_000.0),
        limits=RiskLimits(reduce_only=True),
    )
    assert not decision.allowed
    assert {refusal.kind for refusal in decision.refusals} == {
        RiskKind.STALE_DATA,
        RiskKind.REDUCE_ONLY,
        RiskKind.LEVERAGE,
    }


def test_context_rejects_negative_book_mid_and_equity() -> None:
    with pytest.raises(ValidationError):
        context(book_mid=-1.0)
    with pytest.raises(ValidationError):
        context(equity=-1.0)


# --- the adapter wiring -----------------------------------------------------------


def test_adapter_requires_paired_risk_config(tmp_path) -> None:  # noqa: ANN001
    transport = RecordingTransport()
    journal = OrderJournal(tmp_path)
    with pytest.raises(ValueError, match="together"):
        HyperliquidExecutionAdapter(
            transport, journal, risk_limits=RiskLimits()
        )
    with pytest.raises(ValueError, match="together"):
        HyperliquidExecutionAdapter(
            transport, journal, risk_context=StaticRiskContext(context())
        )


def test_adapter_without_risk_config_places_normally(tmp_path) -> None:  # noqa: ANN001
    transport = RecordingTransport()
    journal = OrderJournal(tmp_path)
    adapter = HyperliquidExecutionAdapter(transport, journal)
    placed = adapter.place(order())
    assert placed.status == "accepted"
    assert len(transport.placed) == 1
    assert len(journal.all()) == 1


def test_adapter_gate_refuses_before_anything_is_recorded_or_sent(tmp_path) -> None:  # noqa: ANN001
    transport = RecordingTransport()
    journal = OrderJournal(tmp_path)
    adapter = HyperliquidExecutionAdapter(
        transport,
        journal,
        risk_limits=RiskLimits(max_leverage=1.0),
        risk_context=StaticRiskContext(context(equity=100.0, book_mid=100.0)),
    )
    with pytest.raises(HyperliquidRiskRefusalError, match=r"\[leverage\]"):
        adapter.place(order(quantity=2.0, limit_price=100.0))
    assert journal.all() == []
    assert len(transport.placed) == 0


def test_adapter_gate_allows_a_clean_order(tmp_path) -> None:  # noqa: ANN001
    transport = RecordingTransport()
    journal = OrderJournal(tmp_path)
    adapter = HyperliquidExecutionAdapter(
        transport,
        journal,
        risk_limits=RiskLimits(),
        risk_context=StaticRiskContext(context(equity=1_000.0)),
    )
    placed = adapter.place(order())
    assert placed.status == "accepted"
    assert len(transport.placed) == 1
    assert len(journal.all()) == 1


def test_adapter_reduce_only_flag_reaches_the_gate(tmp_path) -> None:  # noqa: ANN001
    transport = RecordingTransport()
    journal = OrderJournal(tmp_path)
    adapter = HyperliquidExecutionAdapter(
        transport,
        journal,
        risk_limits=RiskLimits(reduce_only=True),
        risk_context=StaticRiskContext(context()),
    )
    placed = adapter.place(order(), reduce_only=True)
    assert placed.status == "accepted"
    assert len(transport.placed) == 1
    with pytest.raises(HyperliquidRiskRefusalError, match=r"\[reduce_only\]"):
        adapter.place(order())
    assert len(transport.placed) == 1
    assert len(journal.all()) == 1


# --- the funding ledger ------------------------------------------------------------


def test_ledger_anchors_the_first_record(tmp_path) -> None:  # noqa: ANN001
    ledger = FundingLedger(tmp_path)
    entry = ledger.record(position(), cumulative_funding=2.5, at=NOW)
    assert entry is not None
    assert entry.amount == 2.5
    assert ledger.read() == [entry]


def test_ledger_records_deltas_since_the_last_cumulative(tmp_path) -> None:  # noqa: ANN001
    ledger = FundingLedger(tmp_path)
    ledger.record(position(), cumulative_funding=2.5, at=NOW)
    second = ledger.record(position(), cumulative_funding=3.4, at=NOW)
    assert second is not None
    assert second.amount == pytest.approx(0.9)
    # The delta is against the running cumulative, never the last row's
    # delta (which would compound the series to 3.6 here).
    third = ledger.record(position(), cumulative_funding=4.5, at=NOW)
    assert third is not None
    assert third.amount == pytest.approx(1.1)
    assert [entry.amount for entry in ledger.read()] == pytest.approx(
        [2.5, 0.9, 1.1]
    )


def test_ledger_skips_zero_deltas(tmp_path) -> None:  # noqa: ANN001
    ledger = FundingLedger(tmp_path)
    ledger.record(position(), cumulative_funding=2.5, at=NOW)
    assert ledger.record(position(), cumulative_funding=2.5, at=NOW) is None
    assert [entry.amount for entry in ledger.read()] == [2.5]


def test_ledger_tracks_coins_independently(tmp_path) -> None:  # noqa: ANN001
    ledger = FundingLedger(tmp_path)
    btc = position()
    eth = position(coin="ETH", size=-2.0)
    ledger.record(btc, cumulative_funding=2.5, at=NOW)
    ledger.record(eth, cumulative_funding=1.0, at=NOW)
    third = ledger.record(btc, cumulative_funding=2.7, at=NOW)
    assert third is not None
    assert third.amount == pytest.approx(0.2)
    assert [(entry.coin, entry.amount) for entry in ledger.read()] == [
        ("BTC", pytest.approx(2.5)),
        ("ETH", pytest.approx(1.0)),
        ("BTC", pytest.approx(0.2)),
    ]


def test_ledger_fails_closed_on_missing_cumulative(tmp_path) -> None:  # noqa: ANN001
    ledger = FundingLedger(tmp_path)
    with pytest.raises(ValueError, match="no cumulative funding"):
        ledger.record(position(), cumulative_funding=None, at=NOW)


def test_ledger_read_fails_closed_with_line_attribution(tmp_path) -> None:  # noqa: ANN001
    ledger = FundingLedger(tmp_path)
    ledger.record(position(), cumulative_funding=2.5, at=NOW)
    path = tmp_path / "funding.jsonl"
    path.write_text(path.read_text(encoding="utf-8") + "not json\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 2"):
        ledger.read()


def test_ledger_defaults_to_the_orders_dir() -> None:
    assert FundingLedger().root == settings.orders_dir
