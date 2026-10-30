"""Verifier unit evidence; these tests do not qualify accounting or a provider."""

import importlib.util
import json
import os
import select
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def verifier():
    path = Path(__file__).parents[1] / "tools/qualify_portfolio_budgets.py"
    if not path.exists():

        class MissingVerifier:
            def __getattr__(self, name):
                pytest.fail("owned portfolio verifier is missing")

        return MissingVerifier()
    from tools import qualify_portfolio_budgets

    return qualify_portfolio_budgets


@pytest.mark.parametrize("field", ["dsn", "password", "host", "command", "model_key"])
def test_profile_refuses_borrowed_authority(verifier, field):
    with pytest.raises(ValueError, match="profile fields"):
        verifier.Profile.from_mapping({field: "private-marker"})


def test_no_candidate_cannot_be_admitted(verifier):
    raw = {
        "schema_version": 1,
        "root": "/var/tmp/quantmesh-portfolio-test",
        "expected_build": "a" * 40,
        "reviewed_implementation": verifier.BASELINE,
    }
    with pytest.raises(ValueError, match="reviewed implementation"):
        verifier.Profile.from_mapping(raw)


def test_default_cli_never_creates_cluster_or_output(verifier, tmp_path, monkeypatch, capsys):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text("{}")
    profile = SimpleNamespace(root=tmp_path)
    monkeypatch.setattr(verifier.Profile, "from_mapping", lambda raw: profile)
    monkeypatch.setattr(verifier, "admit_runtime", lambda p: {"actual_build": "a" * 40})

    def forbidden(*args):
        pytest.fail("default preflight started a cluster")

    monkeypatch.setattr(verifier, "run_fixture", forbidden)
    output = tmp_path / "never-created"
    assert verifier.main(["--profile", str(profile_path), "--output", str(output)]) == 0
    assert not output.exists()
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["mode"] == "preflight"
    assert receipt["qualified"] is False
    assert receipt["production_release_qualified"] is False


@pytest.mark.parametrize("mutation", ["missing_table", "missing_row", "policy", "clock", "effect"])
def test_restore_compares_complete_accounting_and_effect_rows(verifier, mutation):
    source = {
        "model_effects": {"columns": ["price"], "rows": [["0.50"]]},
        "accounting_policy": {"columns": ["limit"], "rows": [["1"]]},
        "accounting_clock": {"columns": ["high_water"], "rows": [["2026-10-13"]]},
        "accounting_reservations": {"columns": ["category"], "rows": [["development"]]},
    }
    restored = json.loads(json.dumps(source))
    if mutation == "missing_table":
        del restored["accounting_reservations"]
    elif mutation == "missing_row":
        restored["accounting_reservations"]["rows"].clear()
    else:
        table = {
            "policy": "accounting_policy",
            "clock": "accounting_clock",
            "effect": "model_effects",
        }[mutation]
        restored[table]["rows"][0][0] = "changed"
    with pytest.raises(ValueError, match="restore state"):
        verifier.compare_states(source, restored)
    assert verifier.compare_states(source, source) is None


def test_race_requires_two_jobs_and_one_durable_observed_invocation(verifier):
    results = [
        {"job_id": "first", "admitted": True, "invocations": 1, "observer_sha256": "a" * 64},
        {"job_id": "second", "admitted": False, "invocations": 0, "observer_sha256": None},
    ]
    verifier.validate_race(results, ["first", "second"], "a" * 64)
    results[1]["invocations"] = 1
    with pytest.raises(ValueError, match="race"):
        verifier.validate_race(results, ["first", "second"], "a" * 64)


@pytest.mark.parametrize("mutation", ["both_win", "no_win", "duplicate_job", "no_observer"])
def test_race_cannot_qualify_partial_or_unobserved_evidence(verifier, mutation):
    results = [
        {"job_id": "first", "admitted": True, "invocations": 1, "observer_sha256": "a" * 64},
        {"job_id": "second", "admitted": False, "invocations": 0, "observer_sha256": None},
    ]
    if mutation == "both_win":
        results[1].update(admitted=True, invocations=1, observer_sha256="a" * 64)
    elif mutation == "no_win":
        results[0].update(admitted=False, invocations=0, observer_sha256=None)
    elif mutation == "duplicate_job":
        results[1]["job_id"] = "first"
    else:
        results[0]["observer_sha256"] = None
    with pytest.raises(ValueError, match="race"):
        verifier.validate_race(results, ["first", "second"], "a" * 64)


def test_snapshot_refuses_baseline_only_tables(verifier):
    with pytest.raises(ValueError, match="accounting"):
        verifier.validate_tables(["qm_schema", "jobs", "analysis_outbox", "model_effects"])


def test_independent_snapshot_keeps_every_column_and_additive_table(verifier):
    tables = {
        "qm_schema": {"columns": ["version"], "rows": [[1]]},
        "jobs": {"columns": ["job_id", "payload"], "rows": [["second", "{}"], ["first", "{}"]]},
        "analysis_outbox": {"columns": ["job_id"], "rows": []},
        "model_effects": {"columns": ["price", "status"], "rows": [["0.1", "reserved"]]},
        "future_accounting_state": {"columns": ["version", "clock"], "rows": [[1, "utc-month"]]},
        "future_reservations": {"columns": ["usd", "category"], "rows": [["0.1", "operating"]]},
    }

    class Cursor:
        query = None
        description = None

        def execute(self, query):
            self.query = query
            if query.startswith("SELECT *"):
                name = query.split('"')[1]
                self.description = [(column,) for column in tables[name]["columns"]]

        def fetchmany(self, limit):
            if "information_schema.tables" in self.query:
                return [[name] for name in sorted(tables)]
            return tables[self.query.split('"')[1]]["rows"][:limit]

    result = verifier.snapshot(SimpleNamespace(cursor=lambda: Cursor()))
    assert set(result) == set(tables)
    assert result["future_reservations"] == tables["future_reservations"]
    assert result["future_accounting_state"] == tables["future_accounting_state"]
    assert result["jobs"]["rows"] == [["first", "{}"], ["second", "{}"]]


@pytest.mark.skipif(sys.platform != "linux", reason="actual bounded Linux child")
def test_output_exhaustion_reaps_owned_child_and_records_exit(verifier, tmp_path):
    tmp_path.chmod(0o700)
    runner = verifier.Commands(tmp_path, tmp_path)
    with pytest.raises(ValueError, match="output cap"):
        runner.python(["-c", "import os,time;os.write(1,b'x'*2200000);time.sleep(20)"])
    assert runner.command_processes[-1].process.poll() is not None
    receipt = runner.receipts[-1]
    assert receipt["exit"] is not None
    assert (tmp_path / receipt["stdout"]).stat().st_size <= verifier.MAX_OUTPUT


@pytest.mark.skipif(sys.platform != "linux", reason="actual isolated Linux family")
def test_unknown_live_member_is_preserved_and_cannot_qualify_cleanup(verifier, tmp_path):
    tmp_path.chmod(0o700)
    runner = verifier.Commands(tmp_path, tmp_path)
    custody = uuid.uuid4().hex
    ready = tmp_path / "custodian-owned-child.json"
    code = (
        "import json,os,subprocess,sys,time;from pathlib import Path;"
        "p=subprocess.Popen([sys.executable,'-B','-c','import time;time.sleep(30)'],"
        "env={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1',"
        "'TEST_FIXTURE_CUSTODY':os.environ['TEST_FIXTURE_CUSTODY']});"
        "Path(sys.argv[1]).write_text(json.dumps({'pid':p.pid}));time.sleep(30)"
    )
    handle = runner.spawn(
        [sys.executable, "-B", "-c", code, str(ready)],
        {**verifier.environment(tmp_path), "TEST_FIXTURE_CUSTODY": custody},
        tmp_path,
    )
    child_fd = None
    parent_fd = os.pidfd_open(handle.pid)
    try:
        deadline = time.monotonic() + 3
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready.exists()
        pid = json.loads(ready.read_text())["pid"]
        proc = Path("/proc") / str(pid)
        ticks = verifier.owned.process_ticks(pid)
        assert proc.stat().st_uid == os.getuid()
        assert (proc / "exe").resolve() == Path(sys.executable).resolve()
        assert b"TEST_FIXTURE_CUSTODY=" + custody.encode() in (proc / "environ").read_bytes().split(
            b"\0"
        )
        child_fd = os.pidfd_open(pid)
        with pytest.raises(ValueError, match="family ownership refused"):
            runner.collect(handle, "deliberately-unattributed-member", timeout=0.15)
        assert not select.select([child_fd], [], [], 0)[0]
        assert handle.process.poll() is None
        assert not any(m.signals for m in handle.members.values())
        assert runner.receipts[-1]["exit"] is None
    finally:
        # A separate test-only custody marker grants the test retirement authority,
        # never the qualifier. Both fixture children are newly created by this test.
        if child_fd is not None:
            if not select.select([child_fd], [], [], 0)[0]:
                assert verifier.owned.process_ticks(pid) == ticks
                assert b"TEST_FIXTURE_CUSTODY=" + custody.encode() in (
                    proc / "environ"
                ).read_bytes().split(b"\0")
                signal.pidfd_send_signal(child_fd, signal.SIGKILL)
        if handle.process.poll() is None:
            assert verifier.owned.process_ticks(handle.pid) == handle.ticks
            signal.pidfd_send_signal(parent_fd, signal.SIGKILL)
            handle.process.wait(timeout=3)
        if child_fd is not None:
            os.waitpid(pid, 0)
            os.close(child_fd)
        os.close(parent_fd)
        handle.close()


def test_no_environment_credentials_are_forwarded(verifier, tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "private-marker")
    monkeypatch.setenv("PGPASSWORD", "private-marker")
    monkeypatch.setenv("PYTHONPATH", "/untrusted-source")
    env = verifier.environment(tmp_path)
    assert not {"OPENAI_API_KEY", "PGPASSWORD", "PYTHONPATH", "DATABASE_URL"} & env.keys()
    assert "private-marker" not in str(env)


def test_unknown_cli_never_echoes_caller_credential_text(verifier, capsys):
    try:
        result = verifier.main(
            [
                "--profile",
                "/unused-profile",
                "--output",
                "/unused-output",
                "--dsn",
                "private-marker",
            ]
        )
    except SystemExit as exc:
        result = exc.code
    assert result == 2
    captured = capsys.readouterr()
    assert "private-marker" not in captured.out + captured.err


@pytest.mark.skipif(sys.platform != "linux", reason="actual native child flags")
def test_child_retains_no_bytecode_flags_and_excludes_builder(verifier, tmp_path):
    tmp_path.chmod(0o700)
    runner = verifier.Commands(tmp_path, tmp_path)
    _, raw = runner.python(
        [
            "-c",
            "import json,os,sys;print(json.dumps([sys.dont_write_bytecode,"
            "os.environ.get('PYTHONDONTWRITEBYTECODE')]))",
        ]
    )
    assert json.loads(raw) == [True, "1"]
    paths = verifier.python_environment(tmp_path)["PYTHONPATH"].split(":")
    assert all("build-tools" not in p for p in paths)


@pytest.mark.skipif(sys.platform != "linux", reason="actual Linux child identity")
def test_failed_owned_child_is_reaped_without_touching_sibling(verifier, tmp_path):
    tmp_path.chmod(0o700)
    sibling = subprocess.Popen(
        [sys.executable, "-B", "-c", "import time;time.sleep(20)"],
        env=verifier.environment(tmp_path),
    )
    evidence = {"scope": "NATIVE_PYTHON_CHILD_UNIT_ONLY", "sibling_pid": sibling.pid}
    try:
        runner = verifier.Commands(tmp_path, tmp_path)
        with pytest.raises(ValueError, match="command deadline"):
            runner.python(["-c", "import time;time.sleep(20)"], timeout=0.15)
        assert runner.command_processes[-1].process.poll() is not None
        assert sibling.poll() is None
        child = runner.command_processes[-1]
        evidence.update(
            owned_pid=child.pid,
            owned_start_ticks=child.ticks,
            owned_terminal_exit=child.process.poll(),
            sibling_alive_after_owned_failure=True,
        )
        assert runner.receipts[-1]["exit"] is not None
        assert (tmp_path / runner.receipts[-1]["stdout"]).exists()
        assert (tmp_path / runner.receipts[-1]["stderr"]).exists()
    finally:
        sibling.terminate()
        sibling.wait(timeout=3)
        evidence["sibling_terminal_exit"] = sibling.poll()
        (tmp_path / "unit-cleanup.json").write_text(json.dumps(evidence, sort_keys=True))


@pytest.mark.skipif(sys.platform != "linux", reason="actual bounded Linux pipes")
def test_stdout_stderr_and_nonzero_exit_are_retained(verifier, tmp_path):
    tmp_path.chmod(0o700)
    runner = verifier.Commands(tmp_path, tmp_path)
    release = tmp_path / "release-after-registration"
    code = (
        "import sys,time;from pathlib import Path;"
        "print('raw-out');print('raw-err',file=sys.stderr);"
        "\nwhile not Path(sys.argv[1]).exists():"
        "\n time.sleep(0.005)"
        "\nsys.exit(7)"
    )
    try:
        handle = runner.spawn(
            [sys.executable, "-B", "-c", code, str(release)],
            verifier.environment(tmp_path),
            tmp_path,
        )
        release.touch()
        with pytest.raises(ValueError, match="command failed"):
            runner.collect(handle, "python")
    finally:
        release.touch()
        for child in runner.command_processes:
            child.process.wait(timeout=3)
            child.close()
    receipt = runner.receipts[-1]
    assert receipt["exit"] == 7
    assert (tmp_path / receipt["stdout"]).read_bytes() == b"raw-out\n"
    assert (tmp_path / receipt["stderr"]).read_bytes() == b"raw-err\n"


@pytest.mark.skipif(sys.platform != "linux", reason="native registration pidfd")
@pytest.mark.parametrize(
    "transition",
    ["terminal-empty", "live-empty", "terminal-wrong-nonce"],
)
def test_registration_environment_transition_keeps_only_owned_terminal_output(
    verifier, tmp_path, monkeypatch, transition
):
    """A real child exits while its first /proc environment is being read."""
    tmp_path.chmod(0o700)
    release = tmp_path / "release-registration-exit"
    code = (
        "import sys,time;from pathlib import Path;"
        "\nwhile not Path(sys.argv[1]).exists():"
        "\n time.sleep(0.005)"
        "\nprint('raw-out');print('raw-err',file=sys.stderr);sys.exit(7)"
    )
    original_identity, original_read_bytes = verifier.Child.identity, Path.read_bytes
    state = {"pid": None, "handle": None, "observed": False}

    def reading_identity(handle, pid):
        state["pid"] = pid
        state["handle"] = handle
        try:
            return original_identity(handle, pid)
        finally:
            state["pid"] = None

    def transitioning_environment(path):
        pid = state["pid"]
        if not state["observed"] and pid and path == Path("/proc") / str(pid) / "environ":
            raw = original_read_bytes(path)
            assert b"QM_BACKUP_COMMAND_OWNER=" + state["handle"].nonce.encode() in raw.split(b"\0")
            state["observed"] = True
            if transition != "live-empty":
                release.touch()
                fd = os.pidfd_open(pid)
                try:
                    assert select.select([fd], [], [], 3)[0]
                finally:
                    os.close(fd)
            return b"QM_BACKUP_COMMAND_OWNER=wrong\0" if transition.endswith("wrong-nonce") else b""
        return original_read_bytes(path)

    runner = verifier.Commands(tmp_path, tmp_path)
    try:
        with monkeypatch.context() as boundary:
            boundary.setattr(verifier.Child, "identity", reading_identity)
            boundary.setattr(Path, "read_bytes", transitioning_environment)
            boundary.setattr(
                signal,
                "pidfd_send_signal",
                lambda *args: pytest.fail("no signal to an unregistered leader"),
            )
            expected = (
                "command failed" if transition == "terminal-empty" else "family ownership refused"
            )
            with pytest.raises(ValueError, match=expected):
                runner.python(["-c", code, str(release)])
        assert state["observed"]
        if transition == "terminal-empty":
            receipt = runner.receipts[-1]
            assert receipt["exit"] == 7
            assert (tmp_path / receipt["stdout"]).read_bytes() == b"raw-out\n"
            assert (tmp_path / receipt["stderr"]).read_bytes() == b"raw-err\n"
        else:
            assert not runner.receipts
        assert all(
            not member.signals
            for handle in runner.command_processes
            for member in handle.members.values()
        )
    finally:
        release.touch()
        for handle in runner.command_processes:
            handle.process.wait(timeout=3)
            handle.close()


@pytest.mark.skipif(sys.platform != "linux", reason="retained native leader pidfd")
@pytest.mark.parametrize("transition", ["terminal-empty", "live-empty", "terminal-wrong-nonce"])
def test_owned_leader_exit_during_environment_read_preserves_retention(
    verifier, tmp_path, monkeypatch, transition
):
    terminal = transition.startswith("terminal")
    tmp_path.chmod(0o700)
    release = tmp_path / "release-owned-leader"
    code = (
        "import sys,time;from pathlib import Path;deadline=time.monotonic()+15;"
        "\nwhile not Path(sys.argv[1]).exists():"
        "\n if time.monotonic()>deadline: sys.exit(90)"
        "\n time.sleep(0.005)"
        "\nprint('raw-out');print('raw-err',file=sys.stderr);sys.exit(7)"
    )
    runner = verifier.Commands(tmp_path, tmp_path)
    handle = runner.spawn(
        [sys.executable, "-B", "-c", code, str(release)],
        verifier.environment(tmp_path),
        tmp_path,
    )
    member = handle.members[(handle.pid, handle.ticks)]
    environment_path = Path("/proc") / str(handle.pid) / "environ"
    read_bytes = Path.read_bytes
    evidence = {"leader": member.identity.copy(), "transition": transition}
    changed = False

    def exiting_environment(path):
        nonlocal changed
        if path == environment_path and (not changed or not terminal):
            # Only the already admitted leader is inspected; no ambient process is sampled.
            raw = read_bytes(path)
            assert b"QM_BACKUP_COMMAND_OWNER=" + handle.nonce.encode() in raw.split(b"\0")
            assert verifier.owned.process_ticks(handle.pid) == handle.ticks
            changed = True
            if terminal:
                release.touch()
                assert select.select([member.pidfd], [], [], 3)[0]
            evidence.update(
                phase="Child.identity/environ",
                predicate="owner_nonce_absent_in_terminal_window",
                pidfd_ready=member.ready(),
                popen_before_poll=handle.process.returncode,
            )
            # Controlled /proc transition: all earlier identity fields remain real.
            return b"QM_BACKUP_COMMAND_OWNER=wrong\0" if transition.endswith("wrong-nonce") else b""
        return read_bytes(path)

    try:
        with monkeypatch.context() as boundary:
            boundary.setattr(Path, "read_bytes", exiting_environment)
            expected = (
                "command failed" if transition == "terminal-empty" else "family ownership refused"
            )
            with pytest.raises(ValueError, match=expected):
                runner.collect(handle, "owned-leader-exit-transition", timeout=5)
        receipt = runner.receipts[-1]
        if transition == "terminal-empty":
            assert receipt["exit"] == 7
            assert (tmp_path / receipt["stdout"]).read_bytes() == b"raw-out\n"
            assert (tmp_path / receipt["stderr"]).read_bytes() == b"raw-err\n"
            assert member.terminal and member.reaped == "owned_Popen"
        elif not terminal:
            assert handle.process.poll() is None
            assert not member.ready()
            assert receipt["exit"] is None
        assert not member.signals
    finally:
        # The test releases only its own positively admitted child, without signalling.
        release.touch()
        handle.process.wait(timeout=3)
        evidence.update(popen_exit=handle.process.returncode, signals=member.signals)
        handle.close()
        (tmp_path / "owned-leader-transition.json").write_text(json.dumps(evidence, sort_keys=True))


@pytest.mark.skipif(sys.platform != "linux", reason="native registration pidfd")
@pytest.mark.parametrize("terminal", [True, False], ids=["terminal", "live-refusal"])
def test_registration_environment_permission_error_retains_owned_exit(
    verifier, tmp_path, monkeypatch, terminal
):
    release = tmp_path / "release-registration-leader"
    code = (
        "import sys,time;from pathlib import Path;print('R',end='',flush=True);"
        "deadline=time.monotonic()+12;"
        "\nwhile not Path(sys.argv[1]).exists():"
        "\n if time.monotonic()>deadline: sys.exit(90)"
        "\n time.sleep(0.005)"
        "\nprint('raw-out');print('raw-err',file=sys.stderr);sys.exit(7)"
    )
    runner = verifier.Commands(tmp_path, tmp_path)
    identity, read_bytes = verifier.Child.identity, Path.read_bytes
    open_pidfd, select_fds = os.pidfd_open, select.select
    state = {"calls": 0, "pending": False}

    def observed_identity(handle, pid):
        state["handle"] = handle
        state["calls"] += 1
        result = identity(handle, pid)
        if state["calls"] == 1:
            state["first"] = result
        return result

    def retained_pidfd(pid, *args):
        fd = open_pidfd(pid, *args)
        if pid == state["first"]["pid"]:
            state["fd"] = fd
        return fd

    def permission_transition(path):
        handle = state.get("handle")
        if (
            handle is not None
            and state["calls"] == 2
            and path == Path("/proc") / str(handle.pid) / "environ"
        ):
            assert state["first"]["start_ticks"] == handle.ticks
            assert select_fds([handle.process.stdout], [], [], 3)[0]
            assert os.read(handle.process.stdout.fileno(), 1) == b"R"
            state["pending"] = True
            raise PermissionError(13, "controlled owned registration exit window")
        return read_bytes(path)

    def terminal_observation(read, write, error, timeout=None):
        if state["pending"] and read == [state["fd"]] and timeout and terminal:
            release.touch()
        ready = select_fds(read, write, error, timeout)
        if state["pending"] and read == [state["fd"]] and timeout:
            state["observed_terminal"] = bool(ready[0])
        return ready

    try:
        with monkeypatch.context() as boundary:
            boundary.setattr(verifier.Child, "identity", observed_identity)
            boundary.setattr(Path, "read_bytes", permission_transition)
            boundary.setattr(os, "pidfd_open", retained_pidfd)
            boundary.setattr(select, "select", terminal_observation)
            expected = ValueError if terminal else PermissionError
            with pytest.raises(
                expected, match="command failed" if terminal else "controlled owned"
            ):
                handle = runner.spawn(
                    [sys.executable, "-B", "-c", code, str(release)],
                    verifier.environment(tmp_path),
                    tmp_path,
                )
                runner.collect(handle, "owned-registration-transition", timeout=5)
            handle = state["handle"]
            assert not any(m.signals for m in handle.members.values())
            if terminal:
                receipt = runner.receipts[-1]
                assert receipt["exit"] == 7
                assert (tmp_path / receipt["stdout"]).read_bytes() == b"raw-out\n"
                assert (tmp_path / receipt["stderr"]).read_bytes() == b"raw-err\n"
            else:
                assert handle.process.poll() is None
    finally:
        release.touch()
        handle = state.get("handle")
        if handle is not None:
            handle.process.wait(timeout=3)
            handle.close()
            if terminal:
                print(
                    json.dumps(
                        {
                            "first_identity": state.get("first"),
                            "phase": "registration/second-identity/environ",
                            "terminal_observed": state.get("observed_terminal"),
                            "exit": handle.process.returncode,
                            "signals": [],
                        },
                        sort_keys=True,
                    )
                )


def test_pg_prefix_manifest_rejects_substitution(verifier, tmp_path):
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    (prefix / "tool").write_bytes(b"substituted")
    with pytest.raises(ValueError, match="prefix"):
        verifier.admit_prefix(prefix, {"tool": {"size": 3, "sha256": "a" * 64}})


def test_shutdown_does_not_grant_unknown_pid_authority(verifier):
    class Unknown:
        pid = 123

        def close(self):
            raise ValueError("identity unknown")

    failures = verifier.cleanup([], [Unknown()])
    assert failures == [{"pid": 123, "state": "pending", "reason": "identity_refused"}]


def test_module_is_imported_from_owned_repository(verifier):
    assert (
        Path(importlib.util.find_spec(verifier.__name__).origin).resolve()
        == Path(verifier.__file__).resolve()
    )
    assert verifier.BASELINE == "216b378192bbc0a1742a28b7a1fc75a86ae2fda9"
    assert os.path.basename(verifier.__file__) == "qualify_portfolio_budgets.py"


def test_exact_reviewed_candidate_and_new_runtime_are_bound(verifier):
    assert getattr(verifier, "REVIEWED_IMPLEMENTATION", None) == (
        "b10762883edc1bbad164951d1a1adfb9f0f7457c"
    )
    assert str(verifier.PYTHON) == "/var/tmp/quantmesh-portfolio-runtime-72a6m2j0/venv/bin/python"


def test_scripted_invocation_needs_independent_committed_effect_and_charge(verifier):
    observed = {
        "model_effects": {
            "columns": ["job_id", "digest", "price", "status"],
            "rows": [["first", "a" * 64, "0.5", "reserved"]],
        },
        "qm_portfolio_reservations": {
            "columns": ["job_id", "digest", "category", "price"],
            "rows": [["first", "a" * 64, "operating", "0.5"]],
        },
    }
    check = getattr(verifier, "validate_observation", None)
    assert check is not None, "independent observer validation is missing"
    check(observed, "first", "a" * 64)
    observed["qm_portfolio_reservations"]["rows"].clear()
    with pytest.raises(ValueError, match="observation"):
        check(observed, "first", "a" * 64)


def native_command(verifier, tmp_path, code=None):
    native_profile = os.environ.get("QM_TEST_PORTFOLIO_PROFILE")
    if not native_profile or os.environ.get("QM_TEST_PORTFOLIO_ACK") != "owned-disposable":
        pytest.skip("explicit newly owned native portfolio profile required")
    raw = json.loads(Path(native_profile).read_text())
    root = Path(raw["root"])
    output = root / ("test-witness-" + uuid.uuid4().hex + "-" + tmp_path.name)
    env = verifier.environment(root)
    checkout = root / "checkout"
    env["PYTHONPATH"] = ":".join(
        str(p) for p in (checkout, checkout / "src", checkout / "services/research_agent/src")
    )
    if code is None:
        args = [
            "-m",
            "tools.qualify_portfolio_budgets",
            "--profile",
            native_profile,
            "--output",
            str(output),
            "--owned-fixture",
        ]
    else:
        args = ["-c", code, native_profile, str(output)]
    result = subprocess.run(
        [sys.executable, "-B", *args], env=env, cwd=checkout, capture_output=True, timeout=280
    )
    (tmp_path / "native.stdout").write_bytes(result.stdout)
    (tmp_path / "native.stderr").write_bytes(result.stderr)
    (tmp_path / "native.exit").write_text(str(result.returncode))
    return result, output


def test_repeated_native_test_requests_never_reuse_output(verifier, tmp_path, monkeypatch):
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"root": str(tmp_path)}))
    monkeypatch.setenv("QM_TEST_PORTFOLIO_PROFILE", str(profile))
    monkeypatch.setenv("QM_TEST_PORTFOLIO_ACK", "owned-disposable")
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
    )
    _, first = native_command(verifier, tmp_path)
    _, second = native_command(verifier, tmp_path)
    assert first != second, "native proof outputs would overwrite or collide"


def test_actual_owned_pg_race_observer_restore_exhaustion_and_negatives(verifier, tmp_path):
    result, output = native_command(verifier, tmp_path)
    assert result.returncode == 0, result.stdout.decode(errors="replace")
    witness = json.loads((output / "witness.json").read_text())
    assert witness["passed"] is True
    assert witness["production_release_qualified"] is False
    assert witness["cleanup_failures"] == []
    assert witness["race"]["independent_processes"] == 2
    assert witness["race"]["winning_scripted_invocations"] == 1
    assert witness["race"]["denied_scripted_invocations"] == 0
    assert witness["restore"]["complete_state_equal"] is True
    assert witness["restore"]["source_and_restored_categories_exhausted"] is True
    assert set(witness["negatives"]) == {
        "mismatched_policy",
        "missing_policy",
        "malformed_amount",
        "backward_clock",
        "atomic_rollback",
        "malformed_history",
        "unknown_accounting_version",
    }
    assert witness["sibling_survived_individual_cleanup"] is True
    assert all(c["terminal_exit"] is not None for c in witness["clusters"])
    assert all(c["terminal_exit"] is not None for c in witness["children"])


def test_actual_pg_failure_reaps_only_owned_clusters(verifier, tmp_path):
    code = (
        "import json,sys;from pathlib import Path;from tools import qualify_portfolio_budgets as q;"
        "p=q.Profile.from_mapping(json.loads(Path(sys.argv[1]).read_text()));"
        "q.exercise=lambda *args: (_ for _ in ()).throw(ValueError('unit-injected-after-start'));"
        "\ntry:q.run_fixture(p,Path(sys.argv[2]))"
        "\nexcept ValueError as e:sys.exit(9 if str(e)=='unit-injected-after-start' else 10)"
    )
    result, output = native_command(verifier, tmp_path, code)
    assert result.returncode == 9
    witness = json.loads((output / "witness.json").read_text())
    assert witness["passed"] is False
    assert witness["cleanup_failures"] == []
    assert len(witness["clusters"]) == 2
    assert witness["sibling_survived_failure_cleanup"] is True
    assert all(c["terminal_exit"] is not None for c in witness["clusters"])


def _native_boot_timeout_probe(q, profile, output):
    """Actual stopped PG bootstrap; fallback retires only this test's leaked fixture."""
    q.admit_runtime(profile)
    output = q.owned.fresh_directory(profile.root, output)
    runner = q.Commands(profile.root, output)
    password = output / "init-password"
    q.owned.write_private(password, b"owned-disposable-bootstrap-regression")
    sibling = subprocess.Popen(
        [sys.executable, "-B", "-c", "import time;time.sleep(30)"],
        env=q.environment(profile.root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    handle = None
    boot_fd = None
    saved = None
    evidence = {"scope": "ACTUAL_INITDB_BOOT_TIMEOUT_REGRESSION", "sibling_pid": sibling.pid}

    def identity(pid):
        proc = Path("/proc") / str(pid)
        fields = (proc / "stat").read_text().rsplit(")", 1)[1].split()
        exe = (proc / "exe").resolve()
        return {
            "pid": pid,
            "start_ticks": fields[19],
            "uid": proc.stat().st_uid,
            "exe": str(exe),
            "sha256": q.owned.digest(exe),
            "group": int(fields[2]),
            "session": int(fields[3]),
            "nonce_matches": b"QM_BACKUP_COMMAND_OWNER=" + handle.nonce.encode()
            in (proc / "environ").read_bytes().split(b"\0"),
        }

    try:
        handle = runner.spawn(
            [
                str(profile.root / "prefix/bin/initdb"),
                "-D",
                str(output / "data"),
                "-L",
                str(profile.root / "prefix/share/postgresql"),
                "--username=fixture_bootprobe",
                "--pwfile=" + str(password),
                "--auth=scram-sha-256",
                "--no-locale",
                "--encoding=UTF8",
            ],
            q.environment(profile.root),
            output,
        )
        evidence["initdb_pid"] = handle.pid
        deadline = time.monotonic() + 4
        while saved is None and time.monotonic() < deadline:
            descendants = {handle.pid}
            for _ in range(3):
                for proc in Path("/proc").iterdir():
                    if not proc.name.isdecimal():
                        continue
                    try:
                        fields = (proc / "stat").read_text().rsplit(")", 1)[1].split()
                        if int(fields[1]) in descendants:
                            descendants.add(int(proc.name))
                    except (OSError, ValueError):
                        continue
            for pid in descendants - {handle.pid}:
                try:
                    candidate = identity(pid)
                    if (
                        candidate["uid"] == os.getuid()
                        and candidate["nonce_matches"]
                        and candidate["exe"] == str(profile.root / "prefix/bin/postgres")
                        and candidate["sha256"] == q.owned.PG_HASHES["postgres"]
                    ):
                        boot_fd = os.pidfd_open(pid)
                        assert identity(pid) == candidate
                        signal.pidfd_send_signal(boot_fd, signal.SIGSTOP)
                        saved = candidate
                        break
                except (OSError, ValueError):
                    continue
            time.sleep(0.002)
        assert saved is not None, "real initdb bootstrap was not observed"
        evidence["positively_owned_bootstrap"] = saved
        with pytest.raises(ValueError, match="command deadline"):
            runner.collect(handle, "real-initdb-stopped-boot", timeout=0.2)
        evidence.update(
            parent_terminal_exit=handle.process.poll(),
            boot_terminal_before_test_fallback=bool(select.select([boot_fd], [], [], 0)[0]),
            sibling_alive_after_qualifier_cleanup=sibling.poll() is None,
        )
        assert evidence["boot_terminal_before_test_fallback"], (
            "owned postgres --boot survived cleanup"
        )
        assert evidence["parent_terminal_exit"] is not None
        assert evidence["sibling_alive_after_qualifier_cleanup"]
        evidence["qualified_cleanup"] = True
    finally:
        if boot_fd is not None:
            if not select.select([boot_fd], [], [], 0)[0]:
                assert identity(saved["pid"]) == saved
                signal.pidfd_send_signal(boot_fd, signal.SIGKILL)
                evidence["test_fallback_retired_leak"] = True
            os.close(boot_fd)
        if handle:
            handle.close()
        sibling.terminate()
        sibling.wait(timeout=3)
        evidence["sibling_terminal_exit_after_test"] = sibling.poll()
        password.unlink(missing_ok=True)
        evidence["private_password_input_removed"] = not password.exists()
        q.durable(output / "bootstrap-cleanup.json", q.owned.canonical(evidence))


def test_actual_initdb_bootstrap_descendant_timeout_is_terminal(verifier, tmp_path):
    code = (
        "import importlib.util,json,sys;from pathlib import Path;"
        "from tools import qualify_portfolio_budgets as q;"
        "p=q.Profile.from_mapping(json.loads(Path(sys.argv[1]).read_text()));"
        "s=importlib.util.spec_from_file_location('owned_boot_probe',"
        "p.root/'checkout/tests/test_portfolio_budget_qualification.py');"
        "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
        "m._native_boot_timeout_probe(q,p,Path(sys.argv[2]))"
    )
    result, output = native_command(verifier, tmp_path, code)
    evidence = json.loads((output / "bootstrap-cleanup.json").read_text())
    assert result.returncode == 0, evidence
    assert evidence["qualified_cleanup"] is True
    assert evidence["boot_terminal_before_test_fallback"] is True
    assert evidence["sibling_alive_after_qualifier_cleanup"] is True
    assert evidence["private_password_input_removed"] is True


@pytest.mark.skipif(sys.platform != "linux", reason="native whole-process wall timer")
@pytest.mark.parametrize("injected_failure", [False, True])
def test_executor_cleanup_contract_after_work_or_failure(
    verifier, tmp_path, monkeypatch, injected_failure
):
    tmp_path.chmod(0o700)
    stopped = []

    class FixtureCluster:
        def __init__(self, commands, name):
            self.home = commands.output / name
            self.home.mkdir(mode=0o700)
            self.data = self.home / "data"
            self.ticks = "unit-identity"
            self.system_id = "unit-system"
            self.server_log = None
            self.terminal = None
            self.process = SimpleNamespace(
                pid=len(commands.clusters) + 100, poll=lambda: self.terminal
            )
            self.name = name
            commands.clusters.append(self)

        def verify_sql(self):
            assert self.name not in stopped

        def stop(self):
            if self.name not in stopped:
                stopped.append(self.name)
            self.terminal = 0

    monkeypatch.setattr(verifier, "admit_runtime", lambda p: {"actual_build": "unit-fixture"})
    monkeypatch.setattr(verifier.owned.Cluster, "start", FixtureCluster)

    def work(profile, commands, source, sibling, witness):
        witness["scope"] = "SYNTHETIC_EXECUTOR_CONTROL_FLOW_UNIT"
        if injected_failure:
            raise ValueError("unit-injected-work-failure")
        witness["executed_unit_work"] = True

    monkeypatch.setattr(verifier, "exercise", work, raising=False)
    output = tmp_path / "proof"
    profile = SimpleNamespace(root=tmp_path)
    if injected_failure:
        with pytest.raises(ValueError, match="unit-injected-work-failure"):
            verifier.run_fixture(profile, output)
    else:
        assert verifier.run_fixture(profile, output) == 0
    witness = json.loads((output / "witness.json").read_text())
    assert witness["passed"] is not injected_failure
    assert witness["cleanup_failures"] == []
    assert stopped == ["source", "sibling"]
    assert all(c["terminal_exit"] == 0 for c in witness["clusters"])
