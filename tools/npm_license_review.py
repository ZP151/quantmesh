"""Fail-closed license review for the frozen frontend npm closure.

The package lock is the reproducible dependency contract.  Every non-root
entry must carry an exact version, registry integrity, and an SPDX expression
that has been explicitly accepted by QuantMesh.  Unknown or missing metadata
is a release failure; adding a dependency therefore requires a conscious
policy update rather than silently expanding the legal surface.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
LOCK = REPO / "frontend" / "package-lock.json"

# Exact expressions currently present in package-lock.json.  These are all
# permissive, attribution/share-compatible, or weak file-level copyleft terms
# already documented in docs/licenses.md.  Expression spelling is deliberate:
# an upstream metadata change must be reviewed, not normalized away.
ALLOWED_LICENSES = frozenset(
    {
        "(MIT OR CC0-1.0)",
        "0BSD",
        "Apache-2.0",
        "BlueOak-1.0.0",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "CC-BY-4.0",
        "ISC",
        "MIT",
        "MIT-0",
        "MPL-2.0",
        "OFL-1.1",
        "Python-2.0",
    }
)


class FrontendLicenseError(ValueError):
    """The npm lock cannot prove an allowed frontend dependency closure."""


def review_lock_document(document: object) -> dict[str, dict[str, str]]:
    if not isinstance(document, dict) or document.get("lockfileVersion") != 3:
        raise FrontendLicenseError("frontend lock must use npm lockfileVersion 3")
    packages = document.get("packages")
    if not isinstance(packages, dict) or "" not in packages:
        raise FrontendLicenseError("frontend lock packages/root entry is absent")

    inventory: dict[str, dict[str, str]] = {}
    errors: list[str] = []
    for path, raw in sorted(packages.items()):
        if path == "":
            continue
        if not isinstance(path, str) or not path.startswith("node_modules/"):
            errors.append(f"{path!r}: dependency path is not under node_modules")
            continue
        if not isinstance(raw, dict):
            errors.append(f"{path}: package metadata is not an object")
            continue
        version = raw.get("version")
        license_name = raw.get("license")
        resolved = raw.get("resolved")
        integrity = raw.get("integrity")
        if not isinstance(version, str) or not version.strip():
            errors.append(f"{path}: exact version is absent")
        if not isinstance(resolved, str) or not resolved.startswith("https://registry.npmjs.org/"):
            errors.append(f"{path}: registry resolution is absent or untrusted")
        if not isinstance(integrity, str) or not integrity.startswith("sha512-"):
            errors.append(f"{path}: sha512 integrity is absent")
        if not isinstance(license_name, str) or license_name not in ALLOWED_LICENSES:
            errors.append(f"{path}: license {license_name!r} is not allowed")
        if not errors or not errors[-1].startswith(f"{path}:"):
            inventory[path] = {
                "version": str(version),
                "license": str(license_name),
            }

    if errors:
        raise FrontendLicenseError("frontend license review failed:\n" + "\n".join(errors))
    if not inventory:
        raise FrontendLicenseError("frontend dependency inventory is empty")
    return inventory


def main() -> int:
    try:
        document: Any = json.loads(LOCK.read_text(encoding="utf-8"))
        inventory = review_lock_document(document)
    except (OSError, json.JSONDecodeError, FrontendLicenseError) as error:
        print(error, file=sys.stderr)
        return 1

    counts = Counter(item["license"] for item in inventory.values())
    summary = ", ".join(f"{name}={count}" for name, count in sorted(counts.items()))
    print(f"frontend licenses allowed: {len(inventory)} locked packages ({summary})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
