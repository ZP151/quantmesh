"""Offline fixture submit/status entry point; never starts computation or export."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quantmesh.research.job_store import SQLiteJobStore  # noqa: E402
from quantmesh.research.jobs import (  # noqa: E402
    DatasetRejected,
    IdempotencyConflict,
    ResearchJobRequest,
    StoreUnavailable,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    submit = commands.add_parser("submit")
    submit.add_argument("--request", type=Path, required=True)
    submit.add_argument("--key", required=True)
    status = commands.add_parser("status")
    status.add_argument("--job-id", required=True)
    for command in (submit, status):
        command.add_argument("--store", type=Path, required=True)
        command.add_argument("--lake-root", type=Path)
        command.add_argument("--operator-id", default="local")
    args = parser.parse_args(argv)
    try:
        # Validate user JSON before constructing/mutating the store.
        request = (
            ResearchJobRequest.model_validate_json(args.request.read_bytes())
            if args.command == "submit"
            else None
        )
        store = SQLiteJobStore(args.store, lake_root=args.lake_root)
        result = (
            store.submit(args.operator_id, args.key, request)
            if request is not None
            else store.get(args.operator_id, args.job_id)
        )
        print(result.model_dump_json())
        return 0
    except IdempotencyConflict:
        code, exit_code = "idempotency_conflict", 3
    except DatasetRejected as exc:
        code, exit_code = exc.reason, 4
    except StoreUnavailable:
        code, exit_code = "store_unavailable", 5
    except KeyError:
        code, exit_code = "job_not_found", 6
    except (ValueError, OSError):
        code, exit_code = "invalid_request", 2
    print(json.dumps({"error_code": code}), file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
