import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from quantmesh.data.collection_process import (
    CollectionProcessTimeout,
    run_bounded_json_process,
)
from quantmesh.data.moomoo_collection import (
    CollectionStatus,
    CollectionWindow,
    MoomooCollectionPlan,
    MoomooCollectionResult,
    MoomooWorkerRequest,
    evaluate_equity_coverage,
    run_moomoo_worker,
)
from quantmesh.domain.market_data import Bar
from quantmesh.domain.models import Instrument, InstrumentType, Venue


def test_bounded_plan_contains_only_approved_symbols_and_intervals() -> None:
    plan = MoomooCollectionPlan.bounded_default()

    assert {
        (target.provider_symbol, target.canonical_instrument.value, target.interval)
        for target in plan.targets
    } == {
        ("US.AAPL", "moomoo:US:AAPL:XNAS", "1d"),
        ("US.AAPL", "moomoo:US:AAPL:XNAS", "1m"),
        ("US.NVDA", "moomoo:US:NVDA:XNAS", "1d"),
        ("US.NVDA", "moomoo:US:NVDA:XNAS", "1m"),
    }
    assert plan.process_deadline_seconds == 120


def test_collection_window_is_utc_ordered_and_bounded() -> None:
    start = datetime(2026, 8, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="UTC"):
        CollectionWindow(start=start.replace(tzinfo=None), end=start)
    with pytest.raises(ValueError, match="after"):
        CollectionWindow(start=start, end=start - timedelta(days=1))
    with pytest.raises(ValueError, match="366"):
        CollectionWindow(start=start, end=start + timedelta(days=367))


def test_closed_xnys_session_is_not_a_gap() -> None:
    window = CollectionWindow(
        start=datetime(2025, 11, 26, tzinfo=UTC),
        end=datetime(2025, 11, 28, 23, 59, tzinfo=UTC),
    )

    report = evaluate_equity_coverage(
        window,
        observed_sessions=(date(2025, 11, 26), date(2025, 11, 28)),
    )

    assert report.expected == (date(2025, 11, 26), date(2025, 11, 28))
    assert report.missing == ()
    assert report.unexpected == ()


def test_weekend_observation_is_reported_as_unexpected_not_expected() -> None:
    window = CollectionWindow(
        start=datetime(2025, 11, 28, tzinfo=UTC),
        end=datetime(2025, 11, 30, 23, 59, tzinfo=UTC),
    )

    report = evaluate_equity_coverage(
        window,
        observed_sessions=(date(2025, 11, 28), date(2025, 11, 29)),
    )

    assert report.missing == ()
    assert report.unexpected == (date(2025, 11, 29),)


def test_unavailable_result_cannot_claim_real_manifests() -> None:
    result = MoomooCollectionResult.unavailable(
        reason_code="sdk-missing",
        detail="compatible Moomoo SDK is not installed",
    )
    assert result.status is CollectionStatus.UNAVAILABLE
    assert result.manifest_ids == ()

    with pytest.raises(ValueError, match="unavailable"):
        MoomooCollectionResult(
            status=CollectionStatus.UNAVAILABLE,
            reason_code="sdk-missing",
            detail="missing",
            manifest_ids=("a" * 64,),
        )


def test_collection_worker_is_process_bounded_and_leaves_no_staged_output(
    tmp_path: Path,
) -> None:
    with pytest.raises(CollectionProcessTimeout, match="process deadline"):
        run_bounded_json_process(
            [
                sys.executable,
                "-c",
                "import time; time.sleep(30)",
                "{request}",
                "{output}",
            ],
            request={"surface": "read-only"},
            timeout_seconds=0.05,
            scratch_root=tmp_path,
        )

    assert list(tmp_path.iterdir()) == []


def test_collection_worker_returns_only_staged_json(tmp_path: Path) -> None:
    script = (
        "import json,pathlib,sys;"
        "request=json.loads(pathlib.Path(sys.argv[1]).read_text());"
        "pathlib.Path(sys.argv[2]).write_text(json.dumps({'echo':request}))"
    )
    result = run_bounded_json_process(
        [sys.executable, "-c", script, "{request}", "{output}"],
        request={"symbol": "US.AAPL"},
        timeout_seconds=5,
        scratch_root=tmp_path,
    )

    assert result == {"echo": {"symbol": "US.AAPL"}}
    assert list(tmp_path.iterdir()) == []


def test_isolated_moomoo_result_is_revalidated_before_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = next(
        item
        for item in MoomooCollectionPlan.bounded_default().targets
        if item.provider_symbol == "US.AAPL" and item.interval == "1d"
    )
    window = CollectionWindow(
        start=datetime(2026, 8, 10, tzinfo=UTC),
        end=datetime(2026, 8, 12, 23, 59, tzinfo=UTC),
    )
    request = MoomooWorkerRequest(
        target=target,
        window=window,
        host="127.0.0.1",
        port=11111,
        connect_timeout_seconds=1.0,
        request_timeout_seconds=2.0,
    )
    bar = Bar(
        instrument=Instrument(
            symbol="AAPL",
            venue=Venue.MOOMOO,
            instrument_type=InstrumentType.EQUITY,
            currency="USD",
        ),
        timestamp=datetime(2026, 8, 10, 4, 0, tzinfo=UTC),
        interval="1d",
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        volume=1_000.0,
    )
    raw_result = {
        "status": "published",
        "reason_code": None,
        "detail": None,
        "payload": {
            "provider_version": "10.10.7008",
            "received_at": "2026-08-13T00:00:00Z",
            "bars": [bar.model_dump(mode="json")],
            "history_pages": [
                {
                    "code": "US.AAPL",
                    "interval": "1d",
                    "autype": "None",
                    "rows": [
                        {
                            "code": "US.AAPL",
                            "time_key": "2026-08-10",
                            "open": 100.0,
                            "high": 101.0,
                            "low": 99.0,
                            "close": 100.0,
                            "volume": 1_000.0,
                        }
                    ],
                }
            ],
            "adjustment_factors": {"code": "US.AAPL", "rows": []},
            "stock_split_pages": [{"code": "US.AAPL", "rows": []}],
            "dividends": {"code": "US.AAPL", "rows": []},
        },
    }
    monkeypatch.setattr(
        "quantmesh.data.moomoo_collection.run_bounded_json_process",
        lambda *args, **kwargs: raw_result,
    )

    result = run_moomoo_worker(
        request,
        process_deadline_seconds=5,
        scratch_root=tmp_path,
    )
    assert result.payload is not None
    assert result.payload.bars == (bar,)

    raw_result["payload"]["history_pages"][0]["code"] = "US.NVDA"
    with pytest.raises(ValueError, match="code disagrees"):
        run_moomoo_worker(
            request,
            process_deadline_seconds=5,
            scratch_root=tmp_path,
        )
