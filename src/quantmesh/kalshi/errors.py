"""Kalshi typed errors (M6, issue #35, Phase B)."""


class KalshiError(ValueError):
    """Base for every Kalshi adapter failure."""


class KalshiProtocolError(KalshiError):
    """A wire payload violates the pinned contract — fail closed."""


class KalshiUnavailableError(KalshiError):
    """The public API was unreachable or refused the request."""
