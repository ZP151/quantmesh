"""Deterministic license review (M10 Phase D, issue #61; iteration 0013
Phase B makes it closure-deterministic).

The review evaluates the *release closure* — the packages pinned in
``requirements-audit.txt`` — not whatever an ambient development
environment happens to contain:

1. Every pinned package must be installed in this environment, or it is
   refused ("pinned but not installed"); the documented
   platform-restricted closure members — uvloop from
   ``uvicorn[standard]`` and the keyring backend chain
   jeepney/SecretStorage/cryptography/cffi/pycparser (Linux only),
   plus colorama (pytest's win32 marker) and pywin32-ctypes
   (keyring's win32 backend) (Windows only) — are tolerated as
   absent on platforms where they do not resolve.
2. Every installed third-party distribution outside the closure is
   refused ("installed but not pinned") — except the build tooling pip/
   setuptools/wheel that a venv itself provides. This is what makes the
   gate deterministic: pip-audit's own CLI dependencies
   (license-expression, boolean.py, ...) or an old environment's
   leftovers can no longer drift into the inventory; the gate must run
   in the deterministic release environment (``tools/release_gate.py``
   creates one), exactly as iteration 0013 records.
3. Each closure package is classified from its PEP 639
   (License-Expression) or PEP 345 (License / Classifier) metadata and
   must land on the documented allowlist in docs/licenses.md.

The check is stdlib-only (no network), deterministic over the release
closure, and exits 0 only when every closure package is allowed and
nothing untracked is installed — exit 1 names the offenders.

Run: ``python tools/license_review.py``
"""

from __future__ import annotations

import importlib.metadata as md
import re
import sys
from pathlib import Path

from quantmesh.ops.source_contract import PLATFORM_TOLERATED

# The distribution names of the project itself — the review covers
# third-party dependencies, not the package under review.
PROJECT_NAMES = {"quantmesh"}

# Packages a venv itself provides. They are never part of the release
# closure (pip's own resolution depends on them, not the project's) and
# are allowed to be installed without being pinned.
BUILD_TOOLING = {"pip", "setuptools", "wheel"}

# The frozen install closure the review evaluates. The default is the
# repo's requirements-audit.txt; tests may point elsewhere.
CLOSURE_FILE = Path(__file__).resolve().parents[1] / "requirements-audit.txt"

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
    "NCSA",  # University of Illinois/NCSA license (permissive; arch 8)
}

# Hand-verified overrides for closure members whose metadata carries
# no usable license expression/classifier. The key is the distribution
# name (normalized), the value the license the package actually ships
# under. docs/licenses.md must list each with its justification. Only
# closure members belong here: under the closure contract nothing
# outside requirements-audit.txt is ever classified.
LICENSE_EXCEPTIONS = {
    "certifi": "MPL-2.0",
    "tzdata": "Apache-2.0",
}

# Exact package/version/expression choices whose permitted branch QuantMesh
# selects. This stays separate from the generic parser, which deliberately
# refuses ``MIT OR GPL``-shaped expressions when any branch violates policy.
LICENSE_EXPRESSION_EXCEPTIONS = {
    ("simplejson", "4.1.1", "MIT OR AFL-2.1"): "MIT",
}
LICENSE_TEXT_EXCEPTIONS = {
    ("simplejson", "4.1.1", "MIT OR AFL-2.1"): "MIT",
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


# Free-text License fields sometimes inline the whole LICENSES/ folder
# (pandas 2.3.3 Linux wheels: BSD text plus bundled third-party
# Apache/MIT texts in one 91 kB field). When the first line names a
# known license it is authoritative — scanning the whole blob would
# credit a bundled text as the project's own license. Unknown first
# lines (copyright lines, prose) fall through to the keyword scan.
_LINE1_NAMES = {
    "3-Clause BSD License": "BSD-3-Clause",
    "BSD 3-Clause License": "BSD-3-Clause",
    "BSD 2-Clause License": "BSD-2-Clause",
    "The MIT License": "MIT",
    "MIT License": "MIT",
    "Apache License 2.0": "Apache-2.0",
    "Apache License, Version 2.0": "Apache-2.0",
    "Apache License Version 2.0": "Apache-2.0",
    "Python Software Foundation License": "PSF-2.0",
}


def _from_text(text: str) -> str | None:
    """Classify an embedded license text. The first line is
    authoritative when it names a known license (bundled-licenses
    blobs would otherwise misclassify via a bundled text); MIT and
    BSD are otherwise distinguished by the BSD 'Neither the name ...'
    restriction."""
    if "Commons Clause" in text:
        # Apache-2.0 + Commons Clause is source-available, not OSI —
        # the Apache appendix text is inside, so the clause must be
        # refused *before* the Apache pattern can match (vectorbt).
        return None
    first = text.splitlines()[0].strip()
    if first in _LINE1_NAMES:
        return _LINE1_NAMES[first]
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
    "License :: OSI Approved :: University of Illinois/NCSA Open Source License": "NCSA",
}


def classify(dist: md.Distribution) -> str:
    """The license key for a distribution, or ``UNKNOWN`` (a refusal
    to the caller)."""
    name = dist.metadata["Name"]
    expr = dist.metadata.get("License-Expression", "")
    if expr:
        selected = LICENSE_EXPRESSION_EXCEPTIONS.get((name, dist.version, expr))
        if selected is not None:
            return f"{selected} (documented exception)"
        resolved = _from_expression(expr)
        if resolved is not None:
            return resolved
        return f"UNKNOWN (expression {expr!r})"
    classifiers = dist.metadata.get_all("Classifier", [])
    if "License :: OSI Approved :: University of Illinois/NCSA Open Source License" in classifiers:
        return "NCSA"
    text = dist.metadata.get("License", "")
    if text:
        selected = LICENSE_TEXT_EXCEPTIONS.get((name, dist.version, text))
        if selected is not None:
            return f"{selected} (documented exception)"
        resolved = _from_text(text)
        if resolved is not None:
            return resolved
    for classifier in classifiers:
        if classifier in _CLASSIFIER_MAP:
            return _CLASSIFIER_MAP[classifier]
    if name in LICENSE_EXCEPTIONS:
        return f"{LICENSE_EXCEPTIONS[name]} (documented exception)"
    return "UNKNOWN"


def read_closure(path: Path = CLOSURE_FILE) -> dict[str, str]:
    """The pinned closure {name: version} from requirements-audit.txt."""
    closure: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        name, _, version = line.partition("==")
        assert name.strip() and version.strip(), f"malformed pin: {line!r}"
        closure[name.strip()] = version.strip()
    return closure


def review(closure: dict[str, str]) -> tuple[list[str], list[str], list[str], list[str]]:
    """Review the closure against the installed environment.

    Returns ``(rows, failures, untracked, missing)`` where ``rows`` are
    printable ``name==version  license`` lines for reviewed closure
    members, ``failures`` the refusal lines, ``untracked`` the installed
    packages outside the closure, and ``missing`` the pinned closure
    members not installed on this platform.
    """
    rows: list[str] = []
    failures: list[str] = []
    untracked: list[str] = []
    missing: list[str] = []

    installed = {d.metadata["Name"]: d for d in md.distributions()}
    for name in sorted(closure):
        version = closure[name]
        dist = installed.get(name)
        if dist is None:
            if name in PLATFORM_TOLERATED:
                missing.append(
                    f"{name}=={version}  (pinned for another platform; not installed here)"
                )
            else:
                failures.append(
                    f"{name}=={version}  pinned in requirements-audit.txt but not "
                    "installed — incomplete release environment"
                )
            continue
        key = classify(dist)
        rows.append(f"{name}=={version}  {key}")
        if key == "UNKNOWN" or key.startswith("UNKNOWN ("):
            failures.append(f"{name} {version}: {key}")

    for name in sorted(installed):
        if name in PROJECT_NAMES or name in closure or name in BUILD_TOOLING:
            continue
        untracked.append(
            f"{name}=={installed[name].version}  installed but not pinned in "
            "requirements-audit.txt — ambient environment package; run the license "
            "gate in the deterministic release environment (tools/release_gate.py)"
        )
    return rows, failures, untracked, missing


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    closure_path = CLOSURE_FILE
    if argv and argv[0] == "--closure":
        closure_path = Path(argv[1])
        argv = argv[2:]
    if argv:
        print(f"usage: python {Path(__file__).name} [--closure PATH]")
        return 2
    closure = read_closure(closure_path)
    rows, failures, untracked, missing = review(closure)

    print(f"release closure: {len(closure)} packages from {closure_path.name}")
    for line in rows:
        print(line)
    for line in missing:
        print(line)
    print(f"\n{len(rows)} closure packages reviewed on this platform")
    if untracked:
        print(f"\nREFUSED — {len(untracked)} installed package(s) outside the closure:")
        print("\n".join(untracked))
    if failures:
        print(f"\nFAILED: {len(failures)} unclassified or incompatible:\n" + "\n".join(failures))
        return 1
    if untracked:
        return 1
    print("all licenses allowed (docs/licenses.md); environment is the release closure")
    return 0


if __name__ == "__main__":
    sys.exit(main())
