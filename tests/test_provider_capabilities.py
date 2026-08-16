from datetime import UTC, datetime, timedelta, tzinfo

import pytest

from quantmesh.data.capabilities import (
    DataKind,
    EntitlementState,
    HistoryAccess,
    HistoryLimit,
    PaginationPolicy,
    PaginationStyle,
    ProviderAccess,
    ProviderCapability,
    ProviderDescriptor,
    ProviderRequest,
    ProviderResolutionError,
    RateLimitPolicy,
)
from quantmesh.data.providers import (
    HyperliquidFixtureProvider,
    MoomooFixtureProvider,
    Provider,
    ProviderMode,
    ProviderRegistry,
)
from quantmesh.domain.models import Venue


def _descriptor(
    *,
    provider_id: str = "hyperliquid-public",
    access: ProviderAccess = ProviderAccess.PUBLIC_LIVE,
    data_kind: DataKind = DataKind.BARS,
    symbols: frozenset[str] = frozenset({"BTC-PERP"}),
    intervals: frozenset[str] = frozenset({"1m"}),
) -> ProviderDescriptor:
    return ProviderDescriptor(
        provider_id=provider_id,
        venue=Venue.HYPERLIQUID,
        provider_version="0.24.0",
        adapter_schema_version="quantmesh-market-data-v1",
        capabilities=(
            ProviderCapability(
                access=access,
                data_kind=data_kind,
                symbols=symbols,
                intervals=intervals,
                entitlement=EntitlementState.NOT_REQUIRED,
                history_access=HistoryAccess.BOUNDED,
                history_limit=HistoryLimit(
                    max_window_days=7,
                    max_rows=5_000,
                    max_pages=1,
                ),
                source_rights_id="hyperliquid-public-market-data",
                terms_version="2026-08-14",
                timezone="UTC",
                calendar="24/7",
                latency_class="realtime",
                rate_limit=RateLimitPolicy(requests=1_200, per_seconds=60, burst=20),
                pagination=PaginationPolicy(
                    style=PaginationStyle.NONE,
                    max_page_size=5_000,
                ),
            ),
        ),
    )


def _request(
    *,
    provider_id: str = "hyperliquid-public",
    access: ProviderAccess = ProviderAccess.PUBLIC_LIVE,
    data_kind: DataKind = DataKind.BARS,
    symbol: str = "BTC-PERP",
    interval: str | None = "1m",
) -> ProviderRequest:
    return ProviderRequest(
        provider_id=provider_id,
        venue=Venue.HYPERLIQUID,
        access=access,
        data_kind=data_kind,
        symbol=symbol,
        interval=interval,
    )


def _described_provider(
    descriptor: ProviderDescriptor,
) -> Provider:
    class DescribedProvider(Provider):
        venue = Venue.HYPERLIQUID
        mode = ProviderMode.LIVE

        def fetch_bars(self, instrument, *, interval, start=None, end=None):  # noqa: ANN001
            return []

        def fetch_order_books(self, instrument, *, start=None, end=None):  # noqa: ANN001
            return []

        def fetch_trades(self, instrument, *, start=None, end=None):  # noqa: ANN001
            return []

    provider = DescribedProvider()
    provider.descriptor = descriptor
    return provider


def test_registry_resolves_one_exact_read_only_capability() -> None:
    provider = _described_provider(_descriptor())
    registry = ProviderRegistry([provider])

    assert registry.resolve(_request()) is provider


def test_registry_never_upgrades_public_data_to_paper_broker_access() -> None:
    registry = ProviderRegistry([_described_provider(_descriptor())])

    with pytest.raises(ProviderResolutionError, match="paper-broker"):
        registry.resolve(_request(access=ProviderAccess.PAPER_BROKER))


@pytest.mark.parametrize(
    ("provider_request", "message"),
    [
        (_request(symbol="ETH-PERP"), "ETH-PERP"),
        (_request(interval="5m"), "5m"),
        (_request(data_kind=DataKind.TRADES, interval=None), "trades"),
    ],
)
def test_registry_rejects_out_of_capability_requests(
    provider_request: ProviderRequest, message: str
) -> None:
    registry = ProviderRegistry([_described_provider(_descriptor())])

    with pytest.raises(ProviderResolutionError, match=message):
        registry.resolve(provider_request)


@pytest.mark.parametrize(
    "entitlement",
    [
        EntitlementState.DEGRADED,
        EntitlementState.UNAVAILABLE,
        EntitlementState.UNKNOWN,
    ],
)
def test_registry_rejects_non_available_entitlement(
    entitlement: EntitlementState,
) -> None:
    descriptor = _descriptor()
    capability = descriptor.capabilities[0].model_copy(
        update={
            "entitlement": entitlement,
            "entitlement_probed_at": datetime(2026, 8, 14, tzinfo=UTC),
        }
    )
    unavailable = descriptor.model_copy(update={"capabilities": (capability,)})
    registry = ProviderRegistry([_described_provider(unavailable)])

    with pytest.raises(ProviderResolutionError, match=f"entitlement {entitlement.value}"):
        registry.resolve(_request())


def test_registry_allows_multiple_provider_ids_for_one_venue() -> None:
    public = _described_provider(_descriptor())
    delayed = _described_provider(
        _descriptor(
            provider_id="hyperliquid-delayed",
            access=ProviderAccess.AUTHENTICATED_READ_ONLY,
        )
    )
    registry = ProviderRegistry([public, delayed])

    assert registry.resolve(_request()) is public
    assert registry.resolve(
        _request(
            provider_id="hyperliquid-delayed",
            access=ProviderAccess.AUTHENTICATED_READ_ONLY,
        )
    ) is delayed


def test_registry_rejects_duplicate_provider_ids_independent_of_venue_lookup() -> None:
    descriptor = _descriptor()

    with pytest.raises(ValueError, match="already registered with id"):
        ProviderRegistry(
            [_described_provider(descriptor), _described_provider(descriptor)]
        )


def test_registry_rejects_descriptor_with_wrong_provider_venue() -> None:
    descriptor = _descriptor().model_copy(update={"venue": Venue.MOOMOO})

    with pytest.raises(ValueError, match="descriptor venue"):
        ProviderRegistry([_described_provider(descriptor)])


def test_legacy_fixture_descriptor_is_not_eligible_for_exact_resolution() -> None:
    provider = MoomooFixtureProvider()
    registry = ProviderRegistry([provider])
    provider_id = registry.descriptors()[0].provider_id
    request = ProviderRequest(
        provider_id=provider_id,
        venue=Venue.MOOMOO,
        access=ProviderAccess.FIXTURE,
        data_kind=DataKind.BARS,
        symbol="AAPL",
        interval="1m",
    )

    assert registry.get(Venue.MOOMOO) is provider
    with pytest.raises(ProviderResolutionError, match="legacy-only"):
        registry.resolve(request)


def test_explicit_fixture_descriptor_cannot_claim_live_access() -> None:
    class MisclassifiedFixture(HyperliquidFixtureProvider):
        descriptor = _descriptor(access=ProviderAccess.PUBLIC_LIVE)

    with pytest.raises(ValueError, match="fixture access only"):
        ProviderRegistry([MisclassifiedFixture()])


def test_fixture_implementation_cannot_change_its_mode_to_live() -> None:
    class MisclassifiedFixture(HyperliquidFixtureProvider):
        mode = ProviderMode.LIVE
        descriptor = _descriptor(access=ProviderAccess.FIXTURE)

    with pytest.raises(ValueError, match="fixture providers must use fixture mode"):
        ProviderRegistry([MisclassifiedFixture()])


def test_default_fixture_mode_cannot_advertise_live_access() -> None:
    class DefaultModeProvider(Provider):
        venue = Venue.HYPERLIQUID
        descriptor = _descriptor(access=ProviderAccess.PUBLIC_LIVE)

        def fetch_bars(self, instrument, *, interval, start=None, end=None):  # noqa: ANN001
            return []

        def fetch_order_books(self, instrument, *, start=None, end=None):  # noqa: ANN001
            return []

        def fetch_trades(self, instrument, *, start=None, end=None):  # noqa: ANN001
            return []

    with pytest.raises(ValueError, match="fixture mode can advertise fixture access only"):
        ProviderRegistry([DefaultModeProvider()])


def test_capability_records_enforceable_collection_bounds() -> None:
    capability = _descriptor().capabilities[0]

    assert capability.history_limit == HistoryLimit(
        max_window_days=7,
        max_rows=5_000,
        max_pages=1,
    )
    assert capability.pagination.max_page_size == 5_000
    assert capability.pagination.style is PaginationStyle.NONE
    assert capability.rate_limit.requests == 1_200


def test_entitled_capability_requires_an_aware_probe_time() -> None:
    values = _descriptor().capabilities[0].model_dump()
    values["entitlement"] = EntitlementState.AVAILABLE

    with pytest.raises(ValueError, match="entitlement probe time"):
        ProviderCapability.model_validate(values)
    values["entitlement_probed_at"] = datetime(2026, 8, 14, 12, 0)
    with pytest.raises(ValueError, match="timezone-aware"):
        ProviderCapability.model_validate(values)


def test_entitlement_probe_rejects_tzinfo_without_a_utc_offset() -> None:
    class NotActuallyAware(tzinfo):
        def utcoffset(self, dt):  # noqa: ANN001
            return None

        def dst(self, dt):  # noqa: ANN001
            return timedelta(0)

    values = _descriptor().capabilities[0].model_dump()
    values["entitlement"] = EntitlementState.AVAILABLE
    values["entitlement_probed_at"] = datetime(2026, 8, 14, tzinfo=NotActuallyAware())

    with pytest.raises(ValueError, match="timezone-aware"):
        ProviderCapability.model_validate(values)


def test_cursor_pagination_requires_a_bounded_page_size() -> None:
    with pytest.raises(ValueError, match="max_page_size"):
        PaginationPolicy(
            style=PaginationStyle.CURSOR,
            cursor_field="page_req_key",
        )


def test_registry_rejects_malformed_provider_mode() -> None:
    provider = _described_provider(_descriptor())
    provider.mode = None  # type: ignore[assignment]

    with pytest.raises(ValueError, match="valid mode"):
        ProviderRegistry([provider])


def test_membership_keeps_legacy_get_semantics_for_live_only_venues() -> None:
    registry = ProviderRegistry([_described_provider(_descriptor())])

    assert Venue.HYPERLIQUID not in registry
    assert registry.venues() == frozenset({Venue.HYPERLIQUID})
    with pytest.raises(ValueError, match="no provider"):
        registry.get(Venue.HYPERLIQUID)


def test_registry_rejects_unknown_provider_and_request_venue_mismatch() -> None:
    registry = ProviderRegistry([_described_provider(_descriptor())])

    with pytest.raises(ProviderResolutionError, match="missing-provider"):
        registry.resolve(_request(provider_id="missing-provider"))
    mismatched = _request().model_copy(update={"venue": Venue.MOOMOO})
    with pytest.raises(ProviderResolutionError, match="venue mismatch"):
        registry.resolve(mismatched)


def test_descriptor_rejects_ambiguous_capabilities() -> None:
    descriptor = _descriptor()
    values = descriptor.model_dump()
    values["capabilities"] = (
        values["capabilities"][0],
        values["capabilities"][0],
    )

    with pytest.raises(ValueError, match="ambiguous"):
        ProviderDescriptor.model_validate(values)


def test_descriptor_allows_disjoint_limits_for_one_operation() -> None:
    descriptor = _descriptor()
    first = descriptor.capabilities[0]
    second_values = first.model_dump()
    second_values.update(
        symbols=frozenset({"ETH-PERP"}),
        history_limit=HistoryLimit(
            max_window_days=3,
            max_rows=2_500,
            max_pages=1,
        ),
    )
    second = ProviderCapability.model_validate(second_values)

    descriptor_values = descriptor.model_dump()
    descriptor_values["capabilities"] = (first, second)
    split = ProviderDescriptor.model_validate(descriptor_values)

    assert len(split.capabilities) == 2


def test_non_bar_history_capability_can_declare_collection_bounds() -> None:
    values = _descriptor().capabilities[0].model_dump()
    values.update(
        data_kind=DataKind.TRADES,
        intervals=frozenset(),
        history_access=HistoryAccess.BOUNDED,
        history_limit=HistoryLimit(
            max_window_days=1,
            max_rows=1_000,
            max_pages=5,
        ),
    )
    capability = ProviderCapability.model_validate(values)

    assert capability.history_limit is not None


def test_snapshot_only_capability_forbids_history_limits() -> None:
    values = _descriptor().capabilities[0].model_dump()
    values.update(
        data_kind=DataKind.TRADES,
        intervals=frozenset(),
        history_access=HistoryAccess.NONE,
    )

    with pytest.raises(ValueError, match="no-history capability"):
        ProviderCapability.model_validate(values)


def test_bars_request_requires_an_interval() -> None:
    with pytest.raises(ValueError, match="bars requests require an interval"):
        _request(interval=None)


def test_non_bar_request_rejects_an_interval() -> None:
    with pytest.raises(ValueError, match="only bars requests use an interval"):
        _request(data_kind=DataKind.TRADES, interval="1m")
