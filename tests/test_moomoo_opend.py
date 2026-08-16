"""Moomoo OpenD client boundary tests (issue #25, Phase A).

The client must be fully testable with no OpenD instance and no vendor
SDK installed: tests inject a stub transport and assert typed errors,
capability parsing, and fail-closed payload handling.
"""

import importlib.util
import json
from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from quantmesh.moomoo.opend import (
    MoomooOpenDClient,
    OpenDAuthRequiredError,
    OpenDCapabilities,
    OpenDProtocolError,
    OpenDSdkMissingError,
    OpenDTransport,
    OpenDUnavailableError,
    SdkTransport,
)
from quantmesh.settings import Settings

ALL_CAPABLE = {
    "quote": True,
    "history_kline": True,
    "order": True,
    "order_query": True,
    "auth_required": False,
}


class StubTransport(OpenDTransport):
    """Injectable transport: canned probe payload or canned failure."""

    def __init__(self, payload: dict | None = None, error: Exception | None = None) -> None:
        self.payload = payload if payload is not None else dict(ALL_CAPABLE)
        self.error = error
        self.probes = 0
        self.closed = False

    def probe(self) -> dict:
        self.probes += 1
        if self.error is not None:
            raise self.error
        return self.payload

    def close(self) -> None:
        self.closed = True


def _history_rows(start: int, count: int) -> list[dict]:
    first = date(2026, 8, 1)
    return [
        {
            "code": "US.AAPL",
            "time_key": (first + timedelta(days=(start + index) // 200)).isoformat(),
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1.0,
            "source_row": start + index,
        }
        for index in range(count)
    ]


class PagingTransport(OpenDTransport):
    def __init__(self, pages: list[tuple[list[dict], bytes | None]]) -> None:
        self.pages = pages
        self.requested_cursors: list[bytes | None] = []
        self.action_calls: list[tuple] = []

    def probe(self) -> dict:
        return dict(ALL_CAPABLE)

    def history_kline_page(
        self,
        code: str,
        *,
        interval: str,
        start: str | None,
        end: str | None,
        autype: str,
        max_count: int,
        page_req_key: bytes | None,
    ) -> dict:
        self.requested_cursors.append(page_req_key)
        rows, next_cursor = self.pages[len(self.requested_cursors) - 1]
        return {
            "code": code,
            "interval": interval,
            "autype": autype,
            "request_page_req_key": page_req_key,
            "next_page_req_key": next_cursor,
            "rows": rows,
        }

    def adjustment_factors(self, code: str) -> dict:
        self.action_calls.append(("adjustment_factors", code))
        return {"code": code, "rows": [{"ex_div_date": "2026-08-01"}]}

    def stock_splits_page(self, code: str, *, next_key: str | None, num: int) -> dict:
        self.action_calls.append(("stock_splits", code, next_key, num))
        pages = {
            None: {
                "code": code,
                "request_next_key": None,
                "next_key": "page-2",
                "rows": [{"rate": "1->4"}],
            },
            "page-2": {
                "code": code,
                "request_next_key": "page-2",
                "next_key": "-1",
                "rows": [{"rate": "4->1"}],
            },
        }
        return pages[next_key]

    def dividends(self, code: str) -> dict:
        self.action_calls.append(("dividends", code))
        return {"code": code, "rows": [{"pub_date": "2026/03/18"}]}

    def close(self) -> None:
        pass


def test_settings_defaults() -> None:
    s = Settings()
    assert s.moomoo_opend_host == "127.0.0.1"
    assert s.moomoo_opend_port == 11111
    assert s.moomoo_opend_connect_timeout_s == 5.0
    assert s.moomoo_opend_request_timeout_s == 10.0


def test_settings_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QUANTMESH_MOOMOO_OPEND_PORT", "22222")
    assert Settings().moomoo_opend_port == 22222


@pytest.mark.parametrize("kwargs", [{"moomoo_opend_port": 0}, {"moomoo_opend_port": 70000}])
def test_settings_reject_invalid_port(kwargs: dict) -> None:
    with pytest.raises(ValidationError):
        Settings(**kwargs)


@pytest.mark.parametrize(
    "key", ["moomoo_opend_connect_timeout_s", "moomoo_opend_request_timeout_s"]
)
def test_settings_reject_nonpositive_timeouts(key: str) -> None:
    with pytest.raises(ValidationError):
        Settings(**{key: 0})


def test_probe_reports_capabilities() -> None:
    client = MoomooOpenDClient(StubTransport())
    caps = client.probe()
    assert caps == OpenDCapabilities(
        quote=True, history_kline=True, order=True, order_query=True, auth_required=False
    )


def test_probe_reports_auth_required() -> None:
    payload = dict(ALL_CAPABLE, order=True, order_query=True, auth_required=True)
    caps = MoomooOpenDClient(StubTransport(payload)).probe()
    # While the account is locked, trading capabilities are reported
    # unavailable no matter what the transport claims.
    assert caps.auth_required is True
    assert caps.order is False
    assert caps.order_query is False
    assert caps.quote is True


@pytest.mark.parametrize(
    "payload",
    [
        # auth_required missing
        {"quote": True, "history_kline": True, "order": True, "order_query": True},
        dict(ALL_CAPABLE, quote="yes"),  # wrong type
        dict(ALL_CAPABLE, order=1),  # non-bool
    ],
)
def test_probe_fails_closed_on_malformed_payload(payload: dict) -> None:
    with pytest.raises(OpenDProtocolError, match="probe payload"):
        MoomooOpenDClient(StubTransport(payload)).probe()


def test_probe_tolerates_extra_vendor_fields() -> None:
    payload = dict(ALL_CAPABLE, sdk_version="9.x")
    caps = MoomooOpenDClient(StubTransport(payload)).probe()
    assert caps.quote is True


def test_probe_fails_closed_on_non_dict_payload() -> None:
    with pytest.raises(OpenDProtocolError, match="probe payload"):
        MoomooOpenDClient(StubTransport([])).probe()  # type: ignore[arg-type]


def test_unavailable_error_propagates_typed() -> None:
    error = OpenDUnavailableError("connection refused")
    with pytest.raises(OpenDUnavailableError, match="connection refused"):
        MoomooOpenDClient(StubTransport(error=error)).probe()


def test_auth_required_error_propagates_typed() -> None:
    error = OpenDAuthRequiredError("account locked")
    with pytest.raises(OpenDAuthRequiredError, match="account locked"):
        MoomooOpenDClient(StubTransport(error=error)).probe()


def test_close_closes_transport() -> None:
    transport = StubTransport()
    client = MoomooOpenDClient(transport)
    client.close()
    assert transport.closed is True


def test_history_follows_every_page_and_preserves_cursors() -> None:
    transport = PagingTransport(
        [(_history_rows(0, 700), b"next-1"), (_history_rows(700, 600), None)]
    )

    pages = MoomooOpenDClient(transport).history_pages(
        "US.AAPL",
        interval="1m",
        start="2026-08-01",
        end="2026-08-07",
        max_pages=3,
        max_rows=2_000,
    )

    assert sum(len(page["rows"]) for page in pages) == 1_300
    assert transport.requested_cursors == [None, b"next-1"]
    assert [page["request_page_req_key"] for page in pages] == [None, "base64:bmV4dC0x"]


def test_history_rejects_repeated_cursor() -> None:
    transport = PagingTransport(
        [(_history_rows(0, 1), b"repeat"), (_history_rows(1, 1), b"repeat")]
    )

    with pytest.raises(OpenDProtocolError, match="repeated page cursor"):
        MoomooOpenDClient(transport).history_pages(
            "US.AAPL", interval="1m", start="2026-08-01", end="2026-08-07"
        )


def test_history_rejects_empty_nonterminal_page() -> None:
    transport = PagingTransport([([], b"unexpected-continuation")])

    with pytest.raises(OpenDProtocolError, match="empty nonterminal"):
        MoomooOpenDClient(transport).history_pages("US.AAPL", interval="1m")


def test_history_cursor_evidence_is_lossless_canonical_json() -> None:
    opaque = b"\x00\xffcursor"
    transport = PagingTransport([(_history_rows(0, 1), opaque), (_history_rows(1, 1), None)])

    pages = MoomooOpenDClient(transport).history_pages("US.AAPL", interval="1m")

    assert pages[0]["next_page_req_key"] == "base64:AP9jdXJzb3I="
    assert pages[1]["request_page_req_key"] == "base64:AP9jdXJzb3I="
    json.dumps(pages, allow_nan=False)


def test_structural_legacy_transport_gets_explicit_single_page_wrapper() -> None:
    class StructuralLegacyTransport:
        def history_kline(self, code, *, interval, start, end, autype):
            return {
                "code": code,
                "interval": interval,
                "autype": autype,
                "rows": _history_rows(0, 1),
            }

        def close(self) -> None:
            pass

    pages = MoomooOpenDClient(StructuralLegacyTransport()).history_pages("US.AAPL", interval="1m")

    assert pages[0]["_legacy_single_page"] is True


def test_history_enforces_page_row_and_date_bounds() -> None:
    too_many_pages = PagingTransport([(_history_rows(0, 1), b"next"), (_history_rows(1, 1), None)])
    with pytest.raises(OpenDProtocolError, match="max_pages"):
        MoomooOpenDClient(too_many_pages).history_pages("US.AAPL", interval="1m", max_pages=1)

    too_many_rows = PagingTransport([(_history_rows(0, 2), None)])
    with pytest.raises(OpenDProtocolError, match="max_rows"):
        MoomooOpenDClient(too_many_rows).history_pages("US.AAPL", interval="1m", max_rows=1)

    outside = PagingTransport([(_history_rows(1_400, 1), None)])
    with pytest.raises(OpenDProtocolError, match="requested date bounds"):
        MoomooOpenDClient(outside).history_pages(
            "US.AAPL", interval="1m", start="2026-08-01", end="2026-08-02"
        )
    with pytest.raises(ValueError, match="start must not be after end"):
        MoomooOpenDClient(outside).history_pages(
            "US.AAPL", interval="1m", start="2026-08-03", end="2026-08-02"
        )


def test_action_payloads_remain_pandas_free_and_splits_follow_pages() -> None:
    transport = PagingTransport([(_history_rows(0, 1), None)])
    client = MoomooOpenDClient(transport)

    factors = client.adjustment_factors("US.AAPL")
    split_pages = client.stock_splits("US.AAPL", max_pages=3, max_rows=10)
    dividends = client.dividends("US.AAPL")

    assert factors["rows"][0]["ex_div_date"] == "2026-08-01"
    assert [row["rate"] for page in split_pages for row in page["rows"]] == [
        "1->4",
        "4->1",
    ]
    assert dividends["rows"][0]["pub_date"] == "2026/03/18"
    assert transport.action_calls == [
        ("adjustment_factors", "US.AAPL"),
        ("stock_splits", "US.AAPL", None, 50),
        ("stock_splits", "US.AAPL", "page-2", 50),
        ("dividends", "US.AAPL"),
    ]


def test_stock_splits_reject_empty_nonterminal_page() -> None:
    class EmptySplitTransport(PagingTransport):
        def stock_splits_page(self, code: str, *, next_key: str | None, num: int) -> dict:
            return {
                "code": code,
                "request_next_key": next_key,
                "next_key": "more",
                "rows": [],
            }

    with pytest.raises(OpenDProtocolError, match="empty nonterminal"):
        MoomooOpenDClient(EmptySplitTransport([])).stock_splits("US.AAPL")


class _Records:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def to_dict(self, orient: str) -> list[dict]:
        assert orient == "records"
        return self._rows


class _QuoteContext:
    def __init__(self) -> None:
        self.closed = 0
        self.history_calls: list[bytes | None] = []

    def request_history_kline(self, code: str, **kwargs):
        cursor = kwargs["page_req_key"]
        self.history_calls.append(cursor)
        next_cursor = b"second" if cursor is None else None
        return 0, _Records(_history_rows(len(self.history_calls) - 1, 1)), next_cursor

    def get_rehab(self, code: str):
        return 0, _Records(
            [{"ex_div_date": "2026-08-01", "extra": "kept", "missing": float("nan")}]
        )

    def get_corporate_actions_stock_splits(self, code: str, **kwargs):
        return 0, {"next_key": "-1", "split_list": [{"ratio": "4:1", "extra": 7}]}

    def get_corporate_actions_dividends(self, code: str):
        return 0, {"dividend_list": [{"amount": 0.25, "extra": True}]}

    def close(self) -> None:
        self.closed += 1


def test_sdk_history_chain_uses_one_quote_context(monkeypatch) -> None:
    context = _QuoteContext()
    transport = SdkTransport(host="h", port=1, connect_timeout_s=1.0, request_timeout_s=1.0)
    monkeypatch.setattr(transport, "_open_quote_ctx", lambda: context)

    pages = MoomooOpenDClient(transport).history_pages("US.AAPL", interval="1m")

    assert len(pages) == 2
    assert context.history_calls == [None, b"second"]
    assert context.closed == 1


@pytest.mark.parametrize("ret", [False, 0.0, "0", None])
def test_sdk_history_rejects_non_integer_status(monkeypatch, ret) -> None:
    context = _QuoteContext()
    monkeypatch.setattr(
        context,
        "request_history_kline",
        lambda *args, **kwargs: (ret, _Records(_history_rows(0, 1)), None),
    )
    transport = SdkTransport(host="h", port=1, connect_timeout_s=1.0, request_timeout_s=1.0)
    monkeypatch.setattr(transport, "_open_quote_ctx", lambda: context)

    with pytest.raises(OpenDProtocolError, match="integer status"):
        MoomooOpenDClient(transport).history_pages("US.AAPL", interval="1m")
    assert context.closed == 1


def test_sdk_history_rejects_wrong_result_arity_as_protocol_error(monkeypatch) -> None:
    context = _QuoteContext()
    monkeypatch.setattr(context, "request_history_kline", lambda *args, **kwargs: (0,))
    transport = SdkTransport(host="h", port=1, connect_timeout_s=1.0, request_timeout_s=1.0)
    monkeypatch.setattr(transport, "_open_quote_ctx", lambda: context)

    with pytest.raises(OpenDProtocolError, match="3-item result"):
        MoomooOpenDClient(transport).history_pages("US.AAPL", interval="1m")
    assert context.closed == 1


@pytest.mark.parametrize("surface", ["adjustment", "split", "dividend"])
def test_sdk_actions_reject_boolean_status(monkeypatch, surface) -> None:
    context = _QuoteContext()
    if surface == "adjustment":
        monkeypatch.setattr(context, "get_rehab", lambda code: (False, _Records([])))
    elif surface == "split":
        monkeypatch.setattr(
            context,
            "get_corporate_actions_stock_splits",
            lambda code, **kwargs: (False, {"next_key": "-1", "split_list": []}),
        )
    else:
        monkeypatch.setattr(
            context,
            "get_corporate_actions_dividends",
            lambda code: (False, {"dividend_list": []}),
        )
    transport = SdkTransport(host="h", port=1, connect_timeout_s=1.0, request_timeout_s=1.0)
    monkeypatch.setattr(transport, "_open_quote_ctx", lambda: context)

    with pytest.raises(OpenDProtocolError, match="integer status"):
        if surface == "adjustment":
            transport.adjustment_factors("US.AAPL")
        elif surface == "split":
            transport.stock_splits_page("US.AAPL", next_key=None, num=50)
        else:
            transport.dividends("US.AAPL")
    assert context.closed == 1


def test_sdk_actions_preserve_raw_fields_and_close_quote_context(monkeypatch) -> None:
    context = _QuoteContext()
    transport = SdkTransport(host="h", port=1, connect_timeout_s=1.0, request_timeout_s=1.0)
    monkeypatch.setattr(transport, "_open_quote_ctx", lambda: context)

    factors = transport.adjustment_factors("US.AAPL")
    splits = transport.stock_splits_page("US.AAPL", next_key=None, num=50)
    dividends = transport.dividends("US.AAPL")

    assert factors["rows"] == [{"ex_div_date": "2026-08-01", "extra": "kept", "missing": None}]
    assert splits["rows"] == [{"ratio": "4:1", "extra": 7}]
    assert dividends["rows"] == [{"amount": 0.25, "extra": True}]
    json.dumps([factors, splits, dividends], allow_nan=False)
    assert context.closed == 3


def test_sdk_scalar_normalization_rejects_infinity_and_handles_nat(monkeypatch) -> None:
    import pandas as pd

    context = _QuoteContext()
    monkeypatch.setattr(
        context,
        "get_rehab",
        lambda code: (0, _Records([{"missing_date": pd.NaT, "missing_value": float("nan")}])),
    )
    transport = SdkTransport(host="h", port=1, connect_timeout_s=1.0, request_timeout_s=1.0)
    monkeypatch.setattr(transport, "_open_quote_ctx", lambda: context)

    assert transport.adjustment_factors("US.AAPL")["rows"] == [
        {"missing_date": None, "missing_value": None}
    ]

    monkeypatch.setattr(
        context, "get_rehab", lambda code: (0, _Records([{"bad_factor": float("inf")}]))
    )
    with pytest.raises(OpenDProtocolError, match="infinite"):
        transport.adjustment_factors("US.AAPL")


@pytest.mark.parametrize(
    ("method", "missing_name"),
    [
        ("stock_splits_page", "get_corporate_actions_stock_splits"),
        ("dividends", "get_corporate_actions_dividends"),
    ],
)
def test_sdk_actions_report_incompatible_sdk(monkeypatch, method, missing_name) -> None:
    context = _QuoteContext()
    monkeypatch.setattr(context, missing_name, None)
    transport = SdkTransport(host="h", port=1, connect_timeout_s=1.0, request_timeout_s=1.0)
    monkeypatch.setattr(transport, "_open_quote_ctx", lambda: context)

    with pytest.raises(OpenDProtocolError, match="does not expose"):
        if method == "stock_splits_page":
            transport.stock_splits_page("US.AAPL", next_key=None, num=50)
        else:
            transport.dividends("US.AAPL")
    assert context.closed == 1


@pytest.mark.parametrize(
    ("method", "payload", "message"),
    [
        ("stock_splits_page", {"next_key": "-1"}, "split_list"),
        ("stock_splits_page", {"split_list": []}, "next_key"),
        ("dividends", {}, "dividend_list"),
    ],
)
def test_sdk_actions_reject_missing_contract_keys(monkeypatch, method, payload, message) -> None:
    context = _QuoteContext()
    if method == "stock_splits_page":
        monkeypatch.setattr(
            context,
            "get_corporate_actions_stock_splits",
            lambda code, **kwargs: (0, payload),
        )
    else:
        monkeypatch.setattr(context, "get_corporate_actions_dividends", lambda code: (0, payload))
    transport = SdkTransport(host="h", port=1, connect_timeout_s=1.0, request_timeout_s=1.0)
    monkeypatch.setattr(transport, "_open_quote_ctx", lambda: context)

    with pytest.raises(OpenDProtocolError, match=message):
        if method == "stock_splits_page":
            transport.stock_splits_page("US.AAPL", next_key=None, num=50)
        else:
            transport.dividends("US.AAPL")
    assert context.closed == 1


def test_from_settings_builds_sdk_transport() -> None:
    client = MoomooOpenDClient.from_settings(Settings())
    assert isinstance(client._transport, SdkTransport)


def test_classify_auth_language_is_auth_required() -> None:
    transport = SdkTransport(host="h", port=1, connect_timeout_s=1.0, request_timeout_s=1.0)
    error = transport._classify(RuntimeError("please unlock your trade session first"))
    assert isinstance(error, OpenDAuthRequiredError)


def test_classify_connection_language_is_unavailable() -> None:
    transport = SdkTransport(host="h", port=1, connect_timeout_s=1.0, request_timeout_s=1.0)
    error = transport._classify(ConnectionRefusedError("connect call failed"))
    assert isinstance(error, OpenDUnavailableError)


@pytest.mark.skipif(
    importlib.util.find_spec("moomoo") is not None,
    reason="vendor SDK is importable here; probe would hit the real port",
)
def test_sdk_transport_probe_without_sdk_fails_typed() -> None:
    client = MoomooOpenDClient.from_settings(Settings())
    with pytest.raises(OpenDSdkMissingError, match="py-moomoo-api"):
        client.probe()
