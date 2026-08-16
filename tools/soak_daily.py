"""Daily soak driver: collect fresh crypto + latest Moomoo session, then observe.

One UTC-day observation per invocation. Re-running the same UTC day is
idempotent at the data layer (collect reuses existing manifests); a duplicate
observe for the same day is reported but returns success so a scheduler retry
does not flap. Exit 0 when today's report exists, non-zero on a real failure.

Usage (Windows Task Scheduler — one run per UTC day):

    .\\.venv\\Scripts\\python.exe tools\\soak_daily.py ^
        --repo C:\\Users\\...\\QuantMesh-0021-finalize ^
        --data-root C:\\QuantMesh\\trusted-data ^
        --evidence-root C:\\QuantMesh\\trusted-data-evidence
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

_CRYPTO_AGE_MINUTES = 7  # collect a window this far in the past (past the 5m grace)


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(item) for item in command],
        cwd=cwd,
        text=True,
        capture_output=True,
    )


def _crypto_window(now: datetime, *, minutes: int = 30) -> str:
    end = (now - timedelta(minutes=_CRYPTO_AGE_MINUTES)).replace(second=0, microsecond=0)
    start = end - timedelta(minutes=minutes)
    return f"{start:%Y-%m-%dT%H:%M:%S}Z/{end:%Y-%m-%dT%H:%M:%S}Z"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True, help="clean 0021 checkout")
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    args = parser.parse_args(argv)

    python = args.repo / ".venv" / "Scripts" / "python.exe"
    now = datetime.now(UTC)
    cycle = f"daily-{now.date().isoformat()}"

    crypto = _run(
        [
            python, "-m", "quantmesh.data.cli", "collect",
            "--provider", "hyperliquid", "--root", str(args.data_root),
            "--symbols", "BTC,ETH,SOL", "--interval", "1m",
            "--window", _crypto_window(now), "--collection-cycle", cycle,
        ],
        cwd=args.repo,
    )
    if crypto.returncode != 0:
        print(f"crypto collect failed: {crypto.stderr.strip()}", file=sys.stderr)
        return crypto.returncode

    moomoo_window = (
        f"{(now - timedelta(days=7)).date()}T00:00:00Z/{now.date()}T00:00:00Z"
    )
    moomoo = _run(
        [
            python, "-m", "quantmesh.data.cli", "collect",
            "--provider", "moomoo", "--root", str(args.data_root),
            "--symbols", "AAPL,NVDA", "--interval", "1d",
            "--window", moomoo_window, "--collection-cycle", cycle,
        ],
        cwd=args.repo,
    )
    if moomoo.returncode != 0:
        print(f"moomoo collect failed: {moomoo.stderr.strip()}", file=sys.stderr)
        return moomoo.returncode

    observe = _run(
        [
            python, str(args.repo / "tools" / "trusted_data_soak.py"),
            "observe", "--data-root", str(args.data_root),
            "--evidence-root", str(args.evidence_root),
        ],
        cwd=args.repo,
    )
    output = (observe.stdout or "").strip()
    print(output)
    if observe.returncode != 0:
        message = (observe.stderr or "").strip()
        if "UTC day" in message:
            # Today's report already exists; not an error for a scheduler retry.
            return 0
        print(message, file=sys.stderr)
        return observe.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
