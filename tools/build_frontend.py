"""Build the React SPA and commit the bundle into the Python package
(ADR-0013 decision 2).

The workstation serves the compiled bundle from the package itself
(``src/quantmesh/api/static/app/``) — no node runtime at serve time.
Run this from the repository root whenever ``frontend/`` sources
change, then commit the copied bundle.

``--check`` rebuilds into a temporary directory and refuses when the
result differs from the committed bundle — the CI stale-check the
release gate runs in Phase E.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = REPO_ROOT / "frontend"
DIST_DIR = FRONTEND_DIR / "dist"
BUNDLE_DIR = REPO_ROOT / "src" / "quantmesh" / "api" / "static" / "app"


def _npm_build() -> None:
    """npm run build in frontend/; the npm.cmd resolution is Windows-only."""
    command = ["cmd", "/c", "npm", "run", "build"] if os.name == "nt" else ["npm", "run", "build"]
    subprocess.run(command, cwd=FRONTEND_DIR, check=True)


def _copy_to(dest: Path) -> None:
    shutil.copytree(DIST_DIR, dest, dirs_exist_ok=True)


def _tree_diff(left: Path, right: Path) -> list[str]:
    """Names that differ between two trees (missing, extra, or content)."""
    def index(root: Path) -> dict[str, bytes]:
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }

    lindex, rindex = index(left), index(right)
    names = []
    for name in sorted(set(lindex) | set(rindex)):
        if name not in lindex or name not in rindex or lindex[name] != rindex[name]:
            names.append(name)
    return names


def build() -> None:
    _npm_build()
    shutil.rmtree(BUNDLE_DIR, ignore_errors=True)
    _copy_to(BUNDLE_DIR)
    print(f"copied {DIST_DIR} -> {BUNDLE_DIR}")


def check() -> int:
    """Rebuild into a probe tree and compare against the committed bundle."""
    with tempfile.TemporaryDirectory(prefix="qm-frontend-") as tmp:
        probe = Path(tmp) / "probe"
        _npm_build()
        _copy_to(probe)
        if not BUNDLE_DIR.is_dir():
            print(f"missing committed bundle at {BUNDLE_DIR} — run tools/build_frontend.py")
            return 1
        stale = _tree_diff(probe, BUNDLE_DIR)
    if stale:
        print("stale bundle — rebuild and commit the frontend output:")
        for name in stale:
            print(f"  {name}")
        return 1
    print("bundle is current")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="rebuild into a probe tree and refuse when it differs from the committed bundle",
    )
    args = parser.parse_args()
    if args.check:
        return check()
    build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
