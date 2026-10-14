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
import stat
import subprocess
import threading
import time
import uuid
from collections.abc import Callable
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
# Public CPython build signer measured in the immutable configured image.
# This exact public value is not a permission for arbitrary GPG credentials.
_PUBLIC_PYTHON_SIGNER_ENV = "GPG_KEY=7169605F62C751356D054A26A821E680E5FA6305"


class LinuxContainmentError(RuntimeError):
    """Fixed sanitized error code; never forwards Docker/vendor payloads."""


def bootstrap_digest() -> str:
    return hashlib.sha256(Path(__file__).with_name("linux_bootstrap.py").read_bytes()).hexdigest()


def _matches_owned_container(
    doc: dict,
    *,
    container_id: str,
    image_id: str,
    nonce: str,
    command: list[str],
    user: str,
    inputs: str,
    output: str,
    memory_mib: int,
) -> bool:
    """Check the actual Engine record against every control requested by this owner."""
    try:
        config = doc["Config"]
        host = doc["HostConfig"]
        expected_mounts = {
            "/inputs": (str(Path(inputs).resolve()), "ro", False),
            "/output": (str(Path(output).resolve()), "rw", True),
        }
        mounts = {}
        for mount in doc["Mounts"]:
            destination = mount["Destination"]
            if destination in mounts:
                return False
            mounts[destination] = (
                mount["Type"],
                str(Path(mount["Source"]).resolve()),
                mount["Mode"],
                mount["RW"],
            )
        return bool(
            doc["Id"] == container_id
            and doc["Image"] == image_id
            and config["Labels"][OWNER_LABEL] == nonce
            and config["Entrypoint"] == [PYTHON_PATH]
            and config["Cmd"] == command
            and config["User"] == user
            and host["NetworkMode"] == "none"
            and host["Privileged"] is False
            and host["CapAdd"] in (None, [])
            and host["Devices"] in (None, [])
            and host["DeviceRequests"] in (None, [])
            and host["CgroupnsMode"] in (None, "private")
            and host.get("IpcMode") in (None, "", "private")
            and all(host.get(key) in (None, "") for key in ("PidMode", "UTSMode", "UsernsMode"))
            and host.get("Cgroup") in (None, "")
            and host.get("CgroupParent") in (None, "")
            and host.get("CgroupRules") in (None, [])
            and host["ReadonlyRootfs"] is True
            and host["CapDrop"] == ["ALL"]
            and host["SecurityOpt"] == ["no-new-privileges:true"]
            and host["PidsLimit"] == 128
            and host["NanoCpus"] == 1_000_000_000
            and host["Memory"] == memory_mib * 1024 * 1024
            and host["MemorySwap"] == memory_mib * 1024 * 1024
            and host["RestartPolicy"]["Name"] == "no"
            and host["Tmpfs"] == {"/tmp": "rw,noexec,nosuid,size=16m"}
            and host["LogConfig"]["Type"] == "none"
            and set(mounts) == set(expected_mounts)
            and mounts["/inputs"] == ("bind", expected_mounts["/inputs"][0], "ro", False)
            and mounts["/output"][0:2] == ("bind", expected_mounts["/output"][0])
            and mounts["/output"][2] in ("", "rw")
            and mounts["/output"][3] is True
        )
    except (KeyError, TypeError, ValueError, OSError):
        return False


def _binding_stat_signature(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
        info.st_uid,
        info.st_gid,
    )


def _open_parent_binding(root: Path) -> tuple[int, int | None]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    directory_fd = None
    if os.name == "posix" and os.open in os.supports_dir_fd and hasattr(os, "O_DIRECTORY"):
        directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0))
        fd = os.open("parent-binding.json", flags, dir_fd=directory_fd)
    else:
        fd = os.open(root / "parent-binding.json", flags)
    return fd, directory_fd


def _read_parent_binding(root: Path, uid: int, gid: int) -> bytes:
    fd = directory_fd = None
    try:
        fd, directory_fd = _open_parent_binding(root)
        info = os.fstat(fd)
        mode = info.st_mode & 0o777
        immutable = mode == 0o400 if os.name == "posix" else mode & 0o222 == 0
        if (
            not stat.S_ISREG(info.st_mode)
            or not immutable
            or info.st_nlink != 1
            or info.st_size <= 0
            or info.st_size > 16 * 1024
            or (os.name == "posix" and (info.st_uid != uid or info.st_gid != gid))
        ):
            raise OSError("binding metadata changed")
        chunks = []
        remaining = info.st_size + 1
        while remaining:
            chunk = os.read(fd, min(remaining, 4096))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        named = (
            os.stat("parent-binding.json", dir_fd=directory_fd, follow_symlinks=False)
            if directory_fd is not None
            else (root / "parent-binding.json").lstat()
        )
        if (
            len(raw) != info.st_size
            or _binding_stat_signature(info) != _binding_stat_signature(os.fstat(fd))
            or _binding_stat_signature(info) != _binding_stat_signature(named)
        ):
            raise OSError("binding identity changed")
        return raw
    except Exception:
        raise LinuxContainmentError("parent_binding_failed") from None
    finally:
        if fd is not None:
            os.close(fd)
        if directory_fd is not None:
            os.close(directory_fd)


def _parent_binding_signature(
    root: Path, expected_raw: bytes, uid: int, gid: int
) -> tuple[int, ...]:
    raw = _read_parent_binding(root, uid, gid) if os.name != "posix" else None
    if os.name == "posix":
        fd = directory_fd = None
        try:
            fd, directory_fd = _open_parent_binding(root)
            info = os.fstat(fd)
            raw = os.read(fd, 16 * 1024 + 1)
            named = (
                os.stat("parent-binding.json", dir_fd=directory_fd, follow_symlinks=False)
                if directory_fd is not None
                else (root / "parent-binding.json").lstat()
            )
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_mode & 0o777 != 0o400
                or info.st_nlink != 1
                or info.st_uid != uid
                or info.st_gid != gid
                or len(raw) != info.st_size
                or raw != expected_raw
                or _binding_stat_signature(info) != _binding_stat_signature(named)
            ):
                raise OSError("binding identity changed")
            return _binding_stat_signature(info)
        except Exception:
            raise LinuxContainmentError("parent_binding_failed") from None
        finally:
            if fd is not None:
                os.close(fd)
            if directory_fd is not None:
                os.close(directory_fd)
    if raw != expected_raw:
        raise LinuxContainmentError("parent_binding_failed")
    return ()


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
                    e != _PUBLIC_PYTHON_SIGNER_ENV
                    and e.split("=", 1)[0]
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
        *,
        prepare_parent_binding: Callable[[LinuxOwnedProcess, dict], tuple[bytes, str]]
        | None = None,
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
        self._expected_inspect_command = [
            "-B",
            "-I",
            BOOTSTRAP_PATH,
            str(budget.memory_mib),
            str(budget.timeout_seconds),
            *command,
        ]
        self._binding_identity = None
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
            if prepare_parent_binding is None:
                if any(arg in command for arg in ("--binding", "--manifest", "--inventory")):
                    raise LinuxContainmentError("parent_binding_required")
                start_message = "go"
            else:
                try:
                    raw, binding_sha256 = prepare_parent_binding(self, ready)
                    if (
                        type(raw) is not bytes
                        or not isinstance(binding_sha256, str)
                        or not re.fullmatch(r"[0-9a-f]{64}", binding_sha256)
                        or len(raw) > 16 * 1024
                        or hashlib.sha256(raw).hexdigest() != binding_sha256
                    ):
                        raise ValueError
                    from quantmesh.research.worker_build import parse_parent_binding

                    binding = parse_parent_binding(raw, expected_sha256=binding_sha256)
                    if (
                        binding.container_id != self.container_id
                        or binding.owner_nonce != self.nonce
                        or binding.image_id != self.profile.image_id
                        or binding.engine_id != self.evidence.get("engine_id")
                    ):
                        raise ValueError
                    _write_parent_binding(self.inputs, raw, self.profile.uid, self.profile.gid)
                    self._binding_identity = _parent_binding_signature(
                        self.inputs, raw, self.profile.uid, self.profile.gid
                    )
                    self.evidence["parent_binding_sha256"] = binding_sha256
                    start_message = f"go:{binding_sha256}"
                except Exception as exc:
                    raise LinuxContainmentError("parent_binding_failed") from exc
                self._inspect()
            self.transport.send(start_message)
            self.started = time.monotonic()
        except (LinuxContainmentError, ValueError, KeyError, TypeError) as exc:
            try:
                self.close()
            except LinuxContainmentError:
                pass  # Ownership mismatch refuses cleanup rather than touching a sibling.
            raise LinuxContainmentError("admission_failed") from exc

    def _inspect_owner(self) -> dict:
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

    def _inspect(self, *, check_parent_binding: bool = True) -> dict:
        try:
            doc = self._inspect_owner()
            if not _matches_owned_container(
                doc,
                container_id=self.container_id,
                image_id=self.profile.image_id,
                nonce=self.nonce,
                command=self._expected_inspect_command,
                user=f"{self.profile.uid}:{self.profile.gid}",
                inputs=str(self.inputs),
                output=str(self.output),
                memory_mib=self.budget.memory_mib,
            ):
                raise ValueError
            expected_binding = (
                self.evidence.get("parent_binding_sha256") if check_parent_binding else None
            )
            if expected_binding is not None:
                raw = _read_parent_binding(self.inputs, self.profile.uid, self.profile.gid)
                if hashlib.sha256(raw).hexdigest() != expected_binding:
                    raise ValueError
                from quantmesh.research.worker_build import parse_parent_binding

                binding = parse_parent_binding(raw, expected_sha256=expected_binding)
                if (
                    binding.container_id != self.container_id
                    or binding.owner_nonce != self.nonce
                    or binding.image_id != self.profile.image_id
                    or binding.engine_id != self.evidence.get("engine_id")
                    or _parent_binding_signature(
                        self.inputs, raw, self.profile.uid, self.profile.gid
                    )
                    != self._binding_identity
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
                # Exact Engine identity/config/nonce before rm. A tampered binding
                # may reject publication, but must not prevent cleanup of our own
                # still-matching container.
                self._inspect_owner()
                self.profile.invoke(["rm", "--force", self.container_id])
            self.closed = True
        finally:
            if self.transport:
                self.transport.close()  # CLI death is never the containment operation.


def _write_parent_binding(root: Path, raw: bytes, uid: int, gid: int) -> None:
    """Create one immutable-to-child binding in the already RO-mounted bundle."""
    name = "parent-binding.json"
    path = root / name
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    directory_fd = None
    fd = None
    try:
        if os.name == "posix" and os.open in os.supports_dir_fd and hasattr(os, "O_DIRECTORY"):
            directory_fd = os.open(
                root,
                os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
            )
            fd = os.open(name, flags, 0o600, dir_fd=directory_fd)
        else:
            fd = os.open(path, flags, 0o600)
        if os.name == "posix":
            os.fchown(fd, uid, gid)
        view = memoryview(raw)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short binding write")
            view = view[written:]
        os.fsync(fd)
        os.fchmod(fd, 0o400)
        os.fsync(fd)
        info = os.fstat(fd)
        named = (
            os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if directory_fd is not None
            else path.lstat()
        )

        def signature(value):
            return (
                value.st_dev,
                value.st_ino,
                value.st_mode,
                value.st_nlink,
                value.st_size,
                value.st_mtime_ns,
                value.st_ctime_ns,
                value.st_uid,
                value.st_gid,
            )

        mode = info.st_mode & 0o777
        expected_mode = mode == 0o400 if os.name == "posix" else mode & 0o222 == 0
        if (
            signature(info) != signature(named)
            or not expected_mode
            or info.st_nlink != 1
            or info.st_size != len(raw)
        ):
            raise OSError("binding identity changed")
        if directory_fd is not None:
            os.fsync(directory_fd)
    except Exception:
        raise LinuxContainmentError("parent_binding_failed") from None
    finally:
        if fd is not None:
            os.close(fd)
        if directory_fd is not None:
            os.close(directory_fd)
