import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import quantmesh.data.hyperliquid_collection as collection_module
from quantmesh.data.artifacts import (
    ArtifactLayer,
    ArtifactManifest,
    ManifestIntegrityError,
    ManifestStore,
)
from quantmesh.data.hyperliquid_collection import (
    HyperliquidCollectionWindow,
    HyperliquidCollector,
    book_side_source_event_id,
    book_snapshot_epoch,
    trade_source_event_id,
)
from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.hyperliquid.errors import HyperliquidProtocolError
from quantmesh.hyperliquid.market_data import HyperliquidDataAdapter
from quantmesh.hyperliquid.public_info import (
    MAINNET_INFO_URL,
    PublicInfoResponse,
    PublicInfoTransport,
)

NOW = datetime(2026, 8, 14, tzinfo=UTC)


def test_microstructure_identities_are_provider_semantic_and_shared() -> None:
    first = trade_source_event_id(1_750_000_000_000, "btc", 11)
    same = trade_source_event_id(1_750_000_000_000, "BTC", 11)
    later_block = trade_source_event_id(1_750_000_000_001, "BTC", 11)
    epoch = book_snapshot_epoch(
        1_750_000_000_000,
        "btc",
        [[100.0, 1.0]],
        [[100.5, 2.0]],
    )

    assert first == same
    assert first != later_block
    assert book_side_source_event_id(epoch, "bid") != book_side_source_event_id(
        epoch, "ask"
    )


@pytest.mark.parametrize(
    ("block_time", "tid"),
    [(True, 1), (1, False), ("1", 1), (1, "1")],
)
def test_trade_identity_rejects_non_integer_wire_values(
    block_time: object, tid: object
) -> None:
    with pytest.raises(ValueError, match="integer"):
        trade_source_event_id(block_time, "BTC", tid)  # type: ignore[arg-type]


def _candle(index: int) -> dict:
    opened = NOW + timedelta(minutes=index)
    return {
        "t": int(opened.timestamp() * 1000),
        "T": int((opened + timedelta(minutes=1)).timestamp() * 1000) - 1,
        "s": "BTC",
        "i": "1m",
        "o": "100",
        "h": "110",
        "l": "99",
        "c": str(100 + index),
        "v": "10",
        "n": 1,
    }


class ScriptedPublicInfo:
    def __init__(
        self,
        rows: list[dict],
        *,
        received_at: datetime = NOW + timedelta(minutes=10),
    ) -> None:
        self.rows = rows
        self.received_at = received_at
        self.calls = 0

    def candles(self, symbol: str, interval: str, *, start: datetime, end: datetime):
        self.calls += 1
        raw = json.dumps(self.rows, separators=(",", ":")).encode()
        return PublicInfoResponse(
            payload=self.rows,
            raw_bytes=raw,
            received_at=self.received_at,
        )


class StubResponse:
    status_code = 200

    def __init__(self, rows: list[dict]) -> None:
        self.content = json.dumps(rows, separators=(",", ":")).encode()


class StubClient:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self.calls = 0

    def post(self, url: str, *, json: dict, timeout: float) -> StubResponse:
        self.calls += 1
        assert url == MAINNET_INFO_URL
        return StubResponse(self.rows)


def _window(minutes: int = 2) -> HyperliquidCollectionWindow:
    return HyperliquidCollectionWindow(
        start=NOW,
        end=NOW + timedelta(minutes=minutes),
    )


def test_candle_backfill_is_bounded_by_provider_limit(tmp_path: Path) -> None:
    collector = HyperliquidCollector(
        ManifestStore(tmp_path),
        transport=ScriptedPublicInfo([]),
        code_commit="a" * 40,
    )

    with pytest.raises(HyperliquidProtocolError, match="5,000"):
        collector.collect_candles(
            ["BTC"],
            "1m",
            _window(5_000),
        )


def test_real_transport_refuses_unadvertised_interval_before_network(
    tmp_path: Path,
) -> None:
    client = StubClient([])
    collector = HyperliquidCollector(
        ManifestStore(tmp_path),
        transport=PublicInfoTransport(client=client),
        code_commit="9" * 40,
    )

    with pytest.raises(HyperliquidProtocolError, match="exact read-only"):
        collector.collect_candles(
            ["BTC"],
            "10m",
            HyperliquidCollectionWindow(
                start=NOW,
                end=NOW + timedelta(minutes=20),
            ),
        )

    assert client.calls == 0


def test_direct_network_refuses_unverified_code_identity_before_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = PublicInfoTransport()

    def fail_if_called(*args: object, **kwargs: object) -> PublicInfoResponse:
        raise AssertionError("network must not be reached")

    monkeypatch.setattr(PublicInfoTransport, "candles", fail_if_called)
    monkeypatch.setattr(collection_module, "_clean_git_commit_matches", lambda commit: True)
    collector = HyperliquidCollector(
        ManifestStore(tmp_path),
        transport=transport,
        code_commit="8" * 40,
    )
    monkeypatch.setattr(collection_module, "_clean_git_commit_matches", lambda commit: False)

    with pytest.raises(HyperliquidProtocolError, match="code identity"):
        collector.collect_candles(["BTC"], "1m", _window())


def test_code_identity_is_rechecked_immediately_before_each_symbol_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    verdicts = iter((True, False))
    monkeypatch.setattr(
        collection_module,
        "_clean_git_commit_matches",
        lambda commit: next(verdicts),
    )

    def candles(
        self: PublicInfoTransport,
        symbol: str,
        interval: str,
        *,
        start: datetime,
        end: datetime,
    ) -> PublicInfoResponse:
        calls.append(symbol)
        rows = [{**_candle(index), "s": symbol} for index in range(3)]
        return PublicInfoResponse(
            payload=rows,
            raw_bytes=json.dumps(rows, separators=(",", ":")).encode(),
            received_at=NOW + timedelta(minutes=10),
        )

    monkeypatch.setattr(PublicInfoTransport, "candles", candles)
    collector = HyperliquidCollector(
        ManifestStore(tmp_path),
        transport=PublicInfoTransport(),
        code_commit="8" * 40,
    )

    with pytest.raises(HyperliquidProtocolError, match="code identity"):
        collector.collect_candles(["BTC", "ETH"], "1m", _window())

    assert calls == ["BTC"]


@pytest.mark.parametrize(
    "mutate",
    (
        lambda row: {key: value for key, value in row.items() if key != "n"},
        lambda row: {**row, "unexpected": "field"},
        lambda row: {**row, "c": 101.0},
    ),
)
def test_collection_rejects_noncanonical_candle_wire_contract(
    tmp_path: Path,
    mutate: Callable[[dict], dict],
) -> None:
    rows = [_candle(index) for index in range(3)]
    rows[1] = mutate(rows[1])
    root = tmp_path / "fabric"
    collector = HyperliquidCollector(
        ManifestStore(root),
        transport=ScriptedPublicInfo(rows),
        code_commit="5" * 40,
    )

    with pytest.raises(HyperliquidProtocolError, match="wire contract"):
        collector.collect_candles(["BTC"], "1m", _window())

    assert not (root / ".quantmesh-fabric" / "datasets").exists()


def test_public_candles_publish_four_layer_identity_lineage(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    transport = ScriptedPublicInfo([_candle(index) for index in range(3)])
    collector = HyperliquidCollector(
        store,
        transport=transport,
        code_commit="b" * 40,
    )

    publication = collector.collect_candles(
        ["BTC"],
        "1m",
        _window(),
    )[0]
    repeated = collector.collect_candles(
        ["BTC"],
        "1m",
        _window(),
    )[0]

    assert repeated == publication
    assert transport.calls == 2
    assert len(set(publication.manifest_ids)) == 4
    raw, normalized, adjusted, feature = [
        store.open(item).manifest for item in publication.manifest_ids
    ]
    assert [item.layer for item in (raw, normalized, adjusted, feature)] == [
        ArtifactLayer.RAW,
        ArtifactLayer.NORMALIZED,
        ArtifactLayer.ADJUSTED,
        ArtifactLayer.FEATURE,
    ]
    assert normalized.parent_manifest_ids == (raw.manifest_id,)
    assert adjusted.parent_manifest_ids == (normalized.manifest_id,)
    assert adjusted.adjustment_policy == "identity-no-corporate-actions-v1"
    assert feature.parent_manifest_ids == (adjusted.manifest_id,)
    assert publication.qualifies is False


def test_injected_http_client_cannot_publish_qualifying_lineage(
    tmp_path: Path,
) -> None:
    transport = PublicInfoTransport(
        client=StubClient([_candle(index) for index in range(3)]),
        clock=lambda: NOW + timedelta(minutes=10),
    )
    collector = HyperliquidCollector(
        ManifestStore(tmp_path),
        transport=transport,
        code_commit="d" * 40,
    )

    publication = collector.collect_candles(["BTC"], "1m", _window())[0]
    envelope = collector.raw_envelope(publication)

    assert publication.qualifies is False
    assert envelope.qualifies is False
    assert envelope.endpoint == MAINNET_INFO_URL


def test_collection_rejects_gapped_or_truncated_window(tmp_path: Path) -> None:
    rows = [_candle(index) for index in (0, 2, 3)]
    collector = HyperliquidCollector(
        ManifestStore(tmp_path),
        transport=ScriptedPublicInfo(rows),
        code_commit="e" * 40,
    )

    with pytest.raises(HyperliquidProtocolError, match="complete requested window"):
        collector.collect_candles(["BTC"], "1m", _window(3))


def test_collection_rejects_provisional_candle(tmp_path: Path) -> None:
    collector = HyperliquidCollector(
        ManifestStore(tmp_path),
        transport=ScriptedPublicInfo(
            [_candle(index) for index in range(3)],
            received_at=NOW + timedelta(minutes=2, seconds=30),
        ),
        code_commit="f" * 40,
    )

    with pytest.raises(HyperliquidProtocolError, match="not final"):
        collector.collect_candles(["BTC"], "1m", _window())


def test_collection_requires_exclusive_close_boundary(tmp_path: Path) -> None:
    rows = [_candle(index) for index in range(3)]
    last_inclusive_millisecond = datetime.fromtimestamp(rows[-1]["T"] / 1_000, tz=UTC)
    collector = HyperliquidCollector(
        ManifestStore(tmp_path),
        transport=ScriptedPublicInfo(
            rows,
            received_at=last_inclusive_millisecond,
        ),
        code_commit="6" * 40,
    )

    with pytest.raises(HyperliquidProtocolError, match="not final"):
        collector.collect_candles(["BTC"], "1m", _window())


def test_collection_rejects_unaligned_window_before_network(tmp_path: Path) -> None:
    root = tmp_path / "fabric"
    transport = ScriptedPublicInfo([_candle(index) for index in range(3)])
    collector = HyperliquidCollector(
        ManifestStore(root),
        transport=transport,
        code_commit="7" * 40,
    )

    with pytest.raises(HyperliquidProtocolError, match="interval-aligned"):
        collector.collect_candles(
            ["BTC"],
            "1m",
            HyperliquidCollectionWindow(
                start=NOW,
                end=NOW + timedelta(minutes=2, seconds=30),
            ),
        )

    assert transport.calls == 0
    assert not (root / ".quantmesh-fabric" / "datasets").exists()


def test_lineage_rejects_forged_transformation_declarations(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    collector = HyperliquidCollector(
        store,
        transport=ScriptedPublicInfo([_candle(index) for index in range(3)]),
        code_commit="1" * 40,
    )
    publication = collector.collect_candles(["BTC"], "1m", _window())[0]

    def clone(
        manifest_id: str,
        dataset_id: str,
        **updates: object,
    ) -> ArtifactManifest:
        original = store.open(manifest_id).manifest
        values = original.model_dump(exclude={"manifest_id", "compatibility_revision"})
        values.update(dataset_id=dataset_id, **updates)
        forged = ArtifactManifest.build(compatibility_revision=1, **values)
        store.publish(forged, expected_current=None)
        return forged

    normalized = clone(
        publication.normalized_id,
        "forged-hyperliquid-normalized",
        transformation_policy_digest="0" * 64,
    )
    adjusted = clone(
        publication.adjusted_id,
        "forged-hyperliquid-adjusted",
        parent_manifest_ids=(normalized.manifest_id,),
    )
    feature = clone(
        publication.feature_id,
        "forged-hyperliquid-feature",
        parent_manifest_ids=(adjusted.manifest_id,),
    )
    forged_publication = publication.model_copy(
        update={
            "normalized_id": normalized.manifest_id,
            "adjusted_id": adjusted.manifest_id,
            "feature_id": feature.manifest_id,
        }
    )

    with pytest.raises(ManifestIntegrityError, match="dataset identity|declarations"):
        collector.validate_publication(forged_publication)

    normalized_identity = clone(
        publication.normalized_id,
        "forged-hyperliquid-normalized-identity",
    )
    adjusted_identity = clone(
        publication.adjusted_id,
        "forged-hyperliquid-adjusted-identity",
        parent_manifest_ids=(normalized_identity.manifest_id,),
    )
    feature_identity = clone(
        publication.feature_id,
        "forged-hyperliquid-feature-identity",
        parent_manifest_ids=(adjusted_identity.manifest_id,),
    )
    identity_publication = publication.model_copy(
        update={
            "normalized_id": normalized_identity.manifest_id,
            "adjusted_id": adjusted_identity.manifest_id,
            "feature_id": feature_identity.manifest_id,
        }
    )

    with pytest.raises(ManifestIntegrityError, match="dataset identity"):
        collector.validate_publication(identity_publication)


def test_lineage_revalidation_rejects_forged_gapped_raw_window(
    tmp_path: Path,
) -> None:
    rows = [_candle(index) for index in (0, 2, 3)]
    transport = ScriptedPublicInfo(rows)
    collector = HyperliquidCollector(
        ManifestStore(tmp_path),
        transport=transport,
        code_commit="2" * 40,
    )
    response = transport.candles(
        "BTC",
        "1m",
        start=NOW,
        end=NOW + timedelta(minutes=3),
    )
    instrument = Instrument(
        symbol="BTC",
        venue=Venue.HYPERLIQUID,
        instrument_type=InstrumentType.PERPETUAL,
        currency="USD",
    )
    bars = HyperliquidDataAdapter().bars(
        collector._adapter_rows(rows, "1m"),
        instrument,
        interval="1m",
    )

    with pytest.raises(HyperliquidProtocolError, match="complete requested window"):
        collector._publish(
            "BTC",
            "1m",
            NOW,
            NOW + timedelta(minutes=3),
            response,
            bars,
        )

    assert not (tmp_path / ".quantmesh-fabric" / "datasets").exists()


def test_lineage_rejects_semantic_but_noncanonical_derived_bytes(
    tmp_path: Path,
) -> None:
    store = ManifestStore(tmp_path)
    collector = HyperliquidCollector(
        store,
        transport=ScriptedPublicInfo([_candle(index) for index in range(3)]),
        code_commit="4" * 40,
    )
    publication = collector.collect_candles(["BTC"], "1m", _window())[0]
    raw = store.open(publication.raw_id).manifest
    normalized = store.open(publication.normalized_id).manifest
    adjusted = store.open(publication.adjusted_id).manifest
    feature = store.open(publication.feature_id).manifest
    rows = [bar.model_dump(mode="json") for bar in store.open(normalized.manifest_id).read_bars()]
    pretty_ref = store.objects.put_bytes(
        "application/vnd.quantmesh.bars+json",
        json.dumps(rows, indent=2).encode(),
    )

    def candidate(original: ArtifactManifest, **updates: object) -> ArtifactManifest:
        values = original.model_dump(exclude={"manifest_id", "compatibility_revision"})
        values.update(**updates)
        return ArtifactManifest.build(
            compatibility_revision=original.compatibility_revision,
            **values,
        )

    forged_normalized = candidate(normalized, objects=(pretty_ref,))
    forged_adjusted = candidate(
        adjusted,
        objects=(pretty_ref,),
        parent_manifest_ids=(forged_normalized.manifest_id,),
    )
    forged_feature = candidate(
        feature,
        parent_manifest_ids=(forged_adjusted.manifest_id,),
    )
    forged_publication = publication.model_copy(
        update={
            "normalized_id": forged_normalized.manifest_id,
            "adjusted_id": forged_adjusted.manifest_id,
            "feature_id": forged_feature.manifest_id,
        }
    )

    with pytest.raises(ManifestIntegrityError, match="normalized declarations"):
        collector.validate_publication(
            forged_publication,
            candidates=(raw, forged_normalized, forged_adjusted, forged_feature),
        )


def test_collection_rejects_wrong_symbol_before_publication(tmp_path: Path) -> None:
    row = {**_candle(0), "s": "ETH"}
    root = tmp_path / "fabric"
    collector = HyperliquidCollector(
        ManifestStore(root),
        transport=ScriptedPublicInfo([row]),
        code_commit="c" * 40,
    )

    with pytest.raises(HyperliquidProtocolError, match="does not match"):
        collector.collect_candles(
            ["BTC"],
            "1m",
            HyperliquidCollectionWindow(start=NOW, end=NOW),
        )

    assert not (root / ".quantmesh-fabric" / "datasets").exists()
