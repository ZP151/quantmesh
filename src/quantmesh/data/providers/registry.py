"""Capability-aware provider registry with a fixture compatibility path.

New consumers resolve an exact provider/access/data capability. M3 consumers
may still call ``get(Venue)`` for one legacy fixture provider while they migrate.
"""

from collections.abc import Iterable

from quantmesh.data.capabilities import (
    EntitlementState,
    ProviderAccess,
    ProviderDescriptor,
    ProviderRequest,
    ProviderResolutionError,
    fixture_descriptor,
)
from quantmesh.data.providers.base import FixtureProvider, Provider, ProviderMode
from quantmesh.domain.models import Venue


class ProviderRegistry:
    """Resolve exact capabilities without granting stronger access."""

    def __init__(self, providers: Iterable[Provider] | None = None) -> None:
        self._legacy_by_venue: dict[Venue, Provider] = {}
        self._by_id: dict[str, Provider] = {}
        self._descriptors: dict[str, ProviderDescriptor] = {}
        for provider in providers or ():
            self.register(provider)

    def register(self, provider: Provider) -> None:
        if not isinstance(provider.venue, Venue):
            raise ValueError(f"provider {type(provider).__name__} has no valid venue")
        if not isinstance(provider.mode, ProviderMode):
            raise ValueError(f"provider {type(provider).__name__} has no valid mode")
        descriptor = provider.descriptor
        if descriptor is None and provider.mode is not ProviderMode.FIXTURE:
            raise ValueError(
                f"{provider.mode} providers are not allowed in M3 — fixture-only (AGENTS.md)"
            )
        if descriptor is None:
            descriptor = fixture_descriptor(provider, provider.venue)
        if descriptor.venue is not provider.venue:
            raise ValueError(
                f"provider descriptor venue {descriptor.venue} does not match {provider.venue}"
            )
        accesses = {capability.access for capability in descriptor.capabilities}
        if isinstance(provider, FixtureProvider) and provider.mode is not ProviderMode.FIXTURE:
            raise ValueError("fixture providers must use fixture mode")
        if provider.mode is ProviderMode.FIXTURE:
            if accesses and accesses != {ProviderAccess.FIXTURE}:
                raise ValueError("fixture mode can advertise fixture access only")
        elif ProviderAccess.FIXTURE in accesses:
            raise ValueError("non-fixture mode cannot advertise fixture access")
        if descriptor.provider_id in self._by_id:
            raise ValueError(f"provider already registered with id {descriptor.provider_id!r}")
        if provider.mode is ProviderMode.FIXTURE:
            if provider.venue in self._legacy_by_venue:
                raise ValueError(f"provider already registered for venue {provider.venue}")
            self._legacy_by_venue[provider.venue] = provider
        self._by_id[descriptor.provider_id] = provider
        self._descriptors[descriptor.provider_id] = descriptor

    def get(self, venue: Venue) -> Provider:
        try:
            return self._legacy_by_venue[venue]
        except KeyError as error:
            raise ValueError(f"no provider registered for venue {venue}") from error

    def resolve(self, request: ProviderRequest) -> Provider:
        """Resolve one exact capability or fail with the denied request."""
        provider = self._by_id.get(request.provider_id)
        descriptor = self._descriptors.get(request.provider_id)
        description = (
            f"{request.access.value} {request.data_kind.value} for "
            f"{request.venue.value}:{request.symbol}"
            + (f" at {request.interval}" if request.interval is not None else "")
        )
        if provider is None or descriptor is None:
            raise ProviderResolutionError(
                f"provider {request.provider_id!r} cannot resolve {description}"
            )
        if descriptor.venue is not request.venue:
            raise ProviderResolutionError(
                f"provider {request.provider_id!r} cannot resolve {description}: venue mismatch"
            )
        if descriptor.legacy_only:
            raise ProviderResolutionError(
                f"provider {request.provider_id!r} is legacy-only and cannot resolve {description}"
            )
        matches = [item for item in descriptor.capabilities if item.supports(request)]
        if len(matches) != 1:
            raise ProviderResolutionError(
                f"provider {request.provider_id!r} cannot resolve {description}"
            )
        entitlement = matches[0].entitlement
        if entitlement not in (EntitlementState.NOT_REQUIRED, EntitlementState.AVAILABLE):
            raise ProviderResolutionError(
                f"provider {request.provider_id!r} entitlement {entitlement.value} for "
                f"{description}"
            )
        return provider

    def venues(self) -> frozenset[Venue]:
        return frozenset(descriptor.venue for descriptor in self._descriptors.values())

    def descriptors(self) -> tuple[ProviderDescriptor, ...]:
        """Return immutable descriptors in stable provider-ID order."""
        return tuple(self._descriptors[key] for key in sorted(self._descriptors))

    def __contains__(self, venue: object) -> bool:
        return venue in self._legacy_by_venue
