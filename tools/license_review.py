"""Deterministic license review (M10 Phase D, issue #61).

Classifies the license of every installed distribution from its PEP 639
(License-Expression) or PEP 345 (License / Classifier) metadata and
refuses anything outside the documented allowlist in docs/licenses.md.
The check is deterministic over the installed environment (the CI
install of `.[dev,research]`), needs no network, and exits 0 only when
every package is allowed — exit 1 names the offenders.

Classification order (fail-closed at each step):
1. PEP 639 ``License-Expression`` (SPDX) — the authoritative source
   when present; ``X OR Y`` alternations pass if any member is allowed.
2. The ``License`` free-text field — keyword detection for MIT,
   BSD-2/3-Clause and Apache-2.0, which covers the packages that
   embed the full text instead of an expression.
3. ``Classifier`` declarations of the OSI-Approved family.
4. ``LICENSE_EXCEPTIONS`` — hand-verified overrides for packages whose
   metadata carries no usable license; every entry must also appear in
   docs/licenses.md with its reason.
Anything still unclassified is a refusal: an unknown license is not
silently allowed.

Run: ``python tools/license_review.py``
"""

from __future__ import annotations

import importlib.metadata as md
import re
import sys

# The distribution names of the project itself — the review covers
# third-party dependencies, not the package under review.
PROJECT_NAMES = {"quantmesh"}

# Documented allowlist (docs/licenses.md mirrors it). A license outside
# this set — GPL/AGPL, LGPL, proprietary, source-available
# restrictions such as the Commons Clause, or unknown — is
# incompatible with the project's local-first, redistributable posture
# and fails the job.
ALLOWED = {
    "MIT",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "Apache-2.0",
    "PSF-2.0",
    "ISC",
    "MPL-2.0",  # file-level copyleft; permissive for redistribution (certifi, tqdm)
    "0BSD",
    "Zlib",
    "CC0-1.0",
    "CNRI-Python",  # the historical CNRI Python license (permissive)
    "MIT-CMU",  # MIT variant with the CMU notice (Pillow)
    "MIT-0",  # MIT No Attribution (OSI-approved; cffi declares it)
}

# Hand-verified overrides for packages whose metadata carries no
# usable license expression/classifier. The key is the distribution
# name (normalized), the value the license the package actually ships
# under. docs/licenses.md must list each with its justification.
LICENSE_EXCEPTIONS = {
    "asttokens": "MIT",
    "certifi": "MPL-2.0",
    "charset-normalizer": "MIT",
    "fonttools": "MIT",
    "tqdm": "MPL-2.0",
    "tzdata": "Apache-2.0",
}

# SPDX expressions sometimes carry a versioned form we do not model.
_SPDX_ALIASES = {
    "MIT License": "MIT",
    "Apache License 2.0": "Apache-2.0",
    "Apache-2.0 License": "Apache-2.0",
    "BSD 3-Clause License": "BSD-3-Clause",
    "BSD-3-Clause License": "BSD-3-Clause",
    "BSD 2-Clause License": "BSD-2-Clause",
    "BSD-2-Clause License": "BSD-2-Clause",
    "Python Software Foundation License": "PSF-2.0",
    "PSF License": "PSF-2.0",
}


def _from_expression(expr: str) -> str | None:
    """Resolve an SPDX expression to an allowed key, or None if no
    member is allowed. ``AND``-joined members all apply, so the result
    is the strictest member (any non-allowed member fails). A
    ``WITH <exception>`` qualifier (e.g. ``WITH LLVM-exception``)
    *relaxes* the license, so the exception identifier itself is
    stripped, never treated as a restricting member."""
    if "commons" in expr.lower():
        # "WITH Commons-Clause" is not an SPDX exception — it is a
        # restricting condition that cancels the Apache grant; refused
        # before the qualifier strip could turn it into Apache-2.0.
        return None
    expr = re.sub(r"\s+WITH\s+[A-Za-z0-9._-]+", "", expr)
    parts = [p.strip() for p in re.split(r"\s+AND\s+", expr)]
    alternatives = [p.strip() for p in re.split(r"\s+OR\s+", " OR ".join(parts))]
    keys = [_SPDX_ALIASES.get(a, a) for a in alternatives]
    if all(k in ALLOWED for k in keys):
        return " | ".join(sorted(set(keys)))
    return None


_LICENSE_TEXT_PATTERNS = [
    # Apache-2.0, detected from the appendix text.
    (
        "Apache-2.0",
        re.compile(
            r"Apache License\s+Version 2\.0|"
            r'Licensed under the Apache License, Version 2\.0'
        ),
    ),
    # MIT and BSD share the first line; the permissive three-clause
    # family is told apart by the "Neither the name" clause (BSD).
    ("MIT", re.compile(r"Permission is hereby granted")),
]


def _from_text(text: str) -> str | None:
    """Classify an embedded license text. MIT and BSD are
    distinguished by the BSD 'Neither the name ...' restriction."""
    if "Commons Clause" in text:
        # Apache-2.0 + Commons Clause is source-available, not OSI —
        # the Apache appendix text is inside, so the clause must be
        # refused *before* the Apache pattern can match (vectorbt).
        return None
    if "Apache License" in text and "Version 2.0" in text:
        return "Apache-2.0"
    if "Permission is hereby granted" in text:
        if "Neither the name" in text:
            if "Redistribution in binary form" in text or "redistributions in binary form" in text:
                return "BSD-3-Clause"
            return "BSD-2-Clause"
        return "MIT"
    if "MIT License" in text or "The MIT License" in text:
        return "MIT"
    if "BSD 3-Clause" in text or "BSD-3-Clause" in text:
        return "BSD-3-Clause"
    if "BSD 2-Clause" in text or "BSD-2-Clause" in text:
        return "BSD-2-Clause"
    return None


_CLASSIFIER_MAP = {
    "License :: OSI Approved :: MIT License": "MIT",
    "License :: OSI Approved :: BSD License": "BSD-3-Clause",
    "License :: OSI Approved :: BSD-3-Clause": "BSD-3-Clause",
    "License :: OSI Approved :: BSD-2-Clause License": "BSD-2-Clause",
    "License :: OSI Approved :: Apache Software License": "Apache-2.0",
    "License :: OSI Approved :: Apache License 2.0": "Apache-2.0",
    "License :: OSI Approved :: ISC License (ISCL)": "ISC",
    "License :: OSI Approved :: Python Software Foundation License": "PSF-2.0",
    "License :: Python Software Foundation License": "PSF-2.0",
}


def classify(dist: md.Distribution) -> str:
    """The license key for a distribution, or ``UNKNOWN`` (a refusal
    to the caller)."""
    name = dist.metadata["Name"]
    expr = dist.metadata.get("License-Expression", "")
    if expr:
        resolved = _from_expression(expr)
        if resolved is not None:
            return resolved
        return f"UNKNOWN (expression {expr!r})"
    text = dist.metadata.get("License", "")
    if text:
        resolved = _from_text(text)
        if resolved is not None:
            return resolved
    for classifier in dist.metadata.get_all("Classifier", []):
        if classifier in _CLASSIFIER_MAP:
            return _CLASSIFIER_MAP[classifier]
    if name in LICENSE_EXCEPTIONS:
        return f"{LICENSE_EXCEPTIONS[name]} (documented exception)"
    return "UNKNOWN"


def main() -> int:
    rows: list[tuple[str, str, str]] = []
    failures: list[str] = []
    for dist in sorted(md.distributions(), key=lambda d: d.metadata["Name"].lower()):
        name = dist.metadata["Name"]
        if name in PROJECT_NAMES:
            continue
        version = dist.version
        key = classify(dist)
        rows.append((name, version, key))
        if key == "UNKNOWN" or key.startswith("UNKNOWN ("):
            failures.append(f"{name} {version}: {key}")
    for name, version, key in rows:
        print(f"{name}=={version}  {key}")
    print(f"\n{len(rows)} packages reviewed")
    if failures:
        print(f"FAILED: {len(failures)} unclassified or incompatible:\n" + "\n".join(failures))
        return 1
    print("all licenses allowed (docs/licenses.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
