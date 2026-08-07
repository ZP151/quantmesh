"""``quantmesh-moomoo`` operator commands (issue #25, Phase A).

The probe command is the only way QuantMesh reaches a real local OpenD
instance, and it is an explicit operator action: it prints a redacted
capability report to stdout, writes nothing to disk, reads no
credentials, and exits with a typed status code. It must never be
invoked by ingestion, backtesting, or any default path.
"""

import argparse
import sys
from collections.abc import Sequence

from quantmesh.moomoo.opend import (
    MoomooOpenDClient,
    OpenDAuthRequiredError,
    OpenDSdkMissingError,
    OpenDUnavailableError,
)
from quantmesh.settings import Settings, settings

_EXIT_OK = 0
_EXIT_UNAVAILABLE = 1
_EXIT_AUTH_REQUIRED = 2
_EXIT_SDK_MISSING = 3


def _build_client(config: Settings) -> MoomooOpenDClient:
    return MoomooOpenDClient.from_settings(config)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="quantmesh-moomoo",
        description="Moomoo OpenD operator commands (fixture-first; probe is read-only).",
    )
    parser.add_argument("command", choices=["probe"], help="capability probe of a local OpenD")
    parser.parse_args(argv)

    client = _build_client(settings)
    try:
        caps = client.probe()
    except OpenDSdkMissingError as error:
        print(f"sdk missing: {error}", file=sys.stderr)
        return _EXIT_SDK_MISSING
    except OpenDAuthRequiredError as error:
        print(f"auth required: {error}", file=sys.stderr)
        return _EXIT_AUTH_REQUIRED
    except OpenDUnavailableError as error:
        print(f"opend unavailable: {error}", file=sys.stderr)
        return _EXIT_UNAVAILABLE
    finally:
        client.close()
    print(
        "OpenD capabilities: "
        f"quote={caps.quote} history_kline={caps.history_kline} "
        f"order={caps.order} order_query={caps.order_query} "
        f"auth_required={caps.auth_required}"
    )
    return _EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
