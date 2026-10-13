"""Prepare one new owned build context; never pull/build/run or alter Docker.

Run with PYTHONDONTWRITEBYTECODE=1 python -B. The operator separately admits
the exact pinned upstream bytes and the derived immutable image.
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path


def prepare(output: Path) -> dict:
    if not sys.dont_write_bytecode or os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
        raise ValueError("bytecode_policy_required")
    if not output.is_absolute():
        raise ValueError("absolute_owned_output_required")
    for part in (output, *output.parents):
        if part.is_symlink():
            raise ValueError("symlink_output_refused")
    source = Path(__file__).resolve().parent
    repo = source.parents[1]
    output.mkdir(exist_ok=False)
    for name in ("Dockerfile", "curate.py", "base-file-sha256.json"):
        shutil.copyfile(source / name, output / name)
    shutil.copytree(source / "licenses", output / "licenses")
    shutil.copyfile(
        repo / "src/quantmesh/research/linux_bootstrap.py", output / "linux_bootstrap.py"
    )
    files = [
        {
            "path": p.relative_to(output).as_posix(),
            "bytes": p.stat().st_size,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        }
        for p in sorted(output.rglob("*"))
        if p.is_file()
    ]
    return {
        "scope": "Task1 stdlib fixture only",
        "files": files,
        "context_bytes": sum(p["bytes"] for p in files),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(prepare(parser.parse_args().output), indent=2))
