import json
from datetime import UTC, datetime, timedelta

import pytest

from quantmesh.data.capabilities import DataKind, ProviderAccess, ProviderRequest
from quantmesh.domain.market_data import interval_to_timedelta
from quantmesh.domain.models import Venue
from quantmesh.hyperliquid.errors import HyperliquidProtocolError
from quantmesh.hyperliquid.public_info import MAINNET_INFO_URL, PublicInfoTransport

NOW = datetime(2026, 8, 14, tzinfo=UTC)


class StubResponse:
    def __init__(self, payload: object, *, status_code: int = 200) -> None:
        self.content = json.dumps(payload, separators=(",", ":")).encode()
        self.status_code = status_code


class StubClient:
    def __init__(self, responses: list[StubResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, dict, float]] = []

    def post(self, url: str, *, json: dict, timeout: float) -> StubResponse:
        self.calls.append((url, json, timeout))
        return self.responses.pop(0)


def test_public_info_transport_has_no_execution_surface() -> None:
    transport = PublicInfoTransport(client=StubClient([]))

    for name in ("exchange", "order", "wallet", "sign", "cancel", "account"):
        assert not hasattr(transport, name)

    request = ProviderRequest(
        provider_id="hyperliquid-public",
        venue=Venue.HYPERLIQUID,
        access=ProviderAccess.PUBLIC_LIVE,
        data_kind=DataKind.BARS,
        symbol="BTC",
        interval="1m",
    )
    assert sum(item.supports(request) for item in transport.descriptor.capabilities) == 1
    with pytest.raises(AttributeError, match="immutable"):
        transport._client = StubClient([])


def test_candles_use_pinned_mainnet_info_request() -> None:
    rows = [{"t": 1, "T": 2, "s": "BTC", "i": "1m"}]
    client = StubClient([StubResponse(rows)])
    transport = PublicInfoTransport(
        client=client,
        request_timeout_s=3.0,
        clock=lambda: NOW + timedelta(minutes=10),
    )

    response = transport.candles(
        "BTC",
        "1m",
        start=NOW,
        end=NOW + timedelta(minutes=1),
    )

    assert response.payload == rows
    assert response.raw_bytes == json.dumps(rows, separators=(",", ":")).encode()
    assert response.received_at == NOW + timedelta(minutes=10)
    assert client.calls == [
        (
            MAINNET_INFO_URL,
            {
                "type": "candleSnapshot",
                "req": {
                    "coin": "BTC",
                    "interval": "1m",
                    "startTime": int(NOW.timestamp() * 1000),
                    "endTime": int((NOW + timedelta(minutes=1)).timestamp() * 1000),
                },
            },
            3.0,
        )
    ]
    assert transport._is_direct_network_source is False


def test_candle_capabilities_expose_conservative_inclusive_horizons() -> None:
    capabilities = [
        item
        for item in PublicInfoTransport.descriptor.capabilities
        if item.data_kind is DataKind.BARS
    ]

    for capability in capabilities:
        assert capability.history_limit is not None
        assert capability.history_limit.max_rows == 5_000
        interval = next(iter(capability.intervals))
        expected_days = max(
            1,
            int(interval_to_timedelta(interval).total_seconds() * 4_999 // 86_400),
        )
        assert capability.history_limit.max_window_days == expected_days


def test_transport_refuses_unpinned_url_and_invalid_shape() -> None:
    with pytest.raises(HyperliquidProtocolError, match="pinned"):
        PublicInfoTransport(base_url="https://example.com/info", client=StubClient([]))

    transport = PublicInfoTransport(client=StubClient([StubResponse({"not": "candles"})]))
    with pytest.raises(HyperliquidProtocolError, match="list"):
        transport.candles("BTC", "1m", start=NOW, end=NOW)


def test_l2_book_uses_only_public_info_surface() -> None:
    book = {"coin": "BTC", "time": 1, "levels": [[], []]}
    client = StubClient([StubResponse(book)])

    assert PublicInfoTransport(client=client).l2_book("BTC").payload == book
    assert client.calls[0][0] == MAINNET_INFO_URL
    assert client.calls[0][1] == {"type": "l2Book", "coin": "BTC"}
    request = ProviderRequest(
        provider_id="hyperliquid-public",
        venue=Venue.HYPERLIQUID,
        access=ProviderAccess.PUBLIC_LIVE,
        data_kind=DataKind.BOOKS,
        symbol="BTC",
    )
    assert sum(item.supports(request) for item in PublicInfoTransport.descriptor.capabilities) == 1
