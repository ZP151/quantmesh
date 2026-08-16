"""Isolated entry point for one official Moomoo OpenD read-only bundle."""

from __future__ import annotations

import json
import socket
import sys
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from quantmesh.data.moomoo_collection import (
    CollectionStatus,
    MoomooRawPayload,
    MoomooWorkerRequest,
    MoomooWorkerResult,
)
from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.moomoo.opend import (
    MoomooOpenDClient,
    OpenDAuthRequiredError,
    OpenDProtocolError,
    OpenDSdkMissingError,
    OpenDUnavailableError,
)
from quantmesh.moomoo.provider import MoomooOpenDProvider
from quantmesh.settings import Settings

_SDK_VERSION = "10.10.7008"


def _unavailable(reason_code: str, detail: str) -> MoomooWorkerResult:
    return MoomooWorkerResult(
        status=CollectionStatus.UNAVAILABLE,
        reason_code=reason_code,
        detail=detail,
    )


def _opend_reachable(host: str, port: int, timeout_seconds: float) -> bool:
    """Return whether the local read-only OpenD TCP endpoint accepts a connection."""
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return True
    except OSError:
        return False


def collect(request: MoomooWorkerRequest) -> MoomooWorkerResult:
    """Collect one complete target bundle; never publish or write outside staging."""
    try:
        installed = version("moomoo-api")
    except PackageNotFoundError:
        return _unavailable("sdk-missing", "the audited Moomoo SDK is not installed")
    if installed != _SDK_VERSION:
        return _unavailable(
            "sdk-incompatible",
            f"the Moomoo SDK must be exactly {_SDK_VERSION}",
        )
    if not _opend_reachable(
        request.host,
        request.port,
        request.connect_timeout_seconds,
    ):
        return _unavailable("daemon-unavailable", "local OpenD is unavailable")

    settings = Settings(
        moomoo_opend_host=request.host,
        moomoo_opend_port=request.port,
        moomoo_opend_connect_timeout_s=request.connect_timeout_seconds,
        moomoo_opend_request_timeout_s=request.request_timeout_seconds,
    )
    market, symbol = request.target.provider_symbol.split(".", maxsplit=1)
    instrument = Instrument(
        symbol=symbol,
        venue=Venue.MOOMOO,
        instrument_type=InstrumentType.EQUITY,
        currency="USD",
        metadata={"market": market},
    )
    provider = MoomooOpenDProvider(MoomooOpenDClient.from_settings(settings))
    try:
        bundle = provider.fetch_raw_bundle(
            instrument,
            interval=request.target.interval,
            start=request.window.start,
            end=request.window.end,
        )
    except OpenDSdkMissingError:
        return _unavailable("sdk-missing", "the audited Moomoo SDK is not importable")
    except OpenDAuthRequiredError:
        return _unavailable(
            "entitlement-unavailable",
            "OpenD did not authorize the requested read-only market data",
        )
    except OpenDUnavailableError:
        return _unavailable("daemon-unavailable", "local OpenD is unavailable")
    except OpenDProtocolError:
        return MoomooWorkerResult(
            status=CollectionStatus.FAILED,
            reason_code="protocol-invalid",
            detail="OpenD returned untrusted source data",
        )
    finally:
        provider.close()

    received_at = datetime.now(UTC)
    payload = MoomooRawPayload(
        provider_version=installed,
        received_at=received_at,
        bars=bundle.bars,
        history_pages=bundle.history_pages,
        adjustment_factors=bundle.adjustment_factors,
        stock_split_pages=bundle.stock_split_pages,
        dividends=bundle.dividends,
    )
    payload.validate_for(request)
    return MoomooWorkerResult(status=CollectionStatus.PUBLISHED, payload=payload)


def main() -> int:
    if len(sys.argv) != 3:
        return 2
    request_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    try:
        request = MoomooWorkerRequest.model_validate_json(
            request_path.read_text(encoding="utf-8")
        )
        result = collect(request)
        output_path.write_text(
            json.dumps(result.model_dump(mode="json"), sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
    except Exception:  # noqa: BLE001 - parent sees only a typed nonzero worker failure
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
