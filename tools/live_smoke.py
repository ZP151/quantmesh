"""Opt-in periodic live read-only smoke drill (iteration 0015 Phase G).

Checks a RUNNING local live-read-only workstation over plain HTTP
GETs — it never writes, never posts, and has no code path that could
touch an order, watchlist or settings endpoint. The drill is opt-in:
``--url`` must point at the operator's own station (default
``http://127.0.0.1:8766``), and ``--period-minutes`` turns a single
run into a periodic loop for scheduled smoke checks.

Every check is timeout-bounded and reported honestly — ``[PASS]`` /
``[FAIL] label — detail`` — and the exit code is non-zero if any
check failed, so a scheduler sees the drill's real outcome. The
surface contract drilled is the feed's own honesty ladder: state
labels and provenance values come from the five documented states,
connector sources from the six documented states, a venue's
``connected`` flag agrees with its sources, and every instrument the
operator explicitly names in ``--watchlist`` must be present in the
latest-state surface. A station without an attached live feed fails
the drill with the server's own "no live feed is attached" detail —
never a pass from an empty surface.

Run with the release extras installed, from the repository root:
``python tools/live_smoke.py``. The checker functions take an
injected HTTP getter, so the drill suite drives every branch without
the network.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import datetime

HOST = "127.0.0.1"
DEFAULT_URL = f"http://{HOST}:8766"
DEFAULT_TIMEOUT = 10.0  # seconds, per HTTP GET

LABELS = {"real", "delayed", "stale", "synthetic", "unavailable"}
PROVENANCES = {"real", "delayed", "synthetic", "unavailable"}
KINDS = {"quote", "trade", "candle", "l2_snapshot", "l2_delta", "metrics", "status"}
SOURCE_STATES = {"connected", "lagging", "stale", "disconnected", "unavailable"}
_LIVE_STATES = {"connected", "lagging"}  # matches feed._LIVE_STATES

Getter = Callable[[str, float], str]


def _timezone_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def http_get(url: str, timeout: float) -> str:
    """One GET; raises on any non-200 (the drill's only HTTP verb)."""
    with urllib.request.urlopen(url, timeout=timeout) as response:
        if response.status != 200:
            raise AssertionError(f"HTTP {response.status}")
        return response.read().decode("utf-8")


class SmokeCheck:
    """One drilled claim: label, whether it held, and why not."""

    def __init__(self, label: str, ok: bool, detail: str = "") -> None:
        self.label = label
        self.ok = ok
        self.detail = detail

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"SmokeCheck({self.label!r}, {self.ok!r}, {self.detail!r})"


def _json_get(getter: Getter, url: str, path: str, timeout: float) -> dict:
    body = getter(url + path, timeout)
    try:
        data = json.loads(body)
    except (ValueError, TypeError) as error:
        raise ValueError(f"{path}: response is not JSON: {error}") from error
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object, got {type(data).__name__}")
    return data


def _kind_errors(kind: object) -> list[str]:
    """The contract checks for one latest-state kind view."""
    errors: list[str] = []
    if not isinstance(kind, dict):
        return ["kind view is not an object"]
    if kind.get("kind") not in KINDS:
        errors.append(f"kind {kind.get('kind')!r} outside the contract")
    if kind.get("provenance") not in PROVENANCES:
        errors.append(f"provenance {kind.get('provenance')!r} outside the contract")
    if kind.get("label") not in LABELS:
        errors.append(f"label {kind.get('label')!r} outside the contract")
    sequence = kind.get("sequence")
    if sequence is not None and (not isinstance(sequence, int) or sequence < 0):
        errors.append(f"sequence {sequence!r} is not a non-negative int or null")
    if not isinstance(kind.get("sequence_gap"), bool):
        errors.append("sequence_gap is not a boolean")
    age = kind.get("age_ms")
    if not isinstance(age, int) or age < 0:
        errors.append(f"age_ms {age!r} is not a non-negative int")
    for field in ("data_time", "received_at"):
        if not _timezone_timestamp(kind.get(field)):
            errors.append(f"{field} is not a timezone-aware timestamp")
    if not isinstance(kind.get("payload"), dict):
        errors.append("payload is not an object")
    return errors


def check_state(getter: Getter, url: str, timeout: float) -> list[SmokeCheck]:
    """``/live/state``: every instrument's badge and every kind view
    stays inside the documented honesty ladder."""
    checks: list[SmokeCheck] = []
    try:
        data = _json_get(getter, url, "/live/state", timeout)
    except (urllib.error.URLError, OSError, ValueError, AssertionError) as error:
        return [SmokeCheck("latest-state surface answers", False, str(error))]
    instruments = data.get("instruments")
    if not isinstance(instruments, dict):
        return [SmokeCheck("latest-state instruments present", False, "missing instruments")]
    checks.append(SmokeCheck("latest-state instruments present", True))
    if not _timezone_timestamp(data.get("generated_at")):
        checks.append(
            SmokeCheck(
                "latest-state generation time is valid",
                False,
                "generated_at is not a timezone-aware timestamp",
            )
        )
    for instrument, entry in sorted(instruments.items()):
        prefix = f"instrument {instrument}"
        if not isinstance(entry, dict):
            checks.append(SmokeCheck(f"{prefix} is an object", False))
            continue
        badge = entry.get("label")
        venue = entry.get("venue")
        if not isinstance(venue, str) or not venue.strip():
            checks.append(SmokeCheck(f"{prefix} venue is present", False))
        if badge not in LABELS:
            checks.append(
                SmokeCheck(
                    f"{prefix} badge is honest", False, f"label {badge!r} outside the ladder"
                )
            )
        kinds = entry.get("kinds")
        if not isinstance(kinds, dict):
            checks.append(SmokeCheck(f"{prefix} has kinds", False))
            continue
        if badge != "unavailable" and not kinds:
            checks.append(
                SmokeCheck(
                    f"{prefix} has market data",
                    False,
                    f"label {badge!r} cannot have empty kinds",
                )
            )
        for kind_name, kind in kinds.items():
            if isinstance(kind, dict) and kind.get("kind") != kind_name:
                checks.append(
                    SmokeCheck(
                        f"{prefix} {kind_name} view is honest",
                        False,
                        f"map key {kind_name!r} disagrees with kind {kind.get('kind')!r}",
                    )
                )
            for error in _kind_errors(kind):
                checks.append(
                    SmokeCheck(f"{prefix} {kind_name} view is honest", False, error)
                )
        # a badge outside the honest ladder already failed above; only
        # claim honesty for instruments whose badge is one of the five
        if badge in LABELS:
            checks.append(SmokeCheck(f"{prefix} badge is honest", True))
    if not instruments:
        checks.append(
            SmokeCheck("latest-state surface is non-empty", False, "no instruments reported")
        )
    else:
        checks.append(SmokeCheck("latest-state surface is non-empty", True))
    return checks


def check_status(getter: Getter, url: str, timeout: float) -> list[SmokeCheck]:
    """``/live/status``: connector states stay in the ladder and each
    venue's ``connected`` flag agrees with its sources."""
    checks: list[SmokeCheck] = []
    try:
        data = _json_get(getter, url, "/live/status", timeout)
    except (urllib.error.URLError, OSError, ValueError, AssertionError) as error:
        return [SmokeCheck("connector-health surface answers", False, str(error))]
    venues = data.get("venues")
    if not isinstance(venues, list):
        return [SmokeCheck("connector-health venues present", False, "missing venues")]
    checks.append(SmokeCheck("connector-health venues present", True))
    if not venues:
        checks.append(
            SmokeCheck("connector-health surface is non-empty", False, "no venues reported")
        )
    if not _timezone_timestamp(data.get("generated_at")):
        checks.append(
            SmokeCheck(
                "connector-health generation time is valid",
                False,
                "generated_at is not a timezone-aware timestamp",
            )
        )
    for venue in venues:
        if not isinstance(venue, dict):
            checks.append(SmokeCheck("venue row is an object", False))
            continue
        name = venue.get("venue", "?")
        prefix = f"venue {name}"
        if not isinstance(name, str) or not name.strip():
            checks.append(SmokeCheck("venue name is present", False))
        connected = venue.get("connected")
        if not isinstance(connected, bool):
            checks.append(SmokeCheck(f"{prefix} connected flag is a boolean", False))
        sources = venue.get("sources")
        if not isinstance(sources, list):
            checks.append(SmokeCheck(f"{prefix} sources are listed", False))
            continue
        live_sources = 0
        for source in sources:
            if not isinstance(source, dict):
                checks.append(SmokeCheck(f"{prefix} source row is an object", False))
                continue
            instrument = source.get("instrument", "?")
            if not isinstance(instrument, str) or not instrument.strip():
                checks.append(SmokeCheck(f"{prefix} source instrument is present", False))
            state = source.get("state")
            if state not in SOURCE_STATES:
                checks.append(
                    SmokeCheck(
                        f"{prefix} {instrument} state is honest",
                        False,
                        f"state {state!r} outside the ladder",
                    )
                )
            if state in _LIVE_STATES:
                live_sources += 1
            age = source.get("age_ms")
            if age is not None and (not isinstance(age, int) or age < 0):
                checks.append(
                    SmokeCheck(f"{prefix} {instrument} age is honest", False, f"age_ms {age!r}")
                )
            for field in ("data_time", "received_at"):
                timestamp = source.get(field)
                if timestamp is not None and not _timezone_timestamp(timestamp):
                    checks.append(
                        SmokeCheck(
                            f"{prefix} {instrument} {field} is valid",
                            False,
                            "not a timezone-aware timestamp",
                        )
                    )
        if isinstance(connected, bool) and connected != (live_sources > 0):
            checks.append(
                SmokeCheck(
                    f"{prefix} connected flag agrees with its sources",
                    False,
                    f"connected={connected} with {live_sources} live sources",
                )
            )
        elif isinstance(connected, bool):
            checks.append(SmokeCheck(f"{prefix} connected flag agrees with its sources", True))
    return checks


def check_health(getter: Getter, url: str, timeout: float) -> list[SmokeCheck]:
    """``/health`` answers with versioned JSON (the read-only station
    is up and serving the SPA contract)."""
    try:
        data = _json_get(getter, url, "/health", timeout)
    except (urllib.error.URLError, OSError, ValueError, AssertionError) as error:
        return [SmokeCheck("health answers", False, str(error))]
    if data.get("status") != "ok":
        return [
            SmokeCheck(
                "health reports ok", False, f"status {data.get('status')!r}"
            )
        ]
    version = data.get("version")
    if not isinstance(version, str) or not version:
        return [SmokeCheck("health reports a version", False, f"version {version!r}")]
    return [
        SmokeCheck("health answers", True),
        SmokeCheck("health reports ok", True),
        SmokeCheck("health reports a version", True),
    ]


def check_watchlist(
    getter: Getter, url: str, timeout: float, watchlist: list[str]
) -> list[SmokeCheck]:
    """Every instrument the operator explicitly names is present in
    the latest-state surface (fail-closed: the drill never passes an
    empty or partial surface the operator expected to see)."""
    if not watchlist:
        return []
    try:
        data = _json_get(getter, url, "/live/state", timeout)
    except (urllib.error.URLError, OSError, ValueError, AssertionError) as error:
        return [SmokeCheck("watchlist present in the surface", False, str(error))]
    instruments = data.get("instruments")
    present = set(instruments) if isinstance(instruments, dict) else set()
    checks: list[SmokeCheck] = []
    for instrument in watchlist:
        checks.append(
            SmokeCheck(
                f"watchlist instrument {instrument} present",
                instrument in present,
                f"absent (surface reports: {sorted(present)})" if instrument not in present else "",
            )
        )
    return checks


def run_once(getter: Getter, url: str, timeout: float, watchlist: list[str]) -> list[SmokeCheck]:
    """Run every check once against the station; used by the CLI and
    by the drill suite."""
    return [
        *check_health(getter, url, timeout),
        *check_state(getter, url, timeout),
        *check_status(getter, url, timeout),
        *check_watchlist(getter, url, timeout, watchlist),
    ]


def _print_checks(checks: list[SmokeCheck]) -> None:
    for check in checks:
        status = "PASS" if check.ok else "FAIL"
        detail = f" — {check.detail}" if not check.ok and check.detail else ""
        print(f"[{status}] {check.label}{detail}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Opt-in live read-only smoke drill for the local workstation"
    )
    parser.add_argument(
        "--url", default=DEFAULT_URL, help=f"station base URL (default {DEFAULT_URL})"
    )
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="seconds per GET")
    parser.add_argument(
        "--watchlist", default="", help="comma-separated instruments that must be present"
    )
    parser.add_argument(
        "--period-minutes",
        type=float,
        default=0.0,
        help="re-run every N minutes until a run fails (0 = run once)",
    )
    args = parser.parse_args()
    watchlist = [item.strip() for item in args.watchlist.split(",") if item.strip()]
    while True:
        started = time.monotonic()
        checks = run_once(http_get, args.url, args.timeout, watchlist)
        _print_checks(checks)
        failures = [check.label for check in checks if not check.ok]
        if failures:
            print(f"\nLIVE SMOKE FAILED: {len(failures)} of {len(checks)} checks", flush=True)
            return 1
        elapsed = time.monotonic() - started
        print(
            f"\nLIVE SMOKE PASSED: {len(checks)} checks in {elapsed:.1f}s "
            f"against {args.url} (read-only GETs only)",
            flush=True,
        )
        if args.period_minutes <= 0:
            return 0
        try:
            time.sleep(args.period_minutes * 60)
        except KeyboardInterrupt:
            print("\nLIVE SMOKE stopped by operator", flush=True)
            return 0


if __name__ == "__main__":
    sys.exit(main())
