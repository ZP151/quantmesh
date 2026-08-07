"""Polymarket typed errors (M6, issue #34, Phase A)."""


class PolymarketError(ValueError):
    """Base for every Polymarket adapter failure."""


class PolymarketProtocolError(PolymarketError):
    """A wire payload violates the pinned contract — fail closed."""


class PolymarketUnavailableError(PolymarketError):
    """The public API was unreachable or refused the request."""


class PolymarketSDKMissingError(PolymarketError):
    """The vendored ``py-clob-client-v2`` is not importable."""
