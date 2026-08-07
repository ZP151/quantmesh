"""Typed Hyperliquid error family (M5, issue #29).

Mirrors the M4 OpenD error discipline: every failure surface is a
typed ``HyperliquidError`` subclass so the CLI, the drill, and the
safety gates can distinguish "the venue is unreachable" from "the
payload was malformed" from "the SDK is not installed".
"""


class HyperliquidError(RuntimeError):
    """Base class for every Hyperliquid adapter failure."""


class HyperliquidUnavailableError(HyperliquidError):
    """The venue (REST or WS) did not answer, or refused a request."""


class HyperliquidProtocolError(HyperliquidError):
    """A payload or frame violated the wire contract; never guess."""


class HyperliquidSDKMissingError(HyperliquidError):
    """The vendored hyperliquid-python-sdk is not importable."""
