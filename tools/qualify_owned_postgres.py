"""Opt-in, Linux-only qualification of a privately built disposable PostgreSQL.

No download, arbitrary command, borrowed database or ambient credential support.
Profile construction verifies the official archive and private build receipt.
The default CLI performs preflight only; --owned-fixture starts a fresh cluster.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

SOURCE_URL = "https://ftp.postgresql.org/pub/source/v18.6/postgresql-18.6.tar.bz2"
SOURCE_SHA = "555610c24d53e4316da5b7d3fc25c279d96856d5e0e23ee308c328c5fa881d9f"
LICENSE_SHA = "3d6af92ff8a4c2cdf69afb1cf44edea727922f5cd0cf8b5f72b11cdecac8fdfd"
BASELINE = "42fbfa510b8153c7a2b3b6fd3e5d4851eda850e8"
BINARIES = {"postgres", "initdb", "pg_ctl", "pg_controldata"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_bind(host: str) -> str:
    if host != "127.0.0.1":
        raise ValueError("literal private loopback required")
    return host


def owned_child(root: Path, path: Path) -> Path:
    if not path.is_absolute():
        path = path.absolute()
    if not path.is_relative_to(root.absolute()) or path == root:
        raise ValueError("owned path required")
    current = path
    while current != root:
        if current.is_symlink():
            raise ValueError("owned path cannot contain symlinks")
        current = current.parent
    if root.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("owned path required")
    return path


def private_environment(root: Path) -> dict[str, str]:
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": str(root / "home"),
        "TMPDIR": str(root / "tmp"),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "LANGSMITH_TRACING": "false",
        "LANGCHAIN_TRACING_V2": "false",
    }


@contextmanager
def password_input(root: Path, password: str):
    if sys.platform != "linux":
        raise ValueError("private credential input requires native Linux permissions")
    fd, name = tempfile.mkstemp(prefix="pw-", dir=root)
    path = Path(name)
    try:
        os.chmod(path, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write(password + "\n")
        yield path
    finally:
        path.unlink(missing_ok=True)


def redact(text: str, password: str, dsn: str) -> str:
    return text.replace(dsn, "<fixture-dsn>").replace(password, "<fixture-secret>")


def admit_port(port: int) -> None:
    if not isinstance(port, int) or not 1024 <= port <= 65535:
        raise ValueError("private unprivileged port required")
    try:
        with socket.socket() as probe:
            probe.bind((validate_bind("127.0.0.1"), port))
    except OSError as exc:
        raise ValueError("port collision; no fallback permitted") from exc


def validate_gate_counts(counts: dict) -> None:
    if counts != {"tests": 30, "failures": 0, "errors": 0, "skipped": 0}:
        raise ValueError("complete default gate requires 30 tests without failures/errors/skips")


def validate_runtime_paths(root: Path) -> tuple[Path, Path]:
    return owned_child(root, root / "checkout"), owned_child(root, root / "venv")


def validate_source_contents(checkout: Path, env: dict) -> None:
    allowed = {
        "tools/qualify_owned_postgres.py",
        "tests/test_owned_postgres_fixture.py",
        "docs/runbooks/owned-postgres-fixture.md",
    }
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all", "-z"],
        cwd=checkout,
        env=env,
        capture_output=True,
        check=True,
    ).stdout
    for entry in status.split(b"\0"):
        if entry and (entry[:3] != b"?? " or os.fsdecode(entry[3:]) not in allowed):
            raise ValueError("frozen source admits only qualifier additions")


def verify_process_identity(pid: int, data: Path, executable: Path, expected_sha: str) -> str:
    """Fence cleanup/SQL by actual process executable, argv and PID-file identity."""
    try:
        proc = Path("/proc") / str(pid)
        if digest(executable) != expected_sha or (proc / "exe").resolve() != executable.resolve():
            raise ValueError("ownership executable mismatch")
        if proc.stat().st_uid != os.getuid():
            raise ValueError("ownership user mismatch")
        argv = (proc / "cmdline").read_bytes().split(b"\0")
        position = argv.index(b"-D")
        if Path(os.fsdecode(argv[position + 1])).resolve() != data.resolve():
            raise ValueError("ownership data mismatch")
        lines = (data / "postmaster.pid").read_text().splitlines()
        if int(lines[0]) != pid or Path(lines[1]).resolve() != data.resolve():
            raise ValueError("ownership PID-file mismatch")
        # Linux start ticks fence reuse of an otherwise identical PID.
        return (proc / "stat").read_text().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError, ValueError) as exc:
        raise ValueError("owned process ownership verification failed") from exc


@dataclass(frozen=True)
class Profile:
    root: Path
    binary_hashes: tuple[tuple[str, str], ...]

    @classmethod
    def from_mapping(cls, raw: dict) -> Profile:
        fields = {
            "root",
            "source_url",
            "source_sha256",
            "binaries",
            "license_sha256",
            "configure",
            "packages",
        }
        if not isinstance(raw, dict) or set(raw) != fields:
            raise ValueError("invalid profile fields")
        if raw["source_url"] != SOURCE_URL or raw["source_sha256"] != SOURCE_SHA:
            raise ValueError("wrong official source identity")
        if sys.platform != "linux" or os.getuid() == 0:
            raise ValueError("non-root native Linux required")
        root = Path(raw["root"])
        if (
            root.parent != Path("/var/tmp")
            or not root.name.startswith("quantmesh-owned-pg-")
            or root.is_symlink()
            or not root.is_dir()
            or root.stat().st_uid != os.getuid()
            or root.stat().st_mode & 0o777 != 0o700
        ):
            raise ValueError("private owned native root required")
        proof = owned_child(root, root / "build-proof")
        if digest(owned_child(root, proof / "postgresql-18.6.tar.bz2")) != SOURCE_SHA:
            raise ValueError("wrong official source bytes")
        if (
            raw["license_sha256"] != LICENSE_SHA
            or digest(proof / "POSTGRESQL-COPYRIGHT") != LICENSE_SHA
        ):
            raise ValueError("wrong PostgreSQL license identity")
        config = [
            "./configure",
            "--prefix=" + str(root / "prefix"),
            "--without-readline",
            "--without-zlib",
            "--without-icu",
        ]
        if raw["configure"] != config or set(raw["binaries"]) != BINARIES:
            raise ValueError("wrong private build configuration")
        hashes = tuple(sorted(raw["binaries"].items()))
        for name, expected in hashes:
            binary = owned_child(root, root / "prefix/bin" / name)
            if digest(binary) != expected:
                raise ValueError("wrong binary identity")
        env = private_environment(root)
        version = subprocess.run(
            [str(root / "prefix/bin/postgres"), "--version"],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        if version != "postgres (PostgreSQL) 18.6":
            raise ValueError("wrong binary version")
        return cls(root, hashes)

    def verify_binary(self, name: str) -> Path:
        path = owned_child(self.root, self.root / "prefix/bin" / name)
        if digest(path) != dict(self.binary_hashes)[name]:
            raise ValueError("wrong binary identity")
        return path


def run_fixture(profile: Profile, output: Path) -> int:
    """Execute unchanged default gate and stop only the verified owned postmaster."""
    root = profile.root
    checkout, venv = validate_runtime_paths(root)
    if Path(__file__).resolve().parents[1] != checkout.resolve():
        raise ValueError("fixture helper requires its own native checkout")
    if Path(sys.prefix).resolve() != venv.resolve() or sys.version_info[:2] != (3, 12):
        raise ValueError("own Linux CPython3.12 environment required")
    env = private_environment(root)
    source_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=checkout,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if source_sha != BASELINE:
        raise ValueError("wrong service source baseline")
    validate_source_contents(checkout, env)
    import pg8000
    import pg8000.dbapi
    import pydantic
    from pydantic import SecretStr

    for module in [pg8000, pydantic]:
        imported = owned_child(root, Path(module.__file__))
        if not imported.is_relative_to(venv / "lib/python3.12/site-packages"):
            raise ValueError("SQL driver/schema dependency outside owned environment")
    for name in ["home", "tmp"]:
        (root / name).mkdir(exist_ok=True, mode=0o700)
    data = owned_child(root, Path(tempfile.mkdtemp(prefix="cluster-", dir=root)))
    nonce = secrets.token_hex(24)
    (data / "fixture-owner").write_text(nonce)
    # initdb requires an empty directory; the marker belongs beside the cluster.
    marker = data.with_suffix(".owner")
    (data / "fixture-owner").rename(marker)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    admit_port(port)
    role, password = "qm_fixture_" + secrets.token_hex(8), secrets.token_hex(32)
    dsn = SecretStr(f"postgresql://{role}:{password}@127.0.0.1:{port}/postgres?sslmode=disable")
    receipt = {
        "source_commit": source_sha,
        "postgres_version": "18.6",
        "port": port,
        "data_directory": str(data),
        "binary_hashes": dict(profile.binary_hashes),
        "sql_driver": {"version": pg8000.__version__, "path": pg8000.__file__},
        "python": sys.version,
        "prefix": sys.prefix,
        "pid": None,
        "stopped": False,
    }

    def command(argv, name):
        result = subprocess.run(
            argv, env=env, cwd=checkout, capture_output=True, text=True, timeout=240, check=False
        )
        (output / name).write_text(
            redact(result.stdout + result.stderr, password, dsn.get_secret_value())
        )
        if result.returncode:
            raise ValueError("owned fixture command failed: " + name)
        return result.stdout

    pid, start_ticks = None, None
    try:
        with password_input(root, password) as pwfile:
            command(
                [
                    str(profile.verify_binary("initdb")),
                    "-D",
                    str(data),
                    "--username=" + role,
                    "--pwfile=" + str(pwfile),
                    "--auth=scram-sha-256",
                    "--no-locale",
                    "--encoding=UTF8",
                ],
                "initdb.log",
            )
        with (data / "postgresql.conf").open("a") as conf:
            conf.write(
                f"\nlisten_addresses='127.0.0.1'\nport={port}\nunix_socket_directories=''\nssl=off\n"
            )
        # Direct child launch gives ownership even when readiness fails.
        with (output / "postgres.log").open("w") as log:
            process = subprocess.Popen(
                [str(profile.verify_binary("postgres")), "-D", str(data)],
                env=env,
                cwd=root,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        pid = process.pid
        import time

        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise ValueError("owned postmaster exited; possible port collision")
            pidfile = data / "postmaster.pid"
            if pidfile.exists() and "ready" in pidfile.read_text().splitlines()[-1]:
                break
            time.sleep(0.1)
        else:
            raise ValueError("owned postmaster readiness timeout")
        start_ticks = verify_process_identity(
            pid, data, profile.verify_binary("postgres"), dict(profile.binary_hashes)["postgres"]
        )
        receipt.update(
            pid=pid,
            start_ticks=start_ticks,
            cluster_owner_sha256=hashlib.sha256(nonce.encode()).hexdigest(),
        )
        control = command([str(profile.verify_binary("pg_controldata")), str(data)], "control.log")
        cluster_id = next(
            line.split(":", 1)[1].strip()
            for line in control.splitlines()
            if line.startswith("Database system identifier:")
        )
        con = pg8000.dbapi.connect(
            user=role,
            password=password,
            host="127.0.0.1",
            port=port,
            database="postgres",
            timeout=5,
            ssl_context=False,
        )
        try:
            cur = con.cursor()
            cur.execute(
                "SELECT current_setting('data_directory'), current_setting('listen_addresses'), "
                "current_setting('port'), current_user, "
                "(SELECT system_identifier::text FROM pg_control_system()), version()"
            )
            identity = cur.fetchone()
            if identity[:5] != [str(data), "127.0.0.1", str(port), role, cluster_id]:
                raise ValueError("SQL cluster ownership identity mismatch")
            receipt["sql_identity"] = identity
        finally:
            con.close()
        env["QM_TEST_DISPOSABLE_POSTGRES_ACK"] = "owned-disposable"
        env["QM_TEST_DISPOSABLE_POSTGRES_DSN"] = dsn.get_secret_value()
        env["PYTHONPATH"] = os.pathsep.join(
            map(str, [checkout, checkout / "src", checkout / "services/research_agent/src"])
        )
        imported_receipt = json.loads(
            command(
                [
                    sys.executable,
                    "-c",
                    "import hashlib,json,sys; import qm_research_agent.store as store; "
                    "import quantmesh.research.job_store as protocol; "
                    "import quantmesh.research.jobs as schema; import pg8000; "
                    "from pathlib import Path; "
                    "print(json.dumps({'python':sys.version,'prefix':sys.prefix,"
                    "'modules':{m.__name__:{'path':m.__file__,"
                    "'sha256':hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest()} "
                    "for m in [store,protocol,schema,pg8000]}},indent=2))",
                ],
                "imports.json",
            )
        )
        expected_imports = {
            "qm_research_agent.store": checkout
            / "services/research_agent/src/qm_research_agent/store.py",
            "quantmesh.research.job_store": checkout / "src/quantmesh/research/job_store.py",
            "quantmesh.research.jobs": checkout / "src/quantmesh/research/jobs.py",
            "pg8000": Path(pg8000.__file__),
        }
        for module, expected in expected_imports.items():
            item = imported_receipt["modules"][module]
            if Path(item["path"]) != expected or item["sha256"] != digest(expected):
                raise ValueError("imported module outside frozen source/owned environment")
        result = subprocess.run(
            [
                sys.executable,
                "tools/research_service_gate.py",
                "--evidence-dir",
                str(output / "gate"),
            ],
            cwd=checkout,
            env=env,
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
        (output / "gate.log").write_text(
            redact(result.stdout + result.stderr, password, dsn.get_secret_value())
        )
        # Scrub any traceback literals saved by pytest before archiving evidence.
        for path in (output / "gate").rglob("*"):
            if path.is_file() and path.suffix in {".log", ".xml", ".json"}:
                path.write_text(redact(path.read_text(), password, dsn.get_secret_value()))
        receipt["gate_exit"] = result.returncode
        if result.returncode == 0:
            gate = json.loads((output / "gate/service-gate.json").read_text())
            validate_gate_counts(gate.get("tests"))
            junit_paths = list((output / "gate").glob("pytest-*.xml"))
            if len(junit_paths) != 1:
                raise ValueError("one authoritative JUnit receipt required")
            suites = ET.parse(junit_paths[0]).getroot()
            counts = {
                key: sum(int(s.attrib.get(key, 0)) for s in suites.iter("testsuite"))
                for key in ("tests", "failures", "errors", "skipped")
            }
            validate_gate_counts(counts)
            names = {case.attrib["name"] for case in suites.iter("testcase")}
            required = {
                "test_postgres_concurrency_fencing_reopen_recovery",
                "test_postgres_shared_slots_cancellation_and_analysis",
                "test_postgres_concurrent_reservations_cannot_exceed_allowance",
                "test_postgres_manifest_and_artifact_actual_bytes",
                "test_postgres_transaction_rollback_and_unknown_version",
            }
            if not required <= names:
                raise ValueError("all five real PostgreSQL cases required")
            receipt["tests"] = counts
        return result.returncode
    finally:
        if pid is not None and process.poll() is None:
            observed = verify_process_identity(
                pid,
                data,
                profile.verify_binary("postgres"),
                dict(profile.binary_hashes)["postgres"],
            )
            if (start_ticks is not None and observed != start_ticks) or marker.read_text() != nonce:
                raise ValueError("cleanup ownership mismatch; no stop issued")
            command(
                [str(profile.verify_binary("pg_ctl")), "-D", str(data), "-m", "fast", "-w", "stop"],
                "stop.log",
            )
            process.wait(timeout=20)
        receipt["stopped"] = pid is not None and process.poll() is not None
        (output / "fixture.json").write_text(json.dumps(receipt, indent=2))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--owned-fixture", action="store_true")
    args = parser.parse_args(argv)
    try:
        profile = Profile.from_mapping(json.loads(args.profile.read_text()))
        output = owned_child(profile.root, args.output)
        output.mkdir(mode=0o700)  # Fresh evidence only, never reuse a receipt.
        if not args.owned_fixture:
            (output / "preflight.json").write_text(
                json.dumps(
                    {
                        "source_sha256": SOURCE_SHA,
                        "binaries": dict(profile.binary_hashes),
                        "database_started": False,
                    }
                )
            )
            print("owned fixture preflight passed; database not started")
            return 0
        return run_fixture(profile, output)
    except (ValueError, OSError, subprocess.SubprocessError):
        # Never echo caller-controlled values, argv or credentials.
        print("owned fixture refused; inspect owned redacted receipts")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
