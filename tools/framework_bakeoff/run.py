"""Command-line entry point for isolated framework bake-offs."""

from __future__ import annotations

import argparse
from pathlib import Path

from .finrl_x import run_finrl_x, write_evidence
from .fixture import build_nvda_fixture

_REPOSITORY_ROOT = Path(__file__).parents[2]
_DEFAULT_EVIDENCE = _REPOSITORY_ROOT / "docs" / "evidence" / "0020" / "finrl-x-run.json"
_DATASET = "bakeoff-moomoo-nvda"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("framework", choices=("finrl-x",))
    parser.add_argument("--lake-root", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--evidence-path", type=Path, default=_DEFAULT_EVIDENCE)
    args = parser.parse_args(argv)

    manifest_path = args.lake_root / _DATASET / "manifest.json"
    if not manifest_path.is_file():
        build_nvda_fixture(args.lake_root)
    evidence = run_finrl_x(args.lake_root, args.work_root)
    write_evidence(args.evidence_path, evidence)
    print(evidence.model_dump_json(indent=2))
    return 0 if evidence.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
