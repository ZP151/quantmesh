"""Hyperliquid venue supervisor (iteration 0015 Phase B, ADR-0014).

Subscribes the 4–8 perp watchlist over the official public WebSocket
(candle/l2Book/trades/bbo/activeAssetCtx per coin, allMids once),
normalizes every frame into the owned ``MarketUpdate`` contract and
recovers on reconnect exactly like the M5 ``StreamSupervisor``: REST
candle backfill over the dark window, book snapshot replace, trades
reported as an unhealable gap, and per-coin sequence continuity
detection. Every frame that does not match a subscription raises
``HyperliquidProtocolError`` — a stream that silently drops frames is
worse than one that stops.

The wire parsers (``quantmesh.hyperliquid.wire``) and the REST surface
are reused as-is; ``ScriptedHyperliquidTransport`` drives the drills
deterministically, mirroring ``SimulatedStreamTransport``.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from quantmesh.domain.market_data import Bar
from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.hyperliquid.errors import HyperliquidProtocolError
from quantmesh.hyperliquid.identity import (
    book_side_source_event_id,
    book_snapshot_epoch,
    trade_source_event_id,
)
from quantmesh.hyperliquid.rest import RestTransport, to_ms
from quantmesh.hyperliquid.wire import (
    parse_all_mids,
    parse_asset_ctx_map,
    parse_bbo_frame,
    parse_candle_frame,
    parse_l2_book_frame,
    parse_trades_frame,
)
from quantmesh.live.contract import (
    ContinuityEvidence,
    ContinuityState,
    MarketUpdate,
    Provenance,
    SourceState,
    UpdateKind,
)
from quantmesh.live.supervisor import GapFinding, VenueSupervisor

_CANDLE_INTERVAL = "1m"
_RESYNC_WINDOW = timedelta(minutes=5)  # REST candle backfill window on reconnect
_RESYNC_MAX_CANDLES = 5_000


@dataclass(frozen=True)
class CandleObservation:
    rows: list[dict]
    requested_at: datetime
    received_at: datetime


def _instrument(coin: str) -> Instrument:
    return Instrument(
        symbol=coin,
        venue=Venue.HYPERLIQUID,
        instrument_type=InstrumentType.PERPETUAL,
        currency="USD",
    )


def _update(
    instrument: Instrument,
    kind: UpdateKind,
    payload: dict,
    *,
    data_time: datetime,
    sequence: int | None = None,
    continuity: ContinuityState = ContinuityState.COMPLETE,
    source_event_id: str | None = None,
    snapshot_epoch: str | None = None,
    continuity_evidence: ContinuityEvidence | None = None,
    received_at: datetime | None = None,
) -> MarketUpdate:
    return MarketUpdate(
        venue=Venue.HYPERLIQUID,
        instrument=instrument.symbol,
        kind=kind,
        provenance=Provenance.REAL,
        data_time=data_time,
        sequence=sequence,
        continuity=continuity,
        source_event_id=source_event_id,
        snapshot_epoch=snapshot_epoch,
        continuity_evidence=continuity_evidence,
        payload=payload,
        **({"received_at": received_at} if received_at is not None else {}),
    )


def _levels(rows: list) -> list[list[float]]:
    return [[level.price, level.quantity] for level in rows]


def _source_id(value: object) -> str:
    canonical = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _local_metrics_source_id(
    coin: str, channel: str, observed_at: datetime, payload: dict[str, float]
) -> str:
    # These channels have no provider event clock/ID. Preserve the same full
    # local observation time and normalized content that the replay digest uses.
    return _source_id(
        [
            "hl-local-observation-v2",
            coin,
            channel,
            observed_at.astimezone(UTC).isoformat(),
            sorted(payload.items()),
        ]
    )


def _candle_source_id(coin: str, bar: Bar, *, final: bool) -> str:
    # Elapsed close time does not make upstream OHLCV immutable (ADR-0024).
    # Qualify each observation by content identically for WebSocket and REST.
    return _source_id(
        [
            int(to_ms(bar.timestamp)),
            coin,
            _CANDLE_INTERVAL,
            "final" if final else "provisional",
            [bar.open, bar.high, bar.low, bar.close, bar.volume],
        ]
    )


class HyperliquidVenueSupervisor(VenueSupervisor):
    """Normalizes the Hyperliquid public stream into ``MarketUpdate``s.

    Watchlist symbols are perp coins (``"BTC"``, ``"ETH"``, …).
    ``resync`` needs a REST transport; when the watchlist is configured
    without one (drills), reconnects report the recovery gaps without
    REST healing.
    """

    @property
    def venue(self) -> Venue:
        return Venue.HYPERLIQUID

    def __init__(
        self,
        transport,
        *,
        rest: RestTransport | None = None,
        candle_only: bool = False,
        candle_recovery_limit: int = 5,
        **kwargs,
    ) -> None:
        super().__init__(transport, **kwargs)
        if candle_only and (
            type(candle_recovery_limit) is not int or not 1 <= candle_recovery_limit <= 5
        ):
            raise ValueError("market_data_configuration_invalid")
        self.candle_only = candle_only
        self.resync_request_limit = candle_recovery_limit if candle_only else _RESYNC_MAX_CANDLES
        self.observation_issue = None
        self._sample_current_open = None
        self._observation_baseline = None
        self._attempted_through = None
        self._mode_last_status = None
        self._rest = rest
        self._coins: list[str] = []
        self._last_trade_identity: dict[str, str] = {}
        self._last_candle_open: dict[str, datetime] = {}
        self._continuity_pending: dict[tuple[str, str], ContinuityState] = {}
        self._last_event_id: dict[tuple[str, str], str] = {}
        self._disconnect_context: dict[tuple[str, str], tuple[datetime, str | None]] = {}

    def specs(self, watchlist: list[str]) -> dict[str, dict]:
        """identifier -> subscription spec (the SDK's identifier rules)."""
        self._coins = list(watchlist)
        if self.candle_only:
            if watchlist != ["BTC"]:
                raise ValueError("market_data_configuration_invalid")
            return {"candle:btc,1m": {"type": "candle", "coin": "BTC", "interval": "1m"}}
        specs: dict[str, dict] = {}
        for coin in watchlist:
            specs[f"candle:{coin.lower()},{_CANDLE_INTERVAL}"] = {
                "type": "candle",
                "coin": coin,
                "interval": _CANDLE_INTERVAL,
            }
            specs[f"l2Book:{coin.lower()}"] = {"type": "l2Book", "coin": coin}
            specs[f"trades:{coin.lower()}"] = {"type": "trades", "coin": coin}
            specs[f"bbo:{coin.lower()}"] = {"type": "bbo", "coin": coin}
            specs[f"activeAssetCtx:{coin.lower()}"] = {"type": "activeAssetCtx", "coin": coin}
        specs["allMids"] = {"type": "allMids"}
        return specs

    # -- dispatch -------------------------------------------------------------

    def dispatch(self, frame: object, now: datetime) -> list[MarketUpdate]:
        if self.candle_only:
            try:
                return self._dispatch_observation(frame, now)
            except Exception:
                raise HyperliquidProtocolError("market_data_frame_invalid") from None
        if not isinstance(frame, dict):
            raise HyperliquidProtocolError(f"frame must be an object, got {type(frame).__name__}")
        channel = frame.get("channel")
        if channel == "pong":
            return []
        if channel == "subscriptionResponse":
            response = frame.get("data")
            subscription = response.get("subscription") if isinstance(response, dict) else None
            if (
                not isinstance(response, dict)
                or response.get("method") != "subscribe"
                or not isinstance(subscription, dict)
                or not any(
                    all(subscription.get(key) == value for key, value in spec.items())
                    for spec in self._subscribed.values()
                )
            ):
                raise HyperliquidProtocolError("invalid or unsolicited subscription acknowledgment")
            return []
        identifier = _frame_identifier(frame)
        if identifier == "trades" and frame.get("data") == []:
            return []  # empty trades frames carry no coin; the SDK skips them too
        if identifier not in self._subscribed:
            raise HyperliquidProtocolError(
                f"frame for unsubscribed identifier {identifier!r} (channel {channel!r})"
            )
        if identifier.startswith("candle:"):
            return self._on_candle(identifier, frame.get("data"), now)
        if identifier.startswith("l2Book:"):
            return self._on_book(identifier, frame.get("data"), now)
        if identifier.startswith("trades:"):
            return self._on_trades(identifier, frame.get("data"), now)
        if identifier.startswith("bbo:"):
            return self._on_bbo(identifier, frame.get("data"), now)
        if identifier == "allMids":
            return self._on_all_mids(frame.get("data"), now)
        if identifier.startswith("activeAssetCtx:"):
            return self._on_asset_ctx(frame.get("data"), now)
        raise HyperliquidProtocolError(
            f"frame for unsubscribed identifier {identifier!r} (channel {channel!r})"
        )

    def _on_candle(self, identifier: str, data: object, now: datetime) -> list[MarketUpdate]:
        coin = identifier.split(":")[1].rsplit(",", 1)[0].upper()
        bar = parse_candle_frame(data, _instrument(coin), interval=_CANDLE_INTERVAL)
        final = bar.timestamp + timedelta(minutes=1) <= now
        source_event_id = _candle_source_id(coin, bar, final=final)
        continuity, evidence = self._resume_evidence(
            coin,
            "candle",
            source_event_id,
            now,
            recovery_source="hyperliquid-websocket",
            consume=final,
            durable=final,
        )
        return [
            _update(
                _instrument(coin),
                UpdateKind.CANDLE,
                {
                    "interval": _CANDLE_INTERVAL,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                    "final": final,
                },
                data_time=bar.timestamp,
                sequence=int(to_ms(bar.timestamp)),
                continuity=continuity,
                source_event_id=source_event_id,
                continuity_evidence=evidence,
            )
        ]

    def _on_book(self, identifier: str, data: object, now: datetime) -> list[MarketUpdate]:
        coin = identifier.split(":")[1].upper()
        book = parse_l2_book_frame(data, _instrument(coin))
        bids = _levels(book.bids)
        asks = _levels(book.asks)
        epoch = book_snapshot_epoch(int(to_ms(book.timestamp)), coin, bids, asks)
        bid_id = book_side_source_event_id(epoch, "bid")
        ask_id = book_side_source_event_id(epoch, "ask")
        continuity, evidence = self._resume_evidence(
            coin,
            "l2Book",
            bid_id,
            now,
            recovery_source="hyperliquid-websocket",
        )
        return [
            _update(
                _instrument(coin),
                UpdateKind.L2_SNAPSHOT,
                {"side": "bid", "levels": bids},
                data_time=book.timestamp,
                continuity=continuity,
                snapshot_epoch=epoch,
                source_event_id=bid_id,
                continuity_evidence=evidence,
            ),
            _update(
                _instrument(coin),
                UpdateKind.L2_SNAPSHOT,
                {"side": "ask", "levels": asks},
                data_time=book.timestamp,
                continuity=continuity,
                snapshot_epoch=epoch,
                source_event_id=ask_id,
                continuity_evidence=evidence,
            ),
        ]

    def _on_trades(self, identifier: str, data: object, now: datetime) -> list[MarketUpdate]:
        coin = identifier.split(":")[1].upper()
        events = parse_trades_frame(data, _instrument(coin))
        updates: list[MarketUpdate] = []
        for event in events:
            tid = event.venue_sequence
            if tid is None:
                raise HyperliquidProtocolError("trade is missing its provider tid identity")
            block_time = int(to_ms(event.timestamp))
            source_event_id = trade_source_event_id(block_time, coin, tid)
            continuity, evidence = self._resume_evidence(
                coin,
                "trades",
                source_event_id,
                now,
                recovery_source="unavailable-no-public-trade-history",
            )
            updates.append(
                _update(
                    _instrument(coin),
                    UpdateKind.TRADE,
                    {
                        "price": event.price,
                        "size": event.quantity,
                        "side": (
                            "buy" if event.aggressor_side is None else event.aggressor_side.value
                        ),
                        "tid": tid,
                        "block_time_ms": block_time,
                    },
                    data_time=event.timestamp,
                    sequence=tid,
                    continuity=continuity,
                    source_event_id=source_event_id,
                    continuity_evidence=evidence,
                )
            )
        return updates

    def _resume_evidence(
        self,
        coin: str,
        channel: str,
        source_event_id: str,
        now: datetime,
        *,
        recovery_source: str,
        consume: bool = True,
        durable: bool = True,
    ) -> tuple[ContinuityState, ContinuityEvidence | None]:
        del consume, durable  # acknowledgement, not parsing, advances durable state
        continuity = self._continuity_pending.get((coin, channel), ContinuityState.COMPLETE)
        evidence = None
        if continuity is not ContinuityState.COMPLETE:
            disconnected_at, last_id = self._disconnect_context.get(
                (coin, channel), (now, self._last_event_id.get((coin, channel)))
            )
            evidence = ContinuityEvidence(
                channel=channel,
                disconnected_at=disconnected_at,
                last_durable_source_event_id=last_id,
                first_recovered_source_event_id=source_event_id,
                recovered_at=now,
                recovery_source=recovery_source,
            )
        return continuity, evidence

    def on_persisted(self, updates: list[MarketUpdate]) -> None:
        """Advance reconnect cursors only after LiveBuffer commits the rows."""
        acknowledged: set[tuple[str, str]] = set()
        for update in updates:
            if update.venue is not Venue.HYPERLIQUID or not update.source_event_id:
                continue
            coin = update.instrument
            channel: str | None = None
            if update.kind is UpdateKind.CANDLE and update.payload.get("final") is True:
                channel = "candle"
                if update.continuity not in (
                    ContinuityState.KNOWN_GAP,
                    ContinuityState.UNRECOVERABLE,
                ):
                    self._last_candle_open[coin] = update.data_time
                else:
                    # The row is durable evidence of an unresolved hole, not
                    # proof that the channel resumed continuous delivery.
                    self._last_event_id[(coin, channel)] = update.source_event_id
                    continue
            elif update.kind is UpdateKind.L2_SNAPSHOT:
                channel = "l2Book"
            elif update.kind is UpdateKind.TRADE:
                channel = "trades"
                self._last_trade_identity[coin] = update.source_event_id
            elif update.kind is UpdateKind.QUOTE:
                channel = "bbo"
            elif update.kind is UpdateKind.METRICS:
                channel = "allMids" if set(update.payload) == {"mid"} else "activeAssetCtx"
            if channel is None:
                continue
            self._last_event_id[(coin, channel)] = update.source_event_id
            acknowledged.add((coin, channel))
        for key in acknowledged:
            self._continuity_pending.pop(key, None)
            self._disconnect_context.pop(key, None)

    def on_disconnect(self, now: datetime) -> list[GapFinding]:
        if self.candle_only:
            self._continuity_pending[("BTC", "candle")] = ContinuityState.UNKNOWN_AFTER_DISCONNECT
            self._disconnect_context[("BTC", "candle")] = (
                now,
                self._last_event_id.get(("BTC", "candle")),
            )
            self._sample_current_open = None
            self.connected = False
            findings, self._gap_pending = self._gap_pending, []
            for key, state, note in self._freshness.transitions(
                self._source_keys(), now, connected=False
            ):
                self._mode_status(state, note, now)
            return findings
        for coin in self._coins:
            for channel in (
                "candle",
                "l2Book",
                "bbo",
                "allMids",
                "activeAssetCtx",
            ):
                self._continuity_pending[(coin, channel)] = ContinuityState.UNKNOWN_AFTER_DISCONNECT
                self._disconnect_context[(coin, channel)] = (
                    now,
                    self._last_event_id.get((coin, channel)),
                )
            self._continuity_pending[(coin, "trades")] = ContinuityState.UNRECOVERABLE
            self._disconnect_context[(coin, "trades")] = (
                now,
                self._last_event_id.get((coin, "trades")),
            )
        return super().on_disconnect(now)

    def _on_bbo(self, identifier: str, data: object, now: datetime) -> list[MarketUpdate]:
        coin = identifier.split(":")[1].upper()
        payload = parse_bbo_frame(data)
        assert isinstance(data, dict)
        data_time = _frame_time(data)
        if payload is None:
            return []
        source_event_id = _source_id([int(to_ms(data_time)), coin, "bbo", payload])
        continuity, evidence = self._resume_evidence(
            coin,
            "bbo",
            source_event_id,
            now,
            recovery_source="hyperliquid-websocket",
        )
        return [
            _update(
                _instrument(coin),
                UpdateKind.QUOTE,
                payload,
                data_time=data_time,
                continuity=continuity,
                source_event_id=source_event_id,
                continuity_evidence=evidence,
            )
        ]

    def _on_all_mids(self, data: object, now: datetime) -> list[MarketUpdate]:
        mids = parse_all_mids(data)
        updates: list[MarketUpdate] = []
        for coin, price in mids.items():
            if coin not in self._coins:
                continue
            payload = {"mid": price}
            source_event_id = _local_metrics_source_id(coin, "allMids", now, payload)
            continuity, evidence = self._resume_evidence(
                coin,
                "allMids",
                source_event_id,
                now,
                recovery_source="hyperliquid-websocket",
            )
            updates.append(
                _update(
                    _instrument(coin),
                    UpdateKind.METRICS,
                    payload,
                    data_time=now,
                    continuity=continuity,
                    source_event_id=source_event_id,
                    continuity_evidence=evidence,
                )
            )
        return updates

    def _on_asset_ctx(self, data: object, now: datetime) -> list[MarketUpdate]:
        ctx = parse_asset_ctx_map(data)
        updates: list[MarketUpdate] = []
        for coin, metrics in ctx.items():
            if coin not in self._coins:
                continue
            source_event_id = _local_metrics_source_id(coin, "activeAssetCtx", now, metrics)
            continuity, evidence = self._resume_evidence(
                coin,
                "activeAssetCtx",
                source_event_id,
                now,
                recovery_source="hyperliquid-websocket",
            )
            updates.append(
                _update(
                    _instrument(coin),
                    UpdateKind.METRICS,
                    metrics,
                    data_time=now,
                    continuity=continuity,
                    source_event_id=source_event_id,
                    continuity_evidence=evidence,
                )
            )
        return updates

    # -- reconnect recovery -----------------------------------------------------

    def resync(self, now: datetime) -> list[MarketUpdate]:
        """REST-heal the channels that went dark; report unhealable gaps."""
        if self.candle_only:
            return self._resync_observations(now)
        if self._rest is None:
            self._gap_pending.append(
                GapFinding("hyperliquid", "no REST transport; reconnect gaps reported only")
            )
            for coin in self._coins:
                self._gap_pending.append(
                    GapFinding(
                        coin,
                        "disconnect continuity is unknown; trades are unrecoverable",
                    )
                )
            return []
        updates: list[MarketUpdate] = []
        for coin in self._coins:
            instrument = _instrument(coin)
            durable_start = self._last_candle_open.get(coin)
            if durable_start is None:
                start = _floor_minute(now) - _RESYNC_WINDOW
            else:
                start = durable_start + timedelta(minutes=1)
            final_open = _floor_minute(now) - timedelta(minutes=1)
            expected_count = _minute_open_count(start, final_open)
            expected_opens = (
                _minute_opens(start, expected_count)
                if expected_count <= _RESYNC_MAX_CANDLES
                else []
            )
            bars = []
            recovery_state = ContinuityState.KNOWN_GAP
            if expected_count > _RESYNC_MAX_CANDLES:
                self._continuity_pending[(coin, "candle")] = ContinuityState.UNRECOVERABLE
                self._gap_pending.append(
                    GapFinding(
                        coin,
                        "candle outage exceeds the 5,000-row public recovery horizon",
                    )
                )
            elif expected_opens:
                try:
                    rows = self._rest.candles(coin, _CANDLE_INTERVAL, start=start, end=final_open)
                    parsed = [
                        parse_candle_frame(row, instrument, interval=_CANDLE_INTERVAL)
                        for row in rows
                    ]
                    expected_set = set(expected_opens)
                    finalized = [bar for bar in parsed if bar.timestamp <= final_open]
                    bars = [bar for bar in finalized if bar.timestamp in expected_set]
                    exact = [bar.timestamp for bar in finalized] == expected_opens
                    if exact and durable_start is not None:
                        recovery_state = ContinuityState.RECOVERED
                    else:
                        self._gap_pending.append(
                            GapFinding(
                                coin,
                                "candle re-sync did not prove the complete outage window",
                            )
                        )
                except Exception as error:  # network and protocol both fail closed
                    self._gap_pending.append(
                        GapFinding(coin, f"candle re-sync unavailable: {error}")
                    )
                self._continuity_pending[(coin, "candle")] = recovery_state
            batch_evidence: ContinuityEvidence | None = None
            for index, bar in enumerate(bars):
                source_event_id = _candle_source_id(coin, bar, final=True)
                if index == 0:
                    continuity, evidence = self._resume_evidence(
                        coin,
                        "candle",
                        source_event_id,
                        now,
                        recovery_source="hyperliquid-public-info",
                    )
                    batch_evidence = evidence
                else:
                    continuity, evidence = recovery_state, batch_evidence
                updates.append(
                    _update(
                        instrument,
                        UpdateKind.CANDLE,
                        {
                            "interval": _CANDLE_INTERVAL,
                            "open": bar.open,
                            "high": bar.high,
                            "low": bar.low,
                            "close": bar.close,
                            "volume": bar.volume,
                            "final": True,
                        },
                        data_time=bar.timestamp,
                        sequence=int(to_ms(bar.timestamp)),
                        continuity=continuity,
                        source_event_id=source_event_id,
                        continuity_evidence=evidence,
                    )
                )
            try:
                snapshot = self._rest.l2_book(coin, at=now)
                book = parse_l2_book_frame(snapshot, instrument)
                bids = _levels(book.bids)
                asks = _levels(book.asks)
                epoch = book_snapshot_epoch(int(to_ms(book.timestamp)), coin, bids, asks)
                bid_id = book_side_source_event_id(epoch, "bid")
                ask_id = book_side_source_event_id(epoch, "ask")
                continuity, evidence = self._resume_evidence(
                    coin,
                    "l2Book",
                    bid_id,
                    now,
                    recovery_source="hyperliquid-public-info",
                )
                continuity = ContinuityState.RECOVERED
                updates.extend(
                    [
                        _update(
                            instrument,
                            UpdateKind.L2_SNAPSHOT,
                            {"side": "bid", "levels": bids},
                            data_time=book.timestamp,
                            continuity=continuity,
                            snapshot_epoch=epoch,
                            source_event_id=bid_id,
                            continuity_evidence=evidence,
                        ),
                        _update(
                            instrument,
                            UpdateKind.L2_SNAPSHOT,
                            {"side": "ask", "levels": asks},
                            data_time=book.timestamp,
                            continuity=continuity,
                            snapshot_epoch=epoch,
                            source_event_id=ask_id,
                            continuity_evidence=evidence,
                        ),
                    ]
                )
            except Exception as error:
                self._gap_pending.append(GapFinding(coin, f"book re-sync unavailable: {error}"))
            if coin in self._last_trade_identity:
                self._gap_pending.append(
                    GapFinding(
                        coin,
                        "trades cannot be REST re-synced; last durable event is "
                        f"{self._last_trade_identity[coin]}",
                    )
                )
        return updates

    def on_frame(self, frame: object, now: datetime) -> None:
        if not self.candle_only:
            return super().on_frame(frame, now)
        updates = self.dispatch(frame, now)
        self._push_many(updates)
        if isinstance(frame, dict) and frame.get("channel") == "candle":
            # Valid filtered interims renew connector liveness only. No event,
            # source identity or durable sequence is created for their prices.
            self._freshness.note_activity("BTC", now)

    async def run(self) -> None:
        if not self.candle_only:
            return await super().run()
        try:
            await super().run()
        finally:
            # Cancellation joins the actual socket owner as well as the feed.
            self.close(datetime.now(UTC))

    def on_tick(self, now: datetime) -> None:
        if not self.candle_only:
            return super().on_tick(now)
        if self.connected:
            for _key, state, note in self._freshness.transitions(
                self._source_keys(), now, connected=True
            ):
                if state is SourceState.CONNECTED and self.observation_issue:
                    state, note = SourceState.LAGGING, self.observation_issue
                self._mode_status(state, note, now)

    def _mode_status(self, state, note, now):
        if state is SourceState.CONNECTED:
            note = None  # healthy note wording is not a persistent state transition
        key = (state, note)
        if key != self._mode_last_status:
            self._push(self._status("BTC", state, note, now))
            self._mode_last_status = key

    def _observation_problem(self, code, now):
        changed = self.observation_issue != code
        self.observation_issue = code
        self._continuity_pending[("BTC", "candle")] = ContinuityState.KNOWN_GAP
        if changed:
            self._gap_pending.append(GapFinding("BTC", code))
        self._mode_status(SourceState.LAGGING, code, now)

    def _dispatch_observation(self, frame, now):
        if not isinstance(frame, dict) or now.utcoffset() != timedelta(0):
            raise ValueError
        if frame.get("channel") in {"pong", "subscriptionResponse"}:
            return []
        if frame.get("channel") != "candle":
            raise ValueError
        data = frame.get("data")
        if not isinstance(data, dict) or data.get("s") != "BTC" or data.get("i") != "1m":
            raise ValueError
        bar = parse_candle_frame(data, _instrument("BTC"), interval="1m")
        current = _floor_minute(now)
        if bar.timestamp > current:
            raise ValueError
        if bar.timestamp != current:
            return []  # an old interim is never promoted by elapsed local time
        if self._observation_baseline is None:
            # Preserve the session's known start across disconnects, including
            # the interval before its first completed target/REST attempt.
            self._observation_baseline = current
        previous = self._sample_current_open
        self._sample_current_open = current
        if previous is None or current <= previous:
            return []
        target = current - timedelta(minutes=1)
        if current != previous + timedelta(minutes=1):
            self._observation_problem("candle_gap", now)
        return self._observe_window(target, target, now)

    def _observe_window(self, start, final_open, now, *, recovery=False):
        if start > final_open:
            return []
        if self._observation_baseline is None:
            self._observation_baseline = start
        # Check the entire known gap before suppressing already attempted slots.
        # Refusal is not a network attempt and must never shrink future recovery.
        if _minute_open_count(start, final_open) > self.resync_request_limit:
            self._observation_problem("recovery_limit", now)
            return []
        if self._attempted_through is not None:
            start = max(start, self._attempted_through + timedelta(minutes=1))
        if start > final_open:
            return []
        count = _minute_open_count(start, final_open)
        # Mark the entire attempted target range before the network call, even
        # on failure. Same-slot frames/reconnect cannot amplify automatic intent.
        self._attempted_through = final_open
        end = final_open + timedelta(minutes=1) - timedelta(milliseconds=1)
        try:
            observation = self._rest.observe_candles("BTC", "1m", start=start, end=end)
            if not isinstance(observation, CandleObservation) or not (
                observation.requested_at.utcoffset()
                == observation.received_at.utcoffset()
                == timedelta(0)
                and end < observation.requested_at <= observation.received_at
                and now <= observation.requested_at
                and len(observation.rows) == count
            ):
                raise ValueError
            bars = []
            for index, row in enumerate(observation.rows):
                expected = start + timedelta(minutes=index)
                if not isinstance(row, dict) or (
                    row.get("s"),
                    row.get("i"),
                    row.get("t"),
                    row.get("T"),
                ) != (
                    "BTC",
                    "1m",
                    int(to_ms(expected)),
                    int(to_ms(expected + timedelta(minutes=1))) - 1,
                ):
                    raise ValueError
                bars.append(parse_candle_frame(row, _instrument("BTC"), interval="1m"))
        except Exception:
            self._observation_problem("candle_observation_unavailable", now)
            return []
        if recovery:
            durable = self._last_candle_open.get("BTC")
            self._continuity_pending[("BTC", "candle")] = (
                ContinuityState.RECOVERED
                if durable is not None and start == durable + timedelta(minutes=1)
                else ContinuityState.KNOWN_GAP
            )
        updates = []
        for bar in bars:
            source_id = _candle_source_id("BTC", bar, final=True)
            continuity, evidence = self._resume_evidence(
                "BTC",
                "candle",
                source_id,
                observation.received_at,
                recovery_source="hyperliquid-public-info",
            )
            updates.append(
                _update(
                    _instrument("BTC"),
                    UpdateKind.CANDLE,
                    {
                        "interval": "1m",
                        "open": bar.open,
                        "high": bar.high,
                        "low": bar.low,
                        "close": bar.close,
                        "volume": bar.volume,
                        # Existing replay's completion filter; explicitly an observed
                        # post-close snapshot, not a provider immutability watermark.
                        "final": True,
                        "observation_basis": "post_close_rest_snapshot",
                        "provider_finality": "unknown",
                        "historical_pit": "unknown",
                    },
                    data_time=bar.timestamp,
                    sequence=int(to_ms(bar.timestamp)),
                    continuity=continuity,
                    source_event_id=source_id,
                    continuity_evidence=evidence,
                    received_at=observation.received_at,
                )
            )
        self.observation_issue = None
        self._mode_status(SourceState.CONNECTED, None, observation.received_at)
        return updates

    def _resync_observations(self, now):
        current = _floor_minute(now)
        self._sample_current_open = current
        durable = self._last_candle_open.get("BTC")
        start = (
            durable + timedelta(minutes=1)
            if durable is not None
            else self._observation_baseline
            if self._observation_baseline is not None
            else current - timedelta(minutes=self.resync_request_limit)
        )
        return self._observe_window(start, current - timedelta(minutes=1), now, recovery=True)


def _frame_time(row: dict) -> datetime:
    """The BBO row's venue time as an aware datetime."""
    millis = row.get("time")
    if not isinstance(millis, int):
        raise HyperliquidProtocolError("bbo row missing an integer 'time'")
    return datetime.fromtimestamp(millis / 1000, tz=UTC)


def _floor_minute(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(second=0, microsecond=0)


def _minute_open_count(start: datetime, end: datetime) -> int:
    if start > end:
        return 0
    return int((end - start) / timedelta(minutes=1)) + 1


def _minute_opens(start: datetime, count: int) -> list[datetime]:
    return [start + timedelta(minutes=index) for index in range(count)]


def _frame_identifier(frame: dict) -> str:
    """The SDK's ``ws_msg_to_identifier`` for the channels we support."""
    channel = frame.get("channel")
    data = frame.get("data")
    if channel == "l2Book":
        if not isinstance(data, dict):
            raise HyperliquidProtocolError("l2Book frame data must be an object")
        return f"l2Book:{str(data.get('coin')).lower()}"
    if channel == "trades":
        if not isinstance(data, list) or not data:
            return "trades"
        first = data[0]
        if not isinstance(first, dict):
            raise HyperliquidProtocolError("trades frame rows must be objects")
        return f"trades:{str(first.get('coin')).lower()}"
    if channel == "candle":
        if not isinstance(data, dict):
            raise HyperliquidProtocolError("candle frame data must be an object")
        return f"candle:{str(data.get('s')).lower()},{data.get('i')}"
    if channel == "bbo":
        if not isinstance(data, dict):
            raise HyperliquidProtocolError("bbo frame data must be an object")
        return f"bbo:{str(data.get('coin')).lower()}"
    if channel == "allMids":
        return "allMids"
    if channel == "activeAssetCtx":
        if not isinstance(data, dict):
            raise HyperliquidProtocolError("activeAssetCtx frame data must be an object")
        return f"activeAssetCtx:{str(data.get('coin')).lower()}"
    raise HyperliquidProtocolError(f"unknown frame channel {channel!r}")


class ScriptedHyperliquidTransport:
    """Scripted wire for the drills (mirrors ``SimulatedStreamTransport``).

    ``send`` records messages so a drill can assert exactly what the
    supervisor subscribed; ``next_event`` plays the script with
    ``DROP``/``RESUME`` driving connection state.
    """

    def __init__(self, script: list[object]) -> None:
        self._script = list(script)
        self._index = 0
        self.connected = False
        self.sent: list[dict] = []

    def connect(self) -> None:
        self.connected = True

    def close(self) -> None:
        self.connected = False

    def send(self, message: dict) -> None:
        if not self.connected:
            raise HyperliquidProtocolError("socket is closed; message was not delivered")
        self.sent.append(message)

    async def recv(self) -> object:
        raise AssertionError("scripted transports are driven by drills, not the pump")

    def next_event(self) -> object | None:
        """Next scripted event; ``DROP``/``RESUME`` drive connection state."""
        if self._index >= len(self._script):
            return None
        event = self._script[self._index]
        self._index += 1
        if event == "DROP":
            self.connected = False
        return event


class LiveHyperliquidTransport:
    """The live wire for ``HyperliquidVenueSupervisor`` (ADR-0014).

    The supervisor protocol is synchronous (drills), so this transport
    defers the actual socket open to the first ``recv`` and queues the
    subscription sends until the socket is up — the pump flushes them on
    the wire before the first frame. Only the live pump constructs this
    (or the browser E2E, pointed at the local fixture venue); drills use
    ``ScriptedHyperliquidTransport``, and the live smoke drill is this
    path's gate — never unit-tested against the network.
    """

    def __init__(self, url: str, *, connect_timeout_s: float = 10.0) -> None:
        self._url = url
        self._connect_timeout_s = connect_timeout_s
        self._socket = None
        self._outbox: list[str] = []

    def connect(self) -> None:
        """No-op: the socket opens on the first ``recv`` (the pump calls
        this synchronously inside the running loop, so nothing here may
        block or await)."""

    def close(self) -> None:
        """Release the TCP transport immediately, including on cancellation.

        The supervisor's close protocol is synchronous. Aborting the underlying
        asyncio transport avoids leaving an unawaited WebSocket close coroutine
        or an orphaned socket after protocol failure or application shutdown.
        """
        socket = self._socket
        self._socket = None
        self._outbox.clear()
        if socket is not None:
            socket.transport.abort()

    def send(self, message: dict) -> None:
        """Queue a subscription; flushed to the wire once the socket
        opens (each ``on_open`` rebuilds the outbox)."""
        self._outbox.append(json.dumps(message))

    async def recv(self) -> object:
        try:
            socket = await self._ensure_open()
            return json.loads(await socket.recv())
        except asyncio.CancelledError:
            self.close()
            raise

    async def _ensure_open(self):
        import websockets

        if self._socket is None:
            self._socket = await websockets.connect(self._url, open_timeout=self._connect_timeout_s)
        if self._outbox:
            pending, self._outbox = self._outbox, []
            for message in pending:
                await self._socket.send(message)
        return self._socket
