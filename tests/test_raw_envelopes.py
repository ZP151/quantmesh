from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from quantmesh.data.capabilities import DataKind, EntitlementState
from quantmesh.data.envelopes import ProvenanceClass, RawEnvelope
from quantmesh.data.instruments import CanonicalInstrumentId
from quantmesh.data.objects import ObjectStore

T0 = datetime(2026, 8, 12, 13, 30, tzinfo=UTC)


def test_fixture_envelope_captures_raw_object_and_is_nonqualifying(tmp_path: Path) -> None:
    objects = ObjectStore(tmp_path)
    envelope = RawEnvelope.capture(
        objects=objects,
        payload=b'{"symbol":"US.AAPL","close":100.0}',
        content_type="application/json",
        provider_id="fixture-moomoo",
        endpoint="fixture://aapl-daily",
        request_id="request-aapl-20260812",
        request_window_start=T0,
        request_window_end=T0 + timedelta(days=2),
        cursor=None,
        canonical_instrument=CanonicalInstrumentId(value="moomoo:US:AAPL:XNAS"),
        provider_symbol="US.AAPL",
        data_kind=DataKind.BARS,
        source_event_ids=("US.AAPL:2026-08-12",),
        event_start=T0,
        event_end=T0 + timedelta(days=2),
        session_date=date(2026, 8, 12),
        provider_available_at=None,
        received_at=T0 + timedelta(days=2, minutes=1),
        ingested_at=T0 + timedelta(days=2, minutes=2),
        provider_version="fixture-v1",
        adapter_version="fixture-adapter-v1",
        schema_version="fixture-bars-v1",
        source_rights_id="fixture-test-data",
        entitlement=EntitlementState.NOT_REQUIRED,
        provenance=ProvenanceClass.FIXTURE,
    )

    assert objects.get_bytes(envelope.raw_object) == b'{"symbol":"US.AAPL","close":100.0}'
    assert envelope.knowledge_time == envelope.received_at
    assert envelope.qualifies is False


def test_envelope_rejects_ingestion_before_receipt(tmp_path: Path) -> None:
    objects = ObjectStore(tmp_path)
    with pytest.raises(ValueError, match="ingested_at"):
        RawEnvelope.capture(
            objects=objects,
            payload=b"{}",
            content_type="application/json",
            provider_id="fixture-moomoo",
            endpoint="fixture://aapl-daily",
            request_id="request-aapl-invalid",
            request_window_start=T0,
            request_window_end=T0,
            cursor=None,
            canonical_instrument=CanonicalInstrumentId(value="moomoo:US:AAPL:XNAS"),
            provider_symbol="US.AAPL",
            data_kind=DataKind.BARS,
            source_event_ids=("US.AAPL:2026-08-12",),
            event_start=T0,
            event_end=T0,
            session_date=date(2026, 8, 12),
            provider_available_at=None,
            received_at=T0 + timedelta(minutes=2),
            ingested_at=T0 + timedelta(minutes=1),
            provider_version="fixture-v1",
            adapter_version="fixture-adapter-v1",
            schema_version="fixture-bars-v1",
            source_rights_id="fixture-test-data",
            entitlement=EntitlementState.NOT_REQUIRED,
            provenance=ProvenanceClass.FIXTURE,
        )


def test_envelope_rejects_event_after_knowledge_time(tmp_path: Path) -> None:
    objects = ObjectStore(tmp_path)
    with pytest.raises(ValueError, match="event_end"):
        RawEnvelope.capture(
            objects=objects,
            payload=b"{}",
            content_type="application/json",
            provider_id="fixture-moomoo",
            endpoint="fixture://aapl-daily",
            request_id="request-aapl-future",
            request_window_start=T0,
            request_window_end=T0 + timedelta(days=1),
            cursor=None,
            canonical_instrument=CanonicalInstrumentId(value="moomoo:US:AAPL:XNAS"),
            provider_symbol="US.AAPL",
            data_kind=DataKind.BARS,
            source_event_ids=("US.AAPL:2026-08-12",),
            event_start=T0,
            event_end=T0 + timedelta(days=1),
            session_date=date(2026, 8, 12),
            provider_available_at=None,
            received_at=T0 + timedelta(hours=1),
            ingested_at=T0 + timedelta(hours=1),
            provider_version="fixture-v1",
            adapter_version="fixture-adapter-v1",
            schema_version="fixture-bars-v1",
            source_rights_id="fixture-test-data",
            entitlement=EntitlementState.NOT_REQUIRED,
            provenance=ProvenanceClass.FIXTURE,
        )
