"""Removable Docker OCI boundary for trusted, offline Linux research attempts.

No runner integration or report publication. Mocked CLI checks are not native
qualification. Operator configuration is immutable and never a job-request field.
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from quantmesh.research.jobs import RunBudget
from quantmesh.research.linux_bootstrap import MAX_OUTPUT_BYTES, output_size, verify_limits

OWNER_LABEL = "org.quantmesh.research.owner"
BOOTSTRAP_PATH = "/opt/quantmesh/linux_bootstrap.py"
PYTHON_PATH = "/usr/local/bin/python3"
CLI_TIMEOUT = 5.0
CLI_BYTES = 64 * 1024
CONTROL_WRITE_SECONDS = 1.0


class LinuxContainmentError(RuntimeError):
    """Fixed sanitized error code; never forwards Docker/vendor payloads."""


def bootstrap_digest() -> str:
    return hashlib.sha256(Path(__file__).with_name("linux_bootstrap.py").read_bytes()).hexdigest()


def _safe_path(path: Path) -> Path:
    if not path.is_absolute() or any(c in str(path) for c in (",", "\n", "\r")):
        raise LinuxContainmentError("unsafe_path")
    for part in (path, *path.parents):
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise LinuxContainmentError("unsafe_path")
    return path.resolve()


class _Transport:
    """Bounded stdout/stderr draining, including a hung CLI or oversized response."""

    def __init__(self, argv: list[str], env: dict[str, str], *, lines=False):
        self.process = subprocess.Popen(
            argv,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        self.lines: queue.Queue = queue.Queue(maxsize=16)
        self.line_mode = lines
        self.overflow = threading.Event()
        self.stdout = bytearray()
        self.threads = []
        for stream, is_stdout in ((self.process.stdout, True), (self.process.stderr, False)):
            thread = threading.Thread(target=self._drain, args=(stream, is_stdout), daemon=True)
            thread.start()
            self.threads.append(thread)

    def _drain(self, stream, is_stdout):
        count = 0
        pending = b""
        try:
            while chunk := stream.read(1024):
                count += len(chunk)
                if count > CLI_BYTES:
                    self.overflow.set()
                    self.process.kill()
                    break
                if is_stdout:
                    self.stdout.extend(chunk)
                    if not self.line_mode:
                        continue
                    pending += chunk
                    while b"\n" in pending:
                        line, pending = pending.split(b"\n", 1)
                        try:
                            self.lines.put_nowait(line)
                        except queue.Full:
                            self.overflow.set()
                            self.process.kill()
                            return
        except OSError:
            pass
        finally:
            stream.close()

    def receive(self, timeout: float) -> dict:
        try:
            line = self.lines.get(timeout=timeout)
            result = json.loads(line)
            if self.overflow.is_set() or not isinstance(result, dict):
                raise ValueError
            return result
        except (queue.Empty, ValueError) as exc:
            raise LinuxContainmentError("attach_failed") from exc

    def send(self, value: str):
        if self.overflow.is_set() or self.process.poll() is not None:
            raise LinuxContainmentError("control_lost")
        finished = threading.Event()
        failed = threading.Event()

        def write():
            try:
                self.process.stdin.write((value + "\n").encode("ascii"))
                self.process.stdin.flush()
            except (OSError, ValueError):
                failed.set()
            finally:
                finished.set()

        # Killing a wedged attachment unblocks its pipe writer; PID1 owns the tree.
        threading.Thread(target=write, daemon=True).start()
        if not finished.wait(CONTROL_WRITE_SECONDS) or failed.is_set():
            self.overflow.set()
            self.process.kill()
            raise LinuxContainmentError("control_lost")

    def close(self):
        if self.process.poll() is None:
            self.process.kill()
        if self.process.stdin:
            self.process.stdin.close()
        self.process.wait(timeout=CLI_TIMEOUT)
        for thread in self.threads:
            thread.join(timeout=1)


@dataclass(frozen=True)
class LinuxExecutionProfile:
    endpoint: str
    docker_cli: Path
    image_id: str
    uid: int
    gid: int
    fixture_root: Path

    def __post_init__(self):
        allowed = self.endpoint in {
            "unix:///var/run/docker.sock",
            "npipe:////./pipe/dockerDesktopLinuxEngine",
        } or re.fullmatch(r"unix:///run/user/[1-9][0-9]*/docker.sock", self.endpoint)
        if (
            not allowed
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", self.image_id)
            or type(self.uid) is not int
            or type(self.gid) is not int
            or not 1 <= self.uid <= 65535
            or not 1 <= self.gid <= 65535
        ):
            raise LinuxContainmentError("unsafe_profile")
        for name in ("docker_cli", "fixture_root"):
            path = _safe_path(Path(getattr(self, name)))
            object.__setattr__(self, name, path)
        if not self.docker_cli.is_file() or not self.fixture_root.is_dir():
            raise LinuxContainmentError("missing_profile_path")

    def cli_environment(self) -> dict[str, str]:
        # Absolute executable; no HOME, Docker context/config, proxy or credentials.
        return {key: os.environ[key] for key in ("SystemRoot", "WINDIR") if key in os.environ}

    def argv(self, args: list[str]) -> list[str]:
        # Config is an empty, attempt-owned directory; never reads ~/.docker.
        return [
            str(self.docker_cli),
            "--host",
            self.endpoint,
            "--config",
            str(self.fixture_root / ".empty-docker-config"),
            *args,
        ]

    def invoke(self, args: list[str]) -> str:
        try:
            transport = _Transport(self.argv(args), self.cli_environment())
            try:
                code = transport.process.wait(timeout=CLI_TIMEOUT)
                for thread in transport.threads:
                    thread.join(timeout=1)
                if code or transport.overflow.is_set():
                    raise LinuxContainmentError("engine_command_failed")
                return transport.stdout.decode("utf-8").strip()
            finally:
                transport.close()
        except (OSError, subprocess.TimeoutExpired, UnicodeError) as exc:
            raise LinuxContainmentError("engine_unavailable") from exc

    def prerequisites(self) -> dict:
        config = self.fixture_root / ".empty-docker-config"
        _safe_path(config)
        config.mkdir(exist_ok=True)
        if any(config.iterdir()):
            raise LinuxContainmentError("unsafe_docker_config")
        try:
            engine = json.loads(self.invoke(["info", "--format", "{{json .}}"]))
            image = json.loads(self.invoke(["image", "inspect", self.image_id]))[0]
            config = image.get("Config", {})
            image_env = config.get("Env") or []
            if (
                engine["OSType"] != "linux"
                or engine["CgroupVersion"] != "2"
                or image["Id"] != self.image_id
                or image["Os"] != "linux"
                or config.get("Volumes")
                or any(
                    e.split("=", 1)[0]
                    not in {
                        "PATH",
                        "LANG",
                        "LC_ALL",
                        "PYTHONDONTWRITEBYTECODE",
                        "PYTHON_VERSION",
                        "PYTHON_SHA256",
                        "PYTHON_PIP_VERSION",
                        "PYTHON_GET_PIP_URL",
                        "PYTHON_GET_PIP_SHA256",
                    }
                    for e in image_env
                )
            ):
                raise ValueError
            return {
                "engine_id": engine["ID"],
                "image_id": image["Id"],
                "kernel": engine.get("KernelVersion"),
                "engine_version": engine.get("ServerVersion"),
            }
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LinuxContainmentError("unqualified_runtime") from exc


def _attach(profile: LinuxExecutionProfile, container_id: str) -> _Transport:
    try:
        return _Transport(
            profile.argv(["start", "--attach", "--interactive", container_id]),
            profile.cli_environment(),
            lines=True,
        )
    except OSError as exc:
        raise LinuxContainmentError("attach_failed") from exc


class LinuxOwnedProcess:
    """One attempt owns only its returned full container ID and random nonce.

    Caller must pulse at least once per second; no automatic owner-survival
    thread. Missing/hung CLI cannot disable the independent PID1 watchdog.
    """

    def __init__(
        self,
        profile: LinuxExecutionProfile,
        command: list[str],
        budget: RunBudget,
        inputs: Path,
        output: Path,
    ):
        self.profile = profile
        self.container_id = None
        self.nonce = uuid.uuid4().hex
        self.transport = None
        self.evidence: dict = {"qualification": "unqualified", "native": False}
        self.closed = False
        self.started = time.monotonic()
        self.budget = budget
        if budget.cpu_limit != 1:
            raise LinuxContainmentError("fractional_cpu_unsupported")
        if (
            not command
            or any(not isinstance(c, str) or "\x00" in c for c in command)
            or not command[0].startswith("/")
        ):
            raise LinuxContainmentError("unsafe_command")
        self.inputs, self.output = _safe_path(inputs), _safe_path(output)
        root = profile.fixture_root
        if (
            not self.inputs.is_dir()
            or self.output.exists()
            or not self.inputs.is_relative_to(root)
            or self.inputs == root
            or not self.output.is_relative_to(root)
            or self.output == root
            or self.output.is_relative_to(self.inputs)
            or self.inputs.is_relative_to(self.output)
        ):
            raise LinuxContainmentError("unsafe_mounts")
        # Reject existing nested links too; trusted datasets cannot alias host secrets.
        if any(
            p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction())
            for p in self.inputs.rglob("*")
        ):
            raise LinuxContainmentError("unsafe_mounts")
        self.evidence.update(profile.prerequisites())
        self.output.mkdir(parents=False)
        if os.name == "posix":
            os.chown(self.output, profile.uid, profile.gid)
            self.output.chmod(0o700)
        args = [
            "create",
            "--pull=never",
            "--restart=no",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--pids-limit=128",
            "--cpus=1",
            f"--memory={budget.memory_mib}m",
            f"--memory-swap={budget.memory_mib}m",
            "--tmpfs=/tmp:rw,noexec,nosuid,size=16m",
            "--log-driver=none",
            "--interactive",
            "--user",
            f"{profile.uid}:{profile.gid}",
            "--label",
            f"{OWNER_LABEL}={self.nonce}",
            "--mount",
            f"type=bind,src={self.inputs},dst=/inputs,readonly",
            "--mount",
            f"type=bind,src={self.output},dst=/output",
            "--entrypoint",
            PYTHON_PATH,
            profile.image_id,
            "-B",
            "-I",
            BOOTSTRAP_PATH,
            str(budget.memory_mib),
            str(budget.timeout_seconds),
            *command,
        ]
        try:
            returned = profile.invoke(args)
            if not re.fullmatch(r"[0-9a-f]{64}", returned):
                raise LinuxContainmentError("invalid_container_id")
            self.container_id = returned
            self._inspect()
            self.transport = _attach(profile, returned)
            ready = self.transport.receive(CLI_TIMEOUT)
            if ready.get("event") != "ready" or ready.get("bootstrap_sha256") != bootstrap_digest():
                raise LinuxContainmentError("unqualified_bootstrap")
            verify_limits(ready["limits"], budget.memory_mib)
            self.evidence.update(
                limits=ready["limits"], bootstrap_sha256=bootstrap_digest(), container_id=returned
            )
            self.transport.send("go")
            self.started = time.monotonic()
        except (LinuxContainmentError, ValueError, KeyError, TypeError) as exc:
            try:
                self.close()
            except LinuxContainmentError:
                pass  # Ownership mismatch refuses cleanup rather than touching a sibling.
            raise LinuxContainmentError("admission_failed") from exc

    def _inspect(self) -> dict:
        try:
            doc = json.loads(self.profile.invoke(["inspect", self.container_id]))[0]
            if (
                doc["Id"] != self.container_id
                or doc["Image"] != self.profile.image_id
                or doc["Config"]["Labels"][OWNER_LABEL] != self.nonce
            ):
                raise ValueError
            return doc
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            raise LinuxContainmentError("ownership_mismatch") from exc

    def pulse(self) -> None:
        if self.closed or self.transport is None:
            raise LinuxContainmentError("control_lost")
        self.transport.send("pulse")

    def poll(self) -> int | None:
        state = self._inspect()["State"]
        self.evidence.update(
            oom_killed=bool(state["OOMKilled"]),
            exit_code=int(state["ExitCode"]),
            running=bool(state["Running"]),
            elapsed_seconds=time.monotonic() - self.started,
        )
        try:
            oversized = output_size(self.output) > MAX_OUTPUT_BYTES
        except (OSError, ValueError):
            oversized = True
        if oversized:
            self.evidence["controller_failure"] = "output_limit"
            self.close()
            return 125
        if state["Running"]:
            if time.monotonic() - self.started > self.budget.timeout_seconds:
                self.close()
                self.evidence["controller_failure"] = "timeout"
                return 124
            return None
        return 137 if state["OOMKilled"] else int(state["ExitCode"])

    def close(self) -> None:
        if self.closed:
            return
        try:
            if self.container_id:
                self._inspect()  # Exact identity AND nonce before rm --force.
                self.profile.invoke(["rm", "--force", self.container_id])
            self.closed = True
        finally:
            if self.transport:
                self.transport.close()  # CLI death is never the containment operation.
