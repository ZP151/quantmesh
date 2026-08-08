"""The Phase D surfaces: connector panel, credential-free public fetch
with deterministic fallback, and the CSV/JSON/Parquet import pipeline.

Under test, the public path runs against a scripted transport (the same
stub the reconnect drills use), so the tests never touch the network and
can exercise every failure mode: missing SDK, unreachable venue, rate
limit with one bounded retry. The import path drives real files through
the lake + ManifestWriter machinery and asserts the isolation gates:
imports only create new datasets, a reset wipes them, and the seeded
tree is byte-untouched.

The fallback contract is the centerpiece: an unreachable venue returns
the fixture book labeled synthetic with fallback_of + reason — never a
blank page and never an error page.
"""

import io
import json
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from quantmesh.demo.datalink import DatalinkService
from quantmesh.demo.manifest import DemoScenario
from quantmesh.demo.runtime import create_demo_app
from quantmesh.hyperliquid.errors import (
    HyperliquidSDKMissingError,
    HyperliquidUnavailableError,
)
from quantmesh.hyperliquid.rest import ScriptedRestTransport

SCENARIO = DemoScenario()

L2_PAYLOAD = {
    "levels": [
        [{"px": "150.5", "sz": "12.0", "n": 2}, {"px": "150.4", "sz": "30.0", "n": 1}],
        [{"px": "150.9", "sz": "8.0", "n": 1}, {"px": "151.0", "sz": "20.0", "n": 2}],
    ],
    "time": 1781000000000,
}


class _FailingTransport:
    """A RestTransport that raises one configured failure for every call."""

    def __init__(self, error: Exception, *, first_then_ok: bool = False) -> None:
        self._error = error
        self._calls = 0
        self._first_then_ok = first_then_ok

    def l2_book(self, symbol: str, *, at=None) -> dict:
        self._calls += 1
        if self._first_then_ok and self._calls > 1:
            return L2_PAYLOAD
        raise self._error

    def candles(self, symbol, interval, *, start, end):
        raise NotImplementedError

    def funding_history(self, symbol, *, start, end):
        raise NotImplementedError

    def meta(self) -> dict:
        raise NotImplementedError

    def spot_meta(self) -> dict:
        raise NotImplementedError


def _demo_client(tmp_path, **overrides):
    app = create_demo_app(root=tmp_path / "runtime", seed=SCENARIO.seed, host="127.0.0.1")
    service = DatalinkService(root=app.state.demo.root, **overrides)
    app.state.datalink = service
    return app, service


@pytest.fixture()
def demo_client(tmp_path: Path):
    app, service = _demo_client(tmp_path)
    with TestClient(app) as client:
        yield client, app, service


# --- connector panel -----------------------------------------------------


def test_panel_lists_all_five_connectors(demo_client):
    client, _, _ = demo_client
    rows = client.get("/api/demo/connectors").json()
    assert [row["venue"] for row in rows] == [
        "demo", "hyperliquid", "moomoo", "polymarket", "kalshi",
    ]
    assert rows[0]["state"] == "ok"  # fixture/demo is always available
    assert rows[1]["credentials_required"] is False
    assert rows[1]["read_only"] is True
    assert rows[3]["state"] == "unwired"
    assert "fixture-only" in rows[3]["detail"]


def test_probe_hyperliquid_ok_reports_latency(demo_client):
    client, _, service = demo_client
    service.rest = ScriptedRestTransport(l2_books={"BTC": L2_PAYLOAD})
    rows = client.post("/api/demo/connectors/probe").json()
    hl = next(row for row in rows if row["venue"] == "hyperliquid")
    assert hl["state"] == "ok"
    assert hl["latency_ms"] is not None
    assert hl["last_checked_at"] is not None


def test_probe_hyperliquid_missing_sdk_is_instructive(demo_client):
    client, _, service = demo_client
    service.rest = _FailingTransport(HyperliquidSDKMissingError("sdk not importable"))
    rows = client.post("/api/demo/connectors/probe").json()
    hl = next(row for row in rows if row["venue"] == "hyperliquid")
    assert hl["state"] == "degraded"
    assert "Missing software" in hl["detail"]
    assert hl["wired"] is False


def test_probe_hyperliquid_unreachable_is_degraded(demo_client):
    client, _, service = demo_client
    service.rest = _FailingTransport(
        HyperliquidUnavailableError("connection refused")
    )
    rows = client.post("/api/demo/connectors/probe").json()
    hl = next(row for row in rows if row["venue"] == "hyperliquid")
    assert hl["state"] == "degraded"
    assert "Unreachable" in hl["detail"]
    assert "falls back" in hl["detail"]


def test_probe_requires_origin_guard(demo_client):
    client, _, _ = demo_client
    response = client.post(
        "/api/demo/connectors/probe", headers={"Origin": "https://evil.example"}
    )
    assert response.status_code == 403


# --- credential-free public data path ------------------------------------


def test_fetch_public_caches_live_rows(demo_client, tmp_path):
    client, _, service = demo_client
    service.rest = ScriptedRestTransport(l2_books={"SOL": L2_PAYLOAD})
    report = client.post(
        "/api/demo/datalink/fetch", json={"symbols": ["SOL-USD"]}
    ).json()
    assert report["read_only"] is True
    assert report["synthetic"] is False
    row = report["rows"][0]
    assert row["symbol"] == "SOL-USD"
    assert row["coin"] == "SOL"
    assert row["source"] == "hyperliquid-public"
    assert row["synthetic"] is False
    assert row["best_bid"] == 150.5
    assert row["best_ask"] == 150.9
    assert row["reason"] is None
    # Cached under the demo root's .datalink dir, never in the seeded tree.
    cache_path = tmp_path / "runtime" / row["cache"]
    assert cache_path.is_file()
    cached = json.loads(cache_path.read_text(encoding="utf-8"))
    assert cached["source"] == "hyperliquid-public"
    assert cached["fetched_at"]
    # The provenance contract (seeded surfaces) is untouched by the cache.
    status = client.get("/api/demo/status").json()
    assert status["surfaces"]["orders"]["rows"] == 8
    # Cache manifest lists the entry.
    assert [entry["coin"] for entry in report["cached_entries"]] == ["SOL"]


def test_fetch_public_falls_back_deterministically(demo_client):
    client, _, service = demo_client
    service.rest = _FailingTransport(HyperliquidUnavailableError("connection refused"))
    report = client.post(
        "/api/demo/datalink/fetch", json={"symbols": ["SOL-USD"]}
    ).json()
    row = report["rows"][0]
    assert row["source"] == "fixture-fallback"
    assert row["synthetic"] is True
    assert row["fallback_of"] == "hyperliquid-public"
    assert row["degraded"] == "network"
    assert "Unreachable" in row["reason"]
    assert row["cache"] is None


def test_fetch_public_rate_limit_retries_once_then_falls_back(demo_client):
    client, _, service = demo_client
    # The first call is rate-limited; the retry succeeds — one bounded
    # retry with backoff is the rate-limit handling contract.
    service.rest = _FailingTransport(
        HyperliquidUnavailableError("429 rate limit exceeded"), first_then_ok=True
    )
    report = client.post(
        "/api/demo/datalink/fetch", json={"symbols": ["SOL-USD"]}
    ).json()
    assert report["rows"][0]["source"] == "hyperliquid-public"
    # A persistent rate limit still degrades, never errors.
    service.rest = _FailingTransport(
        HyperliquidUnavailableError("429 rate limit exceeded")
    )
    report = client.post(
        "/api/demo/datalink/fetch", json={"symbols": ["SOL-USD"]}
    ).json()
    row = report["rows"][0]
    assert row["source"] == "fixture-fallback"
    assert row["degraded"] == "rate-limited"


def test_fetch_public_missing_sdk_is_instructive(demo_client):
    client, _, service = demo_client
    service.rest = _FailingTransport(HyperliquidSDKMissingError("sdk not importable"))
    report = client.post(
        "/api/demo/datalink/fetch", json={"symbols": ["SOL-USD"]}
    ).json()
    row = report["rows"][0]
    assert row["source"] == "fixture-fallback"
    assert row["degraded"] == "missing-software"
    assert "Missing software" in row["reason"]


def test_fetch_public_refuses_empty_symbols(demo_client):
    client, _, _ = demo_client
    response = client.post("/api/demo/datalink/fetch", json={"symbols": []})
    assert response.status_code == 422


def test_datalink_missing_on_plain_app(tmp_path):
    from quantmesh.api.app import create_app

    with TestClient(create_app(account=None)) as client:  # type: ignore[arg-type]
        assert client.get("/api/demo/connectors").status_code == 404
        assert client.get("/api/demo/imports").status_code == 404


# --- CSV / JSON / Parquet import -----------------------------------------


def _upload(client, filename: str, data: bytes) -> dict:
    response = client.post(
        "/api/demo/import",
        files={"file": (filename, io.BytesIO(data))},
    )
    assert response.status_code == 200, response.text
    return response.json()


CSV_ROWS = (
    "timestamp,open,high,low,close,volume\n"
    "2026-08-01T00:00:00Z,100,105,99,104,1000\n"
    "2026-08-01T01:00:00Z,104,104,98,99,1200\n"
    "not-a-time,1,2,1,2,10\n"
    "2026-08-01T03:00:00Z,99,102,98,101,800\n"
)


def test_csv_import_preview_mapping_commit(demo_client, tmp_path):
    client, _, service = demo_client
    preview = _upload(client, "msft.csv", CSV_ROWS.encode())
    assert preview["format"] == "CSV"
    assert preview["rows"] == 4
    assert preview["filename"] == "msft.csv"
    # Auto-mapping picks the canonical column names.
    assert preview["suggested_mapping"] == {
        "timestamp": "timestamp",
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "volume": "volume",
    }
    assert len(preview["preview"]) == 4
    assert any(column["name"] == "close" for column in preview["columns"])

    body = {
        "session_id": preview["session_id"],
        "dataset": "imported-msft",
        "interval": "1h",
        "venue": "moomoo",
        "symbol": "MSFT",
        "mapping": preview["suggested_mapping"],
    }
    result = client.post("/api/demo/import/commit", json=body).json()
    assert result["dataset"] == "imported-msft"
    assert result["source"] == "operator-import"
    assert result["revision"] == 1
    assert result["accepted"] == 3  # the not-a-time row is rejected
    assert result["rejected"] == 1
    assert result["rejections"][0]["row"] == 4  # header + 2 valid rows precede it
    assert "timestamp" in result["rejections"][0]["reason"]
    coverage = result["coverage"][0]
    assert coverage["interval"] == "1h"
    assert coverage["venue"] == "moomoo"
    assert coverage["symbol"] == "MSFT"
    assert coverage["rows"] == 3

    # The imported dataset is listed and manifest-gated.
    imports = client.get("/api/demo/imports").json()
    assert [entry["dataset"] for entry in imports] == ["imported-msft"]
    assert imports[0]["rows"] == 3
    lake = service.root / "market" / "lake"
    assert (lake / "imported-msft" / "1h" / "moomoo" / "MSFT").is_dir()

    # The seeded surfaces are untouched by the import.
    assert client.get("/api/demo/status").json()["surfaces"]["orders"]["rows"] == 8


def test_json_import_records(demo_client):
    client, _, _ = demo_client
    rows = [
        {"ts": "2026-08-02T00:00:00+00:00", "open": 10, "high": 11, "low": 9,
         "close": 10.5, "vol": 500},
        {"ts": "2026-08-02T01:00:00+00:00", "open": 10.5, "high": 12, "low": 10,
         "close": 11.5, "vol": 600},
    ]
    preview = _upload(client, "btc.json", json.dumps(rows).encode())
    assert preview["format"] == "JSON"
    assert preview["rows"] == 2
    assert preview["suggested_mapping"]["timestamp"] == "ts"
    assert preview["suggested_mapping"]["volume"] == "vol"
    result = client.post(
        "/api/demo/import/commit",
        json={
            "session_id": preview["session_id"],
            "dataset": "imported-btc",
            "interval": "1h",
            "venue": "hyperliquid",
            "symbol": "BTC-USD",
            "mapping": preview["suggested_mapping"],
        },
    ).json()
    assert result["accepted"] == 2
    assert result["rejected"] == 0


def test_parquet_import_via_duckdb(demo_client, tmp_path):
    client, _, _ = demo_client
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2026-08-03 00:00:00", "2026-08-03 01:00:00"], utc=True
            ),
            "open": [1.0, 2.0],
            "high": [3.0, 4.0],
            "low": [0.5, 1.5],
            "close": [2.5, 3.5],
            "volume": [10, 20],
        }
    )
    import duckdb

    parquet_path = tmp_path / "sol.parquet"
    with duckdb.connect() as con:
        con.register("frame", frame)
        target = parquet_path.as_posix().replace("'", "''")
        con.execute(f"COPY frame TO '{target}' (FORMAT PARQUET)")
    preview = _upload(client, "sol.parquet", parquet_path.read_bytes())
    assert preview["format"] == "PARQUET"
    assert preview["rows"] == 2
    result = client.post(
        "/api/demo/import/commit",
        json={
            "session_id": preview["session_id"],
            "dataset": "imported-sol",
            "interval": "1h",
            "venue": "hyperliquid",
            "symbol": "SOL-USD",
            "mapping": preview["suggested_mapping"],
        },
    ).json()
    assert result["accepted"] == 2
    assert result["coverage"][0]["venue"] == "hyperliquid"


def test_import_refuses_overwrite_of_existing_dataset(demo_client):
    client, _, _ = demo_client
    preview = _upload(client, "dup.csv", CSV_ROWS.encode())
    body = {
        "session_id": preview["session_id"],
        "dataset": "imported-dup",
        "interval": "1h",
        "venue": "moomoo",
        "symbol": "AAPL",
        "mapping": preview["suggested_mapping"],
    }
    assert client.post("/api/demo/import/commit", json=body).status_code == 200
    # A second commit to the same dataset is refused — imports never
    # overwrite; the seeded tree is immutable to the import path.
    preview = _upload(client, "dup.csv", CSV_ROWS.encode())
    body["session_id"] = preview["session_id"]
    response = client.post("/api/demo/import/commit", json=body)
    assert response.status_code == 422
    assert "already exists" in response.json()["detail"]


def test_import_validation_reasons(demo_client):
    client, _, _ = demo_client
    bad = (
        "timestamp,open,high,low,close,volume\n"
        "2026-08-01T00:00:00Z,100,105,99,104,1000\n"
        "2026-08-01T01:00:00Z,104,104,110,99,1200\n"  # low > high
        "2026-08-01T02:00:00Z,abc,104,98,99,1200\n"  # open not numeric
    )
    preview = _upload(client, "bad.csv", bad.encode())
    result = client.post(
        "/api/demo/import/commit",
        json={
            "session_id": preview["session_id"],
            "dataset": "imported-bad",
            "interval": "1h",
            "venue": "moomoo",
            "symbol": "AAPL",
            "mapping": preview["suggested_mapping"],
        },
    ).json()
    assert result["accepted"] == 1
    assert result["rejected"] == 2
    reasons = [entry["reason"] for entry in result["rejections"]]
    assert any("exceeds high" in reason for reason in reasons)
    assert any("is not a number" in reason for reason in reasons)


def test_import_unreadable_file_is_instructive(demo_client):
    client, _, _ = demo_client
    response = client.post(
        "/api/demo/import", files={"file": ("junk.txt", io.BytesIO(b"hello"))}
    )
    assert response.status_code == 422
    assert "unsupported file type" in response.json()["detail"]
    response = client.post(
        "/api/demo/import", files={"file": ("junk.csv", io.BytesIO(b""))}
    )
    assert response.status_code == 422
    assert "no rows" in response.json()["detail"]


def test_import_missing_session_is_instructive(demo_client):
    client, _, _ = demo_client
    response = client.post(
        "/api/demo/import/commit",
        json={
            "session_id": "does-not-exist",
            "dataset": "x",
            "interval": "1h",
            "venue": "moomoo",
            "symbol": "AAPL",
            "mapping": {"timestamp": "timestamp"},
        },
    )
    assert response.status_code == 422
    assert "upload the file again" in response.json()["detail"]


def test_reset_clears_imports_and_datalink(demo_client, tmp_path):
    client, _, service = demo_client
    preview = _upload(client, "msft.csv", CSV_ROWS.encode())
    client.post(
        "/api/demo/import/commit",
        json={
            "session_id": preview["session_id"],
            "dataset": "imported-msft",
            "interval": "1h",
            "venue": "moomoo",
            "symbol": "MSFT",
            "mapping": preview["suggested_mapping"],
        },
    )
    assert client.get("/api/demo/imports").json()
    # A live cache entry exists.
    service.rest = ScriptedRestTransport(l2_books={"SOL": L2_PAYLOAD})
    client.post("/api/demo/datalink/fetch", json={"symbols": ["SOL-USD"]})
    assert service.cache_manifest()
    # Reset restores the pristine root: imports and cache are gone.
    response = client.post("/api/demo/reset")
    assert response.status_code == 200
    assert client.get("/api/demo/imports").json() == []
    assert service.cache_manifest() == []
    assert (tmp_path / "runtime" / ".datalink").exists() is False
    # Import sessions are gone too: a stale commit is refused instructively.
    response = client.post(
        "/api/demo/import/commit",
        json={
            "session_id": preview["session_id"],
            "dataset": "imported-msft",
            "interval": "1h",
            "venue": "moomoo",
            "symbol": "MSFT",
            "mapping": preview["suggested_mapping"],
        },
    )
    assert response.status_code == 422
    assert "upload the file again" in response.json()["detail"]


def test_import_write_is_origin_guarded(demo_client):
    client, _, _ = demo_client
    response = client.post(
        "/api/demo/import",
        files={"file": ("a.csv", io.BytesIO(b"x"))},
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 403
