from datetime import UTC, datetime
from importlib import import_module, util


def classify(**kwargs):
    assert util.find_spec("tools.server_market_inventory"), "typed inventory boundary is absent"
    return import_module("tools.server_market_inventory").classify_market_path(**kwargs)


def test_ready_forwarded_gateway_is_personal_pc_and_stale_ingestion():
    result = classify(
        provider="moomoo",
        listener_owner="tailscaled",
        upstream_location="windows",
        readiness="ready",
        last_source_time=datetime(2026, 10, 9, 20, tzinfo=UTC),
        session_open=True,
        now=datetime(2026, 10, 12, 14, tzinfo=UTC),
        provider_delay_seconds=0,
    )
    assert result["gateway_location"] == "personal_pc"
    assert result["pc_dependency"] == "yes"
    assert result["readiness"] == "ready"
    assert result["ingestion"] == "stale"


def test_native_listener_does_not_prove_ingestion():
    result = classify(
        provider="moomoo",
        listener_owner="OpenD",
        upstream_location="server",
        readiness="ready",
        last_source_time=None,
        session_open=True,
        now=datetime(2026, 10, 12, 14, tzinfo=UTC),
    )
    assert result["gateway_location"] == "server"
    assert result["ingestion"] == "unknown"


def test_closed_data_is_accepted_by_shared_calendar_policy():
    result = classify(
        provider="moomoo",
        listener_owner="tailscaled",
        upstream_location="windows",
        readiness="ready",
        last_source_time=datetime(2026, 10, 9, 20, tzinfo=UTC),
        session_open=False,
        now=datetime(2026, 10, 11, 14, tzinfo=UTC),
        provider_delay_seconds=0,
    )
    assert result["ingestion"] == "latest_session"


def test_unknown_delay_or_forward_target_stays_unknown():
    result = classify(
        provider="moomoo",
        listener_owner="sshd",
        upstream_location="unknown",
        readiness="ready",
        last_source_time=datetime(2026, 10, 9, 20, tzinfo=UTC),
        session_open=True,
        now=datetime(2026, 10, 12, 13, 37, tzinfo=UTC),
    )
    assert result["gateway_location"] == "unknown"
    assert result["ingestion"] == "unknown"
    assert result["pc_dependency"] == "unknown"


def test_inventory_declares_crypto_observation_clock_and_lag():
    result = classify(
        provider="hyperliquid",
        listener_owner="direct",
        upstream_location="server",
        readiness="ready",
        session_open=True,
        last_source_time=datetime(2026, 10, 12, 11, 59, 45, tzinfo=UTC),
        now=datetime(2026, 10, 12, 12, tzinfo=UTC),
        provider_delay_seconds=0,
        source_kind="observation",
        interval="30s",
    )
    assert result["ingestion"] == "fresh"
