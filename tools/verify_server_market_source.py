"""Read-only Linux candidate witness. Evidence never certifies application cutover.

Run as ``python -m tools.verify_server_market_source`` from the checkout.
There is no saved-input, endpoint override, authentication or repair mode.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import multiprocessing
import os
import queue
import re
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

from deploy.aws.opend.validate_profile import VERSION, reviewed_configuration, validate_profile
from quantmesh.data.calendars import SessionPolicy
from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.instruments.contracts import HistoricalSeries, LiveTailLineage
from quantmesh.live.session_freshness import evaluate_session_freshness
from quantmesh.moomoo.market_data import MoomooDataAdapter
from quantmesh.moomoo.minute_candles import minute_candles
from quantmesh.moomoo.opend import MoomooOpenDClient, SdkTransport

ORIGIN = "https://quantmesh-staging-8gb.tail99d23c.ts.net"
SYMBOLS = ("AAPL", "NVDA")
MAX_BYTES = 2 * 1024 * 1024
DEADLINE_SECONDS = 240
SAMPLE_SPACING = 35
OHLCV = ("open", "high", "low", "close", "volume")
_SHA40 = re.compile(r"[0-9a-f]{40}\Z")


class WitnessError(Exception):
    """Only fixed diagnostic codes cross the operational boundary."""


def _utc() -> str:
    return datetime.now(UTC).isoformat()


def _clock(value: object) -> datetime:
    if not isinstance(value, str):
        raise WitnessError("unknown_source_clock")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise WitnessError("unknown_source_clock")
    return result.astimezone(UTC)


class _Proc:
    """Native procfs only. No command lines, environments or vendor state."""

    linux = sys.platform == "linux"

    def read(self, path: str) -> str:
        with (Path("/proc") / path).open("rb") as stream:
            value = stream.read(MAX_BYTES + 1)
        if len(value) > MAX_BYTES:
            raise WitnessError("proc_output_limit")
        return value.decode("ascii")

    def entries(self, path: str) -> list[str]:
        result = [item.name for item in (Path("/proc") / path).iterdir()]
        if len(result) > 65536:
            raise WitnessError("proc_output_limit")
        return result

    def link(self, path: str) -> str:
        return os.readlink(Path("/proc") / path)

    def executable_digest(self, pid: int) -> str:
        # /proc/PID/exe hashes the running inode, including replaced-on-disk files.
        with Path(f"/proc/{pid}/exe").open("rb") as stream:
            if os.fstat(stream.fileno()).st_size > 256 * 1024 * 1024:
                raise WitnessError("executable_output_limit")
            return hashlib.file_digest(stream, "sha256").hexdigest()

    def user_id(self, name: str) -> int:
        import pwd

        return pwd.getpwnam(name).pw_uid


def _start_ticks(stat: str) -> int:
    # comm may contain whitespace and ')' characters. Field22 follows final ')'.
    return int(stat.rsplit(")", 1)[1].split()[19])


def _identity_snapshot(profile: dict, proc: _Proc) -> dict:
    uid = proc.user_id(profile["runtime"]["user"])
    if type(uid) is not int or uid <= 0:
        raise WitnessError("gateway_uid_mismatch")
    listeners = []
    for table in ("net/tcp", "net/tcp6"):
        for line in proc.read(table).splitlines()[1:]:
            columns = line.split()
            address, port = columns[1].split(":")
            if columns[3] == "0A" and int(port, 16) == 11112:
                if table != "net/tcp" or address != "0100007F" or int(columns[7]) != uid:
                    raise WitnessError("gateway_listener_not_private_native")
                listeners.append(columns[9])
    if len(listeners) != 1 or not listeners[0].isdigit():
        raise WitnessError("gateway_listener_unproven")
    inode = listeners[0]
    owners = []
    for pid_text in proc.entries(""):
        if not pid_text.isdigit():
            continue
        for fd in proc.entries(f"{pid_text}/fd"):
            if proc.link(f"{pid_text}/fd/{fd}") == f"socket:[{inode}]":
                owners.append(int(pid_text))
                break
    if len(owners) != 1:
        raise WitnessError("gateway_socket_owner_unproven")
    pid = owners[0]
    ticks = _start_ticks(proc.read(f"{pid}/stat"))
    uid_lines = [
        line for line in proc.read(f"{pid}/status").splitlines() if line.startswith("Uid:")
    ]
    if len(uid_lines) != 1 or [int(x) for x in uid_lines[0].split()[1:]] != [uid] * 4:
        raise WitnessError("gateway_uid_mismatch")
    executable = proc.link(f"{pid}/exe")
    if executable != profile["runtime"]["executable"]:
        raise WitnessError("gateway_executable_mismatch")
    digest = proc.executable_digest(pid)
    if digest != profile["artifact"]["executable_sha256"]:
        raise WitnessError("gateway_digest_mismatch")
    boot = proc.read("sys/kernel/random/boot_id").strip()
    if not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", boot):
        raise WitnessError("gateway_boot_identity_unproven")
    return {
        "boot_id": boot,
        "pid": pid,
        "start_ticks": ticks,
        "uid": uid,
        "executable": executable,
        "executable_sha256": digest,
        "socket_inode": inode,
        "endpoint": "127.0.0.1:11112",
    }


def collect_gateway_identity(profile: dict, *, _proc: _Proc | None = None) -> dict:
    """Collect twice; fixtures are Python-test injection, never a CLI mode.

    An unreadable or disappearing PID/fd invalidates ownership. Run with a
    coordinator-approved proc reader privilege; do not weaken permissions here.
    """
    proc = _proc if _proc is not None else _Proc()
    try:
        validate_profile(profile, require_qualified=True, config_bytes=reviewed_configuration())
        if not proc.linux:
            raise WitnessError("native_linux_required")
        first = _identity_snapshot(profile, proc)
        if first != _identity_snapshot(profile, proc):
            raise WitnessError("gateway_identity_changed")
        return first | {"observed_at": _utc()}
    except WitnessError:
        raise
    except (OSError, ValueError, KeyError, IndexError, UnicodeError):
        raise WitnessError("native_identity_unavailable") from None


def _same_identity(first: dict, second: dict) -> bool:
    return {k: v for k, v in first.items() if k != "observed_at"} == {
        k: v for k, v in second.items() if k != "observed_at"
    }


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _read_json_response(response) -> dict:
    if response.status != 200:
        raise WitnessError("application_http_unavailable")
    raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise WitnessError("output_limit")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise WitnessError("application_schema_invalid")
    return value


def _http_json(path: str) -> dict:
    allowed = {"/api/health", "/api/live/state"} | {
        f"/api/instruments/moomoo/{symbol}/history?range=1d" for symbol in SYMBOLS
    }
    if path not in allowed:
        raise WitnessError("application_endpoint_not_admitted")
    # Ignore ambient proxy settings; a redirect never supplies a new destination.
    opener = build_opener(ProxyHandler({}), _NoRedirect())
    with opener.open(ORIGIN + path, timeout=5) as response:
        return _read_json_response(response)


def _instrument(symbol: str) -> Instrument:
    return Instrument(
        symbol=symbol,
        venue=Venue.MOOMOO,
        instrument_type=InstrumentType.EQUITY,
        metadata={"market": "US"},
    )


def _health(value: dict, expected: str) -> dict:
    build = value.get("deployment", {}).get("build_ref", value.get("build_ref"))
    if (
        build != expected
        or value.get("paper_mode") is not True
        or value.get("live_trading") is not False
        or value.get("runtime_mode") != "live"
    ):
        raise WitnessError("application_build_or_safety_mismatch")
    return {"build_ref": build, "paper_mode": True, "live_trading": False, "runtime_mode": "live"}


def _provider(client: MoomooOpenDClient) -> dict:
    result = {}
    for symbol in SYMBOLS:
        instrument = _instrument(symbol)
        quote_payload = client.stock_quote([f"US.{symbol}"])
        row = quote_payload["rows"][0]
        if not row.get("data_time"):
            raise WitnessError("unknown_source_clock")
        quote = MoomooDataAdapter().stock_quote_to_quote(instrument, quote_payload)
        payload = client.current_kline(f"US.{symbol}", num=390)
        # Validate first, then retain only the admitted raw normalization fields.
        minute_candles(instrument, payload)
        result[symbol] = {
            "quote_at": quote.timestamp.isoformat(),
            "bars": {k: payload[k] for k in ("code", "interval", "autype", "session")}
            | {
                "rows": [
                    {k: row[k] for k in ("code", "time_key", *OHLCV)} for row in payload["rows"]
                ]
            },
        }
    return result


def _application(state: dict, history: dict, symbol: str) -> dict:
    # History is strictly validated using the existing API contract; no account
    # endpoint or workspace/risk/positions/proposals snapshot is requested.
    series = HistoricalSeries.model_validate_json(json.dumps(history["primary"]))
    entry = state["instruments"][f"moomoo:{symbol}"]
    if entry["venue"] != "moomoo" or entry["instrument"] != symbol:
        raise WitnessError("application_identity_mismatch")
    kinds = entry["kinds"]
    if any(kind in kinds for kind in ("quote", "l2_snapshot", "l2_delta")):
        raise WitnessError("application_depth_present")
    metric = kinds["metrics"]
    payload = metric["payload"]
    if any(payload.get(k) is not None for k in ("bid", "ask")):
        raise WitnessError("application_depth_present")
    if kinds.get("status", {}).get("label") == "unavailable":
        raise WitnessError("application_source_unavailable")
    # Fixed enum values/numbers/clocks only. Vendor reason and free-text metadata
    # never enter archived evidence, even in an otherwise valid API response.
    live = {
        "status": "degraded",
        "bid": None,
        "ask": None,
        "last": payload["last"],
        "source": "moomoo",
        "provenance": metric["provenance"],
        "data_time": metric["data_time"],
        "received_at": metric["received_at"],
    }
    return {
        "symbol": series.instrument.symbol,
        "venue": series.instrument.venue.value,
        "interval": series.interval,
        "calendar": series.calendar,
        "adjustment": series.adjustment,
        "license": series.license,
        "source": series.source,
        "bars": [
            {
                "timestamp": bar.timestamp.isoformat(),
                "interval": bar.interval,
                **{k: getattr(bar, k) for k in OHLCV},
                "is_live_tail": bar.is_live_tail,
                "live_lineage": bar.live_lineage.model_dump(mode="json")
                if bar.live_lineage
                else None,
            }
            for bar in series.bars
        ],
        "live": live,
        "proposal_allowed": None,
        "provider_delay_seconds": entry["session_freshness"]["provider_delay_seconds"],
    }


def _quiet_child() -> None:
    # The vendor may print before raising. Suppress both Python and native fd IO.
    with open(os.devnull, "w") as sink:
        os.dup2(sink.fileno(), 1)
        os.dup2(sink.fileno(), 2)
    sys.stdout = open(os.devnull, "w")
    sys.stderr = open(os.devnull, "w")


def _sample_child(connection, expected_build: str) -> None:
    _quiet_child()
    try:
        if importlib.metadata.version("moomoo-api") != VERSION:
            raise WitnessError("sdk_version_mismatch")
        client = MoomooOpenDClient(
            SdkTransport(host="127.0.0.1", port=11112, connect_timeout_s=3, request_timeout_s=5)
        )
        before = _provider(client)
        before_at = _utc()
        health = _health(_http_json("/api/health"), expected_build)
        state = _http_json("/api/live/state")
        apps = {
            symbol: _application(
                state, _http_json(f"/api/instruments/moomoo/{symbol}/history?range=1d"), symbol
            )
            for symbol in SYMBOLS
        }
        app_at = _utc()
        after = _provider(client)
        after_at = _utc()
        value = {
            "before_at": before_at,
            "app_at": app_at,
            "after_at": after_at,
            "health": health,
            "symbols": {
                symbol: {
                    "before": before[symbol]["bars"],
                    "after": after[symbol]["bars"],
                    "quote_before_at": before[symbol]["quote_at"],
                    "quote_after_at": after[symbol]["quote_at"],
                    "app": apps[symbol],
                }
                for symbol in SYMBOLS
            },
        }
        # Evaluate schema before publishing. Invalid responses never get archived.
        _check_sample(value, expected_build)
        raw = json.dumps({"sample": value}, allow_nan=False).encode()
        if len(raw) > MAX_BYTES:
            raw = b'{"error":"output_limit"}'
    except Exception:
        # Do not serialize exception strings, vendor codes, responses or tracebacks.
        raw = b'{"error":"source_or_application_unavailable"}'
    try:
        connection.send_bytes(raw)
    finally:
        connection.close()


def _child_ticks(pid: int) -> int | None:
    return _start_ticks(_Proc().read(f"{pid}/stat")) if sys.platform == "linux" else None


def _run_owned_child(target, args: tuple, *, timeout: float) -> dict:
    """Bound SDK/API waits. Only this newly spawned Process can be terminated."""
    context = multiprocessing.get_context("spawn")
    reader, writer = context.Pipe(duplex=False)
    child = context.Process(target=target, args=(writer, *args))
    started = time.monotonic()
    child.start()
    writer.close()
    token = _child_ticks(child.pid)
    messages = queue.Queue(maxsize=1)

    def receive():
        try:
            messages.put((reader.recv_bytes(MAX_BYTES), None))
        except Exception as error:
            messages.put((None, type(error)))

    receiver = threading.Thread(target=receive, daemon=True)
    receiver.start()
    try:
        remaining = max(0, timeout - (time.monotonic() - started))
        try:
            raw, error_type = messages.get(timeout=remaining)
        except queue.Empty:
            raise WitnessError("child_timeout")
        if error_type is OSError:
            raise WitnessError("output_limit") from None
        if error_type is not None:
            raise WitnessError("child_failed")
        remaining = max(0, timeout - (time.monotonic() - started))
        child.join(remaining)
        if child.is_alive():
            raise WitnessError("child_timeout")
        if child.exitcode != 0:
            raise WitnessError("child_failed")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise WitnessError("child_schema_invalid")
        if "error" in value:
            raise WitnessError("source_or_application_unavailable")
        return value
    finally:
        if child.is_alive():
            # Process on Windows holds an owned handle; Linux additionally checks
            # start ticks to fence PID reuse. No pgkill or pre-existing process API.
            if _child_ticks(child.pid) != token:
                raise WitnessError("owned_child_identity_changed")
            child.kill()
            child.join(2)
            if child.is_alive():
                raise WitnessError("owned_child_cleanup_pending")
        reader.close()
        receiver.join(0.2)
        child.close()


def _numbers(bar: dict) -> tuple:
    result = tuple(bar[k] for k in OHLCV)
    if any(type(n) not in (int, float) or not math.isfinite(n) for n in result):
        raise WitnessError("invalid_ohlcv")
    o, h, low, c, v = result
    if min(o, h, low, c) <= 0 or v < 0 or h < max(o, low, c) or low > min(o, h, c):
        raise WitnessError("invalid_ohlcv")
    return result


def _check_sample(sample: dict, expected_build: str) -> dict:
    _health(sample["health"], expected_build)
    before_at, app_at, after_at = (_clock(sample[k]) for k in ("before_at", "app_at", "after_at"))
    if not before_at <= app_at <= after_at or after_at - before_at > timedelta(seconds=30):
        raise WitnessError("sample_time_order_invalid")
    checked = {}
    if set(sample["symbols"]) != set(SYMBOLS):
        raise WitnessError("sample_symbols_missing")
    for symbol in SYMBOLS:
        value = sample["symbols"][symbol]
        app = value["app"]
        if any(
            app.get(k) != required
            for k, required in {
                "symbol": symbol,
                "venue": "moomoo",
                "interval": "1m",
                "calendar": "XNYS",
                "adjustment": "unadjusted",
                "license": "moomoo-private-market-data",
                "source": "moomoo-live-replay",
            }.items()
        ):
            raise WitnessError("application_lineage_mismatch")
        live = app["live"]
        if (
            live.get("status") != "degraded"
            or live.get("source") != "moomoo"
            or live.get("provenance") not in {"real", "delayed"}
            or live.get("bid") is not None
            or live.get("ask") is not None
            or app.get("proposal_allowed") is not None
            and app.get("proposal_allowed") is not False
        ):
            raise WitnessError("application_authority_mismatch")
        if (
            type(live["last"]) not in (int, float)
            or not math.isfinite(live["last"])
            or live["last"] <= 0
        ):
            raise WitnessError("application_metric_invalid")
        source_at = _clock(live["data_time"])
        receipt_at = _clock(live["received_at"])
        quote_before, quote_after = (
            _clock(value[k]) for k in ("quote_before_at", "quote_after_at")
        )
        if (
            source_at > receipt_at
            or receipt_at > app_at
            or quote_before > before_at
            or quote_after > after_at
            or quote_before > quote_after
            or source_at > quote_after
        ):
            raise WitnessError("source_clock_bracket_invalid")
        delay = app["provider_delay_seconds"]
        provider = []
        for side in ("before", "after"):
            rows = minute_candles(_instrument(symbol), value[side])
            if not rows or any(bar["timestamp"] > after_at for bar in rows):
                raise WitnessError("provider_source_clock_invalid")
            provider.append({bar["timestamp"]: bar for bar in rows})
        bars = app["bars"]
        if not isinstance(bars, list) or not 4 <= len(bars) <= 390:
            raise WitnessError("completed_bars_missing")
        previous = None
        completed = []
        for bar in bars:
            if type(bar.get("is_live_tail")) is not bool or bar["is_live_tail"] != (
                bar.get("live_lineage") is not None
            ):
                raise WitnessError("application_live_lineage_missing")
            stamp = _clock(bar["timestamp"])
            if (
                bar["interval"] != "1m"
                or stamp > app_at
                or previous is not None
                and stamp <= previous
            ):
                raise WitnessError("application_bar_clock_invalid")
            previous = stamp
            prices = _numbers(bar)
            if stamp + timedelta(minutes=1) <= before_at:
                if any(
                    stamp not in bracket or _numbers(bracket[stamp]) != prices
                    for bracket in provider
                ):
                    raise WitnessError("provider_ohlcv_mismatch")
                completed.append(stamp + timedelta(minutes=1))
            if bar.get("is_live_tail"):
                lineage = LiveTailLineage.model_validate_json(json.dumps(bar["live_lineage"]))
                if (
                    lineage.data_time != stamp
                    or lineage.provider_end != stamp + timedelta(minutes=1)
                    or lineage.sequence_origin != "local-observation"
                    or lineage.source != "moomoo"
                    or lineage.instrument != symbol
                    or lineage.venue != Venue.MOOMOO
                    or lineage.interval != "1m"
                    or lineage.received_at > app_at
                    or lineage.provider_time_key
                    not in {
                        bracket[stamp]["provider_time_key"]
                        for bracket in provider
                        if stamp in bracket
                    }
                ):
                    raise WitnessError("application_sequence_lineage_invalid")
        if len(completed) < 4:
            raise WitnessError("completed_bars_missing")
        policy = evaluate_session_freshness(
            app["calendar"], SessionPolicy.REGULAR, app_at, max(completed), "1m", delay
        )
        quote_policy = evaluate_session_freshness(
            app["calendar"],
            SessionPolicy.REGULAR,
            app_at,
            source_at,
            "1m",
            delay,
            source_kind="observation",
        )
        provider_quote_policy = evaluate_session_freshness(
            app["calendar"],
            SessionPolicy.REGULAR,
            after_at,
            quote_after,
            "1m",
            delay,
            source_kind="observation",
        )
        latest = bars[-1]
        # Partial app values must be an observed supplier value, never interpolated.
        latest_at = _clock(latest["timestamp"])
        if not any(
            latest_at in bracket and _numbers(bracket[latest_at]) == _numbers(latest)
            for bracket in provider
        ):
            raise WitnessError("provider_live_ohlcv_mismatch")
        checked[symbol] = {
            "policy": policy,
            "quote_policy": quote_policy,
            "provider_quote_policy": provider_quote_policy,
            "latest_at": latest_at,
            "values": _numbers(latest),
            "lineage": latest.get("live_lineage"),
            "source_at": source_at,
            "proposal_allowed": app.get("proposal_allowed"),
        }
    return checked


def _result(status: str, phase: str, reason: str, **extra) -> dict:
    return {
        "status": status,
        "phase": phase,
        "reason": reason,
        "provider_application": "unverified",
        "pc_independence": "unverified",
        "application_source_routing": "unverified",
        "proposal_gate": "unverified",
        "browser": "unverified",
        "recovery": "unverified",
        **extra,
    }


def evaluate_samples(samples: dict) -> dict:
    """Pure evidence check. Never admits native ownership from a saved mapping."""
    try:
        expected = samples["expected_build"]
        if not isinstance(expected, str) or not _SHA40.fullmatch(expected):
            raise WitnessError("expected_build_invalid")
        rows = samples["samples"]
        if not isinstance(rows, list) or len(rows) != 6:
            raise WitnessError("six_samples_required")
        checked = [_check_sample(row, expected) for row in rows]
        times = [_clock(row["app_at"]) for row in rows]
        if times[-1] - times[0] > timedelta(seconds=DEADLINE_SECONDS) or any(
            not 30 <= (b - a).total_seconds() <= 60 for a, b in zip(times, times[1:])
        ):
            raise WitnessError("sample_spacing_invalid")
        policies = [
            entry[symbol][key]
            for entry in checked
            for symbol in SYMBOLS
            for key in ("policy", "quote_policy", "provider_quote_policy")
        ]
        if any(p.data_state == "unknown" or p.market_state == "unknown" for p in policies):
            return _result("pending", "provider_application", "unknown_session_or_latency")
        if any(p.data_state not in {"fresh", "latest_session"} for p in policies):
            raise WitnessError("source_coverage_missing_or_delayed")
        if all(p.market_state == "closed" and p.data_state == "latest_session" for p in policies):
            return _result(
                "pending", "live_acceptance", "pending_live_acceptance", coverage="latest_session"
            )
        if any(p.market_state != "open" for p in policies):
            return _result("pending", "live_acceptance", "session_transition")
        for symbol in SYMBOLS:
            observations = [entry[symbol] for entry in checked]
            boundaries = revisions = 0
            for earlier, later in zip(observations, observations[1:]):
                delta = later["latest_at"] - earlier["latest_at"]
                if delta not in (timedelta(0), timedelta(minutes=1)):
                    raise WitnessError("application_minute_continuity_missing")
                lineage = later["lineage"]
                if not lineage or not earlier["lineage"]:
                    raise WitnessError("application_live_lineage_missing")
                if lineage["sequence"] <= earlier["lineage"]["sequence"]:
                    raise WitnessError("application_sequence_not_advancing")
                if delta:
                    boundaries += 1
                elif later["values"] != earlier["values"]:
                    revisions += 1
            if boundaries < 2 or revisions < 1:
                raise WitnessError("revision_or_two_boundaries_missing")
            if observations[-1]["source_at"] <= observations[0]["source_at"]:
                raise WitnessError("source_clock_not_advancing")
        return _result(
            "pending",
            "cutover",
            "application-source-routing-unverified",
            provider_application="passed",
            coverage="fresh",
        )
    except WitnessError as error:
        return _result("failed", "provider_application", str(error), provider_application="failed")
    except Exception:
        return _result(
            "failed",
            "provider_application",
            "evidence_schema_invalid",
            provider_application="failed",
        )


def _write_json(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def collect_samples(profile: dict, expected_build: str, output: Path) -> dict:
    """Native collection only; current blocked profile exits before SDK/network."""
    try:
        output.mkdir(mode=0o700, parents=True, exist_ok=False)
    except OSError:
        raise WitnessError("output_directory_not_new") from None
    started = time.monotonic()
    collected = {"expected_build": expected_build, "samples": []}
    try:
        if not isinstance(expected_build, str) or not _SHA40.fullmatch(expected_build):
            raise WitnessError("expected_build_invalid")
        validate_profile(profile)
        if profile["qualification"]["state"] != "qualified":
            result = _result("pending", "candidate_qualification", "profile_blocked")
        else:
            config = Path(profile["runtime"]["config_file"]).read_bytes()
            validate_profile(profile, require_qualified=True, config_bytes=config)
            identity = collect_gateway_identity(profile)
            _write_json(output / "identity-before.json", identity)
            for index in range(6):
                due = started + index * SAMPLE_SPACING
                remaining = started + DEADLINE_SECONDS - time.monotonic()
                if remaining <= 0:
                    raise WitnessError("overall_deadline")
                if due > time.monotonic():
                    time.sleep(min(due - time.monotonic(), remaining))
                current = collect_gateway_identity(profile)
                if not _same_identity(identity, current):
                    raise WitnessError("gateway_identity_changed")
                remaining = started + DEADLINE_SECONDS - time.monotonic()
                sample = _run_owned_child(
                    _sample_child, (expected_build,), timeout=min(30, remaining)
                )["sample"]
                after = collect_gateway_identity(profile)
                if not _same_identity(identity, after):
                    raise WitnessError("gateway_identity_changed")
                if time.monotonic() - started > DEADLINE_SECONDS:
                    raise WitnessError("overall_deadline")
                collected["samples"].append(sample)
                _write_json(output / f"sample-{index + 1}.json", sample)
            _write_json(output / "identity-after.json", after)
            result = evaluate_samples(collected)
            result["native_candidate"] = "observed"
    except WitnessError as error:
        result = _result("pending", "native_collection", str(error))
    except Exception:
        result = _result("failed", "candidate_qualification", "profile_or_collection_invalid")
    _write_json(output / "summary.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--expected-build", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.profile.stat().st_size > 16384:
            raise WitnessError("profile_output_limit")
        profile = json.loads(args.profile.read_text(encoding="utf-8"))
        result = collect_samples(profile, args.expected_build, args.output)
    except Exception:
        result = _result("failed", "candidate_qualification", "invocation_invalid")
    print(json.dumps(result, sort_keys=True))
    return {"passed": 0, "failed": 1, "pending": 2}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
