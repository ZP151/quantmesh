"""`quantmesh-moomoo probe` operator command tests (issue #25, Phase A).

The command is the only way to reach a real local OpenD instance, and it
must be an explicit operator action: it probes capabilities and prints a
redacted report to stdout, writes nothing to disk, reads no credentials,
and exits with a typed status code per failure class.
"""

import pytest

from quantmesh.moomoo import cli
from quantmesh.moomoo.opend import (
    OpenDAuthRequiredError,
    OpenDCapabilities,
    OpenDSdkMissingError,
    OpenDUnavailableError,
)


class StubClient:
    def __init__(
        self, caps: OpenDCapabilities | None = None, error: Exception | None = None
    ) -> None:
        self.caps = caps
        self.error = error
        self.closed = False

    def probe(self) -> OpenDCapabilities:
        if self.error is not None:
            raise self.error
        default = OpenDCapabilities(True, True, True, True, False)
        return self.caps if self.caps is not None else default

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def stub_client(monkeypatch: pytest.MonkeyPatch) -> StubClient:
    client = StubClient()
    monkeypatch.setattr(cli, "_build_client", lambda _settings: client)
    return client


def test_probe_prints_redacted_report(
    stub_client: StubClient, capsys: pytest.CaptureFixture
) -> None:
    assert cli.main(["probe"]) == 0
    out = capsys.readouterr().out
    assert "quote=True" in out
    assert "order=True" in out
    assert "auth_required=False" in out
    assert stub_client.closed is True


def test_probe_unavailable_exits_1(
    stub_client: StubClient, capsys: pytest.CaptureFixture
) -> None:
    stub_client.error = OpenDUnavailableError("connection refused")
    assert cli.main(["probe"]) == 1
    assert "unavailable" in capsys.readouterr().err.lower()


def test_probe_auth_required_exits_2(
    stub_client: StubClient, capsys: pytest.CaptureFixture
) -> None:
    stub_client.error = OpenDAuthRequiredError("account locked")
    assert cli.main(["probe"]) == 2
    assert "auth" in capsys.readouterr().err.lower()


def test_probe_sdk_missing_exits_3(
    stub_client: StubClient, capsys: pytest.CaptureFixture
) -> None:
    stub_client.error = OpenDSdkMissingError("vendor sdk not importable")
    assert cli.main(["probe"]) == 3
    assert "sdk" in capsys.readouterr().err.lower()


def test_probe_rejects_unknown_command(stub_client: StubClient) -> None:
    with pytest.raises(SystemExit):
        cli.main(["unlock"])
    assert stub_client.closed is False


def test_probe_closes_client_on_failure(stub_client: StubClient) -> None:
    stub_client.error = OpenDUnavailableError("down")
    cli.main(["probe"])
    assert stub_client.closed is True
