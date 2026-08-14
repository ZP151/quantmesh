from datetime import UTC, datetime

from quantmesh.data.calendars import XNYS_REGULAR_VERSION, SessionPolicy
from quantmesh.data.capabilities import DataKind
from quantmesh.data.collection import CollectionJob, CollectionRun
from quantmesh.data.instruments import CanonicalInstrumentId


def _job(**overrides: object) -> CollectionJob:
    values = {
        "provider_id": "moomoo-opend",
        "endpoints": ("request_history_kline", "get_rehab"),
        "source_request_ids": ("request-bars", "request-factors"),
        "canonical_instruments": (
            CanonicalInstrumentId(value="moomoo:US:AAPL:XNAS"),
        ),
        "data_kinds": (DataKind.BARS, DataKind.ADJUSTMENT_FACTORS),
        "intervals": ("1d",),
        "calendar_version": XNYS_REGULAR_VERSION,
        "session_policy": SessionPolicy.REGULAR,
        "window_start": datetime(2026, 8, 12, 13, 30, tzinfo=UTC),
        "window_end": datetime(2026, 8, 14, 13, 30, tzinfo=UTC),
        "adjustment_policy": "moomoo-forward-adjusted-v1",
        "schema_versions": ("moomoo-bars-v1", "moomoo-adjustment-factors-v1"),
        "mapping_version": "catalog-v1",
        "code_commit": "1" * 40,
    }
    values.update(overrides)
    return CollectionJob.model_validate(values)


def test_job_and_run_identity_are_deterministic_and_attempt_is_separate() -> None:
    first = _job()
    same = _job()

    assert first.job_id == same.job_id
    assert len(first.job_id) == 64
    assert CollectionRun.for_job(first, attempt=1).run_id == CollectionRun.for_job(
        same, attempt=8
    ).run_id
    assert CollectionRun.for_job(first, attempt=1).attempt == 1
    assert CollectionRun.for_job(first, attempt=8).attempt == 8


def test_every_declared_identity_dimension_changes_job_id() -> None:
    base = _job()
    changes = (
        {"endpoints": ("request_history_kline",)},
        {
            "canonical_instruments": (
                CanonicalInstrumentId(value="moomoo:US:NVDA:XNAS"),
            )
        },
        {"data_kinds": (DataKind.BARS,)},
        {"intervals": ("1m",)},
        {"window_end": datetime(2026, 8, 15, 13, 30, tzinfo=UTC)},
        {"adjustment_policy": "unadjusted-identity-v1"},
        {"schema_versions": ("moomoo-bars-v2", "moomoo-adjustment-factors-v1")},
        {"mapping_version": "catalog-v2"},
        {"code_commit": "2" * 40},
    )

    assert all(_job(**change).job_id != base.job_id for change in changes)


def test_provider_cannot_disagree_with_instrument_calendar_or_session() -> None:
    invalid = {
        "provider_id": "hyperliquid-public",
        "canonical_instruments": (
            CanonicalInstrumentId(value="moomoo:US:AAPL:XNAS"),
        ),
    }

    try:
        _job(**invalid)
    except ValueError as error:
        assert "provider, instrument, calendar and session" in str(error)
    else:
        raise AssertionError("provider mismatch was accepted")
