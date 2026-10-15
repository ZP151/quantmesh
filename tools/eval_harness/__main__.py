"""Run with: python -m tools.eval_harness --help."""

import argparse
import json
from pathlib import Path

from tools.eval_harness.core import compare, freeze_dataset
from tools.eval_harness.runner import HARNESS_ROOT, execute, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--repo", type=Path, default=HARNESS_ROOT)
    run.add_argument(
        "--dataset",
        "--catalog",
        type=Path,
        default=HARNESS_ROOT / "benchmarks/quantmesh_v2/dataset.json",
    )
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--timeout", type=float, default=120)
    run.add_argument("--intervention", action="append", default=[], metavar="TASK_ID")
    run.add_argument("--inject-known-bad", action="store_true")
    run.add_argument("--baseline", type=Path)
    freeze = sub.add_parser("freeze", help="pin reviewed sourced cases without executing them")
    freeze.add_argument("--cases", type=Path, required=True)
    freeze.add_argument("--output", type=Path, required=True)
    diff = sub.add_parser("compare")
    diff.add_argument("baseline", type=Path)
    diff.add_argument("candidate", type=Path)
    diff.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "freeze":
            if args.output.exists():
                raise FileExistsError("frozen catalog already exists; version migration required")
            seed = json.loads(args.cases.read_text(encoding="utf-8"))
            if len(seed["cases"]) != 24:
                raise ValueError("production benchmark requires 24 sourced cases")
            frozen = freeze_dataset(HARNESS_ROOT, seed["cases"])
            args.output.parent.mkdir(parents=True, exist_ok=True)
            write_json(args.output, frozen)
            return 0
        if args.command == "run":
            result = execute(
                args.repo,
                args.dataset,
                args.output,
                timeout=args.timeout,
                interventions=tuple(args.intervention),
                inject_known_bad=args.inject_known_bad,
            )
            if args.baseline:
                comparison = compare(json.loads(args.baseline.read_text(encoding="utf-8")), result)
                write_json(args.output / "comparison.json", comparison)
            return (
                0
                if (
                    result["status"] == "complete"
                    and all(r["status"] == "passed" for r in result["results"])
                )
                else 1
            )
        result = compare(
            json.loads(args.baseline.read_text(encoding="utf-8")),
            json.loads(args.candidate.read_text(encoding="utf-8")),
        )
        if args.output.exists():
            raise FileExistsError("comparison output already exists")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        write_json(args.output, result)
        print(
            json.dumps(
                {k: result[k] for k in ("regression_rate", "regressions", "improvements")}, indent=2
            )
        )
        return 1 if result["regressions"] else 0
    except (ValueError, OSError) as exc:
        parser.exit(2, f"eval refused: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
