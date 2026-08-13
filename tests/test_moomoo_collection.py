import json
import os
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from quantmesh.data.artifacts import (
    ArtifactLayer,
    ArtifactManifest,
    ManifestIntegrityError,
    ManifestStore,
    canonical_json_bytes,
)
from quantmesh.data.capabilities import DataKind
from quantmesh.data.collection_process import (
    CollectionProcessTimeout,
    run_bounded_json_process,
)
from quantmesh.data.envelopes import RawEnvelope
from quantmesh.data.fabric import MoomooFabricPublisher
from quantmesh.data.moomoo_collection import (
    CollectionStatus,
    CollectionWindow,
    MoomooCollectionPlan,
    MoomooCollectionResult,
    MoomooCollector,
    MoomooRawPayload,
    MoomooWorkerRequest,
    MoomooWorkerResult,
    evaluate_equity_coverage,
    run_moomoo_worker,
)
from quantmesh.data.moomoo_collection_worker import collect as collect_moomoo_bundle
from quantmesh.domain.market_data import Bar
from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.moomoo.opend import OpenDUnavailableError
from quantmesh.moomoo.provider import MoomooOpenDProvider
from quantmesh.settings import Settings


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


def test_worker_maps_provider_market_before_opening_opend(monkeypatch) -> None:
    target = MoomooCollectionPlan.bounded_default().targets[0]
    request = MoomooWorkerRequest(
        target=target,
        window=CollectionWindow(
            start=datetime(2026, 8, 1, tzinfo=UTC),
            end=datetime(2026, 8, 8, 23, 59, tzinfo=UTC),
        ),
        host="127.0.0.1",
        port=11111,
        connect_timeout_seconds=1.0,
        request_timeout_seconds=2.0,
    )

    def unavailable(self, instrument, **kwargs):
        assert instrument.metadata == {"market": "US"}
        raise OpenDUnavailableError("OpenD is not running")

    monkeypatch.setattr(
        "quantmesh.data.moomoo_collection_worker.version",
        lambda package: "10.10.7008",
    )
    monkeypatch.setattr(
        "quantmesh.data.moomoo_collection_worker._opend_reachable",
        lambda *args: True,
    )
    monkeypatch.setattr(MoomooOpenDProvider, "fetch_raw_bundle", unavailable)

    result = collect_moomoo_bundle(request)

    assert result.status is CollectionStatus.UNAVAILABLE
    assert result.reason_code == "daemon-unavailable"


def test_worker_reports_unreachable_daemon_before_starting_sdk(monkeypatch) -> None:
    target = MoomooCollectionPlan.bounded_default().targets[0]
    request = MoomooWorkerRequest(
        target=target,
        window=CollectionWindow(
            start=datetime(2026, 8, 1, tzinfo=UTC),
            end=datetime(2026, 8, 8, 23, 59, tzinfo=UTC),
        ),
        host="127.0.0.1",
        port=11111,
        connect_timeout_seconds=1.0,
        request_timeout_seconds=2.0,
    )
    monkeypatch.setattr(
        "quantmesh.data.moomoo_collection_worker.version",
        lambda package: "10.10.7008",
    )
    monkeypatch.setattr(
        "quantmesh.data.moomoo_collection_worker._opend_reachable",
        lambda *args: False,
    )
    monkeypatch.setattr(
        MoomooOpenDProvider,
        "fetch_raw_bundle",
        lambda *args, **kwargs: pytest.fail("unreachable daemon must not start the SDK"),
    )

    result = collect_moomoo_bundle(request)

    assert result.status is CollectionStatus.UNAVAILABLE
    assert result.reason_code == "daemon-unavailable"


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


def test_collection_worker_does_not_buffer_sdk_stdout_or_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}
    real_popen = subprocess.Popen

    def recording_popen(*args, **kwargs):
        observed.update(stdout=kwargs.get("stdout"), stderr=kwargs.get("stderr"))
        return real_popen(*args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", recording_popen)
    script = "import json,pathlib,sys;pathlib.Path(sys.argv[2]).write_text('{}')"

    run_bounded_json_process(
        [sys.executable, "-c", script, "{request}", "{output}"],
        request={},
        timeout_seconds=5,
        scratch_root=tmp_path,
    )

    assert observed == {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}


def test_collection_worker_has_runtime_home_but_no_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QUANTMESH_MODEL_API_KEY", "must-not-reach-worker")
    script = (
        "import json,os,pathlib,sys;"
        "result={'home':str(pathlib.Path.home()),"
        "'appdata':os.environ.get('APPDATA'),"
        "'has_secret':'QUANTMESH_MODEL_API_KEY' in os.environ};"
        "pathlib.Path(sys.argv[2]).write_text(json.dumps(result))"
    )

    result = run_bounded_json_process(
        [sys.executable, "-c", script, "{request}", "{output}"],
        request={},
        timeout_seconds=5,
        scratch_root=tmp_path,
    )

    assert result["home"]
    if os.name == "nt":
        assert result["appdata"]
    assert result["has_secret"] is False


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


def _split_payload(request: MoomooWorkerRequest) -> MoomooRawPayload:
    instrument = Instrument(
        symbol="AAPL",
        venue=Venue.MOOMOO,
        instrument_type=InstrumentType.EQUITY,
        currency="USD",
    )
    dates_and_closes = (
        ("2020-08-28", datetime(2020, 8, 28, 4, tzinfo=UTC), 100.0),
        ("2020-08-31", datetime(2020, 8, 31, 4, tzinfo=UTC), 26.0),
        ("2020-09-01", datetime(2020, 9, 1, 4, tzinfo=UTC), 27.0),
    )
    rows = [
        {
            "code": "US.AAPL",
            "time_key": date_text,
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": 1_000.0,
        }
        for date_text, _, close in dates_and_closes
    ]
    bars = tuple(
        Bar(
            instrument=instrument,
            timestamp=timestamp,
            interval=request.target.interval,
            open=close,
            high=close,
            low=close,
            close=close,
            volume=1_000.0,
        )
        for _, timestamp, close in dates_and_closes
    )
    announcement = datetime(2020, 8, 17, tzinfo=UTC)
    return MoomooRawPayload(
        provider_version="10.10.7008",
        received_at=datetime(2020, 9, 2, tzinfo=UTC),
        bars=bars,
        history_pages=(
            {"code": "US.AAPL", "interval": "1d", "autype": "None", "rows": rows},
        ),
        adjustment_factors={
            "code": "US.AAPL",
            "rows": [
                {
                    "ex_div_date": "2020-08-31",
                    "split_base": 1.0,
                    "split_ert": 4.0,
                    "split_ratio": 0.25,
                }
            ],
        },
        stock_split_pages=(
            {
                "code": "US.AAPL",
                "rows": [
                    {
                        "dir_deci_pub_date": int(announcement.timestamp()),
                        "dir_deci_pub_date_str": "2020-08-17",
                        "reform_type": "Split",
                        "rate": "1->4",
                    }
                ],
            },
        ),
        dividends={"code": "US.AAPL", "rows": []},
    )


def test_real_bundle_publishes_separate_raw_and_adjusted_lineage(tmp_path: Path) -> None:
    target = next(
        item
        for item in MoomooCollectionPlan.bounded_default().targets
        if item.provider_symbol == "US.AAPL" and item.interval == "1d"
    )
    request = MoomooWorkerRequest(
        target=target,
        window=CollectionWindow(
            start=datetime(2020, 8, 28, tzinfo=UTC),
            end=datetime(2020, 9, 1, 23, 59, tzinfo=UTC),
        ),
        host="127.0.0.1",
        port=11111,
        connect_timeout_seconds=1.0,
        request_timeout_seconds=2.0,
    )
    store = ManifestStore(tmp_path)
    publisher = MoomooFabricPublisher(store, code_commit="c" * 40)

    publication = publisher.publish(request, _split_payload(request))
    repeated = publisher.publish(request, _split_payload(request))

    assert repeated == publication
    assert len(set(publication.manifest_ids)) == 8
    assert all(
        store.open(manifest_id).manifest.manifest_id == manifest_id
        for manifest_id in publication.manifest_ids
    )
    adjusted = store.open(publication.adjusted_id)
    assert [bar.close for bar in adjusted.read_bars()] == [25.0, 26.0, 27.0]
    assert [bar.volume for bar in adjusted.read_bars()] == [4_000.0, 1_000.0, 1_000.0]
    adjusted_manifest = adjusted.manifest
    assert adjusted_manifest.layer is ArtifactLayer.ADJUSTED
    assert adjusted_manifest.adjustment_policy == "split-adjusted-v1"
    assert adjusted_manifest.parent_manifest_ids == (
        publication.normalized_id,
        publication.actions_id,
    )
    actions = store.open(publication.actions_id).manifest
    assert actions.parent_manifest_ids == (
        publication.factors_raw_id,
        publication.splits_raw_id,
    )
    dividend_raw = store.open(publication.dividends_raw_id).manifest
    assert dividend_raw.layer is ArtifactLayer.RAW


def test_publication_validation_rejects_forged_adjusted_lineage(tmp_path: Path) -> None:
    target = next(
        item
        for item in MoomooCollectionPlan.bounded_default().targets
        if item.provider_symbol == "US.AAPL" and item.interval == "1d"
    )
    request = MoomooWorkerRequest(
        target=target,
        window=CollectionWindow(
            start=datetime(2020, 8, 28, tzinfo=UTC),
            end=datetime(2020, 9, 1, 23, 59, tzinfo=UTC),
        ),
        host="127.0.0.1",
        port=11111,
        connect_timeout_seconds=1.0,
        request_timeout_seconds=2.0,
    )
    store = ManifestStore(tmp_path)
    publisher = MoomooFabricPublisher(store, code_commit="c" * 40)
    publication = publisher.publish(request, _split_payload(request))
    adjusted = store.open(publication.adjusted_id).manifest
    normalized = store.open(publication.normalized_id).manifest
    values = adjusted.model_dump(exclude={"manifest_id", "compatibility_revision"})
    values.update(dataset_id="forged-aapl-adjusted", objects=normalized.objects)
    forged = ArtifactManifest.build(compatibility_revision=1, **values)
    store.publish(forged, expected_current=None)

    with pytest.raises(ManifestIntegrityError, match="not policy-derived"):
        publisher.validate_publication(
            publication.model_copy(update={"adjusted_id": forged.manifest_id})
        )


def test_publication_validation_rejects_wrong_raw_role(tmp_path: Path) -> None:
    target = MoomooCollectionPlan.bounded_default().targets[0]
    request = MoomooWorkerRequest(
        target=target,
        window=CollectionWindow(
            start=datetime(2020, 8, 28, tzinfo=UTC),
            end=datetime(2020, 9, 1, 23, 59, tzinfo=UTC),
        ),
        host="127.0.0.1",
        port=11111,
        connect_timeout_seconds=1.0,
        request_timeout_seconds=2.0,
    )
    publisher = MoomooFabricPublisher(ManifestStore(tmp_path), code_commit="c" * 40)
    publication = publisher.publish(request, _split_payload(request))

    with pytest.raises(ManifestIntegrityError, match="manifest roles"):
        publisher.validate_publication(
            publication.model_copy(
                update={"dividends_raw_id": publication.factors_raw_id}
            )
        )


def test_raw_validation_recomputes_factor_identities_and_event_range(tmp_path: Path) -> None:
    target = MoomooCollectionPlan.bounded_default().targets[0]
    request = MoomooWorkerRequest(
        target=target,
        window=CollectionWindow(
            start=datetime(2020, 8, 28, tzinfo=UTC),
            end=datetime(2020, 9, 1, 23, 59, tzinfo=UTC),
        ),
        host="127.0.0.1",
        port=11111,
        connect_timeout_seconds=1.0,
        request_timeout_seconds=2.0,
    )
    store = ManifestStore(tmp_path)
    publisher = MoomooFabricPublisher(store, code_commit="c" * 40)
    publication = publisher.publish(request, _split_payload(request))
    raw = store.open(publication.factors_raw_id).manifest
    envelope_ref = next(
        item
        for item in raw.objects
        if item.media_type == "application/vnd.quantmesh.raw-envelope+json"
    )
    source_ref = next(item for item in raw.objects if item != envelope_ref)
    envelope = RawEnvelope.model_validate_json(store.objects.get_bytes(envelope_ref))
    forged_time = request.window.start
    forged_envelope = envelope.model_copy(
        update={
            "source_event_ids": ("forged-factor",),
            "event_start": forged_time,
            "event_end": forged_time,
            "session_date": forged_time.date(),
        }
    )
    forged_envelope_ref = store.objects.put_bytes(
        "application/vnd.quantmesh.raw-envelope+json",
        forged_envelope.canonical_bytes(),
    )
    values = raw.model_dump(exclude={"manifest_id", "compatibility_revision"})
    values.update(
        dataset_id="forged-factor-raw",
        objects=(source_ref, forged_envelope_ref),
        row_identities=("forged-factor",),
        event_start=forged_time,
        event_end=forged_time,
    )
    forged = ArtifactManifest.build(compatibility_revision=1, **values)
    store.publish(forged, expected_current=None)

    with pytest.raises(ManifestIntegrityError, match="source-derived"):
        publisher._read_raw(
            forged.manifest_id,
            expected_kind=DataKind.ADJUSTMENT_FACTORS,
            expected_endpoint="get_rehab",
        )


def test_raw_bar_validation_binds_declared_interval_to_source(tmp_path: Path) -> None:
    target = MoomooCollectionPlan.bounded_default().targets[0]
    request = MoomooWorkerRequest(
        target=target,
        window=CollectionWindow(
            start=datetime(2020, 8, 28, tzinfo=UTC),
            end=datetime(2020, 9, 1, 23, 59, tzinfo=UTC),
        ),
        host="127.0.0.1",
        port=11111,
        connect_timeout_seconds=1.0,
        request_timeout_seconds=2.0,
    )
    store = ManifestStore(tmp_path)
    publisher = MoomooFabricPublisher(store, code_commit="c" * 40)
    publication = publisher.publish(request, _split_payload(request))
    raw = store.open(publication.bars_raw_id).manifest
    values = raw.model_dump(exclude={"manifest_id", "compatibility_revision"})
    values.update(dataset_id="forged-bars-raw", interval="1m")
    forged = ArtifactManifest.build(compatibility_revision=1, **values)
    store.publish(forged, expected_current=None)

    with pytest.raises(ManifestIntegrityError, match="source-derived"):
        publisher._read_raw(
            forged.manifest_id,
            expected_kind=DataKind.BARS,
            expected_endpoint="request_history_kline",
        )


def test_raw_validation_rejects_cross_symbol_factor_source(tmp_path: Path) -> None:
    target = MoomooCollectionPlan.bounded_default().targets[0]
    request = MoomooWorkerRequest(
        target=target,
        window=CollectionWindow(
            start=datetime(2020, 8, 28, tzinfo=UTC),
            end=datetime(2020, 9, 1, 23, 59, tzinfo=UTC),
        ),
        host="127.0.0.1",
        port=11111,
        connect_timeout_seconds=1.0,
        request_timeout_seconds=2.0,
    )
    store = ManifestStore(tmp_path)
    publisher = MoomooFabricPublisher(store, code_commit="c" * 40)
    publication = publisher.publish(request, _split_payload(request))
    raw = store.open(publication.factors_raw_id).manifest
    envelope_ref = next(
        item
        for item in raw.objects
        if item.media_type == "application/vnd.quantmesh.raw-envelope+json"
    )
    source_ref = next(item for item in raw.objects if item != envelope_ref)
    source = json.loads(store.objects.get_bytes(source_ref))
    source["code"] = "US.NVDA"
    forged_source_ref = store.objects.put_bytes(
        source_ref.media_type,
        canonical_json_bytes(source),
    )
    envelope = RawEnvelope.model_validate_json(store.objects.get_bytes(envelope_ref))
    forged_envelope = envelope.model_copy(update={"raw_object": forged_source_ref})
    forged_envelope_ref = store.objects.put_bytes(
        envelope_ref.media_type,
        forged_envelope.canonical_bytes(),
    )
    values = raw.model_dump(exclude={"manifest_id", "compatibility_revision"})
    values.update(
        dataset_id="forged-cross-symbol-factor",
        objects=(forged_source_ref, forged_envelope_ref),
    )
    forged = ArtifactManifest.build(compatibility_revision=1, **values)
    store.publish(forged, expected_current=None)

    with pytest.raises(ManifestIntegrityError, match="source declarations"):
        publisher._read_raw(
            forged.manifest_id,
            expected_kind=DataKind.ADJUSTMENT_FACTORS,
            expected_endpoint="get_rehab",
        )


def test_publication_validation_rejects_forged_feature_declaration(tmp_path: Path) -> None:
    target = MoomooCollectionPlan.bounded_default().targets[0]
    request = MoomooWorkerRequest(
        target=target,
        window=CollectionWindow(
            start=datetime(2020, 8, 28, tzinfo=UTC),
            end=datetime(2020, 9, 1, 23, 59, tzinfo=UTC),
        ),
        host="127.0.0.1",
        port=11111,
        connect_timeout_seconds=1.0,
        request_timeout_seconds=2.0,
    )
    store = ManifestStore(tmp_path)
    publisher = MoomooFabricPublisher(store, code_commit="c" * 40)
    publication = publisher.publish(request, _split_payload(request))
    feature = store.open(publication.feature_id).manifest
    values = feature.model_dump(exclude={"manifest_id", "compatibility_revision"})
    values.update(
        dataset_id="forged-aapl-feature",
        transformation_policy_digest="0" * 64,
    )
    forged = ArtifactManifest.build(compatibility_revision=1, **values)
    store.publish(forged, expected_current=None)

    with pytest.raises(ManifestIntegrityError, match="feature declaration"):
        publisher.validate_publication(
            publication.model_copy(update={"feature_id": forged.manifest_id})
        )


def test_publication_validation_rejects_forged_action_coverage(tmp_path: Path) -> None:
    target = MoomooCollectionPlan.bounded_default().targets[0]
    request = MoomooWorkerRequest(
        target=target,
        window=CollectionWindow(
            start=datetime(2020, 8, 28, tzinfo=UTC),
            end=datetime(2020, 9, 1, 23, 59, tzinfo=UTC),
        ),
        host="127.0.0.1",
        port=11111,
        connect_timeout_seconds=1.0,
        request_timeout_seconds=2.0,
    )
    store = ManifestStore(tmp_path)
    publisher = MoomooFabricPublisher(store, code_commit="c" * 40)
    publication = publisher.publish(request, _split_payload(request))
    actions = store.open(publication.actions_id).manifest
    values = actions.model_dump(exclude={"manifest_id", "compatibility_revision"})
    values.update(
        dataset_id="forged-action-coverage",
        event_start=request.window.start,
        event_end=request.window.start,
    )
    forged = ArtifactManifest.build(compatibility_revision=1, **values)
    store.publish(forged, expected_current=None)

    with pytest.raises(ManifestIntegrityError, match="action coverage"):
        publisher.validate_publication(
            publication.model_copy(update={"actions_id": forged.manifest_id})
        )


def test_empty_action_coverage_is_bound_to_empty_source_evidence(tmp_path: Path) -> None:
    target = MoomooCollectionPlan.bounded_default().targets[0]
    request = MoomooWorkerRequest(
        target=target,
        window=CollectionWindow(
            start=datetime(2020, 8, 28, tzinfo=UTC),
            end=datetime(2020, 9, 1, 23, 59, tzinfo=UTC),
        ),
        host="127.0.0.1",
        port=11111,
        connect_timeout_seconds=1.0,
        request_timeout_seconds=2.0,
    )
    payload = _split_payload(request).model_copy(
        update={
            "adjustment_factors": {"code": "US.AAPL", "rows": []},
            "stock_split_pages": ({"code": "US.AAPL", "rows": []},),
        }
    )
    store = ManifestStore(tmp_path)
    publication = MoomooFabricPublisher(store, code_commit="c" * 40).publish(
        request, payload
    )
    factors = store.open(publication.factors_raw_id).manifest
    splits = store.open(publication.splits_raw_id).manifest
    actions = store.open(publication.actions_id).manifest
    source_evidence_time = max(factors.event_end, splits.event_end)

    assert actions.event_start == source_evidence_time
    assert actions.event_end == source_evidence_time


def test_factor_action_mismatch_creates_no_manifest(tmp_path: Path) -> None:
    target = next(
        item
        for item in MoomooCollectionPlan.bounded_default().targets
        if item.provider_symbol == "US.AAPL" and item.interval == "1d"
    )
    request = MoomooWorkerRequest(
        target=target,
        window=CollectionWindow(
            start=datetime(2020, 8, 28, tzinfo=UTC),
            end=datetime(2020, 9, 1, 23, 59, tzinfo=UTC),
        ),
        host="localhost",
        port=11111,
        connect_timeout_seconds=1.0,
        request_timeout_seconds=2.0,
    )
    payload = _split_payload(request)
    bad_page = {
        **payload.stock_split_pages[0],
        "rows": [{**payload.stock_split_pages[0]["rows"][0], "rate": "1->5"}],
    }
    payload = payload.model_copy(update={"stock_split_pages": (bad_page,)})
    store = ManifestStore(tmp_path)

    with pytest.raises(ValueError, match="ambiguous or incomplete"):
        MoomooFabricPublisher(store, code_commit="d" * 40).publish(request, payload)

    datasets = tmp_path / ".quantmesh-fabric" / "datasets"
    assert not datasets.exists()


def test_collector_publishes_nothing_when_worker_is_unavailable(tmp_path: Path) -> None:
    target = next(
        item
        for item in MoomooCollectionPlan.bounded_default().targets
        if item.provider_symbol == "US.AAPL" and item.interval == "1d"
    )
    plan = MoomooCollectionPlan(targets=(target,), process_deadline_seconds=5)

    def unavailable(*args, **kwargs) -> MoomooWorkerResult:
        return MoomooWorkerResult(
            status=CollectionStatus.UNAVAILABLE,
            reason_code="daemon-unavailable",
            detail="OpenD is not running",
        )

    result = MoomooCollector(
        ManifestStore(tmp_path / "fabric"),
        code_commit="e" * 40,
        scratch_root=tmp_path / "scratch",
        settings=Settings(moomoo_opend_host="127.0.0.1"),
        worker=unavailable,
    ).collect(
        plan,
        CollectionWindow(
            start=datetime(2020, 8, 28, tzinfo=UTC),
            end=datetime(2020, 9, 1, 23, 59, tzinfo=UTC),
        ),
    )

    assert result.status is CollectionStatus.UNAVAILABLE
    assert result.reason_code == "daemon-unavailable"
    assert result.manifest_ids == ()
    assert not (tmp_path / "fabric" / ".quantmesh-fabric" / "datasets").exists()


def test_collector_publishes_complete_single_target_result(tmp_path: Path) -> None:
    target = next(
        item
        for item in MoomooCollectionPlan.bounded_default().targets
        if item.provider_symbol == "US.AAPL" and item.interval == "1d"
    )
    window = CollectionWindow(
        start=datetime(2020, 8, 28, tzinfo=UTC),
        end=datetime(2020, 9, 1, 23, 59, tzinfo=UTC),
    )
    request = MoomooWorkerRequest(
        target=target,
        window=window,
        host="127.0.0.1",
        port=11111,
        connect_timeout_seconds=5.0,
        request_timeout_seconds=10.0,
    )

    def successful(*args, **kwargs) -> MoomooWorkerResult:
        return MoomooWorkerResult(
            status=CollectionStatus.PUBLISHED,
            payload=_split_payload(request),
        )

    store = ManifestStore(tmp_path / "fabric")
    parent_observed_before = datetime.now(UTC)
    result = MoomooCollector(
        store,
        code_commit="f" * 40,
        scratch_root=tmp_path / "scratch",
        worker=successful,
    ).collect(MoomooCollectionPlan(targets=(target,)), window)

    assert result.status is CollectionStatus.PUBLISHED
    assert len(result.manifest_ids) == 8
    assert store.open(result.manifest_ids[0]).manifest.knowledge_end >= parent_observed_before
