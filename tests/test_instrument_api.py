from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from quantmesh.api.workstation import create_workstation_app
from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.execution.accounting import PaperAccount
from quantmesh.instruments.api import HistoricalPayload
from quantmesh.instruments.contracts import (
    ComparisonPoint,
    ComparisonSeries,
    CoverageSnapshot,
    HistoricalBar,
    HistoricalSeries,
    HistoryRange,
)
from quantmesh.instruments.history import HistoryService, HistoryUnavailableError
from quantmesh.live.contract import MarketUpdate, Provenance, UpdateKind
from quantmesh.live.feed import LiveFeed

BASE = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)


def _instrument(venue: Venue, symbol: str) -> Instrument:
    return Instrument(
        venue=venue,
        symbol=symbol,
        instrument_type=(
            InstrumentType.PERPETUAL
            if venue is Venue.HYPERLIQUID
            else InstrumentType.EQUITY
        ),
        currency="USD",
    )


def _series(
    venue: Venue,
    symbol: str,
    requested_range: HistoryRange,
    as_of: datetime,
    *,
    interval: str = "1d",
    adjustment: str = "unadjusted",
) -> HistoricalSeries:
    instrument = _instrument(venue, symbol)
    bars = tuple(
        HistoricalBar(
            instrument=instrument,
            timestamp=BASE + timedelta(days=index),
            interval=interval,
            open=100.0 + index,
            high=102.0 + index,
            low=99.0 + index,
            close=101.0 + index,
            volume=1_000.0 + index,
            adjusted_close=(101.0 + index if adjustment != "unadjusted" else None),
        )
        for index in range(2)
    )
    return HistoricalSeries(
        instrument=instrument,
        range=requested_range,
        as_of=as_of,
        bars=bars,
        dataset_id="api-history",
        dataset_revision=3,
        source="quantmesh-deterministic-bakeoff",
        license="fixture-only",
        generated_at=BASE - timedelta(days=1),
        interval=interval,
        calendar="24/7" if venue is Venue.HYPERLIQUID else "XNYS",
        adjustment=adjustment,
        coverage=CoverageSnapshot(
            interval=interval,
            venue=venue,
            symbol=symbol,
            start=BASE,
            end=BASE + timedelta(days=1),
            rows=2,
        ),
        limitations=("baseline limitation",),
    )


class RecordingHistoryService(HistoryService):
    """A typed API seam; Task 5 separately tests the manifest-gated reader."""

    def __init__(self, *, adjustment: str = "unadjusted") -> None:
        self.adjustment = adjustment
        self.history_as_of: list[datetime] = []
        self.compare_as_of: list[datetime] = []
        self.compare_peers: list[tuple[Venue, str]] = []

    def history(
        self,
        venue: Venue,
        symbol: str,
        range: HistoryRange,
        *,
        as_of: datetime | None = None,
    ) -> HistoricalSeries:
        assert as_of is not None
        self.history_as_of.append(as_of)
        if symbol == "MISSING":
            raise HistoryUnavailableError(f"unknown venue/symbol {venue.value}:{symbol}")
        return _series(venue, symbol, range, as_of, adjustment=self.adjustment)

    def compare(
        self,
        *,
        primary: tuple[Venue, str],
        peers: list[tuple[Venue, str]] | tuple[tuple[Venue, str], ...],
        range: HistoryRange,
        as_of: datetime | None = None,
    ) -> ComparisonSeries:
        assert as_of is not None
        self.compare_as_of.append(as_of)
        self.compare_peers = list(peers)
        if any(symbol == "MISSING" for _, symbol in peers):
            raise HistoryUnavailableError("unknown venue/symbol moomoo:MISSING")
        keys = tuple(f"{venue.value}:{symbol}" for venue, symbol in (primary, *peers))
        return ComparisonSeries(
            range=range,
            as_of=as_of,
            keys=keys,
            points=tuple(
                ComparisonPoint(
                    timestamp=BASE + timedelta(days=index),
                    values={key: 100.0 + index for key in keys},
                )
                for index in (0, 1)
            ),
            limitations=("comparison uses common observed timestamps",),
        )


class ProgrammerFailureService(RecordingHistoryService):
    def __init__(self, failure: str) -> None:
        super().__init__()
        self.failure = failure

    def history(
        self,
        venue: Venue,
        symbol: str,
        range: HistoryRange,
        *,
        as_of: datetime | None = None,
    ) -> HistoricalSeries:
        if self.failure == "value-error":
            raise ValueError("internal invariant failed")
        HistoricalBar(
            instrument=_instrument(venue, symbol),
            timestamp=BASE,
            interval="1d",
            open=-1.0,
            high=1.0,
            low=1.0,
            close=1.0,
            volume=1.0,
        )
        raise AssertionError("validation failure should already have raised")


def _app(
    history: HistoryService | None = None,
    live_feed: LiveFeed | None = None,
):
    return create_workstation_app(
        account=PaperAccount(cash=100_000.0),
        history=history,
        live_feed=live_feed,
        host="127.0.0.1",
    )


def _get(
    history: HistoryService | None = None,
    *,
    path: str = "/api/instruments/moomoo/NVDA/history?range=6m",
    live_feed: LiveFeed | None = None,
):
    with TestClient(_app(history, live_feed)) as client:
        return client.get(path)


def _candle(
    *,
    venue: Venue = Venue.MOOMOO,
    symbol: str = "NVDA",
    timestamp: datetime = BASE + timedelta(days=2),
    interval: object = "1d",
    provenance: Provenance = Provenance.REAL,
    sequence: int | None = 2,
    sequence_gap: bool = False,
    open_: float = 102.0,
    high: float = 104.0,
    low: float = 101.0,
    close: float = 103.0,
    volume: float = 1_002.0,
    received_at: datetime | None = None,
) -> MarketUpdate:
    return MarketUpdate(
        venue=venue,
        instrument=symbol,
        kind=UpdateKind.CANDLE,
        provenance=provenance,
        data_time=timestamp,
        received_at=received_at if received_at is not None else datetime.now(UTC),
        sequence=sequence,
        sequence_gap=sequence_gap,
        payload={
            "interval": interval,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
    )


def _ingest_with_predecessor(feed: LiveFeed, update: MarketUpdate) -> None:
    interval = update.payload.get("interval")
    durations = {"1d": timedelta(days=1), "5m": timedelta(minutes=5), "24h": timedelta(days=1)}
    duration = durations.get(interval, timedelta(days=1))
    predecessor_time = update.data_time - duration
    predecessor_receipt = update.received_at - timedelta(seconds=1)
    predecessor_sequence = (
        update.sequence - 1
        if type(update.sequence) is int and update.sequence > 0
        else None
    )
    predecessor = _candle(
        venue=update.venue,
        symbol=update.instrument,
        timestamp=predecessor_time,
        interval=interval,
        provenance=update.provenance,
        sequence=predecessor_sequence,
        received_at=predecessor_receipt,
    )
    feed.ingest([predecessor, update])


def test_history_mounts_at_root_and_api_with_stable_json() -> None:
    service = RecordingHistoryService()
    api_response = _get(
        service,
        path=(
            "/api/instruments/moomoo/NVDA/history"
            "?range=6m&compare=moomoo:AAPL,hyperliquid:BTC"
        ),
    )
    root_response = _get(
        service,
        path=(
            "/instruments/moomoo/NVDA/history"
            "?range=6m&compare=moomoo:AAPL,hyperliquid:BTC"
        ),
    )

    assert api_response.status_code == 200
    assert root_response.status_code == 200
    payload = api_response.json()
    root_payload = root_response.json()
    for current in (payload, root_payload):
        current["primary"].pop("as_of")
        current["comparison"].pop("as_of")
    assert root_payload == payload
    assert payload["primary"]["source"] == "quantmesh-deterministic-bakeoff"
    assert isinstance(payload["primary"]["bars"], list)
    assert isinstance(payload["primary"]["instrument"]["metadata"], dict)
    assert payload["comparison"]["keys"] == [
        "moomoo:NVDA",
        "moomoo:AAPL",
        "hyperliquid:BTC",
    ]
    assert isinstance(payload["comparison"]["points"][0]["values"], dict)


def test_history_uses_one_aware_request_time_for_primary_and_comparison() -> None:
    service = RecordingHistoryService()
    response = _get(
        service,
        path="/api/instruments/moomoo/NVDA/history?range=6m&compare=moomoo:AAPL",
    )

    assert response.status_code == 200
    assert len(service.history_as_of) == 1
    assert len(service.compare_as_of) == 1
    assert service.history_as_of[0] == service.compare_as_of[0]
    assert service.history_as_of[0].tzinfo is not None
    assert response.json()["primary"]["as_of"] == response.json()["comparison"]["as_of"]


def test_compare_accepts_repeated_and_comma_separated_values_deduping_in_order() -> None:
    service = RecordingHistoryService()
    response = _get(
        service,
        path=(
            "/api/instruments/moomoo/NVDA/history?range=6m"
            "&compare=moomoo:AAPL,hyperliquid:BTC"
            "&compare=moomoo:AAPL"
        ),
    )

    assert response.status_code == 200
    assert service.compare_peers == [
        (Venue.MOOMOO, "AAPL"),
        (Venue.HYPERLIQUID, "BTC"),
    ]


@pytest.mark.parametrize(
    "path",
    [
        "/api/instruments/not-a-venue/NVDA/history?range=6m",
        "/api/instruments/moomoo/NVDA/history?range=bogus",
        "/api/instruments/moomoo/BAD%21/history?range=6m",
        "/api/instruments/moomoo/NVDA/history?range=6m&compare=bad",
        "/api/instruments/moomoo/NVDA/history?range=6m&compare=unknown:AAPL",
        "/api/instruments/moomoo/NVDA/history?range=6m&compare=moomoo:",
        "/api/instruments/moomoo/NVDA/history?range=6m&compare=moomoo:NVDA",
        (
            "/api/instruments/moomoo/NVDA/history?range=6m"
            "&compare=moomoo:AAPL,moomoo:MSFT,hyperliquid:BTC,hyperliquid:ETH"
        ),
        f"/api/instruments/moomoo/NVDA/history?range=6m&compare=moomoo:{'A' * 65}",
    ],
)
def test_invalid_history_input_is_422(path: str) -> None:
    response = _get(RecordingHistoryService(), path=path)

    assert response.status_code == 422


def test_compare_repeated_query_values_are_bounded_even_when_duplicates() -> None:
    repeated = "&".join("compare=moomoo:AAPL" for _ in range(9))

    response = _get(
        RecordingHistoryService(),
        path=f"/api/instruments/moomoo/NVDA/history?range=6m&{repeated}",
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "compare supports at most 8 query values"


def test_missing_service_and_missing_data_are_truthful_stable_errors() -> None:
    no_service = _get()
    missing_primary = _get(
        RecordingHistoryService(),
        path="/api/instruments/moomoo/MISSING/history?range=6m",
    )
    missing_peer = _get(
        RecordingHistoryService(),
        path=(
            "/api/instruments/moomoo/NVDA/history"
            "?range=6m&compare=moomoo:MISSING"
        ),
    )

    assert no_service.status_code == 404
    assert no_service.json() == {"detail": "no historical service is attached"}
    assert missing_primary.status_code == 404
    assert missing_primary.json()["detail"].startswith("historical data unavailable: ")
    assert missing_peer.status_code == 404
    assert missing_peer.json()["detail"].startswith("historical data unavailable: ")


@pytest.mark.parametrize("failure", ["value-error", "validation-error"])
def test_programmer_and_validation_errors_remain_observable_as_500(failure: str) -> None:
    app = _app(ProgrammerFailureService(failure))

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/instruments/moomoo/NVDA/history?range=6m")

    assert response.status_code == 500


def test_openapi_operation_ids_are_unique_and_response_is_exact() -> None:
    with TestClient(_app(RecordingHistoryService())) as client:
        schema = client.get("/openapi.json").json()

    operation_ids = [
        operation["operationId"]
        for methods in schema["paths"].values()
        for operation in methods.values()
        if isinstance(operation, dict) and "operationId" in operation
    ]
    assert len(operation_ids) == len(set(operation_ids))
    api_operation = schema["paths"]["/api/instruments/{venue}/{symbol}/history"]["get"]
    assert api_operation["operationId"].startswith("api_")
    assert (
        api_operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/HistoricalPayload"
    )


@pytest.mark.parametrize("provenance", [Provenance.REAL, Provenance.DELAYED])
def test_contiguous_real_or_delayed_live_candle_appends_primary_only(
    provenance: Provenance,
) -> None:
    feed = LiveFeed()
    _ingest_with_predecessor(feed, _candle(provenance=provenance))
    service = RecordingHistoryService()

    response = _get(
        service,
        path="/api/instruments/moomoo/NVDA/history?range=6m&compare=moomoo:AAPL",
        live_feed=feed,
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["primary"]["bars"]) == 3
    assert payload["primary"]["bars"][-1]["is_live_tail"] is True
    assert payload["primary"]["bars"][-1]["close"] == 103.0
    lineage = payload["primary"]["bars"][-1]["live_lineage"]
    assert lineage["source"] == "moomoo"
    assert lineage["venue"] == "moomoo"
    assert lineage["instrument"] == "NVDA"
    assert lineage["provenance"] == provenance.value
    assert lineage["freshness_label"] == provenance.value
    assert lineage["sequence"] == 2
    assert lineage["predecessor_sequence"] == 1
    assert lineage["sequence_gap"] is False
    assert lineage["continuity_proven"] is True
    assert 0 <= lineage["age_ms"] <= 30_000
    assert payload["primary"]["coverage_scope"] == "historical-only"
    assert "coverage is historical-only" in payload["primary"]["limitations"][-1]
    assert len(payload["comparison"]["points"]) == 2
    assert payload["comparison"]["keys"] == ["moomoo:NVDA", "moomoo:AAPL"]
    restored = HistoricalPayload.model_validate_json(response.text, strict=True)
    assert restored.model_dump(mode="json") == payload
    assert restored.primary.bars[-1].live_lineage is not None
    with pytest.raises(ValidationError):
        restored.primary.bars[-1].live_lineage.age_ms = 0


def test_same_last_timestamp_replaces_only_the_last_historical_bar() -> None:
    feed = LiveFeed()
    _ingest_with_predecessor(
        feed,
        _candle(timestamp=BASE + timedelta(days=1), close=110.0, high=111.0),
    )

    payload = _get(RecordingHistoryService(), live_feed=feed).json()["primary"]

    assert len(payload["bars"]) == 2
    assert payload["bars"][0]["is_live_tail"] is False
    assert payload["bars"][-1]["is_live_tail"] is True
    assert payload["bars"][-1]["close"] == 110.0


def test_exact_venue_symbol_kind_selection_survives_cross_venue_symbol_collision() -> None:
    feed = LiveFeed()
    _ingest_with_predecessor(
        feed,
        _candle(venue=Venue.HYPERLIQUID, close=777.0, high=778.0),
    )
    _ingest_with_predecessor(feed, _candle(venue=Venue.MOOMOO, close=103.0))
    feed.ingest(
        [
            MarketUpdate(
                venue=Venue.MOOMOO,
                instrument="NVDA",
                kind=UpdateKind.QUOTE,
                provenance=Provenance.REAL,
                data_time=BASE + timedelta(days=2),
                sequence=99,
                payload={"bid": 102.0, "ask": 103.0},
            ),
        ]
    )

    payload = _get(RecordingHistoryService(), live_feed=feed).json()["primary"]

    assert payload["bars"][-1]["close"] == 103.0
    assert payload["bars"][-1]["is_live_tail"] is True


def test_single_arbitrary_sequence_never_proves_a_live_tail() -> None:
    feed = LiveFeed()
    feed.ingest([_candle(sequence=777_777)])

    primary = _get(RecordingHistoryService(), live_feed=feed).json()["primary"]

    assert len(primary["bars"]) == 2
    assert primary["bars"][-1]["live_lineage"] is None
    assert "continuity is not proven" in primary["limitations"][-1]


@pytest.mark.parametrize(
    "received_at",
    [
        datetime.now(UTC) - timedelta(days=30),
        datetime.now(UTC) + timedelta(days=1),
    ],
)
def test_stale_or_post_snapshot_receipt_is_refused(received_at: datetime) -> None:
    feed = LiveFeed()
    _ingest_with_predecessor(feed, _candle(received_at=received_at))

    primary = _get(RecordingHistoryService(), live_feed=feed).json()["primary"]

    assert len(primary["bars"]) == 2
    assert all(bar["live_lineage"] is None for bar in primary["bars"])
    assert primary["limitations"][-1].startswith("Live candle was not joined: ")


def test_naive_live_receipt_is_refused_without_a_server_error() -> None:
    feed = LiveFeed()
    feed.ingest([_candle(timestamp=BASE + timedelta(days=1), sequence=1)])
    invalid = _candle().model_copy(
        update={"received_at": datetime(2026, 8, 12, 12, 0)}
    )
    feed.ingest([invalid])

    response = _get(RecordingHistoryService(), live_feed=feed)

    assert response.status_code == 200
    primary = response.json()["primary"]
    assert len(primary["bars"]) == 2
    assert "received_at must be timezone-aware" in primary["limitations"][-1]


@pytest.mark.parametrize(
    ("update", "expected"),
    [
        (_candle(provenance=Provenance.SYNTHETIC), "provenance is not real or delayed"),
        (_candle(provenance=Provenance.UNAVAILABLE), "provenance is not real or delayed"),
        (_candle(interval=None), "payload interval is absent or invalid"),
        (_candle(interval="5m"), "does not exactly match"),
        (_candle(interval="24h"), "does not exactly match"),
        (_candle(sequence=None), "sequence is absent or invalid"),
        (_candle(sequence_gap=True), "sequence continuity is not proven"),
        (_candle(timestamp=BASE), "older than the final historical bar"),
        (_candle(timestamp=BASE + timedelta(days=3)), "not the next contiguous interval"),
        (_candle(close=float("nan"), high=float("nan")), "high must be a finite number"),
        (_candle(volume=float("inf")), "volume must be a finite number"),
    ],
)
def test_invalid_matching_live_candle_is_not_joined_and_names_a_limitation(
    update: MarketUpdate,
    expected: str,
) -> None:
    feed = LiveFeed()
    _ingest_with_predecessor(feed, update)

    payload = _get(RecordingHistoryService(), live_feed=feed).json()["primary"]

    assert len(payload["bars"]) == 2
    assert all(bar["is_live_tail"] is False for bar in payload["bars"])
    assert payload["limitations"][0] == "baseline limitation"
    assert len(payload["limitations"]) == 2
    assert payload["limitations"][1].startswith("Live candle was not joined: ")
    assert expected in payload["limitations"][1]


def test_naive_or_future_live_timestamp_is_refused_without_a_server_error() -> None:
    cases = (
        (datetime(2026, 8, 3, 12, 0), "data_time must be timezone-aware"),
        (datetime(2999, 1, 1, tzinfo=UTC), "data_time is later than the request time"),
    )
    for timestamp, expected in cases:
        update = _candle().model_copy(update={"data_time": timestamp})
        feed = LiveFeed()
        feed.ingest([update])

        response = _get(RecordingHistoryService(), live_feed=feed)

        assert response.status_code == 200
        primary = response.json()["primary"]
        assert len(primary["bars"]) == 2
        assert primary["limitations"][-1].startswith("Live candle was not joined: ")
        assert expected in primary["limitations"][-1]


def test_missing_feed_or_matching_candle_leaves_history_unchanged_without_fake_error() -> None:
    no_feed = _get(RecordingHistoryService()).json()["primary"]
    wrong_feed = LiveFeed()
    wrong_feed.ingest([_candle(symbol="AAPL")])
    no_match = _get(RecordingHistoryService(), live_feed=wrong_feed).json()["primary"]

    no_feed.pop("as_of")
    no_match.pop("as_of")
    assert no_feed == no_match
    assert no_feed["limitations"] == ["baseline limitation"]


def test_adjusted_history_refuses_unadjusted_live_tail() -> None:
    feed = LiveFeed()
    _ingest_with_predecessor(feed, _candle())

    primary = _get(
        RecordingHistoryService(adjustment="split-adjusted"), live_feed=feed
    ).json()["primary"]

    assert len(primary["bars"]) == 2
    assert "adjusted historical series" in primary["limitations"][-1]


def test_history_get_does_not_change_execution_authority_or_account_state() -> None:
    app = _app(RecordingHistoryService())
    account_before = app.state.account.model_dump(mode="json")

    with TestClient(app) as client:
        response = client.get("/api/instruments/moomoo/NVDA/history?range=6m")

    assert response.status_code == 200
    assert app.state.account.model_dump(mode="json") == account_before
    assert app.state.account.orders == {}
