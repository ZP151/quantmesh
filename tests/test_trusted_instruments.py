from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

from quantmesh.data.instruments import (
    CanonicalInstrumentId,
    InstrumentCatalog,
    InstrumentResolutionError,
    SymbolAlias,
)

AS_OF = date(2026, 8, 14)
KNOWN_AT = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "value",
    [
        "moomoo:US:AAPL:XNAS",
        "moomoo:US:NVDA:XNAS",
        "hyperliquid:perp:BTC",
        "hyperliquid:perp:ETH",
        "hyperliquid:perp:SOL",
    ],
)
def test_canonical_instrument_id_accepts_only_the_bounded_universe(value: str) -> None:
    assert CanonicalInstrumentId(value=value).value == value


@pytest.mark.parametrize(
    "value",
    [
        "moomoo:US:MSFT:XNAS",
        "moomoo:US:AAPL:XNYS",
        "hyperliquid:spot:BTC",
        "hyperliquid:perp:DOGE",
        "AAPL",
    ],
)
def test_canonical_instrument_id_rejects_unplanned_identity(value: str) -> None:
    with pytest.raises(ValidationError, match="bounded trusted-data universe"):
        CanonicalInstrumentId(value=value)


@pytest.mark.parametrize(
    ("provider_id", "provider_symbol", "expected"),
    [
        ("moomoo-opend", "US.AAPL", "moomoo:US:AAPL:XNAS"),
        ("moomoo-opend", "US.NVDA", "moomoo:US:NVDA:XNAS"),
        ("hyperliquid-public", "BTC", "hyperliquid:perp:BTC"),
        ("hyperliquid-public", "ETH", "hyperliquid:perp:ETH"),
        ("hyperliquid-public", "SOL", "hyperliquid:perp:SOL"),
    ],
)
def test_default_catalog_resolves_all_provider_aliases_at_effective_date(
    provider_id: str, provider_symbol: str, expected: str
) -> None:
    catalog = InstrumentCatalog.bounded_default()

    assert catalog.resolve(
        provider_id,
        provider_symbol,
        effective_at=AS_OF,
        known_at=KNOWN_AT,
    ).value == expected


def test_alias_resolution_is_effective_dated() -> None:
    alias = SymbolAlias(
        provider_id="moomoo-opend",
        provider_symbol="US.AAPL",
        canonical_id=CanonicalInstrumentId(value="moomoo:US:AAPL:XNAS"),
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 7, 1),
        known_from=KNOWN_AT,
    )
    catalog = InstrumentCatalog(aliases=(alias,))

    assert catalog.resolve(
        "moomoo-opend",
        "US.AAPL",
        effective_at=date(2026, 6, 30),
        known_at=KNOWN_AT,
    ) == alias.canonical_id
    with pytest.raises(InstrumentResolutionError, match="not effective"):
        catalog.resolve(
            "moomoo-opend",
            "US.AAPL",
            effective_at=date(2026, 7, 1),
            known_at=KNOWN_AT,
        )


def test_alias_resolution_separates_effective_time_from_knowledge_time() -> None:
    correction_time = KNOWN_AT + timedelta(days=1)
    old = SymbolAlias(
        provider_id="moomoo-opend",
        provider_symbol="US.AAPL",
        canonical_id=CanonicalInstrumentId(value="moomoo:US:AAPL:XNAS"),
        effective_from=date(2026, 1, 1),
        known_from=KNOWN_AT,
        known_to=correction_time,
    )
    corrected = SymbolAlias(
        provider_id="moomoo-opend",
        provider_symbol="US.AAPL",
        canonical_id=CanonicalInstrumentId(value="moomoo:US:AAPL:XNAS"),
        effective_from=date(2000, 1, 1),
        known_from=correction_time,
    )
    catalog = InstrumentCatalog(aliases=(old, corrected))

    assert catalog.resolve_alias(
        "moomoo-opend",
        "US.AAPL",
        effective_at=AS_OF,
        known_at=KNOWN_AT,
    ).effective_from == date(2026, 1, 1)
    assert catalog.resolve_alias(
        "moomoo-opend",
        "US.AAPL",
        effective_at=AS_OF,
        known_at=correction_time,
    ).effective_from == date(2000, 1, 1)
    assert catalog.catalog_id.startswith("sha256:")


def test_alias_rejects_empty_window() -> None:
    with pytest.raises(ValidationError, match="after effective_from"):
        SymbolAlias(
            provider_id="moomoo-opend",
            provider_symbol="US.AAPL",
            canonical_id=CanonicalInstrumentId(value="moomoo:US:AAPL:XNAS"),
            effective_from=AS_OF,
            effective_to=AS_OF,
            known_from=KNOWN_AT,
        )


def test_alias_rejects_provider_outside_bounded_namespaces() -> None:
    with pytest.raises(ValidationError, match="trusted-data provider"):
        SymbolAlias(
            provider_id="other-provider",
            provider_symbol="AAPL",
            canonical_id=CanonicalInstrumentId(value="moomoo:US:AAPL:XNAS"),
            effective_from=AS_OF,
            known_from=KNOWN_AT,
        )


def test_alias_rejects_cross_provider_canonical_mapping() -> None:
    with pytest.raises(ValidationError, match="provider and canonical identity disagree"):
        SymbolAlias(
            provider_id="moomoo-opend",
            provider_symbol="BTC",
            canonical_id=CanonicalInstrumentId(value="hyperliquid:perp:BTC"),
            effective_from=AS_OF,
            known_from=KNOWN_AT,
        )


def test_alias_rejects_cross_instrument_mapping() -> None:
    with pytest.raises(
        ValidationError, match="provider symbol and canonical identity disagree"
    ):
        SymbolAlias(
            provider_id="moomoo-opend",
            provider_symbol="US.AAPL",
            canonical_id=CanonicalInstrumentId(value="moomoo:US:NVDA:XNAS"),
            effective_from=AS_OF,
            known_from=KNOWN_AT,
        )


def test_catalog_rejects_overlapping_alias_windows() -> None:
    canonical = CanonicalInstrumentId(value="moomoo:US:AAPL:XNAS")
    first = SymbolAlias(
        provider_id="moomoo-opend",
        provider_symbol="US.AAPL",
        canonical_id=canonical,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 9, 1),
        known_from=KNOWN_AT,
    )
    second = SymbolAlias(
        provider_id="moomoo-opend",
        provider_symbol="US.AAPL",
        canonical_id=canonical,
        effective_from=date(2026, 8, 1),
        known_from=KNOWN_AT,
    )

    with pytest.raises(ValidationError, match="overlapping alias windows"):
        InstrumentCatalog(aliases=(first, second))


def test_catalog_rejects_unknown_provider_symbol() -> None:
    with pytest.raises(InstrumentResolutionError, match="unknown provider symbol"):
        InstrumentCatalog.bounded_default().resolve(
            "moomoo-opend",
            "US.MSFT",
            effective_at=AS_OF,
            known_at=KNOWN_AT,
        )


def test_catalog_id_is_stable_across_alias_order() -> None:
    catalog = InstrumentCatalog.bounded_default()
    reversed_catalog = InstrumentCatalog(aliases=tuple(reversed(catalog.aliases)))

    assert reversed_catalog.catalog_id == catalog.catalog_id
