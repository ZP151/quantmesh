"""Opt-in live read-only smoke drill checks (0015 Phase G).

The checker functions take an injected HTTP getter, so every branch —
the honest ladder, the connected-flag agreement, the watchlist
presence, a dead station, a malformed body — is drilled without the
network. The getter contract mirrors ``urllib``: returns the body
string or raises ``urllib.error.URLError``.
"""

import urllib.error

from tools.live_smoke import (
    check_health,
    check_state,
    check_status,
    check_watchlist,
    run_once,
)


def _health_body() -> dict:
    return {"version": "0.1.0rc5", "status": "ok"}


def _kind(**overrides: object) -> dict:
    kind = {
        "kind": "quote",
        "provenance": "real",
        "data_time": "2026-08-09T12:00:00+00:00",
        "received_at": "2026-08-09T12:00:00+00:00",
        "age_ms": 0,
        "sequence": 5,
        "sequence_gap": False,
        "label": "real",
        "payload": {"bid": 100.0, "ask": 100.5},
    }
    kind.update(overrides)
    return kind


def _state_body(**overrides: object) -> dict:
    state = {
        "generated_at": "2026-08-09T12:00:00+00:00",
        "instruments": {
            "BTC": {
                "venue": "hyperliquid",
                "label": "real",
                "kinds": {"quote": _kind()},
            }
        },
    }
    state.update(overrides)
    return state


def _status_body(**overrides: object) -> dict:
    status = {
        "generated_at": "2026-08-09T12:00:00+00:00",
        "venues": [
            {
                "venue": "hyperliquid",
                "connected": True,
                "sources": [
                    {
                        "instrument": "BTC",
                        "state": "connected",
                        "note": "freshness state -> connected",
                        "data_time": None,
                        "received_at": None,
                        "age_ms": 0,
                    }
                ],
            }
        ],
    }
    status.update(overrides)
    return status


def _fake_getter(bodies: dict[str, str]) -> callable:
    def getter(url: str, timeout: float) -> str:
        del timeout
        try:
            return bodies[url]
        except KeyError:
            raise urllib.error.URLError(f"no server at {url}") from None

    return getter


def _healthy_getter() -> callable:
    import json

    base = "http://127.0.0.1:8766"
    return _fake_getter(
        {
            f"{base}/health": json.dumps(_health_body()),
            f"{base}/live/state": json.dumps(_state_body()),
            f"{base}/live/status": json.dumps(_status_body()),
        }
    )


class TestHealth:
    def test_healthy_station_passes(self) -> None:
        checks = check_health(_healthy_getter(), "http://127.0.0.1:8766", 10.0)
        assert all(check.ok for check in checks)

    def test_missing_version_fails(self) -> None:
        import json

        getter = _fake_getter(
            {"http://127.0.0.1:8766/health": json.dumps({"status": "ok"})}
        )
        checks = check_health(getter, "http://127.0.0.1:8766", 10.0)
        assert not all(check.ok for check in checks)
        assert any("version" in check.label for check in checks if not check.ok)

    def test_unhealthy_status_fails_even_with_a_version(self) -> None:
        import json

        getter = _fake_getter(
            {
                "http://127.0.0.1:8766/health": json.dumps(
                    {"status": "error", "version": "0.1.0rc5"}
                )
            }
        )
        checks = check_health(getter, "http://127.0.0.1:8766", 10.0)
        assert any(not check.ok and "reports ok" in check.label for check in checks)

    def test_dead_server_fails(self) -> None:
        checks = check_health(_fake_getter({}), "http://127.0.0.1:8766", 10.0)
        assert not checks[0].ok
        assert "no server" in checks[0].detail

    def test_non_json_fails(self) -> None:
        getter = _fake_getter({"http://127.0.0.1:8766/health": "<html>down</html>"})
        checks = check_health(getter, "http://127.0.0.1:8766", 10.0)
        assert not all(check.ok for check in checks)
        assert "not JSON" in checks[0].detail


class TestLatestState:
    def test_healthy_surface_passes(self) -> None:
        checks = check_state(_healthy_getter(), "http://127.0.0.1:8766", 10.0)
        assert all(check.ok for check in checks)
        assert any("non-empty" in check.label for check in checks)

    def test_badge_outside_the_ladder_fails(self) -> None:
        import json

        instruments = _state_body()["instruments"]
        instruments["BTC"] = instruments["BTC"] | {"label": "live"}
        body = json.dumps(_state_body(instruments=instruments))
        getter = _fake_getter({"http://127.0.0.1:8766/live/state": body})
        checks = check_state(getter, "http://127.0.0.1:8766", 10.0)
        failed = [check for check in checks if not check.ok]
        assert any("badge is honest" in check.label for check in failed)
        assert any("outside the ladder" in check.detail for check in failed)

    def test_kind_provenance_outside_the_ladder_fails(self) -> None:
        import json

        instruments = _state_body()["instruments"]
        instruments["BTC"]["kinds"]["quote"] = _kind(provenance="live")
        getter = _fake_getter(
            {"http://127.0.0.1:8766/live/state": json.dumps(_state_body(instruments=instruments))}
        )
        checks = check_state(getter, "http://127.0.0.1:8766", 10.0)
        failed = [check for check in checks if not check.ok]
        assert any("view is honest" in check.label for check in failed)
        assert any("provenance" in check.detail for check in failed)

    def test_negative_sequence_fails(self) -> None:
        import json

        instruments = _state_body()["instruments"]
        instruments["BTC"]["kinds"]["quote"] = _kind(sequence=-1)
        getter = _fake_getter(
            {"http://127.0.0.1:8766/live/state": json.dumps(_state_body(instruments=instruments))}
        )
        checks = check_state(getter, "http://127.0.0.1:8766", 10.0)
        failed = [check for check in checks if not check.ok]
        assert any("sequence" in check.detail for check in failed)

    def test_empty_surface_fails(self) -> None:
        import json

        getter = _fake_getter(
            {
                "http://127.0.0.1:8766/live/state": json.dumps(
                    _state_body(instruments={})
                )
            }
        )
        checks = check_state(getter, "http://127.0.0.1:8766", 10.0)
        assert any(not check.ok and "non-empty" in check.label for check in checks)

    def test_unavailable_badge_and_kinds_are_accepted(self) -> None:
        """The honest degraded surface is a PASS: an instrument whose
        badge is 'unavailable' (a closed venue, a disconnected source)
        stays inside the ladder and so does its kind views."""
        import json

        instruments = {
            "AAPL": {
                "venue": "moomoo",
                "label": "unavailable",
                "kinds": {},
            }
        }
        getter = _fake_getter(
            {
                "http://127.0.0.1:8766/live/state": json.dumps(
                    _state_body(instruments=instruments)
                )
            }
        )
        checks = check_state(getter, "http://127.0.0.1:8766", 10.0)
        assert all(check.ok for check in checks)

    def test_real_badge_with_empty_kinds_fails(self) -> None:
        import json

        body = _state_body(
            instruments={"BTC": {"venue": "hyperliquid", "label": "real", "kinds": {}}}
        )
        getter = _fake_getter(
            {"http://127.0.0.1:8766/live/state": json.dumps(body)}
        )
        checks = check_state(getter, "http://127.0.0.1:8766", 10.0)
        assert any(not check.ok and "market data" in check.label for check in checks)

    def test_missing_venue_and_invalid_kind_shape_fail(self) -> None:
        import json

        body = _state_body(
            instruments={
                "BTC": {
                    "venue": "",
                    "label": "real",
                    "kinds": {"quote": _kind(received_at="not-a-time", payload=[])},
                }
            }
        )
        getter = _fake_getter(
            {"http://127.0.0.1:8766/live/state": json.dumps(body)}
        )
        failed = [
            check
            for check in check_state(getter, "http://127.0.0.1:8766", 10.0)
            if not check.ok
        ]
        assert any("venue" in check.label for check in failed)
        assert any("received_at" in check.detail for check in failed)
        assert any("payload" in check.detail for check in failed)


class TestConnectorHealth:
    def test_healthy_surface_passes(self) -> None:
        checks = check_status(_healthy_getter(), "http://127.0.0.1:8766", 10.0)
        assert all(check.ok for check in checks)

    def test_source_state_outside_the_ladder_fails(self) -> None:
        import json

        venues = _status_body()["venues"]
        venues[0]["sources"][0]["state"] = "live"
        getter = _fake_getter(
            {"http://127.0.0.1:8766/live/status": json.dumps(_status_body(venues=venues))}
        )
        checks = check_status(getter, "http://127.0.0.1:8766", 10.0)
        failed = [check for check in checks if not check.ok]
        assert any("state is honest" in check.label for check in failed)

    def test_connected_flag_mismatch_fails(self) -> None:
        """connected=True with zero live sources is a lie the drill
        must catch."""
        import json

        venues = _status_body()["venues"]
        venues[0]["sources"][0]["state"] = "disconnected"
        getter = _fake_getter(
            {"http://127.0.0.1:8766/live/status": json.dumps(_status_body(venues=venues))}
        )
        checks = check_status(getter, "http://127.0.0.1:8766", 10.0)
        failed = [check for check in checks if not check.ok]
        assert any("connected flag" in check.label for check in failed)
        assert any("0 live sources" in check.detail for check in failed)

    def test_disconnected_venue_passes(self) -> None:
        """The honest disconnected state is a PASS: connected=False
        with no live sources is exactly how a closed venue looks."""
        import json

        venues = _status_body()["venues"]
        venues[0]["connected"] = False
        venues[0]["sources"][0]["state"] = "disconnected"
        getter = _fake_getter(
            {"http://127.0.0.1:8766/live/status": json.dumps(_status_body(venues=venues))}
        )
        checks = check_status(getter, "http://127.0.0.1:8766", 10.0)
        assert all(check.ok for check in checks)

    def test_empty_venue_surface_fails(self) -> None:
        import json

        getter = _fake_getter(
            {
                "http://127.0.0.1:8766/live/status": json.dumps(
                    _status_body(venues=[])
                )
            }
        )
        checks = check_status(getter, "http://127.0.0.1:8766", 10.0)
        assert any(not check.ok and "non-empty" in check.label for check in checks)


class TestWatchlist:
    def test_missing_instrument_fails(self) -> None:
        checks = check_watchlist(_healthy_getter(), "http://127.0.0.1:8766", 10.0, ["NVDA"])
        assert not checks[0].ok
        assert "absent" in checks[0].detail

    def test_present_instrument_passes(self) -> None:
        checks = check_watchlist(_healthy_getter(), "http://127.0.0.1:8766", 10.0, ["BTC"])
        assert checks[0].ok

    def test_empty_watchlist_runs_nothing(self) -> None:
        assert check_watchlist(_healthy_getter(), "http://127.0.0.1:8766", 10.0, []) == []

    def test_dead_station_fails_closed(self) -> None:
        checks = check_watchlist(_fake_getter({}), "http://127.0.0.1:8766", 10.0, ["BTC"])
        assert not checks[0].ok


class TestRunOnce:
    def test_healthy_station_passes_every_check(self) -> None:
        checks = run_once(_healthy_getter(), "http://127.0.0.1:8766", 10.0, ["BTC"])
        assert checks
        assert all(check.ok for check in checks)

    def test_dead_station_fails_every_surface(self) -> None:
        checks = run_once(_fake_getter({}), "http://127.0.0.1:8766", 10.0, [])
        assert checks
        assert not all(check.ok for check in checks)
        failed_labels = [check.label for check in checks if not check.ok]
        assert any("health" in label for label in failed_labels)
        assert any("latest-state" in label for label in failed_labels)
        assert any("connector-health" in label for label in failed_labels)
