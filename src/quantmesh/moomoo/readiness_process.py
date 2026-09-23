"""Whole-process deadline for a read-only OpenD readiness check."""

import math
import sys
import tempfile
from pathlib import Path

from quantmesh.data.collection_process import (
    CollectionProcessError,
    CollectionProcessTimeout,
    run_bounded_json_process,
)
from quantmesh.settings import Settings


def _worker_command() -> list[str]:
    # Use this checkout, even when another worktree owns the editable install.
    return [
        sys.executable, str(Path(__file__).with_name("readiness_worker.py")),
        "{request}", "{output}",
    ]


def run_readiness_process(
    config: Settings,
    codes: list[str],
    *,
    timeout_seconds: float = 30,
    scratch_root: Path | None = None,
) -> dict[str, object]:
    """Return a sanitized report; kill a stalled SDK worker and its children.

    Only non-secret connection settings cross the process boundary. Temporary
    files contain request metadata and a sanitized report, never quote rows or
    account data. The existing collection runner removes them on every path.
    """
    if not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 300:
        raise ValueError("readiness deadline must be finite and within (0, 300] seconds")
    request = {
        "host": config.moomoo_opend_host,
        "port": config.moomoo_opend_port,
        "connect_timeout_s": config.moomoo_opend_connect_timeout_s,
        "request_timeout_s": config.moomoo_opend_request_timeout_s,
        "codes": codes,
    }
    try:
        return run_bounded_json_process(
            _worker_command(), request=request, timeout_seconds=timeout_seconds,
            scratch_root=scratch_root if scratch_root is not None else Path(tempfile.gettempdir()),
        )
    except CollectionProcessTimeout:
        status, detail = "timeout", "OpenD readiness worker exceeded its deadline and was stopped"
    except CollectionProcessError:
        status, detail = "protocol_error", "OpenD readiness worker did not produce a valid report"
    return {"status": status, "detail": detail, "order_checked": False, "symbols": []}
