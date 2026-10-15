"""Opt-in encrypted PG/artifact recovery on NEW owned native local fixtures.

Preflight starts no database and writes nothing. No DSN, repository, password,
command, cloud URL or borrowed restore target is accepted. Fixture reports are
synthetic storage evidence, never numerical Worker or production proof.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import secrets
import selectors
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA = "a645a8bde2b439587f736a6a6875e4ffae77265cdcc2900d0b2def43f5f0de18"
PROTOCOL = "454cce6bd355465e48a59cb61fbbacb775776cb28c41826e54aff554cf2ccae1"
BASELINE = "0503d49a51fdd20b08c809f4289092fbac01ebf9"
TOOL_ADMISSION = "04f5852137b8e35503a1f12c8d431cf747cf258371f8ec7b7eb77c3dd41b8826"
RESTIC_SHA = "20d4142678d0d95ec11a4759def1b73fd9190abc9ca19e4b62d067c0b387e639"
RESTIC_COMPRESSED_SHA = "f415415624dcc452f2a02b8c33641791a8c6d6d3b65bbb3543fcf9a25151585c"
FINGERPRINT = "CF8F18F2844575973F79D4E191A6868BD3F7A907"
PG_HASHES = {
    "postgres": "4cd5ef0c0632e8da70fd6d7a62a9e02a6df00f3517b1b5720511db199d825d08",
    "initdb": "ec107de4c2da562b0001811e63b79793433c28267e35883a80fd55fba7d019e2",
    "pg_ctl": "4122dcb4375873bca2dcd2f83242614c21f28d4ebd872d06ab702a0ab26ae159",
    "pg_controldata": "a8352343c4773b7138e3c9547223e68252021fcde0ec696575f30c37d8bb06ff",
    "pg_dump": "137cf7c068b3459f5205f97f27cd206b537228e031d721f52535daf29c0ab6f8",
    "pg_restore": "cb92c83f39bf0087f9ba1b65cd2763d86ac6695a8f46e343db9505ee88f1bf29",
}
MAX_FILE = 32 * 1024 * 1024
MAX_OUTPUT = 2 * 1024 * 1024
OWNED_FILES = {
    "tools/qualify_research_backup.py",
    "tests/test_research_backup_qualification.py",
    "docs/runbooks/owned-research-backup.md",
}


class NegativeRefused(ValueError):
    """Only a deliberately observed, attributed negative can qualify."""


class FixtureDeadline:
    """Own process wall timer covers SQL/filesystem work as well as commands."""

    def __init__(self, seconds, *, defer=lambda: False):
        if sys.platform != "linux" or signal.getitimer(signal.ITIMER_REAL)[0]:
            raise ValueError("owned wall timer unavailable")
        self.previous = signal.getsignal(signal.SIGALRM)
        self.closed = False
        self.expired = False

        def expired(signum, frame):
            signal.setitimer(signal.ITIMER_REAL, 0)
            self.expired = True
            # A spawned child must be registered before an interruption escapes.
            if not defer():
                raise ValueError("whole fixture deadline")

        signal.signal(signal.SIGALRM, expired)
        signal.setitimer(signal.ITIMER_REAL, seconds)

    def close(self):
        if not self.closed:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, self.previous)
            self.closed = True


class ServerLog:
    """Drain a known child's log pipe; never cap its WAL/data files."""

    def __init__(self, source, path):
        self.failed = False
        self.size = 0

        def drain():
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as stream:
                    while chunk := os.read(source.fileno(), 65536):
                        accepted = chunk[: max(0, MAX_OUTPUT - self.size)]
                        stream.write(accepted)
                        self.size += len(accepted)
                        if len(accepted) != len(chunk):
                            self.failed = True
            except OSError:
                self.failed = True
            finally:
                source.close()

        self.thread = threading.Thread(target=drain, daemon=True)
        self.thread.start()

    def finish(self):
        self.thread.join(timeout=2)
        if self.thread.is_alive():
            self.failed = True


def crypto_refusal(kind, code, raw):
    expected = {
        "wrong_key": (12, b"wrong password or no key found"),
        "corrupt_cipher_copy": (1, b"ciphertext verification failed"),
    }
    if kind not in expected or code != expected[kind][0] or expected[kind][1] not in raw.lower():
        raise ValueError("crypto failure not attributed")
    events = [decode(line) for line in raw.splitlines()]
    if not any(
        event.get("message_type") == "exit_error" and event.get("code") == code for event in events
    ):
        raise ValueError("actual crypto exit evidence required")
    raise NegativeRefused(kind)


def canonical(raw):
    return json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_private(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)


def decode(raw):
    def unique(pairs):
        result = {}
        for name, value in pairs:
            if name in result:
                raise ValueError("duplicate JSON field")
            result[name] = value
        return result

    return json.loads(raw, object_pairs_hook=unique)


def owned_path(root: Path, path: Path) -> Path:
    root = root.absolute()
    path = path if path.is_absolute() else root / path
    if ".." in path.parts or path == root or not path.is_relative_to(root):
        raise ValueError("owned descendant required")
    for component in (path, *path.parents):
        if component.is_symlink():
            raise ValueError("linked path refused")
        if component == root:
            break
    if root.is_symlink() or path.resolve() != path.absolute():
        raise ValueError("owned path refused")
    return path


def fresh_directory(root: Path, path: Path) -> Path:
    path = owned_path(root, path)
    if path.exists():
        raise ValueError("fresh directory required")
    path.mkdir(mode=0o700)
    return path


def read_owned(root: Path, path: Path, *, private=True, limit=MAX_FILE) -> bytes:
    """No-follow descriptor walk, owner/link/mode/size/replacement checks."""
    path = owned_path(root, path)
    directory_fd = fd = None
    try:
        directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        for part in path.relative_to(root).parts[:-1]:
            next_fd = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory_fd
            )
            os.close(directory_fd)
            directory_fd = next_fd
            info = os.fstat(directory_fd)
            if info.st_uid != os.getuid() or info.st_mode & 0o022:
                raise ValueError("directory ownership refused")
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or before.st_nlink != 1
            or before.st_mode & 0o022
            or (private and stat.S_IMODE(before.st_mode) != 0o600)
            or not 0 < before.st_size <= limit
        ):
            raise ValueError("owned regular bytes refused")
        raw = bytearray()
        while len(raw) <= limit:
            chunk = os.read(fd, min(65536, limit + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        after = os.fstat(fd)
        named = os.stat(path.name, dir_fd=directory_fd, follow_symlinks=False)

        def identity(info):
            return (
                info.st_dev,
                info.st_ino,
                info.st_uid,
                info.st_mode,
                info.st_nlink,
                info.st_size,
                info.st_mtime_ns,
                info.st_ctime_ns,
            )

        if identity(before) != identity(after) or identity(after) != identity(named):
            raise ValueError("owned bytes changed during read")
        parent, opened = path.parent.stat(follow_symlinks=False), os.fstat(directory_fd)
        if (parent.st_dev, parent.st_ino) != (opened.st_dev, opened.st_ino):
            raise ValueError("owned directory changed during read")
        if len(raw) != before.st_size:
            raise ValueError("owned bytes incomplete")
        return bytes(raw)
    except OSError:
        raise ValueError("owned bytes unavailable") from None
    finally:
        if fd is not None:
            os.close(fd)
        if directory_fd is not None:
            os.close(directory_fd)


@dataclass(frozen=True)
class Profile:
    root: Path
    expected_build: str

    @classmethod
    def from_mapping(cls, raw):
        if not isinstance(raw, dict) or set(raw) != {"schema_version", "root", "expected_build"}:
            raise ValueError("profile fields refused")
        if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
            raise ValueError("profile version refused")
        if not isinstance(raw["expected_build"], str) or not re.fullmatch(
            r"[0-9a-f]{40}", raw["expected_build"]
        ):
            raise ValueError("build identity required")
        if sys.platform != "linux" or os.getuid() == 0 or not isinstance(raw["root"], str):
            raise ValueError("non-root native Linux required")
        from qm_research_agent.runtime import _directory, _native_filesystem

        root = _directory(Path(raw["root"]))
        if root.parent != Path("/var/tmp") or not root.name.startswith("quantmesh-backup-"):
            raise ValueError("new owned native root required")
        if not _native_filesystem(root):
            raise ValueError("native persistent filesystem required")
        admit_tools(root)
        return cls(root, raw["expected_build"])


def bare_environment(root):
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": str(root / "home"),
        "TMPDIR": str(root / "tmp"),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "LANGSMITH_TRACING": "false",
        "LANGCHAIN_TRACING_V2": "false",
        "LD_LIBRARY_PATH": str(root / "prefix/lib"),
    }


def admit_tools(root):
    """Pins actual archived audit bytes, never caller success booleans."""
    raw = read_owned(root, root / "tool-admission.json", private=False)
    if hashlib.sha256(raw).hexdigest() != TOOL_ADMISSION:
        raise ValueError("tool/notice qualification mismatch")
    audit = decode(raw)
    if audit["modules"] != 79 or audit["notices"] != 98 or audit["fingerprint"] != FINGERPRINT:
        raise ValueError("external-tool closure refused")
    for name, evidence in audit["files"].items():
        path = root / name
        if "link" in evidence:
            if not path.is_symlink() or os.readlink(path) != evidence["link"]:
                raise ValueError("private tool link mismatch")
            if not path.resolve().is_relative_to(root):
                raise ValueError("borrowed tool link refused")
        else:
            data = read_owned(root, path, private=False, limit=80 * 1024 * 1024)
            if (
                len(data) != evidence["size"]
                or hashlib.sha256(data).hexdigest() != evidence["sha256"]
            ):
                raise ValueError("actual tool or license bytes mismatch")
    for name, expected in {**PG_HASHES, "restic": RESTIC_SHA}.items():
        path = root / ("restic" if name == "restic" else "prefix/bin/" + name)
        if digest(path) != expected:
            raise ValueError("binary pin mismatch")
    result = subprocess.run(
        [
            "/usr/bin/gpgv",
            "--homedir",
            "/nonexistent",
            "--status-fd",
            "1",
            "--keyring",
            str(root / "audit/trustedkeys.gpg"),
            str(root / "audit/SHA256SUMS.asc"),
            str(root / "audit/SHA256SUMS"),
        ],
        env=bare_environment(root),
        capture_output=True,
        timeout=10,
        check=False,
    )
    if result.returncode or b"VALIDSIG " + FINGERPRINT.encode() not in result.stdout:
        raise ValueError("trusted official checksum signature required")
    if digest(root / "audit/restic.bz2") != RESTIC_COMPRESSED_SHA:
        raise ValueError("compressed official asset mismatch")


def admit_runtime(profile):
    from qm_research_agent.runtime import _admit_runtime, _git

    from quantmesh.research.job_store import protocol_digest
    from quantmesh.research.jobs import schema_digest

    checkout = owned_path(profile.root, profile.root / "checkout")
    if (
        Path(__file__).absolute().parents[1] != checkout
        or Path(sys.prefix) != profile.root / "venv"
    ):
        raise ValueError("own native checkout and fresh environment required")
    actual, lock = _admit_runtime(profile.expected_build)
    _git(checkout, "merge-base", "--is-ancestor", BASELINE, actual)
    names = set(_git(checkout, "diff", "--name-only", BASELINE, actual).decode().splitlines())
    if names != OWNED_FILES or schema_digest() != SCHEMA or protocol_digest() != PROTOCOL:
        raise ValueError("frozen source or contract mismatch")
    return {
        "actual_build": actual,
        "lock_sha256": lock,
        "schema_digest": SCHEMA,
        "protocol_digest": PROTOCOL,
        "python": sys.version,
        "prefix": sys.prefix,
    }


def validate_bundle(root, manifest_sha):
    raw = read_owned(root, root / "manifest.json")
    if hashlib.sha256(raw).hexdigest() != manifest_sha:
        raise ValueError("manifest substitution refused")
    m = decode(raw)
    if set(m) != {
        "schema_version",
        "schema_digest",
        "protocol_digest",
        "research_schema",
        "dump_sha256",
        "dump_size",
        "state",
        "artifacts",
    }:
        raise ValueError("manifest fields refused")
    if (
        type(m["schema_version"]) is not int
        or m["schema_version"] != 1
        or m["schema_digest"] != SCHEMA
        or m["protocol_digest"] != PROTOCOL
        or m["research_schema"] != "qm_research"
        or m["state"]["versions"] != [[1]]
    ):
        raise ValueError("unknown snapshot schema/protocol")
    if not 1 <= len(m["state"]["jobs"]) <= 128 or not 1 <= len(m["artifacts"]) <= 512:
        raise ValueError("nonempty bounded research snapshot required")
    dump = read_owned(root, root / "research.dump")
    if len(dump) != m["dump_size"] or hashlib.sha256(dump).hexdigest() != m["dump_sha256"]:
        raise ValueError("dump substitution refused")
    keys, job_ids = set(), {row[0] for row in m["state"]["jobs"]}
    for ref in m["artifacts"]:
        if set(ref) != {"job_id", "object_key", "sha256", "byte_size"}:
            raise ValueError("artifact manifest fields refused")
        key = ref["object_key"]
        if (
            ref["job_id"] not in job_ids
            or not key.startswith(ref["job_id"] + "/")
            or not re.fullmatch(r"[0-9a-f]{64}", ref["sha256"])
            or key in keys
        ):
            raise ValueError("artifact ownership/identity mismatch")
        keys.add(key)
        data = read_owned(root, root / "artifacts" / key)
        if len(data) != ref["byte_size"] or hashlib.sha256(data).hexdigest() != ref["sha256"]:
            raise ValueError("artifact substitution refused")
    actual = set()
    for path in (root / "artifacts").rglob("*"):
        if path.is_symlink():
            raise ValueError("linked artifact refused")
        if path.is_file():
            actual.add(path.relative_to(root / "artifacts").as_posix())
    if actual != keys:
        raise ValueError("exact referenced artifact set required")
    return m


def backup_receipt(root, manifest_sha, encrypted):
    if (
        not re.fullmatch(r"[0-9a-f]{64}", encrypted.get("snapshot_id", ""))
        or encrypted.get("backup_exit") != 0
        or encrypted.get("check_exit") != 0
    ):
        raise ValueError("actual encrypted snapshot/check required")
    m = validate_bundle(root, manifest_sha)
    return {
        "schema_version": 1,
        "scope": "OWNED_LOCAL_FIXTURE_ONLY",
        "production_release_qualified": False,
        "snapshot_id": encrypted["snapshot_id"],
        "manifest_sha256": manifest_sha,
        "dump_sha256": m["dump_sha256"],
        "artifact_count": len(m["artifacts"]),
        "job_count": len(m["state"]["jobs"]),
    }


@dataclass(repr=False)
class CommandProcess:
    process: subprocess.Popen
    executable: Path
    binary_sha: str
    argv: list
    nonce: str
    ticks: str | None = None
    stopped: bool = False

    def close(self):
        process = self.process
        if process.poll() is None:
            if self.ticks is None:
                raise ValueError("fixed command kernel identity unknown; cleanup pending")
            proc = Path("/proc") / str(process.pid)
            if (
                process_ticks(process.pid) != self.ticks
                or proc.stat().st_uid != os.getuid()
                or (proc / "exe").resolve() != self.executable
                or digest(proc / "exe") != self.binary_sha
                or (proc / "cmdline").read_bytes().split(b"\0")[:-1]
                != list(map(os.fsencode, self.argv))
                or b"QM_BACKUP_COMMAND_OWNER=" + self.nonce.encode()
                not in (proc / "environ").read_bytes().split(b"\0")
            ):
                raise ValueError("fixed command cleanup ownership pending")
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                if process_ticks(process.pid) != self.ticks:
                    raise ValueError("fixed command PID identity changed") from None
                process.kill()
                process.wait(timeout=2)
        process.stdout.close()
        self.stopped = process.poll() is not None


def bounded_process(argv, environment, cwd, timeout, log=None, *, owner=None):
    """Limit the output stream, not PostgreSQL WAL/data writes."""
    nonce = secrets.token_hex(24)
    executable = Path(argv[0]).resolve()
    binary_sha = digest(executable)
    deadline = time.monotonic() + timeout
    output = bytearray()
    handle = None
    try:
        if owner:
            owner.registering = True
        try:
            process = subprocess.Popen(
                argv,
                cwd=cwd,
                env={**environment, "QM_BACKUP_COMMAND_OWNER": nonce},
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            handle = CommandProcess(process, executable, binary_sha, argv, nonce)
            if owner:
                owner.command_processes.append(handle)
            handle.ticks = process_ticks(process.pid)
        finally:
            if owner:
                owner.registering = False
                owner.check_deadline()
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                if time.monotonic() >= deadline:
                    raise ValueError("fixed command deadline")
                for key, _ in selector.select(min(0.1, deadline - time.monotonic())):
                    chunk = os.read(key.fd, min(65536, MAX_OUTPUT + 1 - len(output)))
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    if len(output) + len(chunk) > MAX_OUTPUT:
                        raise ValueError("fixed command output cap")
                    output.extend(chunk)
                    if log:
                        log.write(chunk)
        return process.wait(timeout=max(0.01, deadline - time.monotonic())), bytes(output)
    finally:
        if handle:
            handle.close()


class Commands:
    """Fixed private binaries, bounded wall/output, no shell or secret output."""

    def __init__(self, root, output):
        self.root, self.output = root, output
        self.deadline = time.monotonic() + 240
        self.receipts = []
        self.clusters = []
        self.command_processes = []
        self.guard = None
        self.registering = False

    def check_deadline(self):
        if (self.guard and self.guard.expired) or time.monotonic() >= self.deadline:
            raise ValueError("whole fixture deadline")
        if any(cluster.server_log and cluster.server_log.failed for cluster in self.clusters):
            raise ValueError("owned server output cap")

    def run(self, tool, args, *, env_extra=None, cwd=None, failure=False):
        if tool not in {*PG_HASHES, "restic"}:
            raise ValueError("unknown external tool")
        binary = self.root / ("restic" if tool == "restic" else "prefix/bin/" + tool)
        if digest(binary) != (RESTIC_SHA if tool == "restic" else PG_HASHES[tool]):
            raise ValueError("binary changed before execution")
        self.check_deadline()

        path = self.output / f"command-{len(self.receipts) + 1:03d}.log"
        with path.open("xb") as log:
            try:
                code, raw = bounded_process(
                    [str(binary), *args],
                    {**bare_environment(self.root), **(env_extra or {})},
                    cwd or self.root,
                    max(0.1, min(40, self.deadline - time.monotonic())),
                    log,
                    owner=self,
                )
            except (ValueError, OSError, subprocess.SubprocessError):
                self.receipts.append(
                    {
                        "tool": tool,
                        "exit": None,
                        "log": path.name,
                        "failure": "command_bound_or_ownership_refused",
                    }
                )
                raise
        self.receipts.append(
            {"tool": tool, "exit": code, "output_size": len(raw), "log": path.name}
        )
        if code and not failure:
            raise ValueError("fixed external command failed")
        return code, raw


def process_ticks(pid):
    return (Path("/proc") / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()[19]


@dataclass(repr=False)
class Cluster:
    commands: Commands = field(repr=False)
    home: Path
    data: Path
    role: str
    password: str = field(repr=False)
    nonce: str = field(repr=False)
    port: int
    process: subprocess.Popen = field(repr=False)
    ticks: str | None
    system_id: str = ""
    stopped: bool = False
    server_log: ServerLog | None = field(default=None, repr=False)

    @classmethod
    def start(cls, commands, name):
        from tools.qualify_owned_postgres import verify_process_identity

        home = fresh_directory(commands.output, commands.output / name)
        data = home / "data"
        password, nonce = secrets.token_hex(32), secrets.token_hex(24)
        role = "fixture_" + secrets.token_hex(8)
        write_private(home / "owner", nonce.encode())
        write_private(home / "init-password", password.encode())
        try:
            commands.run(
                "initdb",
                [
                    "-D",
                    str(data),
                    "-L",
                    str(commands.root / "prefix/share/postgresql"),
                    "--username=" + role,
                    "--pwfile=" + str(home / "init-password"),
                    "--auth=scram-sha-256",
                    "--no-locale",
                    "--encoding=UTF8",
                ],
            )
        finally:
            (home / "init-password").unlink(missing_ok=True)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        with (data / "postgresql.conf").open("a") as stream:
            stream.write(
                f"\nlisten_addresses='127.0.0.1'\nport={port}\nunix_socket_directories=''\n"
                "ssl=off\nlog_statement='none'\nlog_min_error_statement=panic\n"
            )
        write_private(home / "pgpass", f"127.0.0.1:{port}:postgres:{role}:{password}\n".encode())
        cluster = None
        ready = False
        try:
            commands.registering = True
            try:
                process = subprocess.Popen(
                    [str(commands.root / "prefix/bin/postgres"), "-D", str(data)],
                    env={**bare_environment(commands.root), "QM_BACKUP_OWNER": nonce},
                    cwd=home,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )
                cluster = cls(commands, home, data, role, password, nonce, port, process, None)
                if hasattr(commands, "clusters"):
                    commands.clusters.append(cluster)
                cluster.ticks = process_ticks(process.pid)
            finally:
                commands.registering = False
                if hasattr(commands, "check_deadline"):
                    commands.check_deadline()
            cluster.server_log = ServerLog(process.stdout, home / "postgres.log")
            deadline = min(commands.deadline, time.monotonic() + 15)
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise ValueError("new postmaster exited")
                pidfile = data / "postmaster.pid"
                if pidfile.exists() and pidfile.read_text().splitlines()[-1].strip() == "ready":
                    break
                time.sleep(0.05)
            else:
                raise ValueError("new postmaster readiness deadline")
            ticks = verify_process_identity(
                process.pid, data, commands.root / "prefix/bin/postgres", PG_HASHES["postgres"]
            )
            if ticks != cluster.ticks:
                raise ValueError("postmaster PID reused")
            _, raw = commands.run("pg_controldata", [str(data)])
            cluster.system_id = next(
                line.split(":", 1)[1].strip()
                for line in raw.decode().splitlines()
                if line.startswith("Database system identifier:")
            )
            cluster.verify_sql()
            ready = True
            return cluster
        except BaseException:
            if cluster:
                cluster.stop()
            raise
        finally:
            if not ready:
                (home / "pgpass").unlink(missing_ok=True)

    def verify(self):
        if self.ticks is None:
            raise ValueError("kernel start identity unknown; cleanup pending")
        proc = Path("/proc") / str(self.process.pid)
        if (
            self.process.poll() is not None
            or process_ticks(self.process.pid) != self.ticks
            or proc.stat().st_uid != os.getuid()
            or (proc / "exe").resolve() != self.commands.root / "prefix/bin/postgres"
            or digest(proc / "exe") != PG_HASHES["postgres"]
            or (proc / "cmdline").read_bytes().split(b"\0")[:-1]
            != [
                os.fsencode(self.commands.root / "prefix/bin/postgres"),
                b"-D",
                os.fsencode(self.data),
            ]
            or b"QM_BACKUP_OWNER=" + self.nonce.encode()
            not in (proc / "environ").read_bytes().split(b"\0")
            or read_owned(self.home, self.home / "owner") != self.nonce.encode()
        ):
            raise ValueError("owned process identity refused; no stop issued")

    def connection(self):
        import pg8000.dbapi

        self.commands.check_deadline()
        self.verify()
        return pg8000.dbapi.connect(
            user=self.role,
            password=self.password,
            host="127.0.0.1",
            port=self.port,
            database="postgres",
            timeout=5,
            ssl_context=False,
        )

    def verify_sql(self):
        con = self.connection()
        try:
            cursor = con.cursor()
            cursor.execute(
                "SELECT current_setting('data_directory'), current_setting('listen_addresses'), "
                "current_setting('port'), current_user, "
                "(SELECT system_identifier::text FROM pg_control_system())"
            )
            if list(cursor.fetchone()) != [
                str(self.data),
                "127.0.0.1",
                str(self.port),
                self.role,
                self.system_id,
            ]:
                raise ValueError("actual SQL cluster identity refused")
        finally:
            con.close()

    def pg_args(self):
        self.verify_sql()
        return [
            "--host=127.0.0.1",
            "--port=" + str(self.port),
            "--username=" + self.role,
            "--dbname=postgres",
            "--no-password",
        ]

    def store(self, lake, artifacts):
        from pydantic import SecretStr
        from qm_research_agent.store import PostgresJobStore

        self.verify_sql()
        return PostgresJobStore(
            SecretStr(
                f"postgresql://{self.role}:{self.password}@127.0.0.1:"
                f"{self.port}/postgres?sslmode=disable"
            ),
            lake_root=lake,
            artifact_root=artifacts,
        )

    def stop(self):
        if self.stopped:
            return
        try:
            if self.process.poll() is None:
                self.verify()
                self.process.send_signal(signal.SIGINT)
                self.process.wait(timeout=15)
            self.stopped = self.process.poll() is not None
        finally:
            (self.home / "pgpass").unlink(missing_ok=True)
            if self.server_log:
                self.server_log.finish()


def sql_state(connection):
    cur = connection.cursor()
    cur.execute("SET LOCAL statement_timeout='5s'")
    queries = {
        "versions": "SELECT version FROM qm_research.qm_schema ORDER BY version",
        "jobs": (
            "SELECT job_id,operator_id,idempotency_key,payload,sequence "
            "FROM qm_research.jobs ORDER BY sequence"
        ),
        "outbox": (
            "SELECT job_id,lease,attempt,sequence "
            "FROM qm_research.analysis_outbox ORDER BY sequence"
        ),
        "effects": (
            "SELECT job_id,digest,price,status,response,checkpoint "
            "FROM qm_research.model_effects ORDER BY job_id,digest"
        ),
    }
    result = {}
    for name, query in queries.items():
        cur.execute(query)
        rows = cur.fetchmany(129)
        if len(rows) > 128:
            raise ValueError("bounded SQL fixture only")
        result[name] = [list(row) for row in rows]
    if result["versions"] != [[1]]:
        raise ValueError("unknown actual SQL schema")
    return result


def current_state(cluster):
    con = cluster.connection()
    try:
        con.cursor().execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        return sql_state(con)
    finally:
        con.close()


def checked_references(store, state):
    from quantmesh.research.jobs import JobRecord, canonical_request_digest

    refs = []
    for row in state["jobs"]:
        record = JobRecord.model_validate_json(row[3])
        if (
            record.job_id != row[0]
            or record.operator_id != row[1]
            or record.idempotency_key != row[2]
            or canonical_request_digest(record.request) != record.request_digest
        ):
            raise ValueError("captured job/request/idempotency mismatch")
        if record.state == "succeeded":
            store._artifacts(record, record.artifacts)
        references = list(record.artifacts)
        if record.analysis and record.analysis.output_artifact:
            references.append(record.analysis.output_artifact)
        for ref in references:
            raw = read_owned(store.artifact_root, store.artifact_root / ref.object_key)
            if raw != store._artifact_bytes(record, ref):
                raise ValueError("captured artifact bytes inconsistent")
            refs.append((record.job_id, ref, raw))
    if not refs or not any(ref.kind == "report" for _, ref, _ in refs):
        raise ValueError("nonempty published report required")
    return refs


def capture(cluster, store, commands, payload):
    fresh_directory(commands.output, payload)
    fresh_directory(payload, payload / "artifacts")
    con = cluster.connection()
    try:
        cur = con.cursor()
        cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        cur.execute("SELECT pg_export_snapshot()")
        snapshot = cur.fetchone()[0]
        state = sql_state(con)
        commands.run(
            "pg_dump",
            [
                *cluster.pg_args(),
                "--format=custom",
                "--compress=0",
                "--no-owner",
                "--no-privileges",
                "--schema=qm_research",
                "--snapshot=" + snapshot,
                "--file=" + str(payload / "research.dump"),
            ],
            env_extra={"PGPASSFILE": str(cluster.home / "pgpass")},
        )
        refs = checked_references(store, state)
        manifest_refs = []
        for job_id, ref, raw in refs:
            path = owned_path(payload, payload / "artifacts" / ref.object_key)
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            write_private(path, raw)
            manifest_refs.append(
                {
                    "job_id": job_id,
                    "object_key": ref.object_key,
                    "sha256": ref.sha256,
                    "byte_size": ref.byte_size,
                }
            )
        raw_dump = read_owned(payload, payload / "research.dump")
        manifest = {
            "schema_version": 1,
            "schema_digest": SCHEMA,
            "protocol_digest": PROTOCOL,
            "research_schema": "qm_research",
            "dump_sha256": hashlib.sha256(raw_dump).hexdigest(),
            "dump_size": len(raw_dump),
            "state": state,
            "artifacts": manifest_refs,
        }
        write_private(payload / "manifest.json", canonical(manifest))
        anchor = digest(payload / "manifest.json")
        validate_bundle(payload, anchor)
        return anchor
    finally:
        con.close()


def fixture_inputs(checkout, lake):
    def load(name, relative):
        spec = importlib.util.spec_from_file_location(name, checkout / relative)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    fixtures = load("tests.research_fixtures", "tests/research_fixtures.py")
    sys.modules["tests.research_fixtures"] = fixtures
    requests = load("test_research_jobs", "tests/test_research_jobs.py")
    sys.modules["test_research_jobs"] = requests
    publisher = load("backup_contract_fixture", "services/research_agent/tests/conftest.py")
    fixtures.pinned_lake(lake)
    return requests.request_for, publisher.publish


def restic(commands, repo, key, args, *, failure=False):
    owned_path(commands.output, repo)
    read_owned(commands.output, key, limit=256)
    return commands.run(
        "restic",
        ["--repo", str(repo), "--password-file", str(key), "--no-cache", "--json", *args],
        cwd=commands.output,
        failure=failure,
    )


def expect_failure(name, action, receipt, source, unchanged):
    try:
        action()
    except NegativeRefused as error:
        if str(error) != name:
            raise ValueError("negative attribution mismatch") from None
        if current_state(source) != unchanged:
            raise ValueError("negative witness changed source") from None
        receipt["negative_witnesses"][name] = {"refused": True, "source_unchanged": True}
        return
    raise ValueError("negative witness unexpectedly accepted")


def corrupt_copy(root, repository):
    """Mutate one encrypted object only in a freshly allocated owned copy."""
    import shutil

    owned_path(root, repository)
    for path in repository.rglob("*"):
        if path.is_symlink():
            raise ValueError("linked repository refused")
    clone = owned_path(root, root / "corrupt-repository")
    shutil.copytree(repository, clone)  # Fails if target already exists.
    pack = next(path for path in sorted((clone / "data").rglob("*")) if path.is_file())
    raw = read_owned(clone, pack, private=False)
    pack.chmod(0o600)  # Restic's immutable originals stay untouched/read-only.
    pack.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
    return clone, pack.relative_to(clone).as_posix()


def run_fixture(profile, output):
    from decimal import Decimal

    from qm_research_agent.budgets import EffectLedger

    runtime = admit_runtime(profile)
    old_umask = os.umask(0o077)
    commands = Commands(profile.root, fresh_directory(profile.root, output))
    receipt = {
        "scope": "OWNED_LOCAL_FIXTURE_ONLY",
        "production_release_qualified": False,
        "runtime": runtime,
        "negative_witnesses": {},
        "clusters": [],
        "passed": False,
    }
    clusters = commands.clusters
    guard = FixtureDeadline(
        max(0.01, commands.deadline - time.monotonic()), defer=lambda: commands.registering
    )
    commands.guard = guard
    try:
        lake = fresh_directory(output, output / "lake")
        artifacts = fresh_directory(output, output / "source-artifacts")
        source = Cluster.start(commands, "source")
        sibling = Cluster.start(commands, "sibling")
        request_for, publish = fixture_inputs(profile.root / "checkout", lake)
        store = source.store(lake, artifacts)
        effects = EffectLedger(store)
        request = request_for(lake, analysis_requested=True)
        success = store.submit("operator", "fixture-success", request)
        ref = publish(store, success)
        if (
            decode(read_owned(artifacts, artifacts / ref.object_key))["result"].get("fixture")
            is not True
        ):
            raise ValueError("fixture result label required")
        lease = store.claim_analysis("fixture-analyst", store._clock())
        for n in (1, 2):
            if not effects.reserve_call(
                success.job_id, f"{n:064x}", Decimal("0"), request.budget, lease
            ):
                raise ValueError("actual SQL effect reservation failed")
        if not effects.response(lease, f"{1:064x}", '{"fixture":true}'):
            raise ValueError("fixture completed-effect SQL witness failed")
        queued = store.submit("operator", "fixture-queued", request_for(lake))
        cancelled = store.submit("operator", "fixture-cancelled", request_for(lake))
        store.request_cancel("operator", cancelled.job_id)
        payload = output / "payload"
        anchor = capture(source, store, commands, payload)
        captured = validate_bundle(payload, anchor)
        repo = fresh_directory(output, output / "repository")
        key = output / "repository-password"
        write_private(key, secrets.token_hex(32).encode())
        restic(commands, repo, key, ["init"])
        rc, raw = restic(commands, repo, key, ["backup", "--host=owned-fixture", "payload"])
        summary = next(
            decode(line)
            for line in raw.splitlines()
            if line.startswith(b'{"message_type":"summary"')
        )
        check_exit, _ = restic(commands, repo, key, ["check", "--read-data"])
        encrypted = {
            "snapshot_id": summary["snapshot_id"],
            "backup_exit": rc,
            "check_exit": check_exit,
        }
        backup = backup_receipt(payload, anchor, encrypted)
        write_private(output / "backup-receipt.json", canonical(backup))
        receipt["backup"] = backup
        store.request_cancel("operator", queued.job_id)
        store.submit("operator", "after-snapshot", request_for(lake))
        advanced = current_state(source)
        write_private(output / "source-state-after.json", canonical(advanced))
        if advanced == captured["state"]:
            raise ValueError("source did not advance after capture")
        recovered = fresh_directory(output, output / "recovered")
        restic(commands, repo, key, ["restore", backup["snapshot_id"], "--target", str(recovered)])
        restored_payload = recovered / "payload"
        manifest = validate_bundle(restored_payload, anchor)
        target = Cluster.start(commands, "restore")
        commands.run(
            "pg_restore",
            [
                *target.pg_args(),
                "--exit-on-error",
                "--single-transaction",
                "--no-owner",
                "--no-privileges",
                str(restored_payload / "research.dump"),
            ],
            env_extra={"PGPASSFILE": str(target.home / "pgpass")},
        )
        restored_state = current_state(target)
        write_private(output / "restore-state-before-replay.json", canonical(restored_state))
        if restored_state != manifest["state"] or current_state(source) != advanced:
            raise ValueError("restored SQL differs from snapshot or source changed")
        restored_store = target.store(lake, restored_payload / "artifacts")
        checked_references(restored_store, manifest["state"])
        if restored_store.submit("operator", "fixture-success", request) != restored_store.get(
            "operator", success.job_id
        ):
            raise ValueError("restored idempotent replay mismatch")
        if restored_store.get("operator", queued.job_id).state != "queued":
            raise ValueError("current source leaked into restored snapshot")
        if restored_store.get("operator", cancelled.job_id).state != "cancelled":
            raise ValueError("restored cancellation mismatch")
        restored_effects = EffectLedger(restored_store)
        if (
            restored_effects.read(success.job_id, f"{1:064x}")[0] != "completed"
            or restored_effects.read(success.job_id, f"{2:064x}")[0] != "reserved"
            or restored_effects.reserve_call(
                success.job_id, f"{1:064x}", Decimal("0"), request.budget, lease
            )
            or restored_effects.reserve_call(
                success.job_id, f"{2:064x}", Decimal("0"), request.budget, lease
            )
        ):
            raise ValueError("completed/unknown-effect replay mismatch")
        restored_store.request_cancel("operator", queued.job_id)
        receipt["restored"] = {
            "snapshot_sql_equal": True,
            "source_advanced": True,
            "source_unchanged": True,
            "idempotent_replay": True,
            "queued_then_cancelled": True,
            "effect_no_recall": True,
            "artifact_count": len(manifest["artifacts"]),
        }
        wrong_key = output / "wrong-password"
        write_private(wrong_key, secrets.token_hex(32).encode())

        def wrong():
            rc, raw = restic(commands, repo, wrong_key, ["snapshots"], failure=True)
            crypto_refusal("wrong_key", rc, raw)

        expect_failure("wrong_key", wrong, receipt, source, advanced)
        wrong_key.unlink()
        import shutil

        corrupt, changed = corrupt_copy(output, repo)

        def corrupted():
            rc, raw = restic(commands, corrupt, key, ["check", "--read-data"], failure=True)
            crypto_refusal("corrupt_cipher_copy", rc, raw)

        expect_failure("corrupt_cipher_copy", corrupted, receipt, source, advanced)
        receipt["corrupt_object"] = changed
        for name in (
            "missing_artifact",
            "substituted_artifact",
            "substituted_manifest",
            "unknown_schema",
        ):
            negative = output / name
            shutil.copytree(restored_payload, negative)
            artifact = negative / "artifacts" / manifest["artifacts"][0]["object_key"]
            if name == "missing_artifact":
                artifact.unlink()
            elif name == "substituted_artifact":
                artifact.write_bytes(b"substituted")
            elif name == "substituted_manifest":
                (negative / "manifest.json").write_bytes(b"{}")
            else:
                bad = Cluster.start(commands, "unknown-schema-cluster")
                commands.run(
                    "pg_restore",
                    [
                        *bad.pg_args(),
                        "--exit-on-error",
                        "--single-transaction",
                        "--no-owner",
                        "--no-privileges",
                        str(restored_payload / "research.dump"),
                    ],
                    env_extra={"PGPASSFILE": str(bad.home / "pgpass")},
                )
                con = bad.connection()
                try:
                    con.cursor().execute("UPDATE qm_research.qm_schema SET version=999")
                    con.commit()
                finally:
                    con.close()

                def unknown_schema():
                    try:
                        bad.store(lake, negative / "artifacts")
                    except ValueError as error:
                        if str(error) == "unsupported service schema":
                            raise NegativeRefused("unknown_schema") from None
                        raise

                expect_failure(name, unknown_schema, receipt, source, advanced)
                bad.stop()
                continue

            def invalid_bundle():
                expected = {
                    "missing_artifact": "owned bytes unavailable",
                    "substituted_artifact": "artifact substitution refused",
                    "substituted_manifest": "manifest substitution refused",
                }[name]
                try:
                    validate_bundle(negative, anchor)
                except ValueError as error:
                    if str(error) == expected:
                        raise NegativeRefused(name) from None
                    raise

            expect_failure(name, invalid_bundle, receipt, source, advanced)
        target.stop()
        sibling.verify_sql()
        source.stop()
        sibling.verify_sql()
        receipt["sibling_survived_individual_cleanup"] = True
        commands.check_deadline()
        receipt["passed"] = True
        return 0
    finally:
        guard.close()  # Cleanup has its own bounded stop/join deadlines.
        failures = []
        receipt["command_processes"] = []
        for handle in reversed(commands.command_processes):
            try:
                handle.close()
            except (ValueError, OSError, subprocess.SubprocessError):
                failures.append("owned_command_cleanup_pending")
            receipt["command_processes"].append(
                {
                    "pid": handle.process.pid,
                    "start_ticks": handle.ticks,
                    "executable": str(handle.executable),
                    "sha256": handle.binary_sha,
                    "stopped": handle.stopped,
                }
            )
        for cluster in reversed(clusters):
            try:
                cluster.stop()
            except (ValueError, OSError, subprocess.SubprocessError):
                failures.append("owned_cleanup_pending")
            if cluster.server_log and cluster.server_log.failed:
                failures.append("server_log_bound_or_drain_failed")
            receipt["clusters"].append(
                {
                    "pid": cluster.process.pid,
                    "start_ticks": cluster.ticks,
                    "data": str(cluster.data),
                    "system_id": cluster.system_id,
                    "stopped": cluster.stopped,
                }
            )
        for name in ("repository-password", "wrong-password"):
            (output / name).unlink(missing_ok=True)
        receipt["commands"] = commands.receipts
        receipt["cleanup_failures"] = failures
        receipt["passed"] = receipt["passed"] and not failures
        receipt["duration_seconds"] = round(240 - (commands.deadline - time.monotonic()), 3)
        write_private(output / "witness.json", canonical(receipt))
        os.umask(old_umask)
        if failures:
            raise ValueError("owned cleanup incomplete")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--owned-fixture", action="store_true")
    args = parser.parse_args(argv)
    try:
        profile = Profile.from_mapping(decode(args.profile.read_bytes()))
        output = owned_path(profile.root, args.output)
        if output.exists():
            raise ValueError("fresh output required")
        runtime = admit_runtime(profile)
        if not args.owned_fixture:
            print(
                json.dumps(
                    {
                        "scope": "OWNED_LOCAL_FIXTURE_ONLY",
                        "production_release_qualified": False,
                        "database_started": False,
                        "repository_created": False,
                        **runtime,
                    }
                )
            )
            return 0
        result = run_fixture(profile, output)
        print("OWNED_LOCAL_FIXTURE_ONLY; production_release_qualified=false; owned proof recorded")
        return result
    except (ValueError, OSError, subprocess.SubprocessError, KeyError, TypeError):
        print("owned backup refused; inspect fixed private qualification evidence")
        return 2


if __name__ == "__main__":
    checkout = Path(__file__).absolute().parents[1]
    sys.path[:1] = [
        str(checkout),
        str(checkout / "src"),
        str(checkout / "services/research_agent/src"),
    ]
    raise SystemExit(main())
