"""Isolated quote-only worker; stdout/stderr are discarded by its parent."""

import json
import sys
from pathlib import Path


def main() -> int:
    # Explicit script invocation binds imports to this exact checkout.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from quantmesh.moomoo.opend import MoomooOpenDClient, OpenDError, SdkTransport
    from quantmesh.moomoo.readiness import readiness_failure, run_readiness

    request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    client = MoomooOpenDClient(SdkTransport(
        host=request["host"], port=request["port"],
        connect_timeout_s=request["connect_timeout_s"],
        request_timeout_s=request["request_timeout_s"],
    ))
    try:
        report = run_readiness(client, request["codes"]).as_dict()
    except (OpenDError, NotImplementedError) as error:
        status, detail = readiness_failure(error)
        report = {"status": status, "detail": detail, "order_checked": False, "symbols": []}
    finally:
        client.close()
    Path(sys.argv[2]).write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
