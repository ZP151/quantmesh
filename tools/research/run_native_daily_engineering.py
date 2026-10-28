"""Run a closed synthetic native-daily-v2 case; no real-data or trading option."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from quantmesh.data.objects import ObjectStore  # noqa: E402
from quantmesh.research import native_daily_candidate as candidate  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--case", choices=candidate.CASES, default="campaign-v1")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--output-root", type=Path, help="Optional owned original-artifact store")
    args = parser.parse_args(argv)
    value = candidate.engineering_input(args.case)
    protocol = candidate.freeze_protocol(value)
    try:
        if args.output_root is not None:
            store = ObjectStore(args.output_root)
            ref = candidate.publish(value, protocol, store)
            raw = candidate.read_result(store, ref)
            result = json.loads(raw)
        else:
            ref = None
            result = candidate.evaluate(value, protocol)
    except (ValueError, OSError) as error:
        parser.error(f"Engineering run refused: {error}")
    if args.format == "json":
        print(candidate.canonical(result).decode())
    else:
        print("SYNTHETIC ENGINEERING ONLY | native-daily-v2")
        print(f"case={args.case} protocol={result['request_digest']}")
        print("INSUFFICIENT | real-input disabled | no Paper/live authority")
        for scenario, arms in result["calculation"].items():
            for arm, row in arms.items():
                metrics = row["metrics"]
                print(
                    f"{scenario:8} {arm:4} simulated_terminal={metrics['terminal_equity']:.8f} "
                    f"fees={metrics['friction_usd']:.8f} buys={metrics['buy_fill_count']} "
                    f"receivable={metrics['terminal_receivable']:.8f}"
                )
        if ref is not None:
            print("original_result_ref=" + candidate.canonical(ref.model_dump()).decode())
        print(
            "All prices/events are constructed; these numbers are not empirical investment results."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
