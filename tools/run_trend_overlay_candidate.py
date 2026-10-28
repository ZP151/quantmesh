"""Inspect fixed synthetic policy cases, never market backtests or generated fills."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quantmesh.research.trend_overlay_trace import (  # noqa: E402
    CASES,
    _canonical,
    build_trace,
    render_text,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--case", choices=CASES, default="campaign")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    try:
        trace = build_trace(args.case)
    except ValueError as error:
        parser.error(f"Invalid fixed fixture: {error}")
    print(_canonical(trace).decode() if args.format == "json" else render_text(trace))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
