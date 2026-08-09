"""Release-version consistency check (iteration 0014, rc3 cycle).

The v0.1.0-rc2 rejection (operator, 2026-08-09) found the tag claiming
`v0.1.0-rc2` while the package still reported `0.1.0rc1`, and the
existing version test could not catch it because it pinned `0.1.0rc1`
itself. This check closes that hole for the release gate by asserting,
inside the gate's clean checkout:

1. ``pyproject.toml`` and ``quantmesh/__init__.py`` agree on the package
   version (already unit-pinned in tests/test_release.py).
2. The newest ``docs/release-notes/v0.1.0-rc*.md`` file declares the
   *same* version — the notes are the human-declared release intent, so
   a notes/metadata drift (the rc2 defect) fails here before any tag.
3. If any ``v<version>`` tag points at HEAD, the tag version equals the
   package version — a mismatched tag can never be gated green.
4. The version is a PEP 440 prerelease while the 0.1.0 RC line is open.

Exits 0 with a one-line summary; exits 1 naming the first mismatch.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
NOTES_DIR = REPO / "docs" / "release-notes"


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.strip()


def _release_note_version() -> str | None:
    """The version declared by the newest v0.1.0-rcN notes file, if any."""
    newest: tuple[int, Path] | None = None
    for path in NOTES_DIR.glob("v0.1.0-rc*.md"):
        match = re.fullmatch(r"v0\.1\.0-rc(\d+)\.md", path.name)
        if not match:
            continue
        number = int(match.group(1))
        if newest is None or number > newest[0]:
            newest = (number, path)
    return None if newest is None else f"0.1.0rc{newest[0]}"


def _head_version_tags() -> list[str]:
    tags = _git("tag", "--points-at", "HEAD").splitlines()
    return [
        tag
        for tag in tags
        if re.fullmatch(r"v0\.1\.0(-rc\d+)?", tag) and tag != "v0.1.0-rc1"
    ]


def main() -> int:
    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    version = pyproject["project"]["version"]

    init_source = (REPO / "src" / "quantmesh" / "__init__.py").read_text(
        encoding="utf-8"
    )
    if f'__version__ = "{version}"' not in init_source:
        print(f"FAIL: __init__.py does not declare __version__ = {version!r}")
        return 1

    note_version = _release_note_version()
    if note_version is not None and note_version != version:
        print(
            f"FAIL: newest release notes declare {note_version}, "
            f"package metadata says {version}"
        )
        return 1

    for tag in _head_version_tags():
        if tag.removeprefix("v") != version:
            print(f"FAIL: tag {tag} at HEAD, package metadata says {version}")
            return 1

    from packaging.version import Version  # noqa: PLC0415 — heavy import kept lazy

    if not Version(version).is_prerelease:
        print(f"FAIL: {version} is not a prerelease while the RC line is open")
        return 1

    tag_summary = ",".join(_head_version_tags()) or "none"
    print(
        f"ok — package {version}, notes {note_version or 'none'}, "
        f"version tags at HEAD: {tag_summary}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
