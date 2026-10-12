"""Offline native-proc fixtures and source-bracket witness refusal regressions."""

import copy
import json
import struct
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from deploy.aws.opend.validate_profile import EXECUTABLE_SHA256, reviewed_configuration

PROFILE = Path("deploy/aws/opend/gateway-profile.json")
BUILD = "a" * 40


def tool():
    from tools import verify_server_market_source

    return verify_server_market_source


def profile(qualified=False):
    value = json.loads(PROFILE.read_text())
    if qualified:
        value["sdk"]["wire_compatibility_verified"] = True
        value["authentication"]["private_input_verified"] = True
        value["qualification"].update(
            state="qualified",
            install_allowed=True,
            operator_approved=True,
            server_startup_verified=True,
        )
    return value


class ProcFixture:
    """Only admitted proc surfaces; any secret-bearing read fails the test."""

    linux = True
    uid = 987
    pid = 42
    ticks = 12345
    inode = "6789"
    address = "0100007F"
    executable = "/opt/quantmesh/opend/10.10.7008/OpenD"
    digest = EXECUTABLE_SHA256
    ipv6 = False
    missing = False
    mutate = None
    scans = 0

    def read(self, path):
        assert "cmdline" not in path and "environ" not in path and ".xml" not in path
        if self.missing:
            raise PermissionError("SECRET")
        if path == "sys/kernel/random/boot_id":
            return "11111111-2222-3333-4444-555555555555\n"
        if path == "net/tcp":
            self.scans += 1
            if self.scans == 2 and self.mutate:
                setattr(self, *self.mutate)
            return self.socket(self.address)
        if path == "net/tcp6":
            return self.socket("0" * 32) if self.ipv6 else "header\n"
        if path == "42/stat":
            return "42 (OpenD tricky) S " + " ".join(["0"] * 18 + [str(self.ticks)])
        if path == "42/status":
            return f"Name:\tOpenD\nUid:\t{self.uid}\t{self.uid}\t{self.uid}\t{self.uid}\n"
        raise AssertionError(path)

    def socket(self, address):
        return f"header\n0: {address}:2B68 00000000:0000 0A 0:0 0:0 0 {self.uid} 0 {self.inode}\n"

    def entries(self, path):
        return ["42"] if path == "" else ["3"]

    def link(self, path):
        if path == "42/exe":
            return self.executable
        if path == "42/fd/3":
            return f"socket:[{self.inode}]"
        raise AssertionError(path)

    def executable_digest(self, pid):
        assert pid == 42
        return self.digest

    def user_id(self, name):
        assert name == "quantmesh-opend"
        return 987


def test_native_identity_contains_actual_process_socket_and_artifact():
    result = tool().collect_gateway_identity(profile(True), _proc=ProcFixture())
    assert result["pid"] == 42
    assert result["start_ticks"] == 12345
    assert result["uid"] == 987
    assert result["socket_inode"] == "6789"
    assert result["endpoint"] == "127.0.0.1:11112"
    assert result["executable_sha256"] == EXECUTABLE_SHA256
    assert result["boot_id"] == "11111111-2222-3333-4444-555555555555"


@pytest.mark.parametrize(
    "field,value",
    [
        ("address", "00000000"),
        ("address", "0100000A"),
        ("uid", 0),
        ("uid", 986),
        ("executable", "/usr/sbin/sshd"),
        ("executable", "/usr/sbin/tailscaled"),
        ("executable", "/tmp/OpenD"),
        ("executable", ProcFixture.executable + " (deleted)"),
        ("digest", "f" * 64),
        ("ipv6", True),
        ("missing", True),
        ("linux", False),
    ],
)
def test_native_admission_refuses_forward_public_wrong_owner_or_missing_proof(field, value):
    proc = ProcFixture()
    setattr(proc, field, value)
    with pytest.raises(tool().WitnessError):
        tool().collect_gateway_identity(profile(True), _proc=proc)


@pytest.mark.parametrize("mutation", [("ticks", 54321), ("inode", "7890"), ("uid", 986)])
def test_concurrent_pid_or_socket_replacement_invalidates_identity(mutation):
    proc = ProcFixture()
    proc.mutate = mutation
    with pytest.raises(tool().WitnessError):
        tool().collect_gateway_identity(profile(True), _proc=proc)


def test_blocked_profile_stops_before_native_sdk_or_network(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("must not reach native/SDK/network")

    monkeypatch.setattr(tool(), "collect_gateway_identity", forbidden)
    monkeypatch.setattr(tool(), "_run_owned_child", forbidden)
    result = tool().collect_samples(profile(), BUILD, tmp_path / "run")
    assert result["status"] == "pending"
    assert result["reason"] == "profile_blocked"
    assert result["phase"] == "candidate_qualification"


def test_saved_identity_claim_cannot_bypass_real_native_admission(tmp_path, monkeypatch):
    def native(*args, **kwargs):
        raise tool().WitnessError("native_identity_unavailable")

    monkeypatch.setattr(tool(), "collect_gateway_identity", native)
    original_read = Path.read_bytes
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda path: reviewed_configuration() if path.name == "OpenD.xml" else original_read(path),
    )
    (tmp_path / "identity.json").write_text(json.dumps({"native": True, "pc_dependency": "no"}))
    result = tool().collect_samples(profile(True), BUILD, tmp_path / "run")
    assert result["status"] != "passed"
    assert result["reason"] == "native_identity_unavailable"


def raw(symbol, end, volume=100):
    return {
        "code": f"US.{symbol}",
        "time_key": end.strftime("2026-10-12 %H:%M:%S"),
        "open": 100,
        "high": 103,
        "low": 99,
        "close": 101,
        "volume": volume,
    }


def samples(closed=False):
    # Six supplier brackets, 35 seconds apart: revisions at 13:40 and 13:41,
    # canonical starts advance 13:40 -> 13:41 -> 13:42 (two real boundaries).
    start = datetime(2026, 10, 12, 13, 40, 10, tzinfo=UTC)
    result = {"expected_build": BUILD, "samples": []}
    for i in range(6):
        now = start + timedelta(seconds=35 * i)
        if closed:
            now = datetime(2026, 10, 13, 1, tzinfo=UTC) + timedelta(seconds=35 * i)
            end = datetime(2026, 10, 12, 20, tzinfo=UTC)
        else:
            end = now.replace(second=0) + timedelta(minutes=1)
        sample = {
            "before_at": (now - timedelta(seconds=1)).isoformat(),
            "app_at": now.isoformat(),
            "after_at": (now + timedelta(seconds=1)).isoformat(),
            "health": {
                "build_ref": BUILD,
                "paper_mode": True,
                "live_trading": False,
                "runtime_mode": "live",
            },
            "symbols": {},
        }
        for symbol in ("AAPL", "NVDA"):
            rows = []
            for minute in range(5, -1, -1):
                local = end - timedelta(hours=4, minutes=minute)
                rows.append(raw(symbol, local, 100 + i if minute == 0 and not closed else 100))
            payload = {
                "code": f"US.{symbol}",
                "interval": "1m",
                "autype": "None",
                "session": "regular",
                "rows": rows,
            }
            bars = []
            for j, row in enumerate(rows):
                stamp = end - timedelta(minutes=6 - j)
                lineage = None
                if j == 5 and not closed:
                    lineage = {
                        "source": "moomoo",
                        "venue": "moomoo",
                        "instrument": symbol,
                        "provenance": "real",
                        "data_time": stamp.isoformat(),
                        "received_at": now.isoformat(),
                        "interval": "1m",
                        "sequence": i + 1,
                        "predecessor_sequence": i,
                        "predecessor_data_time": stamp.isoformat(),
                        "sequence_gap": False,
                        "continuity_proven": True,
                        "freshness_label": "real",
                        "age_ms": 0,
                        "freshness_time": now.isoformat(),
                        "sequence_origin": "local-observation",
                        "provider_time_key": row["time_key"],
                        "provider_end": end.isoformat(),
                    }
                bars.append(
                    {
                        "timestamp": stamp.isoformat(),
                        "interval": "1m",
                        **{k: row[k] for k in ("open", "high", "low", "close", "volume")},
                        "is_live_tail": lineage is not None,
                        "live_lineage": lineage,
                    }
                )
            sample["symbols"][symbol] = {
                "before": copy.deepcopy(payload),
                "after": copy.deepcopy(payload),
                "quote_before_at": (min(end, now) - timedelta(seconds=2)).isoformat(),
                "quote_after_at": min(end, now).isoformat(),
                "app": {
                    "symbol": symbol,
                    "venue": "moomoo",
                    "interval": "1m",
                    "calendar": "XNYS",
                    "adjustment": "unadjusted",
                    "license": "moomoo-private-market-data",
                    "source": "moomoo-live-replay",
                    "bars": bars,
                    "live": {
                        "status": "degraded",
                        "bid": None,
                        "ask": None,
                        "last": 101,
                        "source": "moomoo",
                        "provenance": "real",
                        "data_time": min(end, now).isoformat(),
                        "received_at": now.isoformat(),
                    },
                    "proposal_allowed": None,
                    "provider_delay_seconds": 0,
                },
            }
        result["samples"].append(sample)
    return result


def test_complete_bracket_evidence_still_does_not_certify_application_routing_or_pc_independence():
    result = tool().evaluate_samples(samples())
    assert result["status"] == "pending"
    assert result["provider_application"] == "passed"
    assert result["reason"] == "application-source-routing-unverified"
    assert result["pc_independence"] == "unverified"
    assert result["proposal_gate"] == "unverified"


def test_closed_latest_session_is_normal_coverage_with_live_acceptance_pending():
    result = tool().evaluate_samples(samples(True))
    assert result["status"] == "pending"
    assert result["reason"] == "pending_live_acceptance"
    assert result["coverage"] == "latest_session"


@pytest.mark.parametrize("change", ["missing", "future", "unknown_delay", "unknown_calendar"])
def test_unresolved_source_clocks_or_policy_cannot_pass(change):
    value = samples()
    for sample in value["samples"]:
        app = sample["symbols"]["AAPL"]["app"]
        if change == "missing":
            app["live"]["data_time"] = None
        elif change == "future":
            app["live"]["data_time"] = "2027-10-12T13:40:00+00:00"
        elif change == "unknown_delay":
            app["provider_delay_seconds"] = None
        else:
            app["calendar"] = "unknown"
    assert tool().evaluate_samples(value)["provider_application"] != "passed"


@pytest.mark.parametrize(
    "change",
    [
        "ohlcv",
        "build",
        "paper",
        "live",
        "depth",
        "proposal",
        "license",
        "sequence",
        "synthetic",
        "source",
        "raw_label",
        "no_revision",
        "no_boundaries",
        "too_few",
        "readiness",
    ],
)
def test_false_acceptance_evidence_fails_closed(change):
    value = samples()
    for sample in value["samples"]:
        app = sample["symbols"]["AAPL"]["app"]
        if change == "ohlcv":
            app["bars"][0]["close"] = 102
        elif change == "build":
            sample["health"]["build_ref"] = "b" * 40
        elif change == "paper":
            sample["health"]["paper_mode"] = 1
        elif change == "live":
            sample["health"]["live_trading"] = True
        elif change == "depth":
            app["live"]["bid"] = 100
        elif change == "proposal":
            app["proposal_allowed"] = True
        elif change == "license":
            app["license"] = "public"
        elif change == "sequence":
            app["bars"][-1]["live_lineage"]["sequence_origin"] = "exchange"
        elif change == "synthetic":
            app["live"]["provenance"] = "synthetic"
        elif change == "source":
            app["source"] = "demo"
        elif change == "raw_label":
            app["bars"][-1]["live_lineage"]["provider_time_key"] = "2026-10-12 10:00:00"
        elif change == "no_revision":
            for side in ("before", "after"):
                sample["symbols"]["AAPL"][side]["rows"][-1]["volume"] = 100
            app["bars"][-1]["volume"] = 100
        elif change == "too_few":
            app["bars"] = app["bars"][-3:]
    if change == "no_boundaries":
        value["samples"] = [copy.deepcopy(value["samples"][0]) for _ in range(6)]
    if change == "readiness":
        value = {"ready": True, "quote": True, "history": True, "native": True}
    result = tool().evaluate_samples(value)
    assert result["status"] == "failed"
    assert result["provider_application"] != "passed"


def test_json_reader_bounds_response_and_disallows_redirects():
    class Response:
        status = 200

        def read(self, count):
            return b"x" * count

    with pytest.raises(tool().WitnessError, match="output_limit"):
        tool()._read_json_response(Response())
    assert tool()._NoRedirect().redirect_request(None, None, 302, "", {}, "http://evil") is None


def hanging_child(connection):
    time.sleep(30)


def noisy_child(connection):
    connection.send_bytes(b"x" * (2 * 1024 * 1024 + 1))


@pytest.mark.parametrize(
    "target,reason", [(hanging_child, "child_timeout"), (noisy_child, "output_limit")]
)
def test_owned_child_deadline_and_output_limit_are_enforced(target, reason):
    started = time.monotonic()
    with pytest.raises(tool().WitnessError, match=reason):
        tool()._run_owned_child(target, (), timeout=0.5)
    assert time.monotonic() - started < 5


def test_cli_blocked_is_nonzero_and_archives_redacted_pending(tmp_path, capsys):
    assert (
        tool().main(
            [
                "--profile",
                str(PROFILE),
                "--expected-build",
                BUILD,
                "--output",
                str(tmp_path / "new"),
            ]
        )
        == 2
    )
    report = json.loads((tmp_path / "new" / "summary.json").read_text())
    assert report["reason"] == "profile_blocked"
    assert "profile_blocked" in capsys.readouterr().out


def test_output_directory_is_exclusive_and_does_not_overwrite_existing_evidence(tmp_path):
    path = tmp_path / "existing"
    path.mkdir()
    (path / "summary.json").write_text("original")
    with pytest.raises(tool().WitnessError):
        tool().collect_samples(profile(), BUILD, path)
    assert (path / "summary.json").read_text() == "original"


def test_invalid_build_and_profile_do_not_echo_untrusted_values(tmp_path, capsys):
    path = tmp_path / "profile.json"
    path.write_text('{"password":"SECRET"}')
    assert (
        tool().main(
            ["--profile", str(path), "--expected-build", BUILD, "--output", str(tmp_path / "new")]
        )
        == 1
    )
    assert "SECRET" not in capsys.readouterr().out


@pytest.mark.parametrize("mutation", ["socket_disappears", "shared_owner", "uid_changes"])
def test_incomplete_or_shared_socket_ownership_is_not_certified(mutation):
    proc = ProcFixture()
    if mutation == "socket_disappears":
        proc.link = lambda path: (_ for _ in ()).throw(FileNotFoundError())
    elif mutation == "shared_owner":
        proc.entries = lambda path: ["42", "43"] if path == "" else ["3"]
        proc.link = lambda path: "socket:[6789]"
    else:
        original = proc.read
        proc.read = lambda path: (
            "Uid:\t987\t0\t987\t987\n" if path == "42/status" else original(path)
        )
    with pytest.raises(tool().WitnessError):
        tool().collect_gateway_identity(profile(True), _proc=proc)


def incomplete_ipc_child(connection):
    # Announce a small framed result, send one byte, then hang before its body.
    import os

    if os.name == "nt":
        connection.send_bytes(b"{")
    else:
        os.write(connection.fileno(), struct.pack("!i", 1000) + b"{")
    time.sleep(30)


def test_partial_child_result_cannot_escape_whole_child_deadline():
    started = time.monotonic()
    with pytest.raises(tool().WitnessError):
        tool()._run_owned_child(incomplete_ipc_child, (), timeout=0.5)
    assert time.monotonic() - started < 5


def market_history(app):
    inst = {
        "symbol": app["symbol"],
        "venue": "moomoo",
        "instrument_type": "equity",
        "currency": "USD",
        "metadata": {"market": "US"},
    }
    return {
        "primary": {
            "instrument": inst,
            "range": "1d",
            "as_of": "2026-10-12T13:40:10Z",
            "bars": [{"instrument": inst, **bar} for bar in app["bars"]],
            "dataset_id": "live-replay-moomoo-aapl",
            "dataset_revision": 1,
            "source": app["source"],
            "license": app["license"],
            "generated_at": "2026-10-12T13:40:10Z",
            "interval": "1m",
            "calendar": "XNYS",
            "adjustment": "unadjusted",
            "coverage": {
                "venue": "moomoo",
                "symbol": app["symbol"],
                "interval": "1m",
                "start": app["bars"][0]["timestamp"],
                "end": app["bars"][-1]["timestamp"],
                "rows": 6,
            },
        },
        "comparison": None,
    }


def test_market_only_projection_uses_real_contract_and_drops_free_text():
    app = samples()["samples"][0]["symbols"]["AAPL"]["app"]
    metric = {
        "payload": {"last": 101, "password": "SECRET"},
        "provenance": "real",
        "data_time": "2026-10-12T13:40:10Z",
        "received_at": "2026-10-12T13:40:10Z",
        "reason": "SECRET",
    }
    state = {
        "instruments": {
            "moomoo:AAPL": {
                "venue": "moomoo",
                "instrument": "AAPL",
                "kinds": {"metrics": metric},
                "session_freshness": {"provider_delay_seconds": None},
            }
        }
    }
    value = tool()._application(state, market_history(app), "AAPL")
    assert value["proposal_allowed"] is None
    assert value["provider_delay_seconds"] is None
    assert "SECRET" not in json.dumps(value)
    assert value["bars"][-1]["live_lineage"]["sequence_origin"] == "local-observation"


@pytest.mark.parametrize(
    "path",
    [
        "/api/account",
        "/api/positions",
        "/api/instruments/moomoo/AAPL/workspace",
        "https://evil.example/api/health",
    ],
)
def test_account_or_fetched_endpoint_is_refused_before_network(path):
    with pytest.raises(tool().WitnessError, match="application_endpoint_not_admitted"):
        tool()._http_json(path)


def test_provider_uses_quote_only_client_and_reduces_raw_fields():
    from quantmesh.moomoo.opend import MoomooOpenDClient

    class Transport:
        def stock_quote(self, codes):
            return {
                "rows": [
                    {
                        "code": codes[0],
                        "data_date": "2026-10-12",
                        "data_time": "09:40:10",
                        "last_price": 101,
                        "volume": 100,
                        "account": "SECRET",
                    }
                ]
            }

        def current_kline(self, code, *, num):
            assert num == 390
            row = raw(code[3:], datetime(2026, 10, 12, 9, 41)) | {"credential": "SECRET"}
            return {
                "code": code,
                "interval": "1m",
                "autype": "None",
                "session": "regular",
                "rows": [row],
            }

    value = tool()._provider(MoomooOpenDClient(Transport()))
    assert set(value) == {"AAPL", "NVDA"}
    assert value["AAPL"]["quote_at"] == "2026-10-12T13:40:10+00:00"
    assert "SECRET" not in json.dumps(value)


def test_proposal_boolean_is_strict():
    value = samples()
    value["samples"][0]["symbols"]["AAPL"]["app"]["proposal_allowed"] = 0
    assert tool().evaluate_samples(value)["status"] == "failed"


def test_bar_lineage_flags_are_strict():
    value = samples()
    bar = value["samples"][0]["symbols"]["AAPL"]["app"]["bars"][-1]
    bar["is_live_tail"] = False
    assert tool().evaluate_samples(value)["status"] == "failed"


def test_sdk_version_mismatch_refuses_client_construction(monkeypatch):
    import importlib.metadata

    monkeypatch.setattr(tool(), "_quiet_child", lambda: None)
    monkeypatch.setattr(importlib.metadata, "version", lambda name: "10.02.0000")
    monkeypatch.setattr(tool(), "MoomooOpenDClient", lambda *args: pytest.fail("SDK reached"))

    class Connection:
        value = None

        def send_bytes(self, raw):
            self.value = json.loads(raw)

        def close(self):
            pass

    connection = Connection()
    tool()._sample_child(connection, BUILD)
    assert connection.value == {"error": "source_or_application_unavailable"}


def test_native_candidate_requires_qualified_flags_even_if_profile_claims_qualified():
    value = profile()
    value["qualification"]["state"] = "qualified"
    with pytest.raises(tool().WitnessError):
        tool().collect_gateway_identity(value, _proc=ProcFixture())


def test_normal_poll_lag_is_checked_by_shared_policy_not_exact_quote_clock_equality():
    value = samples()
    for sample in value["samples"]:
        for symbol in ("AAPL", "NVDA"):
            live = sample["symbols"][symbol]["app"]["live"]
            live["data_time"] = (
                datetime.fromisoformat(live["data_time"]) - timedelta(seconds=5)
            ).isoformat()
    assert tool().evaluate_samples(value)["provider_application"] == "passed"


def test_source_provider_quote_coverage_is_checked_independently():
    value = samples()
    for sample in value["samples"]:
        sample["symbols"]["AAPL"]["quote_before_at"] = "2026-10-09T20:00:00Z"
        sample["symbols"]["AAPL"]["quote_after_at"] = "2026-10-09T20:00:00Z"
    assert tool().evaluate_samples(value)["provider_application"] == "failed"


def prepare_native_collection(monkeypatch):
    original_read = Path.read_bytes
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda path: reviewed_configuration() if path.name == "OpenD.xml" else original_read(path),
    )
    elapsed = [0.0]
    monkeypatch.setattr(tool().time, "monotonic", lambda: elapsed[0])
    monkeypatch.setattr(
        tool().time, "sleep", lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds)
    )
    identity = tool().collect_gateway_identity(profile(True), _proc=ProcFixture())
    monkeypatch.setattr(tool(), "collect_gateway_identity", lambda profile: identity.copy())
    rows = iter(samples()["samples"])
    monkeypatch.setattr(tool(), "_run_owned_child", lambda *args, **kwargs: {"sample": next(rows)})
    return identity


def test_six_native_brackets_are_archived_but_cutover_remains_pending(tmp_path, monkeypatch):
    prepare_native_collection(monkeypatch)
    result = tool().collect_samples(profile(True), BUILD, tmp_path / "new")
    assert result["provider_application"] == "passed"
    assert result["native_candidate"] == "observed"
    assert result["status"] == "pending"
    assert len(list((tmp_path / "new").glob("sample-*.json"))) == 6


def test_post_sample_identity_replacement_does_not_publish_candidate_sample(tmp_path, monkeypatch):
    identity = prepare_native_collection(monkeypatch)
    sequence = iter([identity, identity, identity | {"start_ticks": 22222}])
    monkeypatch.setattr(tool(), "collect_gateway_identity", lambda profile: next(sequence))
    result = tool().collect_samples(profile(True), BUILD, tmp_path / "new")
    assert result["status"] == "pending"
    assert result["reason"] == "gateway_identity_changed"
    assert not list((tmp_path / "new").glob("sample-*.json"))
