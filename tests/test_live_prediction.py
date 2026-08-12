"""Prediction-market surface drills (iteration 0015 Phase E, ADR-0014).

Three layers, all wall-clock-free:

- the pair registry: ``parse_prediction_watchlist`` and the board's
  pure ``render`` over a latest-state snapshot;
- the venue supervisors: Polymarket's market channel and Kalshi's
  three-channel socket, driven frame-by-frame through the generic
  scripted transport with stub REST book sources;
- the integration seam: both supervisors → one ``LiveFeed`` →
  ``PredictionBoard.render`` — the exact pipeline the comparison
  screen polls.

Every emitted ``MarketUpdate`` is contract-validated at construction,
so an invalid normalized payload fails the drill before any assertion.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from quantmesh.domain.models import Venue
from quantmesh.kalshi.wire import KalshiLevel, KalshiOrderbook
from quantmesh.live.buffer import LiveBuffer
from quantmesh.live.contract import UpdateKind
from quantmesh.live.feed import LiveFeed
from quantmesh.live.kalshi import (
    KalshiProtocolError,
    KalshiVenueSupervisor,
)
from quantmesh.live.polymarket import (
    PolymarketProtocolError,
    PolymarketVenueSupervisor,
)
from quantmesh.live.prediction import (
    PredictionBoard,
    PredictionPair,
    demo_board,
    parse_prediction_watchlist,
)
from quantmesh.live.supervisor import ScriptedVenueTransport
from quantmesh.polymarket.wire import ClobBook, ClobLevel

NOW = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)
TS_US = 1_753_000_000_000_000  # fixed venue microsecond timestamp
TS = datetime.fromtimestamp(TS_US / 1_000_000, tz=UTC)

PM_TOKEN = "0xasset-btc-100k"
KALSHI_TICKER = "KXBTD-26JUN26-1000-C"


# ---------------------------------------------------------------------------
# watchlist parsing + board
# ---------------------------------------------------------------------------


class TestWatchlistParsing:
    def test_full_entry_with_expiry(self):
        pairs = parse_prediction_watchlist(
            "btc-100k:BTC above 100k:0xabc:KXBTD-26JUN26-1000-C:2026-06-26"
        )
        assert len(pairs) == 1
        pair = pairs[0]
        assert pair.event_key == "btc-100k"
        assert pair.title == "BTC above 100k"
        assert pair.symbols == {Venue.POLYMARKET: "0xabc", Venue.KALSHI: "KXBTD-26JUN26-1000-C"}
        assert pair.expiry == datetime(2026, 6, 26, tzinfo=UTC)

    def test_expiry_is_day_granular_utc(self):
        (pair,) = parse_prediction_watchlist("k:BTC:0x1:KX1:2026-06-26")
        assert pair.expiry == datetime(2026, 6, 26, tzinfo=UTC)

    def test_partial_venues_and_default_title(self):
        pairs = parse_prediction_watchlist(
            "pm1:First:0xone, ks1:Second::KXone, pm0::0xzero, "
            "bare:Default:0x2: :2026-06-26"
        )
        assert pairs[0].symbols == {Venue.POLYMARKET: "0xone"}
        assert pairs[0].title == "First"
        assert pairs[1].symbols == {Venue.KALSHI: "KXone"}
        assert pairs[1].title == "Second"
        assert pairs[2].symbols == {Venue.POLYMARKET: "0xzero"}
        assert pairs[2].title == "pm0"  # empty title defaults to the key
        assert pairs[3].symbols == {Venue.POLYMARKET: "0x2"}
        assert pairs[3].title == "Default"
        assert pairs[3].expiry == datetime(2026, 6, 26, tzinfo=UTC)

    def test_blanks_and_whitespace_are_skipped(self):
        pairs = parse_prediction_watchlist("  a:One:0x1,   ,b:Two::KX2  ")
        assert [p.event_key for p in pairs] == ["a", "b"]

    @pytest.mark.parametrize(
        "text,message",
        [
            ("", "empty"),
            (",,", "empty"),
            ("a:1:2:3:4:5", "more than 5"),
            (":title", "empty key"),
            ("dup:One:0x1,dup:Two", "repeats key"),
            ("nosymbols", "no venue symbol"),
            ("k:Title:0x1::nonsense-date", "not an ISO date"),
        ],
    )
    def test_refuses_malformed(self, text, message):
        with pytest.raises(ValueError, match=message):
            parse_prediction_watchlist(text)


class TestPredictionBoard:
    def test_validation(self):
        with pytest.raises(ValueError, match="at least one pair"):
            PredictionBoard([])
        bad_venue = PredictionPair(
            event_key="k",
            title="t",
            expiry=None,
            symbols={Venue.HYPERLIQUID: "BTC"},
        )
        with pytest.raises(ValueError, match="only .* stream here"):
            PredictionBoard([bad_venue])

    def test_venues_deduplicates(self):
        board = demo_board()
        by_venue = board.venues()
        assert by_venue[Venue.POLYMARKET] == ["0xasset-btc-100k", "0xasset-eth-5k", "0xasset-solo"]
        assert by_venue[Venue.KALSHI] == ["KXBTD-26JUN26-1000-C", "KXETHD-30SEP26-5000-C"]

    def test_render_unconfigured_venue_is_unavailable(self):
        rows = demo_board().render({"instruments": {}}, NOW)
        solo = next(r for r in rows if r["event_key"] == "solo-pm")
        pm, ks = solo["venues"]
        assert pm["venue"] == "polymarket" and pm["label"] == "unavailable"
        assert pm["probability"] is None
        assert ks["venue"] == "kalshi" and ks["symbol"] is None
        assert ks["label"] == "unavailable"
        assert solo["diff"] is None

    def test_render_full_surface(self):
        rows = demo_board().render(
            {
                "instruments": {
                    "polymarket:0xasset-btc-100k": {
                        "venue": "polymarket",
                        "kinds": {
                            "quote": {
                                "label": "real",
                                "payload": {
                                    "bid": 0.60,
                                    "ask": 0.65,
                                    "bid_size": 100.0,
                                    "ask_size": 75.0,
                                },
                            },
                            "l2_snapshot": {
                                "label": "real",
                                "payload": {
                                    "side": "bid",
                                    "levels": [[0.60, 100.0], [0.59, 50.0]],
                                },
                            },
                        },
                    },
                    "kalshi:KXBTD-26JUN26-1000-C": {
                        "venue": "kalshi",
                        "kinds": {
                            "quote": {
                                "label": "real",
                                "payload": {
                                    "bid": 0.60,
                                    "ask": 0.64,
                                    "bid_size": 100.0,
                                    "ask_size": 20.0,
                                },
                            }
                        },
                    },
                }
            },
            NOW,
        )
        row = next(r for r in rows if r["event_key"] == "btc-100k")
        assert row["title"] == "BTC above $100k on 2026-06-26"
        assert row["expiry"] == "2026-06-26T00:00:00+00:00"
        pm, ks = row["venues"]
        assert pm["probability"] == 62.5
        assert pm["spread_bps"] == pytest.approx(800.0, rel=1e-9)
        assert pm["depth"] == 175.0
        assert pm["liquidity"] == 150.0
        assert pm["label"] == "real"
        assert ks["probability"] == 62.0
        assert row["diff"] == pytest.approx(0.5, rel=1e-9)

    def test_render_diff_needs_both_venues(self):
        rows = demo_board().render(
            {
                "instruments": {
                    "polymarket:0xasset-solo": {
                        "venue": "polymarket",
                        "kinds": {
                            "quote": {
                                "label": "real",
                                "payload": {"bid": 0.6, "ask": 0.65},
                            }
                        },
                    }
                }
            },
            NOW,
        )
        solo = next(r for r in rows if r["event_key"] == "solo-pm")
        assert solo["venues"][0]["probability"] == 62.5
        assert solo["diff"] is None

    def test_render_carries_label_and_refuses_garbage(self):
        rows = demo_board().render(
            {
                "instruments": {
                    "polymarket:0xasset-btc-100k": {
                        "venue": "polymarket",
                        "kinds": {
                            "quote": {
                                "label": "stale",
                                "payload": {"bid": "not-a-number", "ask": 0.65},
                            }
                        },
                    }
                }
            },
            NOW,
        )
        pm = rows[0]["venues"][0]
        assert pm["label"] == "unavailable"  # malformed quote → no surface
        assert pm["probability"] is None


# ---------------------------------------------------------------------------
# helpers: frames + stub REST sources
# ---------------------------------------------------------------------------


def pm_book(
    token: str,
    *,
    bids: tuple = (("0.60", "100"), ("0.59", "50")),
    asks: tuple = (("0.65", "75"), ("0.66", "25")),
) -> dict:
    return {
        "event_type": "book",
        "asset_id": token,
        "timestamp": str(TS_US),
        "bids": [{"price": price, "size": size} for price, size in bids],
        "asks": [{"price": price, "size": size} for price, size in asks],
    }


def pm_price_change(token: str, changes: list[dict]) -> dict:
    return {
        "event_type": "price_change",
        "asset_id": token,
        "timestamp": str(TS_US),
        "price_changes": changes,
    }


def kalshi_frame(kind: str, ticker: str, msg: dict) -> dict:
    return {"type": kind, "ticker": ticker, "ts": TS_US, "msg": msg}


class StubBookSource:
    """Dict-backed REST book source; a missing token or ``raise_on``
    behaves exactly like a live fetch failure."""

    def __init__(self, books: dict[str, object] | None = None, *, raise_on: str | None = None):
        self._books = dict(books or {})
        self._raise_on = raise_on
        self.calls: list[str] = []

    def _get(self, key: str):
        self.calls.append(key)
        if self._raise_on == key:
            raise RuntimeError(f"fetch failed for {key}")
        if key not in self._books:
            raise KeyError(f"no book for {key}")
        return self._books[key]


class StubPMBookSource(StubBookSource):
    def clob_book(self, token_id: str):
        return self._get(token_id)


class StubKalshiBookSource(StubBookSource):
    def orderbook(self, ticker: str):
        return self._get(ticker)


def pm_book_snapshot(token: str = PM_TOKEN) -> ClobBook:
    return ClobBook(
        market="0xcondition",
        asset_id=token,
        timestamp=TS,
        hash="0xhash",
        bids=[ClobLevel(price=0.60, size=100.0), ClobLevel(price=0.59, size=50.0)],
        asks=[ClobLevel(price=0.65, size=75.0), ClobLevel(price=0.66, size=25.0)],
    )


def kalshi_book_snapshot(ticker: str = KALSHI_TICKER) -> KalshiOrderbook:
    return KalshiOrderbook(
        yes_dollars=[KalshiLevel(price=0.60, size=100.0), KalshiLevel(price=0.59, size=50.0)],
        no_dollars=[KalshiLevel(price=0.35, size=80.0), KalshiLevel(price=0.36, size=20.0)],
    )


def make_pm_supervisor(script, *, source: StubPMBookSource | None = None):
    supervisor = PolymarketVenueSupervisor(
        ScriptedVenueTransport(script), book_source=source, lag=timedelta(seconds=5)
    )
    supervisor.subscribe([PM_TOKEN])
    return supervisor


def make_kalshi_supervisor(script, *, source: StubKalshiBookSource | None = None):
    supervisor = KalshiVenueSupervisor(
        ScriptedVenueTransport(script), book_source=source, lag=timedelta(seconds=5)
    )
    supervisor.subscribe([KALSHI_TICKER])
    return supervisor


def kinds_by(snapshot: dict, symbol: str) -> dict:
    return snapshot["instruments"][symbol]["kinds"]


# ---------------------------------------------------------------------------
# Polymarket venue supervisor
# ---------------------------------------------------------------------------


class TestPolymarketSupervisor:
    def test_subscription_envelope(self):
        supervisor = make_pm_supervisor([])
        supervisor.on_open(NOW)
        transport = supervisor._transport
        assert transport.connected
        assert transport.sent == [
            {"method": "subscribe", "subscription": {"type": "market", "assets_ids": [PM_TOKEN]}}
        ]

    def test_book_frame_quote_and_l2(self):
        supervisor = make_pm_supervisor([])
        supervisor.on_open(NOW)
        supervisor.on_frame(pm_book(PM_TOKEN), NOW)
        updates = supervisor.drain()
        kinds = [u.kind for u in updates]
        assert kinds == [UpdateKind.L2_SNAPSHOT, UpdateKind.L2_SNAPSHOT, UpdateKind.QUOTE]
        bid, ask, quote = updates
        assert bid.payload == {
            "side": "bid",
            "levels": [(0.60, 100.0), (0.59, 50.0)],
        }
        assert ask.payload == {
            "side": "ask",
            "levels": [(0.65, 75.0), (0.66, 25.0)],
        }
        assert quote.payload == {
            "bid": 0.60,
            "ask": 0.65,
            "bid_size": 100.0,
            "ask_size": 75.0,
        }
        for update in updates:
            assert update.instrument == PM_TOKEN
            assert update.data_time == TS
            assert update.received_at == NOW
            assert update.sequence is None
            assert update.provenance.value == "real"

    def test_book_frame_deduplicates_and_drops_zero(self):
        supervisor = make_pm_supervisor([])
        supervisor.on_open(NOW)
        supervisor.on_frame(
            pm_book(
                PM_TOKEN,
                bids=(("0.60", "100"), ("0.60", "90"), ("0.59", "0")),
                asks=(("0.65", "0"),),
            ),
            NOW,
        )
        updates = supervisor.drain()
        # zero-size levels carry no liquidity; the ask ladder is empty,
        # so only the bid side (and no quote) is emitted — an empty
        # l2 payload would violate the contract.
        assert len(updates) == 1
        assert updates[0].payload["levels"] == [(0.60, 90.0)]

    def test_price_change_composes_sizes_from_book_state(self):
        supervisor = make_pm_supervisor([])
        supervisor.on_open(NOW)
        supervisor.on_frame(pm_book(PM_TOKEN), NOW)
        supervisor.drain()
        supervisor.on_frame(
            pm_price_change(PM_TOKEN, [{"price": "0.62", "side": "BUY"}]), NOW
        )
        (quote,) = supervisor.drain()
        assert quote.payload == {
            "bid": 0.62,
            "ask": 0.65,
            "bid_size": 100.0,
            "ask_size": 75.0,
        }

    def test_single_sided_price_change_waits_for_complete_touch(self):
        supervisor = make_pm_supervisor([])
        supervisor.on_open(NOW)
        supervisor.on_frame(pm_price_change(PM_TOKEN, [{"price": "0.62", "side": "BUY"}]), NOW)
        assert supervisor.drain() == []
        supervisor.on_frame(
            pm_price_change(PM_TOKEN, [{"price": "0.66", "side": "SELL"}]), NOW
        )
        (quote,) = supervisor.drain()
        assert quote.payload["bid"] == 0.62 and quote.payload["ask"] == 0.66
        assert "bid_size" not in quote.payload  # no book state yet — sizes stay honest

    @pytest.mark.parametrize(
        "frame,message",
        [
            ({"event_type": "nonsense", "asset_id": PM_TOKEN, "timestamp": TS_US}, "unknown"),
            (pm_book("0xunsubscribed"), "unsubscribed"),
            (pm_book(PM_TOKEN, bids=(("0.60", "-1"),)), "negative"),
            (pm_book(PM_TOKEN, bids=(("1.5", "10"),)), "outside"),
            ({"event_type": "book", "asset_id": PM_TOKEN, "timestamp": str(TS_US),
              "bids": "nope", "asks": []}, "expected a list"),
            (pm_price_change(PM_TOKEN, [{"price": "0.60", "side": "MID"}]), "unknown side"),
            (pm_price_change(
                PM_TOKEN,
                [{"price": "0.70", "side": "BUY"}, {"price": "0.60", "side": "SELL"}],
             ),
             "below bid"),
            ({"event_type": "book", "asset_id": PM_TOKEN, "bids": [], "asks": []},
             "timestamp"),
        ],
    )
    def test_protocol_errors_fail_closed(self, frame, message):
        supervisor = make_pm_supervisor([])
        supervisor.on_open(NOW)
        with pytest.raises(PolymarketProtocolError, match=message):
            supervisor.on_frame(frame, NOW)

    def test_tick_size_change_is_benign(self):
        supervisor = make_pm_supervisor([])
        supervisor.on_open(NOW)
        supervisor.on_frame(
            {"event_type": "tick_size_change", "asset_id": PM_TOKEN, "timestamp": TS_US}, NOW
        )
        assert supervisor.drain() == []

    def test_resync_seeds_depth_and_quote(self):
        source = StubPMBookSource({PM_TOKEN: pm_book_snapshot()})
        supervisor = make_pm_supervisor([], source=source)
        supervisor.on_open(NOW, reconnected=True)
        updates = supervisor.drain()
        assert [u.kind for u in updates] == [
            UpdateKind.L2_SNAPSHOT,
            UpdateKind.L2_SNAPSHOT,
            UpdateKind.QUOTE,
        ]
        supervisor.on_frame(
            pm_price_change(PM_TOKEN, [{"price": "0.61", "side": "SELL"}]), NOW
        )
        (quote,) = supervisor.drain()
        assert quote.payload["ask"] == 0.61
        assert quote.payload["ask_size"] == 75.0  # composed from the REST snapshot

    def test_resync_refuses_empty_book(self):
        source = StubPMBookSource(
            {PM_TOKEN: ClobBook(market="m", asset_id=PM_TOKEN, timestamp=TS, hash="h",
                                bids=[], asks=[])}
        )
        supervisor = make_pm_supervisor([], source=source)
        findings = supervisor.on_open(NOW, reconnected=True)
        assert supervisor.drain() == []
        assert [f.key for f in findings] == [PM_TOKEN]
        assert "no levels" in findings[0].message

    def test_resync_reports_fetch_failures(self):
        source = StubPMBookSource({PM_TOKEN: pm_book_snapshot()}, raise_on=PM_TOKEN)
        supervisor = make_pm_supervisor([], source=source)
        findings = supervisor.on_open(NOW, reconnected=True)
        assert supervisor.drain() == []
        assert findings[0].key == PM_TOKEN and "unavailable" in findings[0].message

    def test_resync_without_source_is_a_venue_finding(self):
        supervisor = make_pm_supervisor([])
        findings = supervisor.on_open(NOW, reconnected=True)
        assert [f.key for f in findings] == ["polymarket"]


# ---------------------------------------------------------------------------
# Kalshi venue supervisor
# ---------------------------------------------------------------------------


class TestKalshiSupervisor:
    def test_subscription_envelope(self):
        supervisor = make_kalshi_supervisor([])
        supervisor.on_open(NOW)
        assert supervisor._transport.sent == [
            {
                "id": 1,
                "cmd": "subscribe",
                "params": {
                    "channels": ["market", "orderbook_delta", "trades"],
                    "ticker": KALSHI_TICKER,
                },
            }
        ]

    def test_first_open_seeds_book_from_rest(self):
        source = StubKalshiBookSource({KALSHI_TICKER: kalshi_book_snapshot()})
        supervisor = make_kalshi_supervisor([], source=source)
        supervisor.on_open(NOW)
        updates = supervisor.drain()
        assert [u.kind for u in updates] == [
            UpdateKind.L2_SNAPSHOT,
            UpdateKind.L2_SNAPSHOT,
            UpdateKind.QUOTE,
        ]
        bid, ask, quote = updates
        assert bid.payload == {"side": "bid", "levels": [[0.60, 100.0], [0.59, 50.0]]}
        assert ask.payload == {"side": "ask", "levels": [[0.64, 20.0], [0.65, 80.0]]}
        assert quote.payload == {
            "bid": 0.60,
            "ask": 0.64,
            "bid_size": 100.0,
            "ask_size": 20.0,
        }
        assert source.calls == [KALSHI_TICKER]

    def test_deltas_apply_to_seeded_book(self):
        source = StubKalshiBookSource({KALSHI_TICKER: kalshi_book_snapshot()})
        supervisor = make_kalshi_supervisor([], source=source)
        supervisor.on_open(NOW)
        supervisor.drain()
        supervisor.on_frame(
            kalshi_frame(
                "orderbook_delta",
                KALSHI_TICKER,
                {"side": "yes", "delta": [{"price": 60, "count": -40}]},
            ),
            NOW,
        )
        supervisor.on_frame(
            kalshi_frame(
                "orderbook_delta",
                KALSHI_TICKER,
                {"side": "no", "delta": [{"price": 36, "count": -20}]},
            ),
            NOW,
        )
        updates = supervisor.drain()
        kinds = [u.kind for u in updates]
        assert kinds == [UpdateKind.L2_SNAPSHOT, UpdateKind.L2_SNAPSHOT, UpdateKind.QUOTE,
                         UpdateKind.L2_SNAPSHOT, UpdateKind.L2_SNAPSHOT, UpdateKind.QUOTE]
        assert updates[-1].payload == {
            "bid": 0.60,
            "ask": 0.65,
            "bid_size": 60.0,
            "ask_size": 80.0,
        }
        # after the 36¢ NO level is removed the ask ladder is just the
        # 35¢ complement at 0.65 (second frame's ask snapshot)
        assert updates[4].payload["levels"] == [[0.65, 80.0]]

    def test_delta_removal_of_unseen_level_fails_closed(self):
        source = StubKalshiBookSource({KALSHI_TICKER: kalshi_book_snapshot()})
        supervisor = make_kalshi_supervisor([], source=source)
        supervisor.on_open(NOW)
        supervisor.drain()
        with pytest.raises(KalshiProtocolError, match="never saw"):
            supervisor.on_frame(
                kalshi_frame(
                    "orderbook_delta",
                    KALSHI_TICKER,
                    {"side": "no", "delta": [{"price": 50, "count": -5}]},
                ),
                NOW,
            )

    def test_deltas_before_seed_are_ignored(self):
        supervisor = make_kalshi_supervisor([])  # no REST source
        supervisor.on_open(NOW)
        supervisor.drain()
        supervisor.on_frame(
            kalshi_frame(
                "orderbook_delta",
                KALSHI_TICKER,
                {"side": "yes", "delta": [{"price": 60, "count": 100}]},
            ),
            NOW,
        )
        assert supervisor.drain() == []

    def test_market_metrics(self):
        source = StubKalshiBookSource({KALSHI_TICKER: kalshi_book_snapshot()})
        supervisor = make_kalshi_supervisor([], source=source)
        supervisor.on_open(NOW)
        supervisor.drain()
        supervisor.on_frame(
            kalshi_frame(
                "market",
                KALSHI_TICKER,
                {"last_price": 62, "volume": 12_345, "open_interest": 2_345},
            ),
            NOW,
        )
        (update,) = supervisor.drain()
        assert update.kind is UpdateKind.METRICS
        assert update.payload == {"last": 0.62, "volume": 12_345, "open_interest": 2_345}
        assert update.data_time == TS

    def test_market_metrics_fail_closed(self):
        supervisor = make_kalshi_supervisor([])
        supervisor.on_open(NOW)
        with pytest.raises(KalshiProtocolError, match="last_price"):
            supervisor.on_frame(
                kalshi_frame("market", KALSHI_TICKER, {"volume": 1}), NOW
            )
        with pytest.raises(KalshiProtocolError, match="volume"):
            supervisor.on_frame(
                kalshi_frame("market", KALSHI_TICKER, {"last_price": 62, "volume": "x"}),
                NOW,
            )

    def test_trades_normalize_with_complementary_price(self):
        supervisor = make_kalshi_supervisor([])
        supervisor.on_open(NOW)
        supervisor.on_frame(
            kalshi_frame(
                "trade",
                KALSHI_TICKER,
                {
                    "yes_price": 62,
                    "no_price": 38,
                    "taker_side": "yes",
                    "count": 15,
                    "created_time": TS_US,
                },
            ),
            NOW,
        )
        (update,) = supervisor.drain()
        assert update.kind is UpdateKind.TRADE
        assert update.payload == {"price": 0.62, "size": 15, "side": "buy"}
        supervisor.on_frame(
            kalshi_frame(
                "trade",
                KALSHI_TICKER,
                {
                    "yes_price": 62,
                    "no_price": 38,
                    "taker_side": "no",
                    "count": 7,
                    "created_time": TS_US,
                },
            ),
            NOW,
        )
        (update,) = supervisor.drain()
        assert update.payload == {"price": 0.38, "size": 7, "side": "sell"}

    def test_crossed_book_emits_no_quote(self):
        source = StubKalshiBookSource(
            {
                KALSHI_TICKER: KalshiOrderbook(
                    yes_dollars=[KalshiLevel(price=0.60, size=10.0)],
                    no_dollars=[KalshiLevel(price=1.0, size=10.0)],  # derived ask = 0
                )
            }
        )
        supervisor = make_kalshi_supervisor([], source=source)
        supervisor.on_open(NOW)
        updates = supervisor.drain()
        assert [u.kind for u in updates] == [UpdateKind.L2_SNAPSHOT]  # bid only
        assert updates[0].payload["levels"] == [[0.60, 10.0]]

    def test_reconnect_refetches_snapshot(self):
        source = StubKalshiBookSource({KALSHI_TICKER: kalshi_book_snapshot()})
        supervisor = make_kalshi_supervisor([], source=source)
        supervisor.on_open(NOW)
        supervisor.drain()
        # the venue's book moved while we were away
        source._books[KALSHI_TICKER] = KalshiOrderbook(
            yes_dollars=[KalshiLevel(price=0.70, size=5.0)],
            no_dollars=[KalshiLevel(price=0.29, size=5.0)],
        )
        supervisor._transport.connected = False
        supervisor.on_open(NOW, reconnected=True)
        updates = supervisor.drain()
        assert updates[-1].payload == {"bid": 0.70, "ask": 0.71, "bid_size": 5.0, "ask_size": 5.0}

    def test_resync_failure_blocks_deltas(self):
        source = StubKalshiBookSource({KALSHI_TICKER: kalshi_book_snapshot()},
                                      raise_on=KALSHI_TICKER)
        supervisor = make_kalshi_supervisor([], source=source)
        findings = supervisor.on_open(NOW)
        assert supervisor.drain() == []
        assert findings[0].key == KALSHI_TICKER and "unavailable" in findings[0].message
        supervisor.on_frame(
            kalshi_frame(
                "orderbook_delta",
                KALSHI_TICKER,
                {"side": "yes", "delta": [{"price": 60, "count": 100}]},
            ),
            NOW,
        )
        assert supervisor.drain() == []

    def test_no_source_reports_venue_finding(self):
        supervisor = make_kalshi_supervisor([])
        findings = supervisor.on_open(NOW)
        assert [f.key for f in findings] == ["kalshi"]

    @pytest.mark.parametrize(
        "frame,message",
        [
            ({"type": "nonsense", "ticker": KALSHI_TICKER, "ts": TS_US}, "unknown"),
            (kalshi_frame("market", "KXUNKNOWN", {"last_price": 1}), "unsubscribed"),
            (kalshi_frame("orderbook_delta", KALSHI_TICKER, {"side": "maybe"}), "side"),
            (kalshi_frame("trade", KALSHI_TICKER, {"taker_side": "maybe"}), "taker_side"),
            (kalshi_frame("trade", KALSHI_TICKER, {"taker_side": "yes", "count": 1}),
             "created_time"),
            ({"type": "market", "ticker": KALSHI_TICKER, "msg": {}}, "ts"),
        ],
    )
    def test_protocol_errors_fail_closed(self, frame, message):
        supervisor = make_kalshi_supervisor(
            [], source=StubKalshiBookSource({KALSHI_TICKER: kalshi_book_snapshot()})
        )
        supervisor.on_open(NOW)
        supervisor.drain()  # seeded: delta frames reach the side check
        with pytest.raises(KalshiProtocolError, match=message):
            supervisor.on_frame(frame, NOW)


# ---------------------------------------------------------------------------
# integration: both venues → feed → board
# ---------------------------------------------------------------------------


class TestPredictionPipeline:
    def _feed(self, tmp_path) -> LiveFeed:
        return LiveFeed(
            lake=LiveBuffer(root=str(tmp_path / "lake")),
            lag=timedelta(seconds=5),
            stale=timedelta(seconds=10),
        )

    def test_both_venues_stream_into_one_board(self, tmp_path):
        feed = self._feed(tmp_path)
        pm = make_pm_supervisor([], source=StubPMBookSource({PM_TOKEN: pm_book_snapshot()}))
        ks = make_kalshi_supervisor(
            [], source=StubKalshiBookSource({KALSHI_TICKER: kalshi_book_snapshot()})
        )
        for supervisor in (pm, ks):
            feed.attach(supervisor)
        pm.on_open(NOW)
        ks.on_open(NOW)
        pm.on_frame(pm_book(PM_TOKEN), NOW)
        feed.ingest(pm.drain() + ks.drain())
        pm.on_frame(
            pm_price_change(PM_TOKEN, [{"price": "0.62", "side": "BUY"}]), NOW
        )
        ks.on_frame(
            kalshi_frame(
                "orderbook_delta",
                KALSHI_TICKER,
                {"side": "yes", "delta": [{"price": 60, "count": -40}]},
            ),
            NOW,
        )
        feed.ingest(pm.drain() + ks.drain())

        board = PredictionBoard(
            [
                PredictionPair(
                    event_key="btc-100k",
                    title="BTC above $100k",
                    expiry=None,
                    symbols={Venue.POLYMARKET: PM_TOKEN, Venue.KALSHI: KALSHI_TICKER},
                )
            ]
        )
        snapshot = feed.latest_state(now=NOW)
        rows = board.render(snapshot, NOW)
        (row,) = rows
        pm_row, ks_row = row["venues"]
        assert pm_row["label"] == "real"
        assert pm_row["probability"] == 63.5  # (0.62 + 0.65) / 2
        assert pm_row["depth"] == 175.0
        assert ks_row["probability"] == 62.0
        assert row["diff"] == pytest.approx(1.5, rel=1e-9)

    def test_quiet_venues_go_stale_through_the_feed(self, tmp_path):
        feed = self._feed(tmp_path)
        pm = make_pm_supervisor([], source=StubPMBookSource({PM_TOKEN: pm_book_snapshot()}))
        feed.attach(pm)
        pm.on_open(NOW)
        pm.on_frame(pm_book(PM_TOKEN), NOW)
        feed.ingest(pm.drain())
        later = NOW + timedelta(seconds=6)
        snapshot = feed.latest_state(now=later)
        board = demo_board()
        row = next(r for r in board.render(snapshot, later) if r["event_key"] == "btc-100k")
        assert row["venues"][0]["label"] == "stale"
