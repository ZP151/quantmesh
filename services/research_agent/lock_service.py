"""Add registry release hashes to pip-tools' resolved pins, without downloading
every platform wheel. Regeneration uses only official PyPI release metadata.
"""

import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent


def release(pin):
    name, version = pin
    with urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=30) as response:
        metadata = json.load(response)
    hashes = sorted({item["digests"]["sha256"] for item in metadata["urls"]})
    if not hashes:
        raise ValueError("release has no hashes")
    return (
        name
        + "=="
        + version
        + " \\\n"
        + " \\\n".join("    --hash=sha256:" + digest for digest in hashes)
    )


if __name__ == "__main__":
    pins = []
    for line in (ROOT / "requirements.pins").read_text().splitlines():
        match = re.fullmatch(r"([\w.-]+)(?:\[[\w,.-]+\])?==([^ ;]+)", line)
        if match:
            pins.append(match.groups())
    with ThreadPoolExecutor(6) as pool:
        requirements = list(pool.map(release, pins))
    lock = ROOT / "requirements.lock"
    lock.write_bytes(
        (
            "# Isolated CPython 3.13 Windows qualification; Linux certification pending.\n"
            "# Resolved by pip-tools; hashes from official PyPI release JSON.\n"
            + "\n".join(requirements)
            + "\n"
        ).encode("utf-8")
    )
    print(
        json.dumps(
            {"packages": len(pins), "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest()}
        )
    )
