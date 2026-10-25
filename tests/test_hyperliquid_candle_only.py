"""Mode-only post-close observation, using controlled wire/receipt doubles."""

from datetime import UTC, datetime, timedelta

import pytest

from quantmesh.hyperliquid.errors import HyperliquidProtocolError
from quantmesh.live import hyperliquid as hl
from quantmesh.live.contract import UpdateKind
from quantmesh.live.supervisor import ScriptedVenueTransport

AT = datetime(2026, 10, 25, 16, tzinfo=UTC)


def row(at, close=101):
    return dict(
        t=int(at.timestamp() * 1000),
        T=int((at + timedelta(minutes=1)).timestamp() * 1000) - 1,
        s="BTC",
        i="1m",
        o="100",
        h="1000",
        l="99",
        c=str(close),
        v="10",
        n=1,
    )


def frame(at, close=101):
    return dict(channel="candle", data=row(at, close))


class Rest:
    def __init__(self, *, error=False, mutate=None):
        self.calls = []
        self.error, self.mutate = error, mutate

    def observe_candles(self, symbol, interval, *, start, end):
        self.calls.append((symbol, interval, start, end))
        if self.error:
            raise RuntimeError("PRIVATE raw provider failure/path/token")
        rows = [
            row(start + timedelta(minutes=i), 102 + i)
            for i in range(int((end - start).total_seconds() // 60) + 1)
        ]
        requested = end + timedelta(seconds=4)
        received = requested + timedelta(milliseconds=15)
        if self.mutate:
            rows, requested, received = self.mutate(rows, requested, received)
        return hl.CandleObservation(rows=rows, requested_at=requested, received_at=received)

    def l2_book(self, *args, **kwargs):
        pytest.fail("book recovery forbidden")

    def candles(self, *args, **kwargs):
        pytest.fail("receipt-losing recovery forbidden in this mode")


def supervisor(rest=None, limit=5):
    transport = ScriptedVenueTransport([])
    source = hl.HyperliquidVenueSupervisor(
        transport, rest=rest or Rest(), candle_only=True, candle_recovery_limit=limit
    )
    source.subscribe(["BTC"])
    return source, transport


def test_default_specs_unchanged_and_mode_has_one_exact_subscription():
    ordinary = hl.HyperliquidVenueSupervisor(ScriptedVenueTransport([]))
    ordinary.subscribe(["BTC"])
    assert set(ordinary._subscribed) == {
        "candle:btc,1m",
        "l2Book:btc",
        "trades:btc",
        "bbo:btc",
        "activeAssetCtx:btc",
        "allMids",
    }
    source, transport = supervisor()
    source.on_open(AT)
    assert transport.sent == [
        dict(method="subscribe", subscription=dict(type="candle", coin="BTC", interval="1m"))
    ]
    assert source.resync_request_limit == 5


def test_interims_generate_no_events_or_durable_heartbeat_but_keep_liveness():
    rest = Rest()
    source, _ = supervisor(rest)
    source.on_open(AT)
    for i in range(1, 601):
        now = AT + timedelta(milliseconds=i * 90)
        source.on_frame(frame(AT, 101 + i / 100), now)
        source.on_tick(now)
    updates = source.drain()
    assert rest.calls == []
    assert len(updates) == 1 and updates[0].kind is UpdateKind.STATUS
    assert updates[0].state.value == "connected"
    assert source._last_candle_open == {}  # no pre-commit durable acknowledgment


def test_next_minute_fetches_actual_bar_and_uses_actual_response_receipt():
    rest = Rest()
    source, _ = supervisor(rest)
    source.on_open(AT)
    source.on_frame(frame(AT, 999), AT + timedelta(seconds=5))
    source.on_frame(frame(AT + timedelta(minutes=1), 888), AT + timedelta(minutes=1, seconds=2))
    updates = [u for u in source.drain() if u.kind is UpdateKind.CANDLE]
    assert len(updates) == 1
    item = updates[0]
    assert rest.calls == [("BTC", "1m", AT, AT + timedelta(minutes=1) - timedelta(milliseconds=1))]
    assert item.data_time == AT and item.payload["close"] == 102
    assert item.received_at == AT + timedelta(minutes=1, milliseconds=4014)
    assert item.payload["observation_basis"] == "post_close_rest_snapshot"
    assert item.payload["provider_finality"] == item.payload["historical_pit"] == "unknown"
    assert source._last_candle_open == {}
    for i in range(20):
        source.on_frame(frame(AT + timedelta(minutes=1)), AT + timedelta(minutes=1, seconds=3 + i))
    assert len(rest.calls) == 1
    source.on_persisted(updates)
    assert source._last_candle_open["BTC"] == AT


def test_failure_is_one_attempt_and_never_leaks_raw_exception_or_fills_price():
    rest = Rest(error=True)
    source, _ = supervisor(rest)
    source.on_open(AT)
    source.on_frame(frame(AT), AT)
    for i in range(10):
        source.on_frame(frame(AT + timedelta(minutes=1)), AT + timedelta(minutes=1, seconds=i))
    source.resync(AT + timedelta(minutes=1, seconds=20))
    assert len(rest.calls) == 1
    updates = source.drain()
    assert not any(u.kind is UpdateKind.CANDLE for u in updates)
    assert "PRIVATE" not in str(updates)
    assert source.observation_issue == "candle_observation_unavailable"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda rows, q, r: ([], q, r),
        lambda rows, q, r: (rows * 2, q, r),
        lambda rows, q, r: ([{**rows[0], "s": "ETH"}], q, r),
        lambda rows, q, r: ([{**rows[0], "i": "5m"}], q, r),
        lambda rows, q, r: ([{**rows[0], "T": rows[0]["T"] + 1}], q, r),
        lambda rows, q, r: ([{**rows[0], "t": rows[0]["t"] + 60000}], q, r),
        lambda rows, q, r: ([{**rows[0], "c": "NaN"}], q, r),
        lambda rows, q, r: (rows, q, q - timedelta(seconds=1)),
        lambda rows, q, r: (rows, q - timedelta(minutes=1), r),
    ],
)
def test_wrong_extra_or_unclosed_observation_refuses_before_event(mutate):
    rest = Rest(mutate=mutate)
    source, _ = supervisor(rest)
    source.on_open(AT)
    source.on_frame(frame(AT), AT)
    source.on_frame(frame(AT + timedelta(minutes=1)), AT + timedelta(minutes=1, seconds=1))
    assert not any(u.kind is UpdateKind.CANDLE for u in source.drain())
    assert source.observation_issue == "candle_observation_unavailable"


def test_future_ws_bar_cannot_trigger_early_rest_and_other_channels_refuse():
    rest = Rest()
    source, _ = supervisor(rest)
    source.on_open(AT)
    source.on_frame(frame(AT), AT)
    with pytest.raises(HyperliquidProtocolError, match="market_data_frame_invalid"):
        source.on_frame(frame(AT + timedelta(minutes=1)), AT + timedelta(seconds=20))
    assert rest.calls == []
    with pytest.raises(HyperliquidProtocolError, match="market_data_frame_invalid"):
        source.dispatch(dict(channel="allMids", data={"mids": {"BTC": "123"}}), AT)


def test_rest_receipt_before_the_ws_trigger_cannot_be_reused_as_new_observation():
    def stale(rows, requested, received):
        return (
            rows,
            AT + timedelta(minutes=1, milliseconds=100),
            AT + timedelta(minutes=1, milliseconds=200),
        )

    rest = Rest(mutate=stale)
    source, _ = supervisor(rest)
    source.on_open(AT)
    source.on_frame(frame(AT), AT)
    source.on_frame(frame(AT + timedelta(minutes=1)), AT + timedelta(minutes=1, seconds=2))
    assert not any(u.kind is UpdateKind.CANDLE for u in source.drain())
    assert source.observation_issue == "candle_observation_unavailable"


def test_reconnect_is_finite_exact_targets_and_over_horizon_has_no_request():
    rest = Rest()
    source, _ = supervisor(rest, limit=2)
    source.on_open(AT)  # no initial REST
    assert rest.calls == []
    recovered = source.resync(AT + timedelta(minutes=3))
    assert len(recovered) == 2
    assert rest.calls[0][2:] == (
        AT + timedelta(minutes=1),
        AT + timedelta(minutes=3) - timedelta(milliseconds=1),
    )
    source.on_persisted(recovered)
    assert source.resync(AT + timedelta(minutes=10)) == []
    assert len(rest.calls) == 1 and source.observation_issue == "recovery_limit"


@pytest.mark.parametrize("limit", [0, 6, True])
def test_invalid_mode_profile_cannot_expand_recovery(limit):
    with pytest.raises(ValueError):
        supervisor(limit=limit)


def test_candle_only_cannot_subscribe_another_identity():
    source, _ = supervisor()
    with pytest.raises(ValueError):
        source.subscribe(["BTC", "ETH"])


def test_failed_known_slot_does_not_allow_truncating_a_long_reconnect_gap():
    rest = Rest(error=True)
    source, _ = supervisor(rest, limit=2)
    source.on_open(AT)
    source.on_frame(frame(AT), AT)
    source.on_frame(frame(AT + timedelta(minutes=1)), AT + timedelta(minutes=1, seconds=2))
    assert len(rest.calls) == 1
    source.resync(AT + timedelta(minutes=10))
    assert len(rest.calls) == 1
    assert source.observation_issue == "recovery_limit"
