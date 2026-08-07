"""Provider registry keyed by Venue (issue #17).

The registry is the only path from consumers to providers: strategies
and ingestion address venues, never vendor classes, which is what keeps
provider identity out of the lake and the consumer contract.
"""

from collections.abc import Iterable

from quantmesh.data.providers.base import Provider, ProviderMode
from quantmesh.domain.models import Venue


class ProviderRegistry:
    """One provider per venue; the only way consumers reach vendors."""

    def __init__(self, providers: Iterable[Provider] | None = None) -> None:
        self._by_venue: dict[Venue, Provider] = {}
        for provider in providers or ():
            self.register(provider)

    def register(self, provider: Provider) -> None:
        if not isinstance(provider.venue, Venue):
            raise ValueError(f"provider {type(provider).__name__} has no valid venue")
        if provider.mode is not ProviderMode.FIXTURE:
            raise ValueError(
                f"{provider.mode} providers are not allowed in M3 — fixture-only (AGENTS.md)"
            )
        if provider.venue in self._by_venue:
            raise ValueError(f"provider already registered for venue {provider.venue}")
        self._by_venue[provider.venue] = provider

    def get(self, venue: Venue) -> Provider:
        try:
            return self._by_venue[venue]
        except KeyError as error:
            raise ValueError(f"no provider registered for venue {venue}") from error

    def venues(self) -> frozenset[Venue]:
        return frozenset(self._by_venue)

    def __contains__(self, venue: object) -> bool:
        return venue in self._by_venue
