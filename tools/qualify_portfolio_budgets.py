"""Owned, opt-in local PostgreSQL portfolio accounting/restore witness.

The default is read-only preflight. Only a supplied reviewed implementation
and its clean committed verifier descendant can run a new disposable cluster.
Providers and numerical reports are explicitly scripted contract fixtures.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import re
import secrets
import select
import selectors
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from tools import qualify_research_backup as owned

BASELINE = "216b378192bbc0a1742a28b7a1fc75a86ae2fda9"
REVIEWED_IMPLEMENTATION = "b10762883edc1bbad164951d1a1adfb9f0f7457c"
PG_SOURCE = Path("/var/tmp/quantmesh-owned-pg-0ue7gicj")
PYTHON = Path("/var/tmp/quantmesh-portfolio-runtime-72a6m2j0/venv/bin/python")
PYTHON_PREFIX = PYTHON.parent.parent
PYTHON_SHA = "e50d468e8b0adfb05733f5b87b3cff34829c4a8c1aea50c865aa8bdfe4bb150f"
PG_AUDIT = Path("/var/tmp/quantmesh-backup-final-xvcv1u9k/tool-admission.json")
PREFIX_SHA = "f54df012fca9e020ad14fcfc66555ab4daf0bbca02812b5410f67f0f2bcea3c4"
MAX_OUTPUT = owned.MAX_OUTPUT
OWNED_FILES = {
    "tools/qualify_portfolio_budgets.py",
    "tests/test_portfolio_budget_qualification.py",
    "docs/runbooks/portfolio-budget-qualification.md",
}
BASE_TABLES = {"qm_schema", "jobs", "analysis_outbox", "model_effects"}


def environment(root):
    return owned.bare_environment(root)


def admit_prefix(prefix, manifest):
    """Compare every prefix file and link with independently pinned audit bytes."""
    if prefix.is_symlink() or prefix.resolve() != prefix.absolute():
        raise ValueError("prefix path refused")
    actual = {p.relative_to(prefix).as_posix() for p in prefix.rglob("*") if not p.is_dir()}
    if actual != set(manifest):
        raise ValueError("prefix inventory refused")
    for name, evidence in manifest.items():
        path = prefix / name
        if ".." in Path(name).parts or Path(name).is_absolute():
            raise ValueError("prefix manifest path refused")
        if "link" in evidence:
            if (
                not path.is_symlink()
                or os.readlink(path) != evidence["link"]
                or not path.resolve().is_relative_to(prefix)
            ):
                raise ValueError("prefix link refused")
        elif path.is_symlink() or not path.is_file():
            raise ValueError("prefix regular file required")
        else:
            data = path.read_bytes()
            if (
                len(data) != evidence["size"]
                or hashlib.sha256(data).hexdigest() != evidence["sha256"]
            ):
                raise ValueError("prefix file substituted")


def prefix_manifest():
    raw = PG_AUDIT.read_bytes()
    if hashlib.sha256(raw).hexdigest() != owned.TOOL_ADMISSION:
        raise ValueError("previous independent PG audit unavailable")
    audit = owned.decode(raw)
    manifest = {
        name[7:]: item for name, item in audit["files"].items() if name.startswith("prefix/")
    }
    if hashlib.sha256(owned.canonical(manifest)).hexdigest() != PREFIX_SHA:
        raise ValueError("prefix audit mismatch")
    return manifest


@dataclass(frozen=True)
class Profile:
    root: Path
    expected_build: str
    reviewed_implementation: str

    @classmethod
    def from_mapping(cls, raw):
        if not isinstance(raw, dict) or set(raw) != {
            "schema_version",
            "root",
            "expected_build",
            "reviewed_implementation",
        }:
            raise ValueError("profile fields refused")
        if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
            raise ValueError("profile version refused")
        for key in ("expected_build", "reviewed_implementation"):
            if not isinstance(raw[key], str) or not re.fullmatch(r"[0-9a-f]{40}", raw[key]):
                raise ValueError("reviewed implementation and exact build required")
        if raw["reviewed_implementation"] != REVIEWED_IMPLEMENTATION:
            raise ValueError("reviewed implementation identity refused")
        if sys.platform != "linux" or os.getuid() == 0 or not isinstance(raw["root"], str):
            raise ValueError("non-root native Linux required")
        from qm_research_agent.runtime import _directory, _native_filesystem

        root = _directory(Path(raw["root"]))
        if (
            root.parent != Path("/var/tmp")
            or not root.name.startswith("quantmesh-portfolio-")
            or not _native_filesystem(root)
        ):
            raise ValueError("new private native root required")
        admit_prefix(root / "prefix", prefix_manifest())
        return cls(root, raw["expected_build"], raw["reviewed_implementation"])


def admit_runtime(profile):
    from qm_research_agent.runtime import _admit_runtime, _git

    from quantmesh.research.job_store import protocol_digest
    from quantmesh.research.jobs import schema_digest

    checkout = owned.owned_path(profile.root, profile.root / "checkout")
    if Path(__file__).absolute().parents[1] != checkout or Path(sys.prefix) != PYTHON_PREFIX:
        raise ValueError("exact owned checkout and audited readonly interpreter required")
    actual, lock = _admit_runtime(profile.expected_build)
    _git(checkout, "merge-base", "--is-ancestor", BASELINE, profile.reviewed_implementation)
    _git(checkout, "merge-base", "--is-ancestor", profile.reviewed_implementation, actual)
    changes = set(
        _git(checkout, "diff", "--name-only", profile.reviewed_implementation, actual)
        .decode()
        .splitlines()
    )
    if changes != OWNED_FILES:
        raise ValueError("owned-only verifier descendant required")
    # The reviewed service candidate cannot change the frozen store or core contracts.
    implementation = set(
        _git(checkout, "diff", "--name-only", BASELINE, profile.reviewed_implementation)
        .decode()
        .splitlines()
    )
    fixed = {
        "services/research_agent/src/qm_research_agent/budgets.py",
        "services/research_agent/src/qm_research_agent/orchestrator.py",
        "services/research_agent/src/qm_research_agent/runtime.py",
        "services/research_agent/README.md",
    }
    existing = set(_git(checkout, "ls-tree", "-r", "--name-only", BASELINE).decode().splitlines())
    for name in implementation:
        if name in fixed or name.startswith("services/research_agent/tests/"):
            continue
        if (
            name not in existing
            and name.startswith("services/research_agent/src/qm_research_agent/")
            and name.endswith(".py")
        ):
            continue
        raise ValueError("reviewed implementation expands frozen scope")
    if (
        schema_digest() != owned.SCHEMA
        or protocol_digest() != owned.PROTOCOL
        or sys.version_info[:3] != (3, 12, 3)
        or owned.digest(PYTHON.resolve()) != PYTHON_SHA
    ):
        raise ValueError("frozen contracts or audited runtime mismatch")
    from qm_research_agent.budgets import PortfolioBudgetPolicy

    return {
        "actual_build": actual,
        "reviewed_implementation": profile.reviewed_implementation,
        "lock_sha256": lock,
        "schema_digest": owned.SCHEMA,
        "protocol_digest": owned.PROTOCOL,
        "python": sys.version,
        "python_executable_sha256": owned.digest(PYTHON.resolve()),
        "prefix_manifest_sha256": PREFIX_SHA,
        "pg_binary_sha256": owned.PG_HASHES,
        "policy_api": PortfolioBudgetPolicy.__name__,
        "source_sha256": {
            name: owned.digest(checkout / name)
            for name in (
                "tools/qualify_portfolio_budgets.py",
                "tools/qualify_research_backup.py",
                "tools/qualify_owned_postgres.py",
                "services/research_agent/src/qm_research_agent/budgets.py",
                "services/research_agent/src/qm_research_agent/accounting.py",
                "services/research_agent/src/qm_research_agent/store.py",
                "services/research_agent/src/qm_research_agent/runtime.py",
                "src/quantmesh/research/job_store.py",
                "src/quantmesh/research/jobs.py",
            )
        },
        "pg_source_sha256": owned.digest(PG_SOURCE / "build-proof/postgresql-18.6.tar.bz2"),
        "pg_build_receipt_sha256": owned.digest(PG_SOURCE / "build-proof/build.json"),
        "pg_copyright_sha256": owned.digest(PG_SOURCE / "build-proof/POSTGRESQL-COPYRIGHT"),
    }


class Subreaper:
    """Temporary current-process adoption; reap only positively registered PIDs."""

    users = 0
    previous = 0

    @classmethod
    def acquire(cls):
        if sys.platform != "linux" or not hasattr(os, "pidfd_open"):
            raise ValueError("native command family handles unavailable")
        libc = ctypes.CDLL(None, use_errno=True)
        if cls.users == 0:
            value = ctypes.c_int()
            if libc.prctl(37, ctypes.byref(value), 0, 0, 0):
                raise ValueError("native subreaper query refused")
            cls.previous = value.value
            if libc.prctl(36, 1, 0, 0, 0):
                raise ValueError("native subreaper activation refused")
        cls.users += 1

    @classmethod
    def release(cls):
        if cls.users <= 0:
            raise ValueError("command family reaper accounting refused")
        cls.users -= 1
        if cls.users == 0 and ctypes.CDLL(None, use_errno=True).prctl(36, cls.previous, 0, 0, 0):
            raise ValueError("native subreaper restoration refused")


@dataclass(repr=False)
class FamilyMember:
    identity: dict
    pidfd: int
    terminal: bool = False
    exit_status: int | None = None
    reaped: str | None = None
    signals: list = field(default_factory=list)
    images: list = field(default_factory=list)

    def ready(self):
        return bool(select.select([self.pidfd], [], [], 0)[0])

    def receipt(self):
        return {
            **self.identity,
            "terminal": self.terminal,
            "exit_status": self.exit_status,
            "reaped": self.reaped,
            "signals": self.signals,
            "observed_images": self.images,
        }


@dataclass(repr=False)
class Child(owned.CommandProcess):
    allowed_binaries: dict = field(default_factory=dict)
    members: dict = field(default_factory=dict)
    released: bool = False

    @property
    def pid(self):
        return self.process.pid

    def identity(self, pid):
        proc = Path("/proc") / str(pid)
        fields = (proc / "stat").read_text().rsplit(")", 1)[1].split()
        if fields[0] == "Z":
            raise ProcessLookupError("terminal member")
        executable = (proc / "exe").resolve()
        argv = (proc / "cmdline").read_bytes().split(b"\0")[:-1]
        if (
            proc.stat().st_uid != os.getuid()
            or int(fields[2]) != self.pid
            or int(fields[3]) != self.pid
            or executable not in self.allowed_binaries
            or owned.digest(proc / "exe") != self.allowed_binaries[executable]
            or (pid == self.pid and argv != list(map(os.fsencode, self.argv)))
        ):
            raise ValueError("command family ownership refused; no unowned signal")
        environment = (proc / "environ").read_bytes()
        if b"QM_BACKUP_COMMAND_OWNER=" + self.nonce.encode() not in environment.split(b"\0"):
            member = self.members.get((pid, fields[19]))
            if (
                not environment
                and pid == self.pid
                and fields[19] == self.ticks
                and member is not None
                and member.ready()
            ):
                # A retained leader may lose /proc/environ while exiting. This
                # terminal pidfd grants retirement only, never signal authority.
                raise ProcessLookupError("terminal owned leader")
            raise ValueError("command family ownership refused; no unowned signal")
        return {
            "pid": pid,
            "start_ticks": fields[19],
            "uid": os.getuid(),
            "group": int(fields[2]),
            "session": int(fields[3]),
            "executable": str(executable),
            "binary_sha256": self.allowed_binaries[executable],
            "argv_sha256": hashlib.sha256(b"\0".join(argv)).hexdigest(),
            "nonce_sha256": hashlib.sha256(self.nonce.encode()).hexdigest(),
        }

    def scan(self):
        """No adoption from an ambient group: kernel SID/PGID must equal this new leader."""
        active = []
        for proc in Path("/proc").iterdir():
            if not proc.name.isdecimal():
                continue
            try:
                fields = (proc / "stat").read_text().rsplit(")", 1)[1].split()
                if int(fields[2]) != self.pid or int(fields[3]) != self.pid or fields[0] == "Z":
                    continue
                identity = self.identity(int(proc.name))
                key = (identity["pid"], identity["start_ticks"])
                if key not in self.members:
                    if len(self.members) >= 128:
                        raise ValueError("command family member cap")
                    fd = os.pidfd_open(identity["pid"])
                    try:
                        if select.select([fd], [], [], 0)[0]:
                            continue
                        try:
                            second = self.identity(identity["pid"])
                        except PermissionError:
                            if (
                                identity["pid"] == self.pid
                                and identity["start_ticks"] == self.ticks
                                and select.select([fd], [], [], 0.1)[0]
                            ):
                                # The first identity was fully admitted. Observe
                                # retirement through its held handle, never signal.
                                continue
                            raise
                        if any(
                            second[k] != identity[k]
                            for k in (
                                "pid",
                                "start_ticks",
                                "uid",
                                "group",
                                "session",
                                "nonce_sha256",
                            )
                        ):
                            raise ValueError("command family identity changed")
                        identity = second
                        self.members[key] = FamilyMember(identity, fd)
                        self.members[key].images.append(identity.copy())
                        fd = None
                    finally:
                        if fd is not None:
                            os.close(fd)
                member = self.members[key]
                if member.identity != identity:
                    if member.ready():
                        continue
                    # A positively fenced shell may exec the pinned postgres image.
                    # identity() already requires an admitted executable and owner nonce.
                    member.images.append(identity.copy())
                    member.identity = identity
                active.append(member)
            except (FileNotFoundError, ProcessLookupError):
                continue
            except PermissionError:
                # Linux can revoke /proc/environ during the final exit window.
                # A direct owned Popen terminal result grants no signal authority.
                if int(proc.name) == self.pid and self.process.poll() is not None:
                    continue
                try:
                    after = (proc / "stat").read_text().rsplit(")", 1)[1].split()
                    if after[0] == "Z":
                        continue
                except (FileNotFoundError, ProcessLookupError):
                    continue
                raise
        return active

    def signal_member(self, member, signum):
        if member.ready():
            return
        try:
            if self.identity(member.identity["pid"]) != member.identity:
                raise ValueError("command family signal identity changed")
            signal.pidfd_send_signal(member.pidfd, signum)
            member.signals.append(signum)
        except (FileNotFoundError, ProcessLookupError):
            pass

    def family_receipt(self):
        return [member.receipt() for member in self.members.values()]

    def close(self):
        if self.released:
            return
        deadline = time.monotonic() + 3
        stopped_by_us = []
        try:
            # Freeze eligible members first; no blind group signal can hit a new/unknown member.
            while True:
                active = self.scan()
                if not active:
                    break
                frozen = True
                for member in active:
                    pid = member.identity["pid"]
                    try:
                        fields = (
                            (Path("/proc") / str(pid) / "stat")
                            .read_text()
                            .rsplit(")", 1)[1]
                            .split()
                        )
                    except (FileNotFoundError, ProcessLookupError):
                        continue
                    if fields[0] not in {"T", "t", "Z"}:
                        self.signal_member(member, signal.SIGSTOP)
                        stopped_by_us.append(member)
                        frozen = False
                if frozen:
                    second = self.scan()
                    if {tuple(m.identity.items()) for m in active} == {
                        tuple(m.identity.items()) for m in second
                    }:
                        # All identified members are stopped; none can fork during final signalling.
                        for member in sorted(second, key=lambda m: m.identity["pid"] == self.pid):
                            self.signal_member(member, signal.SIGKILL)
                        break
                if time.monotonic() >= deadline:
                    raise ValueError("command family freeze deadline")
                time.sleep(0.005)
        except BaseException:
            # Preserve unknown processes, and restore only the eligible processes we paused.
            for member in stopped_by_us:
                try:
                    self.signal_member(member, signal.SIGCONT)
                except (OSError, ValueError):
                    pass
            raise
        self.process.wait(timeout=max(0.01, deadline - time.monotonic()))
        for member in self.members.values():
            while not member.ready():
                if time.monotonic() >= deadline:
                    raise ValueError("command family terminal deadline")
                time.sleep(0.005)
            member.terminal = True
            if member.identity["pid"] == self.pid:
                member.exit_status, member.reaped = self.process.returncode, "owned_Popen"
            else:
                try:
                    pid, status = os.waitpid(member.identity["pid"], os.WNOHANG)
                    if pid:
                        member.exit_status = os.waitstatus_to_exitcode(status)
                        member.reaped = "owned_subreaper"
                    else:
                        raise ValueError("owned descendant adoption pending")
                except ChildProcessError:
                    member.reaped = "terminal_pidfd_immediate_parent_reaped"
        if self.scan():
            raise ValueError("command family still live")
        for member in self.members.values():
            os.close(member.pidfd)
        self.process.stdout.close()
        self.process.stderr.close()
        self.stopped = True
        self.released = True
        Subreaper.release()


class Commands(owned.Commands):
    """Reuse cluster ownership fences; retain separate bounded command streams."""

    def spawn(self, argv, env, cwd):
        self.check_deadline()
        nonce = secrets.token_hex(24)
        executable = Path(argv[0]).resolve()
        sha = owned.digest(executable)
        allowed = {executable: sha}
        for name, expected in owned.PG_HASHES.items():
            allowed[self.root / "prefix/bin" / name] = expected
        # initdb's fixed upstream popen uses the installed base-system /bin/sh.
        shell = Path("/bin/sh").resolve()
        allowed[shell] = owned.digest(shell)
        Subreaper.acquire()
        handle = None
        self.registering = True
        try:
            process = subprocess.Popen(
                argv,
                env={**env, "QM_BACKUP_COMMAND_OWNER": nonce},
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            handle = Child(process, executable, sha, argv, nonce)
            handle.allowed_binaries = allowed
            self.command_processes.append(handle)
            handle.ticks = owned.process_ticks(process.pid)
            handle.scan()
        finally:
            if handle is None:
                Subreaper.release()
            self.registering = False
            self.check_deadline()
        return handle

    def collect(self, handle, tool, timeout=40, *, failure=False):
        n = len(self.receipts) + 1
        names = {"stdout": f"command-{n:03d}.stdout", "stderr": f"command-{n:03d}.stderr"}
        receipt = {"tool": tool, "pid": handle.pid, "exit": None, **names}
        self.receipts.append(receipt)
        deadline = min(self.deadline, time.monotonic() + timeout)
        buffers = {key: bytearray() for key in names}
        error = None
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(handle.process.stdout, selectors.EVENT_READ, "stdout")
                selector.register(handle.process.stderr, selectors.EVENT_READ, "stderr")
                while selector.get_map():
                    self.check_deadline()
                    handle.scan()
                    if time.monotonic() >= deadline:
                        raise ValueError("command deadline")
                    for key, _ in selector.select(min(0.1, max(0, deadline - time.monotonic()))):
                        chunk = os.read(key.fd, 65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                        elif len(buffers[key.data]) + len(chunk) > MAX_OUTPUT:
                            raise ValueError("command output cap")
                        else:
                            buffers[key.data].extend(chunk)
                handle.process.wait(timeout=max(0.01, deadline - time.monotonic()))
        except (ValueError, subprocess.SubprocessError) as exc:
            error = exc
        finally:
            try:
                handle.close()
            finally:
                receipt["exit"] = handle.process.poll()
                receipt["family"] = handle.family_receipt()
                for key, name in names.items():
                    raw = bytes(buffers[key])
                    owned.write_private(self.output / name, raw)
                    receipt[key + "_sha256"] = hashlib.sha256(raw).hexdigest()
                owned.write_private(self.output / f"command-{n:03d}.json", owned.canonical(receipt))
        if error:
            raise error
        if receipt["exit"] and not failure:
            raise ValueError("command failed")
        return receipt["exit"], bytes(buffers["stdout"])

    def python(self, args, *, timeout=40):
        handle = self.spawn([sys.executable, "-B", *args], environment(self.root), self.root)
        return self.collect(handle, "python", timeout)

    def run(self, tool, args, *, env_extra=None, cwd=None, failure=False):
        if tool not in owned.PG_HASHES:
            raise ValueError("only fixed PostgreSQL tools permitted")
        binary = self.root / "prefix/bin" / tool
        if owned.digest(binary) != owned.PG_HASHES[tool]:
            raise ValueError("fixed binary substituted")
        handle = self.spawn(
            [str(binary), *args], {**environment(self.root), **(env_extra or {})}, cwd or self.root
        )
        return self.collect(handle, tool, failure=failure)


def cleanup(clusters, children):
    failures = []
    for item in [*reversed(children), *reversed(clusters)]:
        pid = getattr(item, "pid", None)
        if pid is None:
            pid = item.process.pid
        try:
            item.close() if isinstance(item, Child) or not hasattr(item, "stop") else item.stop()
        except (ValueError, OSError, subprocess.SubprocessError):
            failures.append({"pid": pid, "state": "pending", "reason": "identity_refused"})
    return failures


def validate_tables(names):
    if not BASE_TABLES.issubset(names) or len(set(names) - BASE_TABLES) < 2:
        raise ValueError("complete additive accounting tables required")
    if any(not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", name) for name in names):
        raise ValueError("accounting table identifier refused")


def snapshot(connection):
    """Independent SQL enumeration, all columns/rows, no implementation table guess."""
    cursor = connection.cursor()
    cursor.execute("SET LOCAL statement_timeout='5s'")
    cursor.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='qm_research' AND table_type='BASE TABLE' ORDER BY table_name"
    )
    names = [row[0] for row in cursor.fetchmany(33)]
    if len(names) > 32:
        raise ValueError("bounded schema required")
    validate_tables(names)
    tables = {}
    for name in names:
        cursor.execute(f'SELECT * FROM qm_research."{name}"')
        rows = cursor.fetchmany(129)
        if len(rows) > 128:
            raise ValueError("bounded accounting snapshot required")
        columns = [column[0] for column in cursor.description]
        tables[name] = {
            "columns": columns,
            "rows": sorted([list(row) for row in rows], key=owned.canonical),
        }
    return tables


def state(cluster):
    con = cluster.connection()
    try:
        con.cursor().execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        return snapshot(con)
    finally:
        con.close()


def compare_states(source, restored):
    if source != restored:
        raise ValueError("complete restore state mismatch")


def validate_race(results, jobs, observer_sha):
    if len(results) != 2 or len(set(jobs)) != 2 or {r["job_id"] for r in results} != set(jobs):
        raise ValueError("independent two-job race required")
    winners = [r for r in results if r["admitted"] is True]
    losers = [r for r in results if r["admitted"] is False]
    if (
        len(winners) != 1
        or len(losers) != 1
        or winners[0]["invocations"] != 1
        or winners[0]["observer_sha256"] != observer_sha
        or losers[0]["invocations"] != 0
        or losers[0]["observer_sha256"] is not None
    ):
        raise ValueError("race lacks exact durable-before-scripted-invocation evidence")


def records(table):
    return [dict(zip(table["columns"], row, strict=True)) for row in table["rows"]]


def validate_observation(tables, job_id, digest):
    effects = records(tables["model_effects"])
    charges = records(tables["qm_portfolio_reservations"])
    if (
        len(effects) != 1
        or len(charges) != 1
        or effects[0]["job_id"] != job_id
        or effects[0]["digest"] != digest
        or effects[0]["price"] != "0.5"
        or effects[0]["status"] != "reserved"
        or charges[0]["job_id"] != job_id
        or charges[0]["digest"] != digest
        or charges[0]["price"] != "0.5"
        or charges[0]["category"] != "operating"
    ):
        raise ValueError("durable independent reservation observation required")


def durable(path, raw):
    """Publish fresh private bytes durably before releasing an invocation barrier."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def python_environment(root):
    checkout = root / "checkout"
    return {
        **environment(root),
        "PYTHONPATH": ":".join(
            str(p) for p in (checkout, checkout / "src", checkout / "services/research_agent/src")
        ),
    }


def fixture_policy():
    from qm_research_agent.budgets import PortfolioBudgetPolicy

    return PortfolioBudgetPolicy("owned-scripted-portfolio", Decimal("0.5"), Decimal("0.5"))


def wait_for(path, root, commands=None, *, seconds=15):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if commands:
            commands.check_deadline()
            if any(c.process.poll() not in (None, 0) for c in commands.command_processes):
                raise ValueError("owned contender exited before barrier")
        if path.exists():
            return owned.decode(owned.read_owned(root, path))
        time.sleep(0.02)
    raise ValueError("owned contender barrier deadline")


def worker_store(profile, spec):
    """No borrowed DSN: verify the parent's new postmaster before independent SQL."""
    from pydantic import SecretStr
    from qm_research_agent.store import PostgresJobStore, connect

    from tools.qualify_owned_postgres import verify_process_identity

    info = spec["cluster"]
    data = owned.owned_path(profile.root, Path(info["data"]))
    home = owned.owned_path(profile.root, Path(info["home"]))
    binary = profile.root / "prefix/bin/postgres"
    ticks = verify_process_identity(info["pid"], data, binary, owned.PG_HASHES["postgres"])
    proc = Path("/proc") / str(info["pid"])
    if (
        ticks != info["start_ticks"]
        or owned.read_owned(home, home / "owner") != info["nonce"].encode()
        or b"QM_BACKUP_OWNER=" + info["nonce"].encode()
        not in (proc / "environ").read_bytes().split(b"\0")
        or not re.fullmatch(r"fixture_[0-9a-f]{16}", info["role"])
        or type(info["port"]) is not int
        or not 1024 <= info["port"] <= 65535
        or not re.fullmatch(r"[0-9a-f]{64}", info["password"])
    ):
        raise ValueError("independent worker cluster ownership refused")
    dsn = SecretStr(
        f"postgresql://{info['role']}:{info['password']}@127.0.0.1:"
        f"{info['port']}/postgres?sslmode=disable"
    )
    con = connect(dsn)
    try:
        cursor = con.cursor()
        cursor.execute("SET LOCAL statement_timeout='5s'")
        cursor.execute(
            "SELECT current_setting('data_directory'),current_setting('listen_addresses'),"
            "current_setting('port'),current_user,"
            "(SELECT system_identifier::text FROM pg_control_system())"
        )
        if list(cursor.fetchone()) != [
            str(data),
            "127.0.0.1",
            str(info["port"]),
            info["role"],
            info["system_id"],
        ]:
            raise ValueError("independent SQL cluster identity refused")
    finally:
        con.close()
    clock = datetime.fromisoformat(spec["store_clock"])
    return PostgresJobStore(
        dsn,
        lake_root=owned.owned_path(profile.root, Path(spec["lake"])),
        artifact_root=owned.owned_path(profile.root, Path(spec["artifacts"])),
        clock=lambda: clock,
    )


def worker(root, spec_path):
    from qm_research_agent.budgets import EffectLedger

    from quantmesh.research.jobs import AnalysisLease, RunBudget

    root, spec_path = Path(root), Path(spec_path)
    spec = owned.decode(owned.read_owned(root, spec_path))
    profile = Profile.from_mapping(spec["profile"])
    if profile.root != root:
        raise ValueError("worker root mismatch")
    admit_runtime(profile)
    output = owned.owned_path(root, Path(spec["output"]))
    store = worker_store(profile, spec)
    effects = EffectLedger(store, policy=fixture_policy(), category="operating")
    lease = AnalysisLease.model_validate(spec["lease"])
    budget = RunBudget.model_validate(spec["budget"])
    name = spec["name"]
    if name not in {"first", "second"}:
        raise ValueError("contender identifier refused")
    durable(
        output / (name + "-ready.json"),
        owned.canonical(
            {
                "pid": os.getpid(),
                "job_id": lease.job_id,
                "start_ticks": owned.process_ticks(os.getpid()),
            }
        ),
    )
    start = wait_for(output / "race-start.json", output)
    if start != {"nonce": spec["race_nonce"]}:
        raise ValueError("race start ownership refused")
    admitted = effects.reserve_call(lease.job_id, spec["digest"], Decimal("0.5"), budget, lease)
    result = {
        "job_id": lease.job_id,
        "admitted": admitted,
        "invocations": 0,
        "observer_sha256": None,
        "pid": os.getpid(),
    }
    durable(output / (name + "-admission.json"), owned.canonical(result))
    if admitted:
        gate = wait_for(output / "observer-gate.json", output)
        raw = owned.read_owned(output, output / "observer.json")
        sha = hashlib.sha256(raw).hexdigest()
        observation = owned.decode(raw)
        if gate != {"observer_sha256": sha, "job_id": lease.job_id, "digest": spec["digest"]}:
            raise ValueError("durable observer barrier refused")
        validate_observation(observation["state"], lease.job_id, spec["digest"])
        # This is the complete scripted provider: local receipt bytes, no SDK/network.
        durable(
            output / "scripted-invocation.json",
            owned.canonical(
                {
                    "fixture": True,
                    "real_provider": False,
                    "count": 1,
                    "pid": os.getpid(),
                    "job_id": lease.job_id,
                    "digest": spec["digest"],
                    "observer_sha256": sha,
                }
            ),
        )
        if not effects.response(lease, spec["digest"], '{"fixture":true,"scripted":true}'):
            raise ValueError("scripted response persistence failed")
        result.update(invocations=1, observer_sha256=sha)
    print(json.dumps(result))
    return 0


def worker_main(root, spec_path):
    try:
        return worker(root, spec_path)
    except (ValueError, OSError, ImportError, subprocess.SubprocessError):
        print(json.dumps({"error": "owned_worker_refused", "real_provider": False}))
        return 2


def deny(effects, job, lease, digest, price="0.01"):
    if effects.reserve_call(job.job_id, digest, Decimal(price), job.request.budget, lease):
        raise ValueError("exhaustion/negative reservation unexpectedly accepted")
    if effects.read(job.job_id, digest) is not None:
        raise ValueError("denied effect was inserted")


def exercise(profile, commands, source, sibling, witness):
    from qm_research_agent.budgets import EffectLedger

    output = commands.output
    lake = owned.fresh_directory(output, output / "lake")
    artifacts = owned.fresh_directory(output, output / "artifacts")
    request_for, publish = owned.fixture_inputs(profile.root / "checkout", lake)
    store = source.store(lake, artifacts)
    clock = datetime.now(UTC)
    store._clock = lambda: clock
    policy = fixture_policy()
    EffectLedger(store, policy=policy, category="operating")
    pairs = []
    for name in ("first", "second"):
        job = store.submit(
            "operator", "owned-portfolio-" + name, request_for(lake, analysis_requested=True)
        )
        ref = publish(store, job)
        envelope = owned.decode((artifacts / ref.object_key).read_bytes())
        if envelope["result"].get("fixture") is not True:
            raise ValueError("scripted contract report label missing")
        lease = store.claim_analysis("owned-analyst-" + name, clock)
        if lease is None or lease.job_id != job.job_id:
            raise ValueError("new owned analysis lease missing")
        pairs.append((job, lease))
    witness["fixture_store_clock"] = clock.isoformat()
    witness["numerical_report"] = "SCRIPTED_CONTRACT_FIXTURE_ONLY"
    children = []
    nonce = secrets.token_hex(24)
    digests = [hashlib.sha256(name.encode()).hexdigest() for name in ("first", "second")]
    for name, (job, lease), digest in zip(("first", "second"), pairs, digests, strict=True):
        spec = {
            "profile": {
                "schema_version": 1,
                "root": str(profile.root),
                "expected_build": profile.expected_build,
                "reviewed_implementation": profile.reviewed_implementation,
            },
            "cluster": {
                "data": str(source.data),
                "home": str(source.home),
                "pid": source.process.pid,
                "start_ticks": source.ticks,
                "role": source.role,
                "password": source.password,
                "nonce": source.nonce,
                "port": source.port,
                "system_id": source.system_id,
            },
            "store_clock": clock.isoformat(),
            "lease": lease.model_dump(mode="json"),
            "budget": job.request.budget.model_dump(mode="json"),
            "name": name,
            "digest": digest,
            "output": str(output),
            "lake": str(lake),
            "artifacts": str(artifacts),
            "race_nonce": nonce,
        }
        path = output / (name + "-private-spec.json")
        owned.write_private(path, owned.canonical(spec))
        children.append(
            commands.spawn(
                [
                    str(PYTHON),
                    "-B",
                    "-c",
                    "import sys;from tools.qualify_portfolio_budgets "
                    "import worker_main;sys.exit(worker_main(sys.argv[1],sys.argv[2]))",
                    str(profile.root),
                    str(path),
                ],
                python_environment(profile.root),
                profile.root / "checkout",
            )
        )
    for name in ("first", "second"):
        wait_for(output / (name + "-ready.json"), output, commands)
    durable(output / "race-start.json", owned.canonical({"nonce": nonce}))
    admitted = [
        wait_for(output / (name + "-admission.json"), output, commands)
        for name in ("first", "second")
    ]
    winners = [r for r in admitted if r["admitted"]]
    if len(winners) != 1 or (output / "scripted-invocation.json").exists():
        raise ValueError("last-slot race or pre-invocation ordering failed")
    winner = next(i for i, (job, _) in enumerate(pairs) if job.job_id == winners[0]["job_id"])
    observed = state(source)  # Different raw SQL connection, outside both effect transactions.
    validate_observation(observed, pairs[winner][0].job_id, digests[winner])
    observation = {
        "scope": "INDEPENDENT_RAW_SQL_BEFORE_SCRIPTED_INVOCATION",
        "state": observed,
        "observer_pid": os.getpid(),
        "contender_pids": [c.pid for c in children],
        "invocation_file_absent": True,
    }
    durable(output / "observer.json", owned.canonical(observation))
    observer_sha = owned.digest(output / "observer.json")
    durable(
        output / "observer-gate.json",
        owned.canonical(
            {
                "observer_sha256": observer_sha,
                "job_id": pairs[winner][0].job_id,
                "digest": digests[winner],
            }
        ),
    )
    results = [
        owned.decode(commands.collect(c, "independent-scripted-contender", 20)[1]) for c in children
    ]
    validate_race(results, [job.job_id for job, _ in pairs], observer_sha)
    witness["race"] = {
        "independent_processes": 2,
        "results": results,
        "winning_scripted_invocations": 1,
        "denied_scripted_invocations": 0,
        "observer_sha256": observer_sha,
    }
    job, lease = pairs[1 - winner]
    development = EffectLedger(store, policy=policy, category="development")
    if not development.reserve_call(
        job.job_id, "d" * 64, Decimal("0.5"), job.request.budget, lease
    ):
        raise ValueError("separate development exact-boundary reservation failed")
    for category in ("operating", "development"):
        deny(
            EffectLedger(store, policy=policy, category=category),
            job,
            lease,
            hashlib.sha256(("source-exhausted-" + category).encode()).hexdigest(),
        )
    reopened = source.store(lake, artifacts)
    reopened._clock = lambda: clock
    for category in ("operating", "development"):
        deny(
            EffectLedger(reopened, policy=policy, category=category),
            job,
            lease,
            hashlib.sha256(("reopened-exhausted-" + category).encode()).hexdigest(),
        )
    captured_con = source.connection()
    try:
        cursor = captured_con.cursor()
        cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        captured = snapshot(captured_con)
        cursor.execute("SELECT pg_export_snapshot()")
        snapshot_id = cursor.fetchone()[0]
        commands.run(
            "pg_dump",
            [
                *source.pg_args(),
                "--format=custom",
                "--compress=0",
                "--no-owner",
                "--no-privileges",
                "--schema=qm_research",
                "--snapshot=" + snapshot_id,
                "--file=" + str(output / "research.dump"),
            ],
            env_extra={"PGPASSFILE": str(source.home / "pgpass")},
        )
    finally:
        captured_con.close()
    durable(output / "source-captured.json", owned.canonical(captured))
    target = owned.Cluster.start(commands, "restored")
    commands.run(
        "pg_restore",
        [
            *target.pg_args(),
            "--exit-on-error",
            "--single-transaction",
            "--no-owner",
            "--no-privileges",
            str(output / "research.dump"),
        ],
        env_extra={"PGPASSFILE": str(target.home / "pgpass")},
    )
    restored = state(target)
    compare_states(captured, restored)
    durable(output / "restored-before-replay.json", owned.canonical(restored))
    restored_store = target.store(lake, artifacts)
    restored_store._clock = lambda: clock
    for candidate in (reopened, restored_store):
        for category in ("operating", "development"):
            deny(
                EffectLedger(candidate, policy=policy, category=category),
                job,
                lease,
                hashlib.sha256(("post-restore-denied-" + category).encode()).hexdigest(),
            )
    compare_states(captured, state(source))
    compare_states(captured, state(target))
    witness["restore"] = {
        "complete_state_equal": True,
        "source_and_restored_categories_exhausted": True,
        "dump_sha256": owned.digest(output / "research.dump"),
        "tables": sorted(captured),
        "source_reopened": True,
        "snapshot_id": snapshot_id,
        "same_fixture_store_clock": True,
    }
    negatives(profile, store, restored_store, source, target, pairs, clock, captured, witness)
    target.stop()
    sibling.verify_sql()
    witness["sibling_survived_restore_cleanup"] = True


def negatives(profile, store, restored_store, source, target, pairs, clock, captured, witness):
    from qm_research_agent.budgets import EffectLedger, PortfolioBudgetPolicy

    job, lease = pairs[0]
    policy = fixture_policy()
    result = witness["negatives"]
    try:
        EffectLedger(
            store,
            policy=PortfolioBudgetPolicy("changed-id", Decimal("0.5"), Decimal("0.5")),
            category="operating",
        )
    except ValueError as exc:
        if str(exc) != "portfolio policy mismatch":
            raise
        result["mismatched_policy"] = {"denied": True, "scripted_invocations": 0}
    else:
        raise ValueError("mismatched policy accepted")
    deny(EffectLedger(store), job, lease, "e" * 64, "0")
    result["missing_policy"] = {"denied": True, "scripted_invocations": 0}
    effects = EffectLedger(store, policy=policy, category="operating")
    deny(effects, job, lease, "f" * 64, "NaN")
    result["malformed_amount"] = {"denied": True, "scripted_invocations": 0}
    store._clock = lambda: clock - timedelta(seconds=1)
    try:
        deny(effects, job, lease, "1" * 64, "0")
    finally:
        store._clock = lambda: clock
    result["backward_clock"] = {
        "denied": True,
        "scripted_invocations": 0,
        "fixture_clock_test": True,
    }
    original = store._transaction

    class RollbackProbe(ValueError):
        pass

    @contextmanager
    def interrupted_transaction():
        with original() as con:
            yield con
            if not con.execute(
                "SELECT 1 FROM qm_portfolio_reservations WHERE digest=?", ("2" * 64,)
            ).fetchone():
                raise ValueError("rollback did not reach atomic reservation insertion")
            raise RollbackProbe("owned rollback after both inserts")

    store._transaction = interrupted_transaction
    try:
        effects.reserve_call(job.job_id, "2" * 64, Decimal("0"), job.request.budget, lease)
    except RollbackProbe:
        result["atomic_rollback"] = {
            "both_inserts_observed_inside_transaction": True,
            "scripted_invocations": 0,
        }
    else:
        raise ValueError("rollback probe failed to interrupt")
    finally:
        store._transaction = original
    compare_states(captured, state(source))
    restored_effects = EffectLedger(restored_store, policy=policy, category="operating")
    con = target.connection()
    try:
        cursor = con.cursor()
        cursor.execute("UPDATE qm_research.qm_portfolio_reservations SET price='NaN'")
        con.commit()
    finally:
        con.close()
    deny(restored_effects, job, lease, "3" * 64, "0")
    result["malformed_history"] = {
        "denied": True,
        "scripted_invocations": 0,
        "only_new_restored_cluster_mutated": True,
    }
    con = target.connection()
    try:
        con.cursor().execute("UPDATE qm_research.qm_portfolio_schema SET version=999")
        con.commit()
    finally:
        con.close()
    try:
        EffectLedger(restored_store, policy=policy, category="operating")
    except ValueError as exc:
        if str(exc) != "unsupported portfolio accounting version":
            raise
        result["unknown_accounting_version"] = {"denied": True, "scripted_invocations": 0}
    else:
        raise ValueError("unknown accounting version accepted")
    compare_states(captured, state(source))
    durable(
        source.commands.output / "negative-state.json",
        owned.canonical(
            {
                "source_unchanged": state(source),
                "deliberately_corrupted_restored": state(target),
                "negatives": result,
            }
        ),
    )


def run_fixture(profile, output):
    runtime = admit_runtime(profile)  # Immediately before allocating any DB/fixture resource.
    old_umask = os.umask(0o077)
    commands = None
    guard = None
    witness = {
        "scope": "OWNED_LOCAL_POSTGRES_SCRIPTED_PORTFOLIO_ONLY",
        "passed": False,
        "production_release_qualified": False,
        "real_provider_calls": 0,
        "paid_calls": 0,
        "live_trading": False,
        "source_host_qualified": False,
        "numerical_worker_qualified": False,
        "production_tls_qualified": False,
        "offhost_backup_qualified": False,
        "runtime": runtime,
        "negatives": {},
    }
    try:
        commands = Commands(profile.root, owned.fresh_directory(profile.root, output))
        guard = owned.FixtureDeadline(240, defer=lambda: commands.registering)
        commands.guard = guard
        source = owned.Cluster.start(commands, "source")
        sibling = owned.Cluster.start(commands, "sibling")
        exercise(profile, commands, source, sibling, witness)
        commands.check_deadline()
        witness["passed"] = True
        return 0
    finally:
        if guard:
            guard.close()
        failures = []
        if commands:
            failures.extend(cleanup([], commands.command_processes))
            clusters = commands.clusters
            # Stop each independent target/source while a known owned sibling stays alive.
            if len(clusters) >= 2:
                sibling = clusters[1]
                failures.extend(cleanup(clusters[2:], []))
                try:
                    sibling.verify_sql()
                    failures.extend(cleanup(clusters[:1], []))
                    sibling.verify_sql()
                    witness["sibling_survived_individual_cleanup"] = True
                    witness["sibling_survived_failure_cleanup"] = True
                except (ValueError, OSError, subprocess.SubprocessError):
                    failures.append(
                        {
                            "pid": sibling.process.pid,
                            "state": "pending",
                            "reason": "sibling_survival_unproven",
                        }
                    )
                failures.extend(cleanup(clusters[:2], []))
            else:
                failures.extend(cleanup(clusters, []))
            for name in ("first-private-spec.json", "second-private-spec.json"):
                (output / name).unlink(missing_ok=True)
            for cluster in clusters:
                if cluster.server_log and cluster.server_log.failed:
                    failures.append(
                        {
                            "pid": cluster.process.pid,
                            "state": "failed",
                            "reason": "server_stream_bound_or_drain",
                        }
                    )
            witness.update(
                clusters=[
                    {
                        "pid": c.process.pid,
                        "start_ticks": c.ticks,
                        "data": str(c.data),
                        "system_id": c.system_id,
                        "terminal_exit": c.process.poll(),
                    }
                    for c in clusters
                ],
                children=[
                    {
                        "pid": c.pid,
                        "start_ticks": c.ticks,
                        "executable": str(c.executable),
                        "binary_sha256": c.binary_sha,
                        "terminal_exit": c.process.poll(),
                        "family": c.family_receipt(),
                    }
                    for c in commands.command_processes
                ],
                commands=commands.receipts,
                cleanup_failures=failures,
                duration_seconds=round(240 - (commands.deadline - time.monotonic()), 3),
            )
            witness["passed"] = witness["passed"] and not failures
            durable(output / "witness.json", owned.canonical(witness))
        os.umask(old_umask)
        if failures:
            raise ValueError("owned native cleanup incomplete")


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError("cli_configuration_refused")


def main(argv=None):
    parser = Parser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--owned-fixture", action="store_true")
    try:
        args = parser.parse_args(argv)
        if args.profile.stat().st_size > 65536:
            raise ValueError("bounded profile required")
        profile = Profile.from_mapping(owned.decode(args.profile.read_bytes()))
        if args.owned_fixture:
            return run_fixture(profile, args.output)
        runtime = admit_runtime(profile)
        print(
            json.dumps(
                {
                    "mode": "preflight",
                    "qualified": False,
                    "production_release_qualified": False,
                    "runtime": runtime,
                }
            )
        )
        return 0
    except (ValueError, OSError, ImportError, subprocess.SubprocessError):
        print(
            json.dumps(
                {
                    "mode": "blocked",
                    "qualified": False,
                    "production_release_qualified": False,
                    "error": "admission_or_fixture_refused",
                }
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
