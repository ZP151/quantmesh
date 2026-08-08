"""Prompt-data redaction (M8, issue #48, Phase D).

`redact_context` scrubs secret material from research context BEFORE
anything reaches the gateway, and returns a deterministic
`RedactionReport` counting what was removed. Two layers: known secret
values (the `QUANTMESH_*KEY/SECRET/TOKEN` environment values, or an
explicitly supplied mapping) replaced verbatim, and shape scans for
key/token material — including inside *retrieved document text*
(prompt-injection containment). Over-redaction is the safe direction
and is deliberate: bare 64-hex runs are treated as key-shaped, while
pure 40-hex commit hashes and 16-hex ids survive.
"""

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass

from quantmesh.ai.errors import RedactionError

__all__ = [
    "REDACTED_ENV_SECRET",
    "REDACTED_PRIVATE_KEY",
    "REDACTED_TOKEN",
    "RedactionReport",
    "redact_context",
]

REDACTED_PRIVATE_KEY = "[REDACTED_PRIVATE_KEY]"
REDACTED_TOKEN = "[REDACTED_TOKEN]"
REDACTED_ENV_SECRET = "[REDACTED_ENV_SECRET]"

_SECRET_ENV_NAME = re.compile(r"^QUANTMESH_.*(KEY|SECRET|TOKEN)$")
_PRIVATE_KEY = re.compile(r"(0x[0-9a-fA-F]{64}|[0-9a-fA-F]{64})")
_BEARER_TOKEN = re.compile(r"Bearer\s+[A-Za-z0-9._~+/\-=]+")
_SK_TOKEN = re.compile(r"sk-[A-Za-z0-9]{16,}")
# Long opaque runs that are not pure hex (pure 40-hex commits survive;
# pure 64-hex is caught by the key rule).
_LONG_RUN = re.compile(r"[A-Za-z0-9+/=_-]{40,}")


@dataclass(frozen=True)
class RedactionReport:
    """How much of each secret class was removed from the context."""

    total: int
    by_class: Mapping[str, int]

    def __post_init__(self) -> None:
        if self.total < 0 or any(count < 0 for count in self.by_class.values()):
            raise ValueError("redaction counts must be non-negative")


def _env_secrets() -> dict[str, str]:
    """Known secret values from the environment (exact-match removal)."""
    return {
        name: value
        for name, value in os.environ.items()
        if _SECRET_ENV_NAME.fullmatch(name) and value
    }


def _is_pure_hex(text: str) -> bool:
    return all(char in "0123456789abcdefABCDEF" for char in text)


def redact_context(
    context: Mapping[str, str],
    *,
    secrets: Mapping[str, str] | None = None,
) -> tuple[dict[str, str], RedactionReport]:
    """Scrub secret material from every context value.

    Returns the redacted copy (never mutates the input) plus a
    `RedactionReport`. `secrets=None` collects the environment's
    `QUANTMESH_*KEY/SECRET/TOKEN` values; an explicit `secrets` mapping
    is used instead (and is how a caller pins the gateway key). Known
    values are replaced first (longest first, so a value that contains
    another leaves no partial artifacts), then the shape scans. A
    non-string context value or a non-string secret entry is a typed
    `RedactionError` naming the part.
    """
    if secrets is None:
        secrets = _env_secrets()
    for name, value in secrets.items():
        if not isinstance(name, str) or not isinstance(value, str):
            raise RedactionError(
                f"secret entries must be strings, got {type(name).__name__}:"
                f" {type(value).__name__}"
            )
    known = sorted(
        (value for value in secrets.values() if value.strip()), key=len, reverse=True
    )
    counts = {"env_secret": 0, "private_key": 0, "token": 0}
    redacted: dict[str, str] = {}
    for name, content in context.items():
        if not isinstance(name, str):
            raise RedactionError(f"context name must be a string, got {type(name).__name__}")
        if not isinstance(content, str):
            raise RedactionError(
                f"context {name!r} content must be a string, got {type(content).__name__}"
            )
        text = content
        for secret in known:
            if secret in text:
                counts["env_secret"] += text.count(secret)
                text = text.replace(secret, REDACTED_ENV_SECRET)
        text = _PRIVATE_KEY.sub(REDACTED_PRIVATE_KEY, text)
        text = _BEARER_TOKEN.sub(REDACTED_TOKEN, text)
        text = _SK_TOKEN.sub(REDACTED_TOKEN, text)
        text = _LONG_RUN.sub(
            lambda match: (
                REDACTED_TOKEN if not _is_pure_hex(match.group(0)) else match.group(0)
            ),
            text,
        )
        counts["private_key"] += text.count(REDACTED_PRIVATE_KEY)
        counts["token"] += text.count(REDACTED_TOKEN)
        redacted[name] = text
    return redacted, RedactionReport(total=sum(counts.values()), by_class=dict(counts))
