"""Literal local authority; hostile URLs never become operator origins."""

import pytest
from fastapi.testclient import TestClient

from quantmesh.api import workstation
from quantmesh.api.watchlist import WatchlistStore
from quantmesh.execution.accounting import PaperAccount


@pytest.mark.parametrize(
    "host", ["127.attacker.example", "127.0.0.1.example", "127.1", "127.0.0.999"]
)
def test_dns_127_prefix_is_not_loopback(host):
    assert not workstation._is_loopback(host)


@pytest.mark.parametrize(
    "origin",
    [
        "https://127.attacker.example",
        "ftp://localhost",
        "//localhost",
        "http://user@localhost",
        "http://localhost:99999",
        "http://localhost:bad",
        "http://localhost/path",
        "http://localhost?x=1",
        "http://localhost#x",
        "http://[::1",
        "http://localhost:",
        "http://localhost/",
        "http://localhost\n",
        "http://localhost?",
        "http://localhost#",
        "http://[::1]attacker.example",
        "http://[::1]%suffix",
        "http://[::1]attacker.example:8000",
        "http://[::1]%suffix:8000",
    ],
)
def test_noncanonical_browser_origins_refused(origin):
    assert not workstation._is_allowed_browser_origin(origin)


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost",
        "https://localhost:8000",
        "http://127.0.0.1:8000",
        "http://127.99.99.99",
        "http://[::1]:8000",
    ],
)
def test_literal_local_browser_origins_are_admitted(origin):
    assert workstation._is_allowed_browser_origin(origin)


def test_private_staging_origin_is_exact(monkeypatch):
    origin = "https://research.example.ts.net"
    monkeypatch.setattr(workstation.settings, "environment", "staging")
    monkeypatch.setattr(workstation.settings, "staging_origin", origin)
    assert workstation._is_allowed_browser_origin(origin)
    assert not workstation._is_allowed_browser_origin(origin + ".attacker.example")


def test_hostile_origin_cannot_change_paper_account(tmp_path):
    app = workstation.create_workstation_app(
        account=PaperAccount(cash=1000),
        host="127.0.0.1",
        watchlist=WatchlistStore(tmp_path / "watchlist"),
    )
    client = TestClient(app)
    response = client.post(
        "/api/kill-switch",
        json={"action": "engage"},
        headers={"Origin": "https://127.attacker.example"},
    )
    assert response.status_code == 403
    assert not app.state.account_store.get().kill_switch
    response = client.post(
        "/api/kill-switch", json={"action": "engage"}, headers={"Origin": "http://127.0.0.1:8000"}
    )
    assert response.status_code == 200
    assert app.state.account_store.get().kill_switch
