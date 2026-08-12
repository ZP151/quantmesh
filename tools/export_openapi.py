"""Export the workstation OpenAPI document deterministically for code generation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from quantmesh.api.workstation import create_workstation_app
from quantmesh.execution.accounting import PaperAccount


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    app = create_workstation_app(
        account=PaperAccount(cash=100_000.0),
        host="127.0.0.1",
    )
    rendered = json.dumps(
        app.openapi(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    args.output.write_text(f"{rendered}\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
