"""MoomooOpenDProvider and the fixture-through-lake path (issue #26, Phase B).

The provider is explicit-construction-only: the fixture-only registry
refuses it (LIVE mode), so OpenD is reachable only through an
operator-built client. With a wire fixture transport it serves canonical
bars and trades, and those land in the lake through the M3 machinery —
write, manifest, gate, read back, coverage clean — exactly the
"fixture data through Lake before any live OpenD read" acceptance.
"""

from datetime import UTC, datetime

import pytest
from moomoo_wire import (
    AAPL,
    HK_00700_1D,
    HK_00700_5M,
    TENCENT,
    US_AAPL_1D,
    US_AAPL_5M,
    WireTransport,
)

from quantmesh.data.ingestion import coverage_gaps
from quantmesh.data.lake import Lake
from quantmesh.data.manifest import ManifestWriter
from quantmesh.data.providers import ProviderRegistry
from quantmesh.domain.models import InstrumentType, Venue
from quantmesh.moomoo.opend import MoomooOpenDClient, OpenDProtocolError
from quantmesh.moomoo.provider import MoomooOpenDProvider


def make_provider(kline: dict | None = None, ticker: dict | None = None) -> MoomooOpenDProvider:
    return MoomooOpenDProvider(MoomooOpenDClient(WireTransport(kline=kline, ticker=ticker)))


# --- provider surface --------------------------------------------------------


def test_fetch_bars_returns_canonical_utc_bars() -> None:
    bars = make_provider().fetch_bars(AAPL, interval="1d")
    assert len(bars) == 3
    assert all(bar.timestamp.tzinfo is UTC for bar in bars)
    assert bars[0].timestamp == datetime(2026, 8, 3, 4, 0, tzinfo=UTC)


def test_fetch_bars_converts_utc_bounds_to_venue_local_dates() -> None:
    transport = WireTransport()
    provider = MoomooOpenDProvider(MoomooOpenDClient(transport))
    provider.fetch_bars(AAPL, interval="1d", start=datetime(2026, 8, 4, tzinfo=UTC))
    # 2026-08-04 00:00 UTC is still 2026-08-03 evening in New York, so the
    # SDK is asked for venue dates from 08-03; the UTC filter is applied
    # to the returned bars, not to the request window.
    assert transport.kline_requests[0][2] == "2026-08-03"


def test_fetch_bars_filters_by_utc_range() -> None:
    provider = make_provider()
    bars = provider.fetch_bars(
        AAPL,
        interval="1d",
        start=datetime(2026, 8, 4, tzinfo=UTC),
        end=datetime(2026, 8, 5, tzinfo=UTC),  # the 08-05 bar opens at 04:00 UTC
    )
    assert [bar.timestamp.date().isoformat() for bar in bars] == ["2026-08-04"]


def test_fetch_bars_rejects_naive_bounds() -> None:
    with pytest.raises(ValueError, match="start"):
        make_provider().fetch_bars(AAPL, interval="1d", start=datetime(2026, 8, 4))


def test_fetch_bars_rejects_reversed_utc_instants_before_date_conversion() -> None:
    with pytest.raises(ValueError, match="start must not be after end"):
        make_provider().fetch_bars(
            AAPL,
            interval="1d",
            start=datetime(2026, 8, 3, 20, tzinfo=UTC),
            end=datetime(2026, 8, 3, 19, tzinfo=UTC),
        )


def test_fetch_bars_rejects_non_mapping_payload() -> None:
    class NotAMappingTransport(WireTransport):
        def history_kline(self, code, *, interval, start, end, autype):
            return ["not", "a", "mapping"]

    provider = MoomooOpenDProvider(MoomooOpenDClient(NotAMappingTransport()))
    with pytest.raises(OpenDProtocolError, match="non-mapping"):
        provider.fetch_bars(AAPL, interval="1d")


def test_fetch_bars_cross_checks_interval_echo() -> None:
    provider = make_provider(kline=US_AAPL_5M)
    with pytest.raises(OpenDProtocolError, match="interval"):
        provider.fetch_bars(AAPL, interval="1d")


def test_fetch_bars_cross_checks_autype_echo() -> None:
    adjusted = {"code": "US.AAPL", "interval": "1d", "autype": "qfq", "rows": US_AAPL_1D["rows"]}
    provider = make_provider(kline=adjusted)
    with pytest.raises(OpenDProtocolError, match="autype"):
        provider.fetch_bars(AAPL, interval="1d")


def test_fetch_raw_bundle_keeps_unadjusted_pages_and_source_actions() -> None:
    class BundleTransport(WireTransport):
        def history_kline(self, *args, **kwargs):
            raise AssertionError("trusted raw collection must use the paginated surface")

        def history_kline_page(
            self,
            code: str,
            *,
            interval: str,
            start: str | None,
            end: str | None,
            autype: str,
            max_count: int,
            page_req_key: bytes | None,
        ) -> dict:
            assert page_req_key is None
            return {
                **US_AAPL_1D,
                "request_page_req_key": None,
                "next_page_req_key": None,
            }

        def adjustment_factors(self, code: str) -> dict:
            return {"code": code, "rows": [{"ex_div_date": "2026-08-01"}]}

        def stock_splits_page(self, code: str, *, next_key: str | None, num: int) -> dict:
            return {
                "code": code,
                "request_next_key": next_key,
                "next_key": "-1",
                "rows": [{"rate": "1->4"}],
            }

        def dividends(self, code: str) -> dict:
            return {"code": code, "rows": [{"pub_date": "2026/03/18"}]}

    provider = MoomooOpenDProvider(MoomooOpenDClient(BundleTransport()))

    bundle = provider.fetch_raw_bundle(AAPL, interval="1d")

    assert [bar.close for bar in bundle.bars] == [204.0, 207.0, 209.5]
    assert bundle.history_pages[0]["autype"] == "None"
    assert bundle.adjustment_factors["rows"]
    assert bundle.stock_split_pages[0]["rows"]
    assert bundle.dividends["rows"]
    assert all(bar.close == raw["close"] for bar, raw in zip(bundle.bars, US_AAPL_1D["rows"]))


def test_fetch_raw_bundle_rejects_legacy_single_page_history() -> None:
    class LegacyBundleTransport(WireTransport):
        def adjustment_factors(self, code: str) -> dict:
            return {"code": code, "rows": []}

        def stock_splits_page(self, code: str, *, next_key: str | None, num: int) -> dict:
            return {
                "code": code,
                "request_next_key": next_key,
                "next_key": "-1",
                "rows": [],
            }

        def dividends(self, code: str) -> dict:
            return {"code": code, "rows": []}

    provider = MoomooOpenDProvider(MoomooOpenDClient(LegacyBundleTransport()))

    with pytest.raises(OpenDProtocolError, match="legacy single-page"):
        provider.fetch_raw_bundle(AAPL, interval="1d")


def test_fetch_trades_returns_canonical_trades() -> None:
    trades = make_provider().fetch_trades(AAPL)
    assert len(trades) == 3
    assert trades[0].timestamp == datetime(2026, 8, 3, 13, 30, 1, tzinfo=UTC)


def test_fetch_order_books_is_out_of_scope() -> None:
    with pytest.raises(NotImplementedError, match="Phase B"):
        make_provider().fetch_order_books(AAPL)


def test_registry_refuses_live_provider() -> None:
    provider = make_provider()
    with pytest.raises(ValueError, match="fixture-only"):
        ProviderRegistry().register(provider)


def test_provider_requires_market_metadata() -> None:
    bare = AAPL.model_copy(update={"metadata": {}})
    with pytest.raises(ValueError, match="market"):
        make_provider().fetch_bars(bare, interval="1d")


def test_provider_close_closes_client() -> None:
    transport = WireTransport()
    provider = MoomooOpenDProvider(MoomooOpenDClient(transport))
    provider.close()
    assert transport.closed is True


# --- fixture data through the lake -------------------------------------------


def _bar_fields(bars) -> list[tuple]:
    """Canonical data fields of a bar — the lake round-trip surface.

    The lake stores ``instrument_type`` and ``currency`` but not the
    ``metadata`` dict (ADR-0003 contract); market metadata is request-side
    identity, rebuilt from the instrument at fetch time. Comparing these
    fields — plus the identity assertions below — pins that boundary
    instead of hiding it.
    """
    return [(b.timestamp, b.interval, b.open, b.high, b.low, b.close, b.volume) for b in bars]


def _assert_same_series(written, read_back, symbol: str) -> None:
    assert _bar_fields(written) == _bar_fields(read_back)
    assert [b.instrument.symbol for b in read_back] == [symbol] * len(read_back)
    assert {b.instrument.instrument_type for b in read_back} == {InstrumentType.EQUITY}
    expected_currency = {"USD"} if symbol == "AAPL" else {"HKD"}
    assert {b.instrument.currency for b in read_back} == expected_currency
    assert all(not b.instrument.metadata for b in read_back)  # metadata is request-side


def _assert_clean_coverage(root, dataset: str) -> None:
    report = coverage_gaps(root, dataset)
    assert report.series, "coverage report must not be empty"
    for series in report.series:
        assert not series.missing_days, f"{series} has missing days"
        assert not series.unexpected_days, f"{series} has unexpected days"


def test_us_daily_fixture_pipeline_through_lake(tmp_path) -> None:
    lake = Lake(tmp_path)
    provider = make_provider()
    bars = provider.fetch_bars(AAPL, interval="1d")
    lake.write_bars("us_equities", bars)
    ManifestWriter(lake.root).generate("us_equities", source="test", license="fixture-only")
    dataset = lake.dataset("us_equities")
    read_back = dataset.read_bars(interval="1d", venue=Venue.MOOMOO, symbol="AAPL")
    _assert_same_series(bars, read_back, "AAPL")
    _assert_clean_coverage(lake.root, "us_equities")


def test_us_and_hk_series_share_a_dataset(tmp_path) -> None:
    lake = Lake(tmp_path)
    transport = WireTransport(kline_by_code={"US.AAPL": US_AAPL_1D, "HK.00700": HK_00700_1D})
    provider = MoomooOpenDProvider(MoomooOpenDClient(transport))
    us_bars = provider.fetch_bars(AAPL, interval="1d")
    hk_bars = provider.fetch_bars(TENCENT, interval="1d")
    lake.write_bars("equities", us_bars)
    lake.write_bars("equities", hk_bars)
    ManifestWriter(lake.root).generate("equities", source="test", license="fixture-only")
    dataset = lake.dataset("equities")
    read_back_us = dataset.read_bars(interval="1d", venue=Venue.MOOMOO, symbol="AAPL")
    read_back_hk = dataset.read_bars(interval="1d", venue=Venue.MOOMOO, symbol="00700")
    _assert_same_series(us_bars, read_back_us, "AAPL")
    _assert_same_series(hk_bars, read_back_hk, "00700")
    _assert_clean_coverage(lake.root, "equities")


def test_intraday_fixture_pipeline_through_lake(tmp_path) -> None:
    lake = Lake(tmp_path)
    provider = make_provider(kline=US_AAPL_5M)
    bars = provider.fetch_bars(AAPL, interval="5m")
    lake.write_bars("us_intraday", bars)
    ManifestWriter(lake.root).generate("us_intraday", source="test", license="fixture-only")
    dataset = lake.dataset("us_intraday")
    read_back = dataset.read_bars(interval="5m", venue=Venue.MOOMOO, symbol="AAPL")
    _assert_same_series(bars, read_back, "AAPL")
    _assert_clean_coverage(lake.root, "us_intraday")


def test_hk_intraday_fixture_pipeline_through_lake(tmp_path) -> None:
    lake = Lake(tmp_path)
    provider = make_provider(kline=HK_00700_5M)
    bars = provider.fetch_bars(TENCENT, interval="5m")
    lake.write_bars("hk_intraday", bars)
    ManifestWriter(lake.root).generate("hk_intraday", source="test", license="fixture-only")
    dataset = lake.dataset("hk_intraday")
    read_back = dataset.read_bars(interval="5m", venue=Venue.MOOMOO, symbol="00700")
    _assert_same_series(bars, read_back, "00700")
    _assert_clean_coverage(lake.root, "hk_intraday")


def test_ingestion_jobs_can_target_the_open_d_provider_surface(tmp_path) -> None:
    # The registry refuses the provider, so scheduled ingestion is not
    # available for OpenD; the provider surface itself (fetch_bars +
    # lake + manifest) is what the M4 operator path composes.
    lake = Lake(tmp_path)
    provider = make_provider()
    bars = provider.fetch_bars(AAPL, interval="1d", start=datetime(2026, 8, 4, tzinfo=UTC))
    assert len(bars) == 2
    lake.write_bars("us_equities", bars)
    ManifestWriter(lake.root).generate("us_equities", source="test", license="fixture-only")
    _assert_clean_coverage(lake.root, "us_equities")
