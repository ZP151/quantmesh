"""Inherited-FD admission and real Linux synthetic lifecycle regressions."""

from __future__ import annotations

import json
import os
import stat
import sys
from contextlib import contextmanager

import pytest

from tools import qualify_opend_private_terminal as terminal

NATIVE = pytest.mark.skipif(sys.platform != "linux", reason="requires native Linux PTY/pidfd")


@contextmanager
def private_pty():
    import pty
    import termios

    master, slave = pty.openpty()
    try:
        os.fchmod(slave, 0o600)
        attrs = termios.tcgetattr(slave)
        attrs[3] &= ~(termios.ECHO | termios.ECHONL)
        termios.tcsetattr(slave, termios.TCSANOW, attrs)
        yield master, slave
    finally:
        os.close(master)
        os.close(slave)


def test_default_preflight_has_no_resource_effect(monkeypatch, capsys):
    def forbidden():
        pytest.fail("default preflight created native resources")

    monkeypatch.setattr(terminal, "run_owned_fixture", forbidden)
    assert terminal.main([]) == 2
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["status"] == "pending"
    assert receipt["production_release_qualified"] is False
    assert receipt["source_host_private_input_verified"] is False


@pytest.mark.parametrize("argv", [["--command", "true"], ["--tty", "/dev/tty"], ["--root", "/tmp"]])
def test_cli_rejects_arbitrary_targets(argv):
    with pytest.raises(SystemExit) as exc:
        terminal.main(argv)
    assert exc.value.code == 2


@NATIVE
@pytest.mark.parametrize("uid", [True, False, -1, 1.0, "1000", None])
def test_invalid_uid_refuses_before_inspection(uid):
    with pytest.raises(terminal.TerminalQualificationError, match="invalid_uid"):
        terminal.inspect_private_terminal(0, 1, 2, expected_uid=uid)


@NATIVE
@pytest.mark.parametrize("fd", [True, -1, 1.0, "0", None, 999999])
def test_invalid_descriptor_refuses(fd):
    with pytest.raises(terminal.TerminalQualificationError, match="invalid_descriptor"):
        terminal.inspect_private_terminal(fd, fd, fd, expected_uid=os.getuid())


@NATIVE
def test_admission_returns_only_kernel_metadata_and_does_not_read(monkeypatch):
    with private_pty() as (_, slave):

        def forbidden(*args):
            pytest.fail("admission read terminal bytes")

        monkeypatch.setattr(os, "read", forbidden)
        proof = terminal.inspect_private_terminal(slave, slave, slave, expected_uid=os.getuid())
        assert set(proof) == {"descriptors", "owner_uid", "mode", "echo", "echonl"}
        assert proof["mode"] == 0o600
        assert proof["owner_uid"] == os.getuid()
        assert proof["echo"] is False and proof["echonl"] is False
        for descriptor in proof["descriptors"]:
            assert set(descriptor) == {"fd", "device", "inode", "rdev"}
            assert descriptor["rdev"] == os.fstat(slave).st_rdev


@NATIVE
@pytest.mark.parametrize("flag", ["ECHO", "ECHONL"])
def test_each_echo_flag_refuses(flag):
    import termios

    with private_pty() as (_, slave):
        attrs = termios.tcgetattr(slave)
        attrs[3] |= getattr(termios, flag)
        termios.tcsetattr(slave, termios.TCSANOW, attrs)
        with pytest.raises(terminal.TerminalQualificationError, match="echo_enabled"):
            terminal.inspect_private_terminal(slave, slave, slave, expected_uid=os.getuid())


@NATIVE
@pytest.mark.parametrize("mode", [0o620, 0o640, 0o604, 0o666])
def test_nonprivate_mode_refuses(mode):
    with private_pty() as (_, slave):
        os.fchmod(slave, mode)
        with pytest.raises(terminal.TerminalQualificationError, match="nonprivate_mode"):
            terminal.inspect_private_terminal(slave, slave, slave, expected_uid=os.getuid())


@NATIVE
def test_wrong_owner_refuses():
    with private_pty() as (_, slave):
        with pytest.raises(terminal.TerminalQualificationError, match="wrong_owner"):
            terminal.inspect_private_terminal(slave, slave, slave, expected_uid=os.getuid() + 1)


@NATIVE
def test_regular_file_and_non_tty_character_device_refuse(tmp_path):
    with (tmp_path / "ordinary").open("w+") as handle, open(os.devnull) as null:
        assert stat.S_ISCHR(os.fstat(null.fileno()).st_mode)
        for fd in [handle.fileno(), null.fileno()]:
            with pytest.raises(terminal.TerminalQualificationError, match="not_terminal"):
                terminal.inspect_private_terminal(fd, fd, fd, expected_uid=os.getuid())


@NATIVE
def test_different_terminals_refuse():
    with private_pty() as (_, first), private_pty() as (_, second):
        with pytest.raises(terminal.TerminalQualificationError, match="terminal_mismatch"):
            terminal.inspect_private_terminal(first, first, second, expected_uid=os.getuid())


@NATIVE
def test_replaced_fd_during_inspection_refuses(monkeypatch):
    with private_pty() as (_, first), private_pty() as (_, second):
        original = os.isatty
        replaced = False

        def replace(fd):
            nonlocal replaced
            if not replaced:
                os.dup2(second, first)
                replaced = True
            return original(fd)

        monkeypatch.setattr(os, "isatty", replace)
        with pytest.raises(terminal.TerminalQualificationError, match="descriptor_changed"):
            terminal.inspect_private_terminal(first, first, first, expected_uid=os.getuid())


@NATIVE
def test_owned_fixture_proves_transport_cleanup_and_sibling_survival():
    receipt = terminal.run_owned_fixture()
    assert receipt["status"] == "passed"
    assert receipt["scope"] == "OWNED_LOCAL_PRIVATE_TERMINAL_FIXTURE"
    assert receipt["elapsed_seconds"] <= 90
    assert receipt["owned_root_mode"] == 0o700
    assert receipt["owned_root_removed"] is True
    assert receipt["input"]["accepted_bytes"] == 65
    assert receipt["input"]["digest_matched"] is True
    assert receipt["input"]["marker_not_echoed"] is True
    assert receipt["input"]["observed_bytes"] == 4
    for name in [
        "disconnect",
        "blocked",
        "output_growth",
        "gate_timeout",
        "missing_handle",
        "registration_interrupted",
    ]:
        case = receipt["cases"][name]
        assert case["terminal"] is True, name
        assert case["sibling_survived"] is True, name
        assert case["released"] is (name in {"disconnect", "blocked", "output_growth"})
    assert receipt["cases"]["disconnect"]["returncode"] == -1
    assert receipt["cases"]["blocked"]["returncode"] == -9
    assert receipt["cases"]["output_growth"]["observed_bytes"] <= 4096
    assert receipt["all_owned_children_terminal"] is True
    for name in [
        "production_release_qualified",
        "source_host_private_input_verified",
        "private_input_verified",
        "sdk_wire_verified",
        "server_startup_verified",
        "operator_authenticated",
        "installation_approved",
        "market_verified",
    ]:
        assert receipt[name] is False


@NATIVE
def test_release_rechecks_echo_before_any_child_input(tmp_path):
    import termios

    with private_pty() as (_, slave):
        child = terminal._spawn(tmp_path, "blocked", slave, terminal._Deadline())
        try:
            attrs = termios.tcgetattr(slave)
            attrs[3] |= termios.ECHO
            termios.tcsetattr(slave, termios.TCSANOW, attrs)
            with pytest.raises(terminal.TerminalQualificationError, match="echo_enabled"):
                child.release(slave)
            assert child.released is False
        finally:
            child.close()
        assert child.proc.returncode is not None


@NATIVE
@pytest.mark.parametrize("failure", ["missing_handle", "registration_interrupted"])
def test_registration_failure_never_releases_and_waits_for_owned_child(tmp_path, failure):
    with private_pty() as (_, slave):
        with pytest.raises(terminal.TerminalQualificationError) as caught:
            terminal._spawn(tmp_path, "blocked", slave, terminal._Deadline(), failure=failure)
        assert caught.value.cleanup["terminal"] is True
        assert caught.value.cleanup["released"] is False


@NATIVE
def test_pty_setup_failure_closes_both_owned_descriptors(monkeypatch):
    import pty

    original = pty.openpty
    captured = []

    def remember():
        pair = original()
        captured.extend(pair)
        return pair

    def refuse(*args):
        raise OSError("synthetic permission failure")

    monkeypatch.setattr(pty, "openpty", remember)
    monkeypatch.setattr(os, "fchmod", refuse)
    with pytest.raises(OSError):
        with terminal._private_pty():
            pytest.fail("setup failure entered fixture")
    for fd in captured:
        with pytest.raises(OSError):
            os.fstat(fd)


@NATIVE
def test_missing_proc_identity_closes_gate_without_bare_pid_signal(tmp_path, monkeypatch):
    def refuse(*args):
        raise terminal.TerminalQualificationError("process_identity_unavailable")

    def forbidden(*args):
        pytest.fail("registration failure signalled an unregistered PID")

    monkeypatch.setattr(terminal, "_identity", refuse)
    monkeypatch.setattr(os, "kill", forbidden)
    monkeypatch.setattr(os, "killpg", forbidden)
    with private_pty() as (_, slave):
        with pytest.raises(terminal.TerminalQualificationError) as caught:
            terminal._spawn(tmp_path, "blocked", slave, terminal._Deadline())
    assert caught.value.cleanup["terminal"] is True
    assert caught.value.cleanup["released"] is False


@NATIVE
@pytest.mark.parametrize("position", [0, 1, 2])
def test_wrong_descriptor_access_mode_refuses(position):
    with private_pty() as (_, slave):
        # Release pytest is a session leader. A negative access-mode fixture
        # must never acquire this slave as its controlling terminal: closing
        # the owned master would otherwise send SIGHUP to the test runner.
        mode = os.O_WRONLY if position == 0 else os.O_RDONLY
        fd = os.open(f"/proc/self/fd/{slave}", mode | os.O_NOCTTY)
        try:
            descriptors = [slave, slave, slave]
            descriptors[position] = fd
            with pytest.raises(terminal.TerminalQualificationError, match="descriptor_access"):
                terminal.inspect_private_terminal(*descriptors, expected_uid=os.getuid())
        finally:
            os.close(fd)


@NATIVE
def test_sigint_inside_popen_window_waits_for_the_actual_child(tmp_path, monkeypatch):
    import signal
    import subprocess

    original = subprocess.Popen
    created = []

    def interrupt(*args, **kwargs):
        proc = original(*args, **kwargs)
        created.append(proc)
        # A real signal arrives after creation but before Popen returns its handle.
        signal.raise_signal(signal.SIGINT)
        return proc

    monkeypatch.setattr(subprocess, "Popen", interrupt)
    try:
        with private_pty() as (_, slave):
            with pytest.raises(terminal.TerminalQualificationError) as caught:
                terminal._spawn(tmp_path, "blocked", slave, terminal._Deadline())
        assert caught.value.code == "registration_interrupted"
        assert caught.value.cleanup["returncode"] == 40
        assert caught.value.cleanup["terminal"] is True
        assert created[0].returncode == 40
    finally:
        for proc in created:
            proc.wait(timeout=4)


@NATIVE
def test_second_pipe_failure_closes_first_owned_pair(tmp_path, monkeypatch):
    original = os.pipe
    captured = []

    def fail_second():
        if captured:
            raise OSError("synthetic descriptor exhaustion")
        pair = original()
        captured.extend(pair)
        return pair

    monkeypatch.setattr(os, "pipe", fail_second)
    with private_pty() as (_, slave):
        with pytest.raises(terminal.TerminalQualificationError):
            terminal._spawn(tmp_path, "blocked", slave, terminal._Deadline())
    for fd in captured:
        with pytest.raises(OSError):
            os.fstat(fd)
