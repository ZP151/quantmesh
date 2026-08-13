"""Capability contracts for read-only provider resolution.

The access class is part of the lookup key. Resolving public market data can
therefore never upgrade a caller to paper-broker or later execution authority.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantmesh.data.layout import validate_symbol
from quantmesh.domain.market_data import interval_to_timedelta
from quantmesh.domain.models import Venue


class ProviderResolutionError(ValueError):
    """No provider has the exact requested capability."""


class ProviderAccess(StrEnum):
    """The strongest operation a capability may perform."""

    FIXTURE = "fixture"
    PUBLIC_LIVE = "public-live"
    AUTHENTICATED_READ_ONLY = "authenticated-read-only"
    PAPER_BROKER = "paper-broker"


class DataKind(StrEnum):
    """Provider data surfaces admitted to the trusted-data registry."""

    BARS = "bars"
    QUOTES = "quotes"
    BOOKS = "books"
    TRADES = "trades"
    ADJUSTMENT_FACTORS = "adjustment-factors"
    SPLITS = "splits"
    DIVIDENDS = "dividends"


class EntitlementState(StrEnum):
    """Whether the local operator can currently use a capability."""

    NOT_REQUIRED = "not-required"
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class PaginationStyle(StrEnum):
    """How a provider proves that a bounded response is terminal."""

    NONE = "none"
    CURSOR = "cursor"


class HistoryAccess(StrEnum):
    """Whether a capability can answer a bounded historical request."""

    NONE = "none"
    BOUNDED = "bounded"


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class HistoryLimit(_FrozenContract):
    """Enforceable upper bounds for one historical-data request."""

    max_window_days: int = Field(gt=0)
    max_rows: int = Field(gt=0)
    max_pages: int = Field(gt=0)


class RateLimitPolicy(_FrozenContract):
    """A token-bucket-shaped provider request allowance."""

    requests: int = Field(gt=0)
    per_seconds: int = Field(gt=0)
    burst: int = Field(gt=0)


class PaginationPolicy(_FrozenContract):
    """Provider paging contract used to reject silent truncation."""

    style: PaginationStyle
    max_page_size: int | None = Field(default=None, gt=0)
    cursor_field: str | None = None

    @model_validator(mode="after")
    def cursor_shape_matches_style(self) -> "PaginationPolicy":
        if self.style is PaginationStyle.CURSOR:
            if self.cursor_field is None or not self.cursor_field.strip():
                raise ValueError("cursor pagination requires cursor_field")
            if self.max_page_size is None:
                raise ValueError("cursor pagination requires max_page_size")
        elif self.cursor_field is not None:
            raise ValueError("non-cursor pagination cannot declare cursor_field")
        return self


class ProviderCapability(_FrozenContract):
    """One bounded data operation advertised by a provider."""

    access: ProviderAccess
    data_kind: DataKind
    symbols: frozenset[str] = Field(default_factory=frozenset)
    intervals: frozenset[str] = Field(default_factory=frozenset)
    entitlement: EntitlementState
    entitlement_probed_at: datetime | None = None
    history_access: HistoryAccess
    history_limit: HistoryLimit | None = None
    source_rights_id: str = Field(min_length=1)
    terms_version: str = Field(min_length=1)
    timezone: str = Field(min_length=1)
    calendar: str = Field(min_length=1)
    latency_class: str = Field(min_length=1)
    rate_limit: RateLimitPolicy
    pagination: PaginationPolicy

    @field_validator("symbols")
    @classmethod
    def symbols_are_canonical(cls, values: frozenset[str]) -> frozenset[str]:
        for value in values:
            validate_symbol(value)
        return values

    @field_validator("intervals")
    @classmethod
    def intervals_are_canonical(cls, values: frozenset[str]) -> frozenset[str]:
        for value in values:
            interval_to_timedelta(value)
        return values

    @field_validator(
        "source_rights_id",
        "terms_version",
        "timezone",
        "calendar",
        "latency_class",
    )
    @classmethod
    def metadata_is_not_blank(cls, value: str, info) -> str:
        if not value.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return value

    @model_validator(mode="after")
    def shape_matches_data_kind(self) -> "ProviderCapability":
        if self.data_kind is DataKind.BARS:
            if not self.intervals:
                raise ValueError("bars capabilities require bounded intervals")
            if self.history_access is not HistoryAccess.BOUNDED:
                raise ValueError("bars capabilities require bounded history access")
        elif self.intervals:
            raise ValueError("only bars capabilities declare intervals")
        if self.history_access is HistoryAccess.BOUNDED and self.history_limit is None:
            raise ValueError("bounded-history capability requires history limits")
        if self.history_access is HistoryAccess.NONE and self.history_limit is not None:
            raise ValueError("no-history capability cannot declare history limits")
        if not self.symbols:
            raise ValueError("provider capabilities require bounded symbols")
        if self.entitlement is not EntitlementState.NOT_REQUIRED:
            if self.entitlement_probed_at is None:
                raise ValueError("entitlement probe time is required")
            if (
                self.entitlement_probed_at.tzinfo is None
                or self.entitlement_probed_at.utcoffset() is None
            ):
                raise ValueError("entitlement probe time must be timezone-aware")
        elif self.entitlement_probed_at is not None:
            if (
                self.entitlement_probed_at.tzinfo is None
                or self.entitlement_probed_at.utcoffset() is None
            ):
                raise ValueError("entitlement probe time must be timezone-aware")
        return self

    def supports(self, request: "ProviderRequest") -> bool:
        """Return true only for an exact, non-upgrading capability match."""
        if self.access is not request.access or self.data_kind is not request.data_kind:
            return False
        if request.symbol not in self.symbols:
            return False
        return self.data_kind is not DataKind.BARS or request.interval in self.intervals


class ProviderDescriptor(_FrozenContract):
    """Immutable identity and advertised capabilities of one provider."""

    provider_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*(?::[a-z0-9_-]+)*$")
    venue: Venue
    provider_version: str = Field(min_length=1)
    adapter_schema_version: str = Field(min_length=1)
    capabilities: tuple[ProviderCapability, ...] = ()
    legacy_only: bool = False

    @field_validator("provider_version", "adapter_schema_version")
    @classmethod
    def versions_are_not_blank(cls, value: str, info) -> str:
        if not value.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return value

    @model_validator(mode="after")
    def capabilities_are_unambiguous(self) -> "ProviderDescriptor":
        if self.legacy_only:
            if self.capabilities:
                raise ValueError("legacy-only descriptors cannot advertise capabilities")
            return self
        if not self.capabilities:
            raise ValueError("resolvable descriptors require capabilities")
        for index, left in enumerate(self.capabilities):
            for right in self.capabilities[index + 1 :]:
                same_operation = (
                    left.access is right.access and left.data_kind is right.data_kind
                )
                same_symbol = bool(left.symbols & right.symbols)
                same_interval = (
                    left.data_kind is not DataKind.BARS
                    or bool(left.intervals & right.intervals)
                )
                if same_operation and same_symbol and same_interval:
                    raise ValueError("provider capabilities are ambiguous")
        return self


class ProviderRequest(_FrozenContract):
    """Exact capability requested by a data consumer."""

    provider_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*(?::[a-z0-9_-]+)*$")
    venue: Venue
    access: ProviderAccess
    data_kind: DataKind
    symbol: str
    interval: str | None = None

    @field_validator("symbol")
    @classmethod
    def symbol_is_canonical(cls, value: str) -> str:
        validate_symbol(value)
        return value

    @model_validator(mode="after")
    def interval_matches_data_kind(self) -> "ProviderRequest":
        if self.data_kind is DataKind.BARS:
            if self.interval is None:
                raise ValueError("bars requests require an interval")
            interval_to_timedelta(self.interval)
        elif self.interval is not None:
            raise ValueError("only bars requests use an interval")
        return self


def fixture_descriptor(provider: object, venue: Venue) -> ProviderDescriptor:
    """Compatibility descriptor for the M3 fixture-only provider contract.

    The legacy ``get(Venue)`` path remains available. The registry refuses to
    use this descriptor for exact resolution because injectable fixture roots
    do not have a trustworthy static symbol/interval inventory.
    """
    class_path = f"{type(provider).__module__}.{type(provider).__qualname__}".lower()
    slug = "".join(character if character.isalnum() else "-" for character in class_path)
    slug = "-".join(part for part in slug.split("-") if part)
    return ProviderDescriptor(
        provider_id=f"fixture:{venue.value}:{slug}",
        venue=venue,
        provider_version="bundled",
        adapter_schema_version="quantmesh-market-data-v1",
        legacy_only=True,
    )
