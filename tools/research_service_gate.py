"""Separate service gate. Default acceptance requires real disposable PostgreSQL.

Run using the service's locked venv. --offline proves only scripted/local API
boundaries and must never be reported as PostgreSQL/service acceptance.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as md
import json
import os
import re
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "services" / "research_agent"
SCHEMA = "a645a8bde2b439587f736a6a6875e4ffae77265cdcc2900d0b2def43f5f0de18"
PROTOCOL = "454cce6bd355465e48a59cb61fbbacb775776cb28c41826e54aff554cf2ccae1"


def normalize(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def read_lock(path: Path) -> dict[str, str]:
    content = path.read_text(encoding="utf-8")
    pins = {}
    for block in re.split(r"\n(?=[\w.-]+==)", content):
        match = re.search(r"^([\w.-]+)==([\w.+-]+)", block, re.M)
        if not match:
            continue
        name, version = match.groups()
        name = normalize(name)
        if name in pins or not re.search(r"--hash=sha256:[0-9a-f]{64}(?:\s|$)", block):
            raise ValueError("lock requires unique hash-pinned packages")
        pins[name] = version
    if not pins or pins.get("pydantic") != "2.13.5":
        raise ValueError("qualified service lock required")
    return pins


def require_postgres_fixture(environment) -> bool:
    return environment.get("QM_TEST_DISPOSABLE_POSTGRES_ACK") == "owned-disposable" and bool(
        environment.get("QM_TEST_DISPOSABLE_POSTGRES_DSN")
    )


def license_inventory(pins):
    from tools.license_review import BUILD_TOOLING, classify

    installed = {normalize(d.metadata["Name"]): d for d in md.distributions()}
    failures, inventory = [], []
    for name, version in pins.items():
        dist = installed.get(name)
        if dist is None or dist.version != version:
            failures.append("locked distribution missing or mismatched: " + name)
            continue
        license_key = classify(dist)
        # scramp's exact wheel declares MIT No Attribution, a policy-allowed
        # license whose classifier the core parser does not recognize. This
        # service-owned exception is checked against the installed license bytes.
        if name == "scramp" and version == "1.4.17":
            path = dist.locate_file(next(f for f in dist.files if str(f).endswith("/LICENSE")))
            if (
                hashlib.sha256(path.read_bytes()).hexdigest()
                == "2429a638bd9df049495c9f153dc504c4c5c9fda5803d9f8843e21baf5d2b00a3"
            ):
                license_key = "MIT-0"
        if (
            name == "orjson"
            and version == "3.13.0"
            and dist.metadata.get("License-Expression") == "MPL-2.0 AND (Apache-2.0 OR MIT)"
        ):
            # Both applicable branches are in the repository policy. Select
            # Apache-2.0 under the exact upstream parenthesized expression.
            license_key = "MPL-2.0 AND Apache-2.0"
        inventory.append({"name": name, "version": version, "license": license_key})
        if license_key.startswith("UNKNOWN"):
            failures.append("unqualified license: " + name)
    extras = (
        set(installed)
        - set(pins)
        - {normalize(n) for n in BUILD_TOOLING}
        - {"quantmesh", "qm-research-agent"}
    )
    failures.extend("untracked installed distribution: " + name for name in sorted(extras))
    return inventory, failures


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--evidence-dir", type=Path, default=SERVICE / "evidence")
    args = parser.parse_args(argv)
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(SERVICE / "src")]
    pins = read_lock(SERVICE / "requirements.lock")
    inventory, failures = license_inventory(pins)
    from quantmesh.research.job_store import protocol_digest
    from quantmesh.research.jobs import schema_digest

    if schema_digest() != SCHEMA or protocol_digest() != PROTOCOL:
        failures.append("frozen contract mismatch")
    result = {
        "profile": "OFFLINE_SCRIPTED_ONLY" if args.offline else "POSTGRES_REQUIRED",
        "postgres": "pending",
        "licenses": inventory,
        "failures": failures,
        "lock_sha256": hashlib.sha256((SERVICE / "requirements.lock").read_bytes()).hexdigest(),
        "schema_digest": schema_digest(),
        "protocol_digest": protocol_digest(),
        "commands": [],
    }
    run_id = uuid.uuid4().hex
    junit = args.evidence_dir / ("pytest-" + run_id + ".xml")
    commands = [
        [sys.executable, "-m", "pip", "check"],
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            str(SERVICE / "src"),
            str(SERVICE / "tests"),
            str(SERVICE / "lock_service.py"),
            str(Path(__file__)),
        ],
        [
            sys.executable,
            "-m",
            "ruff",
            "format",
            "--check",
            str(SERVICE / "src"),
            str(SERVICE / "tests"),
            str(SERVICE / "lock_service.py"),
            str(Path(__file__)),
        ],
        [
            sys.executable,
            "-m",
            "pytest",
            "-c",
            str(SERVICE / "pyproject.toml"),
            str(SERVICE / "tests"),
            "-q",
            "--basetemp",
            str(args.evidence_dir / ("pytest-owned-" + run_id)),
            "--junitxml",
            str(junit),
        ],
        ["git", "diff", "--check"],
    ]
    if not failures:
        for i, command in enumerate(commands):
            log = args.evidence_dir / f"service-gate-{i}.log"
            with log.open("w", encoding="utf-8") as handle:
                completed = subprocess.run(
                    command, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT
                )
            result["commands"].append({"argv": command, "exit": completed.returncode})
            if completed.returncode:
                failures.append(f"gate command {i} failed; inspect {log.name}")
                break
    if junit.exists():
        suites = ET.parse(junit).getroot()
        counts = {
            key: sum(int(s.attrib.get(key, 0)) for s in suites.iter("testsuite"))
            for key in ("tests", "failures", "errors", "skipped")
        }
        result["tests"] = counts
        if not args.offline and require_postgres_fixture(os.environ) and counts["skipped"] == 0:
            result["postgres"] = "verified-disposable-tests"
    if not args.offline and result["postgres"] != "verified-disposable-tests":
        failures.append("real owned disposable PostgreSQL evidence pending")
    result["exit"] = 1 if failures else 0
    (args.evidence_dir / "service-gate.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "profile": result["profile"],
                "postgres": result["postgres"],
                "exit": result["exit"],
                "failures": failures,
                "tests": result.get("tests"),
            }
        )
    )
    return result["exit"]


if __name__ == "__main__":
    raise SystemExit(main())
