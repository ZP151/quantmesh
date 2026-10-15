"""Behavior checks for admission, private credentials and owned cleanup fences."""

import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest


def helper():
    return importlib.import_module("tools.qualify_owned_postgres")


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "localhost", "192.168.1.2"])
def test_fixture_rejects_nonliteral_loopback(host):
    with pytest.raises(ValueError, match="loopback"):
        helper().validate_bind(host)


def test_fixture_accepts_only_literal_loopback():
    assert helper().validate_bind("127.0.0.1") == "127.0.0.1"


@pytest.mark.parametrize("key", ["dsn", "password", "command", "data_dir", "DATABASE_URL"])
def test_profile_rejects_external_authority(key):
    with pytest.raises(ValueError, match="profile fields"):
        helper().Profile.from_mapping({key: "external"})


def test_profile_rejects_wrong_official_source():
    raw = {
        "root": "/var/tmp/quantmesh-owned-pg-example",
        "source_url": "https://example.com/arbitrary.tar.bz2",
        "source_sha256": "0" * 64,
        "binaries": {},
        "license_sha256": "0" * 64,
        "configure": [],
        "packages": [],
    }
    with pytest.raises(ValueError, match="official source"):
        helper().Profile.from_mapping(raw)


def test_owned_path_refuses_borrowed_directory_and_symlink(tmp_path):
    owned = tmp_path / "owned"
    borrowed = tmp_path / "borrowed"
    owned.mkdir()
    borrowed.mkdir()
    with pytest.raises(ValueError, match="owned path"):
        helper().owned_child(owned, borrowed)
    if sys.platform != "linux":
        return  # Native symlink ownership is verified on the admitted Linux runtime.
    link = owned / "link"
    link.symlink_to(borrowed, target_is_directory=True)
    with pytest.raises(ValueError, match="owned path"):
        helper().owned_child(owned, link)


def test_environment_has_no_ambient_credentials_or_tracing(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-must-not-leak")
    monkeypatch.setenv("DATABASE_URL", "synthetic-must-not-leak")
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    env = helper().private_environment(tmp_path)
    assert "OPENAI_API_KEY" not in env and "DATABASE_URL" not in env
    assert env["LANGSMITH_TRACING"] == "false"
    assert "synthetic-must-not-leak" not in str(env)


def test_password_file_private_and_removed_after_use(tmp_path):
    if sys.platform != "linux":
        with pytest.raises(ValueError, match="native Linux permissions"):
            with helper().password_input(tmp_path, "synthetic-password"):
                pytest.fail("non-Linux credential input must be refused")
        return
    with helper().password_input(tmp_path, "synthetic-password") as path:
        assert path.read_text() == "synthetic-password\n"
        assert path.stat().st_mode & 0o777 == 0o600
    assert not path.exists()


def test_output_redacts_password_and_raw_dsn():
    secret = "synthetic-password"
    dsn = "postgresql://fixture:" + secret + "@127.0.0.1:55432/postgres?sslmode=disable"
    output = helper().redact("failure " + dsn + " password=" + secret, secret, dsn)
    assert secret not in output and dsn not in output


def test_cleanup_rejects_pid_data_or_executable_mismatch(tmp_path):
    with pytest.raises(ValueError, match="ownership"):
        helper().verify_process_identity(os.getpid(), tmp_path, Path(sys.executable), "bad")


def test_collision_fails_without_fallback():
    import socket

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        with pytest.raises(ValueError, match="port collision"):
            helper().admit_port(listener.getsockname()[1])


def test_invalid_profile_cli_does_not_start_cluster_or_echo_values(tmp_path):
    path = tmp_path / "profile.json"
    path.write_text('{"dsn":"synthetic-private-dsn"}')
    completed = subprocess.run(
        [
            sys.executable,
            "tools/qualify_owned_postgres.py",
            "--profile",
            str(path),
            "--output",
            str(tmp_path / "proof"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    assert "owned fixture refused" in completed.stdout
    assert "synthetic-private-dsn" not in completed.stdout + completed.stderr
    assert not (tmp_path / "proof").exists()


def test_wrong_binary_bytes_refused_before_execution(tmp_path):
    prefix = tmp_path / "prefix/bin"
    prefix.mkdir(parents=True)
    (prefix / "postgres").write_bytes(b"unqualified binary")
    profile = helper().Profile(tmp_path, (("postgres", "0" * 64),))
    with pytest.raises(ValueError, match="wrong binary identity"):
        profile.verify_binary("postgres")


@pytest.mark.skipif(sys.platform != "linux", reason="actual /proc ownership requires Linux")
@pytest.mark.parametrize("mismatch", [None, "pid", "data", "executable", "hash"])
def test_actual_process_identity_and_cleanup_fences(tmp_path, mismatch):
    data = tmp_path / "cluster"
    data.mkdir()
    binary = Path(sys.executable).resolve()
    with subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(20)", "-D", str(data)]
    ) as process:
        try:
            pid = process.pid
            (data / "postmaster.pid").write_text(f"{pid}\n{data}\n")
            expected = helper().digest(binary)
            if mismatch == "pid":
                (data / "postmaster.pid").write_text(f"{pid + 1}\n{data}\n")
            if mismatch == "data":
                data = tmp_path
            if mismatch == "executable":
                binary = Path("/usr/bin/false")
            if mismatch == "hash":
                expected = "0" * 64
            if mismatch:
                with pytest.raises(ValueError, match="ownership"):
                    helper().verify_process_identity(pid, data, binary, expected)
            else:
                assert helper().verify_process_identity(pid, data, binary, expected).isdigit()
        finally:
            process.terminate()


@pytest.mark.parametrize("count", [25, 29, 31])
def test_gate_count_cannot_certify_partial_suite(count):
    with pytest.raises(ValueError, match="complete default gate"):
        helper().validate_gate_counts({"tests": count, "failures": 0, "errors": 0, "skipped": 0})


@pytest.mark.parametrize("key", ["failures", "errors", "skipped"])
def test_gate_refuses_failures_errors_and_skips(key):
    counts = {"tests": 30, "failures": 0, "errors": 0, "skipped": 0}
    counts[key] = 1
    with pytest.raises(ValueError, match="complete default gate"):
        helper().validate_gate_counts(counts)


@pytest.mark.skipif(sys.platform != "linux", reason="native symlink admission requires Linux")
@pytest.mark.parametrize("name", ["checkout", "venv"])
def test_runtime_paths_reject_borrowed_symlink(tmp_path, name):
    root = tmp_path / "owned"
    root.mkdir()
    borrowed = tmp_path / "borrowed"
    borrowed.mkdir()
    (root / name).symlink_to(borrowed, target_is_directory=True)
    with pytest.raises(ValueError, match="owned path"):
        helper().validate_runtime_paths(root)


def test_source_admission_allows_only_qualifier_additions(tmp_path):
    subprocess.run(["git", "init", str(tmp_path)], capture_output=True, check=True)
    (tmp_path / "baseline.txt").write_text("frozen source")
    subprocess.run(["git", "add", "baseline.txt"], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-m",
            "fixture baseline",
        ],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    env = helper().private_environment(tmp_path)
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools/qualify_owned_postgres.py").write_text("fixture qualifier")
    helper().validate_source_contents(tmp_path, env)
    (tmp_path / "pg8000.py").write_text("untracked shadow module")
    with pytest.raises(ValueError, match="frozen source"):
        helper().validate_source_contents(tmp_path, env)
    (tmp_path / "pg8000.py").unlink()
    (tmp_path / "baseline.txt").write_text("modified source")
    with pytest.raises(ValueError, match="frozen source"):
        helper().validate_source_contents(tmp_path, env)
