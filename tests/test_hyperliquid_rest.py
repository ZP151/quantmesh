"""Hyperliquid REST transport tests (M5, issue #29, Phase A).

``SdkRestTransport`` is lazy, import-guarded, and testnet-pinned: the
mainnet URL is refused at construction, the SDK is only reached when a
method is called, and time ranges convert to unix milliseconds at the
boundary. ``ScriptedRestTransport`` is the deterministic stub the
reconnect drills drive.
"""

import builtins
from datetime import UTC, datetime, timedelta

import pytest

from quantmesh.hyperliquid.errors import (
    HyperliquidProtocolError,
    HyperliquidSDKMissingError,
    HyperliquidUnavailableError,
)
from quantmesh.hyperliquid.rest import (
    MAINNET_API_URL,
    TESTNET_API_URL,
    ScriptedRestTransport,
    SdkRestTransport,
    to_ms,
)

T0 = 1754600400000
NOW = datetime.fromtimestamp(T0 / 1000, tz=UTC)


class StubInfo:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []
        self.candles_rows = [{"t": T0, "i": "1m", "s": "BTC"}]
        self.funding_rows = [{"coin": "BTC", "time": T0}]
        self.l2_payload = {"coin": "BTC", "time": T0}
        self.meta_payload = {"universe": []}
        self.spot_meta_payload = {"universe": [], "tokens": []}

    def candles_snapshot(self, *args):  # noqa: ANN002
        self.calls.append(("candles_snapshot", args))
        return self.candles_rows

    def funding_history(self, *args):  # noqa: ANN002
        self.calls.append(("funding_history", args))
        return self.funding_rows

    def l2_snapshot(self, *args):  # noqa: ANN002
        self.calls.append(("l2_snapshot", args))
        return self.l2_payload

    def meta(self):  # noqa: ANN201
        return self.meta_payload

    def spot_meta(self):  # noqa: ANN201
        return self.spot_meta_payload


def sdk_transport(
    monkeypatch: pytest.MonkeyPatch, *, stub: StubInfo | None = None
) -> SdkRestTransport:
    stub = stub or StubInfo()
    monkeypatch.setattr(SdkRestTransport, "_sdk", lambda self: stub)
    return SdkRestTransport()


def test_construction_refuses_a_non_testnet_base_url() -> None:
    with pytest.raises(HyperliquidProtocolError, match="refusing base URL"):
        SdkRestTransport(MAINNET_API_URL)


def test_construction_defaults_to_testnet() -> None:
    assert SdkRestTransport()._base_url == TESTNET_API_URL


def test_candles_convert_aware_ranges_to_unix_millis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub = StubInfo()
    transport = sdk_transport(monkeypatch, stub=stub)
    end = NOW + timedelta(minutes=5)

    rows = transport.candles("BTC", "1m", start=NOW, end=end)

    assert rows == stub.candles_rows
    assert stub.calls == [("candles_snapshot", ("BTC", "1m", T0, T0 + 300_000))]


def test_naive_range_times_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = sdk_transport(monkeypatch)

    with pytest.raises(HyperliquidProtocolError, match="timezone-aware"):
        transport.candles("BTC", "1m", start=datetime(2026, 8, 8), end=NOW)


def test_non_list_candle_payload_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = StubInfo()
    stub.candles_rows = {"not": "a list"}
    transport = sdk_transport(monkeypatch, stub=stub)

    with pytest.raises(HyperliquidProtocolError, match="must be a list"):
        transport.candles("BTC", "1m", start=NOW, end=NOW)


def test_l2_book_and_funding_pass_through(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = StubInfo()
    transport = sdk_transport(monkeypatch, stub=stub)

    assert transport.l2_book("BTC") == stub.l2_payload
    assert transport.funding_history("BTC", start=NOW, end=NOW) == stub.funding_rows
    assert transport.meta() == stub.meta_payload
    assert transport.spot_meta() == stub.spot_meta_payload


def test_sdk_import_failure_is_typed(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def no_hyperliquid(name, *args, **kwargs):
        if name == "hyperliquid" or name.startswith("hyperliquid."):
            raise ImportError("vendored SDK not installed in this venv")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_hyperliquid)
    transport = SdkRestTransport()

    with pytest.raises(HyperliquidSDKMissingError, match="not importable"):
        transport.candles("BTC", "1m", start=NOW, end=NOW)


def test_sdk_exceptions_become_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = StubInfo()

    def boom(*args):  # noqa: ANN002
        raise ConnectionError("refused")

    stub.candles_snapshot = boom
    transport = sdk_transport(monkeypatch, stub=stub)

    with pytest.raises(HyperliquidUnavailableError, match="failed"):
        transport.candles("BTC", "1m", start=NOW, end=NOW)


def test_to_ms_rejects_naive_times() -> None:
    with pytest.raises(HyperliquidProtocolError, match="timezone-aware"):
        to_ms(datetime(2026, 8, 8))


# --- ScriptedRestTransport ---------------------------------------------------

def test_scripted_candles_filter_by_window() -> None:
    transport = ScriptedRestTransport(
        candles={("BTC", "1m"): [{"t": T0}, {"t": T0 + 60_000}, {"t": T0 + 120_000}]}
    )

    rows = transport.candles("BTC", "1m", start=NOW, end=NOW + timedelta(minutes=1))

    assert [row["t"] for row in rows] == [T0, T0 + 60_000]


def test_scripted_candles_missing_key_fails_closed() -> None:
    transport = ScriptedRestTransport()

    with pytest.raises(HyperliquidProtocolError, match="no candles"):
        transport.candles("BTC", "1m", start=NOW, end=NOW)


def test_scripted_l2_book_can_serve_a_fresh_snapshot() -> None:
    transport = ScriptedRestTransport(
        l2_books={"BTC": lambda at: {"coin": "BTC", "time": T0, "levels": [[], []]}}
    )

    payload = transport.l2_book("BTC", at=NOW)

    assert payload["coin"] == "BTC"


def test_scripted_meta_missing_fails_closed() -> None:
    transport = ScriptedRestTransport()

    with pytest.raises(HyperliquidProtocolError, match="no meta payload"):
        transport.meta()
