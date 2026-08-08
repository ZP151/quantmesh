"""Signed audit exports (M10 Phase A, issue #58).

``export_audit_bundle`` serializes the four system-of-record surfaces
— the M2 order journal, the M6 mapping ledger, the M8 decision log and
the M10 metrics store — into one JSON bundle whose content digest is
HMAC-SHA256-signed with the key held by the KeyStore. Integrity is
semantic, not byte-level: verification re-canonicalizes the parsed
content (JSON with sorted keys), so any change to a value fails the
digest, while whitespace-only reformatting still verifies. Any
tamper, wrong key, or malformed bundle is refused with a typed
``BundleVerificationError`` naming the failure.
"""

import hashlib
import hmac
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

BUNDLE_FORMAT = "quantmesh-audit-bundle"
BUNDLE_VERSION = 1
DIGEST_ALGORITHM = "sha256"
SIGNATURE_ALGORITHM = "hmac-sha256"


class BundleVerificationError(ValueError):
    """The bundle is malformed, tampered, or signed by another key."""


def _canonical(content: dict[str, list[dict]]) -> str:
    return json.dumps(content, sort_keys=True, separators=(",", ":"))


def export_audit_bundle(
    target: Path,
    *,
    orders: Sequence[BaseModel],
    mappings: Sequence[BaseModel],
    decisions: Sequence[BaseModel],
    metrics: Sequence[BaseModel],
    key: bytes,
    exported_at: datetime | None = None,
) -> Path:
    """Write the signed bundle and return its path."""
    content = {
        "orders": [order.model_dump(mode="json") for order in orders],
        "mappings": [mapping.model_dump(mode="json") for mapping in mappings],
        "decisions": [decision.model_dump(mode="json") for decision in decisions],
        "metrics": [metric.model_dump(mode="json") for metric in metrics],
    }
    canonical = _canonical(content)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    signature = hmac.new(key, digest.encode("ascii"), hashlib.sha256).hexdigest()
    bundle = {
        "format": BUNDLE_FORMAT,
        "version": BUNDLE_VERSION,
        "exported_at": (exported_at or datetime.now(UTC)).astimezone(UTC).isoformat(),
        "digest_algorithm": DIGEST_ALGORITHM,
        "signature_algorithm": SIGNATURE_ALGORITHM,
        "content": content,
        "digest": digest,
        "signature": signature,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(bundle, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    return target


def verify_audit_bundle(path: Path, *, key: bytes) -> dict:
    """Verify the bundle's integrity and return its parsed content.

    Refuses (typed error, nothing returned): a missing or unreadable
    bundle, a wrong format/version, a missing content section, a
    digest that does not match the content, or a signature that does
    not match the digest under this key.
    """
    try:
        bundle = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BundleVerificationError(f"cannot read bundle {path}: {error}") from error
    if bundle.get("format") != BUNDLE_FORMAT:
        raise BundleVerificationError(
            f"bundle {path} is not a {BUNDLE_FORMAT} (format {bundle.get('format')!r})"
        )
    if bundle.get("version") != BUNDLE_VERSION:
        raise BundleVerificationError(
            f"bundle {path} has unsupported version {bundle.get('version')!r}"
        )
    content = bundle.get("content")
    if not isinstance(content, dict):
        raise BundleVerificationError(f"bundle {path} has no content object")
    expected_digest = hashlib.sha256(_canonical(content).encode("utf-8")).hexdigest()
    if not hmac.compare_digest(bundle.get("digest", ""), expected_digest):
        raise BundleVerificationError(f"bundle {path} content digest does not match")
    expected_signature = hmac.new(
        key, expected_digest.encode("ascii"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(bundle.get("signature", ""), expected_signature):
        raise BundleVerificationError(
            f"bundle {path} signature does not verify under this key"
        )
    return content
