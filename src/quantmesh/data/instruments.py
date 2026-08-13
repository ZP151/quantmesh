"""Bounded canonical instruments and bitemporal provider aliases."""

import hashlib
import json
from datetime import UTC, date, datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_CANONICAL_IDS = frozenset(
    {
        "moomoo:US:AAPL:XNAS",
        "moomoo:US:NVDA:XNAS",
        "hyperliquid:perp:BTC",
        "hyperliquid:perp:ETH",
        "hyperliquid:perp:SOL",
    }
)
_PROVIDER_PREFIX = {
    "moomoo-opend": "moomoo:",
    "hyperliquid-public": "hyperliquid:",
}
_ALIAS_TARGETS = {
    ("moomoo-opend", "US.AAPL"): "moomoo:US:AAPL:XNAS",
    ("moomoo-opend", "US.NVDA"): "moomoo:US:NVDA:XNAS",
    ("hyperliquid-public", "BTC"): "hyperliquid:perp:BTC",
    ("hyperliquid-public", "ETH"): "hyperliquid:perp:ETH",
    ("hyperliquid-public", "SOL"): "hyperliquid:perp:SOL",
}


class InstrumentResolutionError(ValueError):
    """A provider symbol has no single point-in-time canonical identity."""


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class CanonicalInstrumentId(_FrozenContract):
    """One of the five identities admitted to Iteration 0021."""

    value: str

    @field_validator("value")
    @classmethod
    def value_is_in_bounded_universe(cls, value: str) -> str:
        if value not in _CANONICAL_IDS:
            raise ValueError(f"{value!r} is outside the bounded trusted-data universe")
        return value


class SymbolAlias(_FrozenContract):
    """Provider mapping with independent effective and knowledge intervals."""

    provider_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    provider_symbol: str = Field(min_length=1)
    canonical_id: CanonicalInstrumentId
    effective_from: date
    effective_to: date | None = None
    known_from: datetime
    known_to: datetime | None = None

    @field_validator("provider_id")
    @classmethod
    def provider_is_in_bounded_universe(cls, value: str) -> str:
        if value not in _PROVIDER_PREFIX:
            raise ValueError(f"{value!r} is not a trusted-data provider")
        return value

    @field_validator("provider_symbol")
    @classmethod
    def provider_symbol_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("provider_symbol must not be blank")
        return value

    @field_validator("known_from", "known_to")
    @classmethod
    def knowledge_time_is_utc(cls, value: datetime | None) -> datetime | None:
        if value is not None and (
            value.tzinfo is None or value.utcoffset() != timedelta(0)
        ):
            raise ValueError("knowledge time must be UTC")
        return value

    @model_validator(mode="after")
    def identity_and_windows_are_valid(self) -> "SymbolAlias":
        if not self.canonical_id.value.startswith(_PROVIDER_PREFIX[self.provider_id]):
            raise ValueError("provider and canonical identity disagree")
        expected = _ALIAS_TARGETS.get((self.provider_id, self.provider_symbol))
        if expected != self.canonical_id.value:
            raise ValueError("provider symbol and canonical identity disagree")
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must be after effective_from")
        if self.known_to is not None and self.known_to <= self.known_from:
            raise ValueError("known_to must be after known_from")
        return self

    def is_visible(self, effective_at: date, known_at: datetime) -> bool:
        effective = self.effective_from <= effective_at and (
            self.effective_to is None or effective_at < self.effective_to
        )
        known = self.known_from <= known_at and (
            self.known_to is None or known_at < self.known_to
        )
        return effective and known


def _date_windows_overlap(left: SymbolAlias, right: SymbolAlias) -> bool:
    return (
        left.effective_to is None or right.effective_from < left.effective_to
    ) and (right.effective_to is None or left.effective_from < right.effective_to)


def _knowledge_windows_overlap(left: SymbolAlias, right: SymbolAlias) -> bool:
    return (left.known_to is None or right.known_from < left.known_to) and (
        right.known_to is None or left.known_from < right.known_to
    )


class InstrumentCatalog(_FrozenContract):
    """Immutable bitemporal aliases with a content-addressed catalog ID."""

    aliases: tuple[SymbolAlias, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def aliases_do_not_overlap(self) -> "InstrumentCatalog":
        grouped: dict[tuple[str, str], list[SymbolAlias]] = {}
        for alias in self.aliases:
            grouped.setdefault((alias.provider_id, alias.provider_symbol), []).append(alias)
        for key, aliases in grouped.items():
            for index, left in enumerate(aliases):
                for right in aliases[index + 1 :]:
                    if _date_windows_overlap(left, right) and _knowledge_windows_overlap(
                        left, right
                    ):
                        raise ValueError(
                            f"overlapping alias windows for {key[0]}:{key[1]}"
                        )
        return self

    @property
    def catalog_id(self) -> str:
        rows = [alias.model_dump(mode="json") for alias in self.aliases]
        rows.sort(key=lambda row: json.dumps(row, sort_keys=True, separators=(",", ":")))
        payload = json.dumps(
            {"schema_version": 1, "aliases": rows},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return f"sha256:{hashlib.sha256(payload).hexdigest()}"

    def resolve(
        self,
        provider_id: str,
        provider_symbol: str,
        *,
        effective_at: date,
        known_at: datetime,
    ) -> CanonicalInstrumentId:
        return self.resolve_alias(
            provider_id,
            provider_symbol,
            effective_at=effective_at,
            known_at=known_at,
        ).canonical_id

    def resolve_alias(
        self,
        provider_id: str,
        provider_symbol: str,
        *,
        effective_at: date,
        known_at: datetime,
    ) -> SymbolAlias:
        if known_at.tzinfo is None or known_at.utcoffset() != timedelta(0):
            raise InstrumentResolutionError("known_at must be UTC")
        matching = [
            alias
            for alias in self.aliases
            if alias.provider_id == provider_id
            and alias.provider_symbol == provider_symbol
        ]
        if not matching:
            raise InstrumentResolutionError(
                f"unknown provider symbol {provider_id}:{provider_symbol}"
            )
        visible = [
            alias for alias in matching if alias.is_visible(effective_at, known_at)
        ]
        if len(visible) != 1:
            raise InstrumentResolutionError(
                f"provider symbol {provider_id}:{provider_symbol} is not effective or known "
                f"at effective_at={effective_at}, known_at={known_at.isoformat()}"
            )
        return visible[0]

    @classmethod
    def bounded_default(cls) -> "InstrumentCatalog":
        known_from = datetime(2026, 8, 14, tzinfo=UTC)
        aliases = tuple(
            (
                provider_id,
                provider_symbol,
                canonical_id,
                date(2000, 1, 1) if provider_id == "moomoo-opend" else date(2023, 1, 1),
            )
            for (provider_id, provider_symbol), canonical_id in _ALIAS_TARGETS.items()
        )
        return cls(
            aliases=tuple(
                SymbolAlias(
                    provider_id=provider_id,
                    provider_symbol=provider_symbol,
                    canonical_id=CanonicalInstrumentId(value=canonical_id),
                    effective_from=effective_from,
                    known_from=known_from,
                )
                for provider_id, provider_symbol, canonical_id, effective_from in aliases
            )
        )
