"""Moomoo OpenD client boundary tests (issue #25, Phase A).

The client must be fully testable with no OpenD instance and no vendor
SDK installed: tests inject a stub transport and assert typed errors,
capability parsing, and fail-closed payload handling.
"""

import importlib.util

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
