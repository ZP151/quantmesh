"""Offline, redacted server topology/ingestion qualification.

Run ``python -m tools.server_market_inventory --input evidence.json``. The
input is curated nonsecret evidence, never vendor XML, account state or logs.
This tool neither connects nor modifies a gateway. Readiness cannot certify
collection and a tunnel listener cannot certify server-owned OpenD.
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from quantmesh.data.calendars import SessionPolicy
from quantmesh.live.session_freshness import evaluate_session_freshness


class MarketPathEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider: Literal["moomoo", "hyperliquid"]
    listener_owner: Literal["tailscaled", "sshd", "ssh", "OpenD", "FutuOpenD", "direct", "unknown"]
    upstream_location: Literal["windows", "personal_pc", "server", "unknown"]
    readiness: Literal["ready", "unavailable", "unknown"]
    last_source_time: datetime | None
    session_open: bool | None = None
    now: datetime
    provider_delay_seconds: int | None = None
    interval: str = "1m"
    source_kind: Literal["bar_end", "observation"] = "bar_end"


def classify_market_path(
    provider: str,
    listener_owner: str,
    upstream_location: str,
    readiness: str,
    last_source_time: datetime | None,
    session_open: bool | None,
    *,
    now: datetime | None = None,
    provider_delay_seconds: int | None = None,
    interval: str = "1m",
    source_kind: Literal["bar_end", "observation"] = "bar_end",
) -> dict[str, str]:
    """The calendar is authoritative; session_open is retained input evidence only."""
    gateway, dependency = "unknown", "unknown"
    if upstream_location in {"windows", "personal_pc"}:
        gateway, dependency = "personal_pc", "yes"
    elif upstream_location == "server" and (
        (provider == "moomoo" and listener_owner in {"OpenD", "FutuOpenD"})
        or (provider == "hyperliquid" and listener_owner == "direct")
    ):
        gateway, dependency = "server", "no"
    calendar_id = {"moomoo": "XNYS", "hyperliquid": "24/7"}.get(provider, "unknown")
    policy = SessionPolicy.CONTINUOUS if calendar_id == "24/7" else SessionPolicy.REGULAR
    freshness = evaluate_session_freshness(
        calendar_id,
        policy,
        now if now is not None else datetime.now(UTC),
        last_source_time,
        interval,
        provider_delay_seconds,
        source_kind=source_kind,
    )
    ingestion = {"delayed": "stale"}.get(freshness.data_state, freshness.data_state)
    return {
        "gateway_location": gateway,
        "pc_dependency": dependency,
        "readiness": readiness if readiness in {"ready", "unavailable"} else "unknown",
        "ingestion": ingestion,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    try:
        evidence = MarketPathEvidence.model_validate_json(args.input.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        # Validation details can contain raw input. Never print them.
        parser.exit(2, "invalid curated market-path evidence\n")
    print(json.dumps(classify_market_path(**evidence.model_dump()), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
