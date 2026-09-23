"""Read-only Moomoo/OpenD quote and history readiness tests."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from quantmesh.moomoo.opend import (
    OpenDAuthRequiredError,
    OpenDCapabilities,
    OpenDProtocolError,
    OpenDSdkMissingError,
    OpenDUnavailableError,
)
from quantmesh.moomoo.readiness import run_readiness

CAPABILITIES = OpenDCapabilities(
    quote=True,
    history_kline=True,
    order=False,
    order_query=False,
    auth_required=False,
)


def _quote(code: str) -> dict:
    return {
        "rows": [
            {
                "code": code,
                "data_date": "2026-09-23",
                "data_time": "10:00:00",
                "last_price": 210.0,
                "volume": 1000.0,
            }
        ]
    }


def _history(code: str) -> dict:
    return {
        "code": code,
        "interval": "1d",
        "autype": "None",
        "rows": [
            {
                "code": code,
                "time_key": "2026-09-22",
                "open": 209.0,
                "high": 212.0,
                "low": 208.0,
                "close": 210.0,
                "volume": 1000.0,
            }
        ],
    }


@dataclass
class StubClient:
    capabilities: OpenDCapabilities = CAPABILITIES
    history_errors: dict[str, Exception] | None = None
    quote_payloads: dict[str, dict] | None = None
    history_payloads: dict[str, dict] | None = None

    def __post_init__(self) -> None:
        self.quote_calls: list[list[str]] = []
        self.history_calls: list[str] = []
        self.order_calls = 0

    def probe_market_data(self) -> OpenDCapabilities:
        return self.capabilities

    def stock_quote(self, codes: list[str]) -> dict:
        self.quote_calls.append(codes)
        code = codes[0]
        return (self.quote_payloads or {}).get(code, _quote(code))

    def history_kline(
        self,
        code: str,
        *,
        interval: str,
        start: str | None = None,
        end: str | None = None,
        autype: str = "None",
    ) -> dict:
        assert interval == "1d"
        assert start is None
        assert end is None
        assert autype == "None"
        self.history_calls.append(code)
        error = (self.history_errors or {}).get(code)
        if error is not None:
            raise error
        return (self.history_payloads or {}).get(code, _history(code))


def test_readiness_requires_quote_and_history_for_every_symbol() -> None:
    report = run_readiness(StubClient(), ["US.AAPL", "US.NVDA"])

    assert report.status == "ready"
    assert [row.status for row in report.symbols] == ["ready", "ready"]
    assert [row.quote_status for row in report.symbols] == ["ready", "ready"]
    assert [row.history_status for row in report.symbols] == ["ready", "ready"]


def test_readiness_preserves_partial_symbol_failure() -> None:
    client = StubClient(history_errors={"US.NVDA": OpenDUnavailableError("entitlement denied")})

    report = run_readiness(client, ["US.AAPL", "US.NVDA"])

    assert report.status == "partial"
    assert report.symbols[0].status == "ready"
    assert report.symbols[1].status == "partial"
    assert report.symbols[1].history_status == "unavailable"
    assert "entitlement denied" not in (report.symbols[1].history_detail or "")


def test_empty_history_is_unavailable() -> None:
    client = StubClient(history_payloads={"US.AAPL": {**_history("US.AAPL"), "rows": []}})

    report = run_readiness(client, ["US.AAPL"])

    assert report.status == "partial"
    assert report.symbols[0].quote_status == "ready"
    assert report.symbols[0].history_status == "unavailable"
    assert report.symbols[0].history_detail == "OpenD returned no history rows"


@pytest.mark.parametrize(
    "payloads, field",
    [
        ({"US.AAPL": {"rows": [{"code": "US.AAPL"}]}}, "quote_status"),
        ({"US.AAPL": {**_history("US.AAPL"), "rows": [{"code": "US.AAPL"}]}}, "history_status"),
    ],
)
def test_malformed_payload_is_protocol_error(payloads: dict[str, dict], field: str) -> None:
    client = StubClient(
        quote_payloads=payloads if field == "quote_status" else None,
        history_payloads=payloads if field == "history_status" else None,
    )

    report = run_readiness(client, ["US.AAPL"])

    assert getattr(report.symbols[0], field) == "protocol_error"


def test_all_malformed_symbols_set_protocol_error_summary() -> None:
    client = StubClient(
        quote_payloads={
            "US.AAPL": {"rows": [{"code": "US.AAPL"}]},
            "US.NVDA": {"rows": [{"code": "US.NVDA"}]},
        }
    )

    report = run_readiness(client, ["US.AAPL", "US.NVDA"])

    assert report.status == "protocol_error"
    assert [row.status for row in report.symbols] == ["protocol_error", "protocol_error"]


@pytest.mark.parametrize("kind", ["quote", "history"])
def test_cross_market_payload_is_protocol_error(kind: str) -> None:
    if kind == "quote":
        client = StubClient(quote_payloads={"US.AAPL": _quote("HK.AAPL")})
    else:
        client = StubClient(history_payloads={"US.AAPL": _history("HK.AAPL")})

    report = run_readiness(client, ["US.AAPL"])

    assert report.symbols[0].status == "protocol_error"
    assert report.symbols[0].quote_status == ("protocol_error" if kind == "quote" else "ready")
    assert report.symbols[0].history_status == (
        "protocol_error" if kind == "history" else "ready"
    )


def test_readiness_never_calls_order_operations() -> None:
    client = StubClient()

    report = run_readiness(client, ["US.AAPL"])

    assert report.status == "ready"
    assert client.order_calls == 0
    assert report.capabilities.order is False
    assert report.order_checked is False


@pytest.mark.parametrize("error, status", [
    (OpenDAuthRequiredError, "auth_required"),
    (OpenDSdkMissingError, "sdk_missing"),
    (OpenDProtocolError, "protocol_error"),
    (OpenDUnavailableError, "unavailable"),
])
def test_operation_failure_is_typed_and_redacted(error, status):
    report = run_readiness(
        StubClient(history_errors={"US.AAPL": error("SECRET_SENTINEL")}), ["US.AAPL"]
    )
    assert report.symbols[0].history_status == status
    assert "SECRET_SENTINEL" not in str(report.as_dict())
    assert report.status == ("partial" if status == "unavailable" else status)


def test_malformed_provider_values_are_redacted():
    report = run_readiness(
        StubClient(quote_payloads={"US.AAPL": _quote("SECRET_SENTINEL")}), ["US.AAPL"]
    )
    assert report.status == "protocol_error"
    assert "SECRET_SENTINEL" not in str(report.as_dict())


@pytest.mark.parametrize("codes, interval", [(["INVALID"], "1d"), (["US.AAPL"], "oops")])
def test_invalid_request_is_rejected_before_provider(codes, interval):
    class NoNetwork:
        def probe_market_data(self):
            pytest.fail("invalid request must not contact provider")

    with pytest.raises(ValueError):
        run_readiness(NoNetwork(), codes, interval=interval)


@pytest.mark.parametrize("field, value", [("interval", "1m"), ("autype", "qfq")])
def test_history_must_match_requested_interval_and_adjustment(field, value):
    payload = {**_history("US.AAPL"), field: value}
    report = run_readiness(StubClient(history_payloads={"US.AAPL": payload}), ["US.AAPL"])
    assert report.status == "protocol_error"
