"""Fixed offline PID1 controller, shipped as bytes in an operator-qualified image.

Standard library only. This file is also executable without importing QuantMesh.
Its stdin belongs exclusively to the owner; the trusted child receives DEVNULL.
Exiting PID1 closes the PID namespace, including reparented descendants.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import selectors
import signal
import subprocess
import sys
import time
from pathlib import Path

CGROUP = Path("/sys/fs/cgroup")
LIMIT_KEYS = ("memory.max", "memory.swap.max", "cpu.max", "pids.max")
MAX_OUTPUT_BYTES = 16 * 1024 * 1024
WATCHDOG_SECONDS = 5.0


def verify_limits(values: dict[str, str], memory_mib: int) -> None:
    """Admission uses actual cgroup v2 values, never Docker flag acceptance."""
    cpu = values["cpu.max"].split()
    if (
        int(values["memory.max"]) != memory_mib * 1024 * 1024
        or int(values["memory.swap.max"]) != 0
        or int(values["pids.max"]) != 128
        or len(cpu) != 2
        or int(cpu[0]) != int(cpu[1])
        or int(cpu[1]) <= 0
    ):
        raise ValueError("ineffective_limits")


def output_size(root: Path) -> int:
    total = 0
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("unsafe_output")
        if path.is_file():
            total += path.stat().st_size
    return total


def _bound_command(command: list[str], parent_binding_sha256: str | None) -> list[str]:
    """Append the parent-authenticated digest to the one fixed entry argv."""
    flags = ("--binding", "--manifest", "--inventory")
    present = {flag: command.count(flag) for flag in (*flags, "--binding-sha256")}
    if parent_binding_sha256 is None:
        if any(present.values()):
            raise ValueError("missing_parent_binding")
        return list(command)
    if (
        not re.fullmatch(r"[0-9a-f]{64}", parent_binding_sha256)
        or any(present[flag] != 1 for flag in flags)
        or present["--binding-sha256"]
        or len(command) != 11
        or command[0] != "/opt/quantmesh/venv/bin/python3"
        or command[1:5] != ["-B", "-I", "-S", "/opt/quantmesh/worker_entry.py"]
        or command[5::2] != ["--binding", "--manifest", "--inventory"]
        or command[6::2]
        != [
            "/inputs/parent-binding.json",
            "/opt/quantmesh/manifest.json",
            "/opt/quantmesh/inventory.json",
        ]
    ):
        raise ValueError("invalid_parent_binding")
    return [*command, "--binding-sha256", parent_binding_sha256]


class Control:
    """Nonblocking, bounded line protocol; no threads can keep PID1 alive."""

    def __init__(self):
        self.selector = selectors.DefaultSelector()
        self.selector.register(0, selectors.EVENT_READ)
        self.buffer = b""

    def read(self, timeout: float) -> list[str]:
        if not self.selector.select(timeout):
            return []
        data = os.read(0, 1024)
        if not data:
            raise EOFError
        self.buffer += data
        if len(self.buffer) > 4096:
            raise ValueError("invalid_control")
        lines = self.buffer.split(b"\n")
        self.buffer = lines.pop()
        return [line.decode("ascii") for line in lines]

    def close(self):
        self.selector.close()


def supervise(
    command: list[str],
    output: Path,
    timeout_seconds: int,
    *,
    watchdog_seconds: float = WATCHDOG_SECONDS,
    max_output_bytes: int = MAX_OUTPUT_BYTES,
    control: Control | None = None,
    parent_binding_sha256: str | None = None,
) -> int:
    """Controller loop, independently testable on Linux without claiming PID1 proof."""
    try:
        command = _bound_command(command, parent_binding_sha256)
    except (TypeError, ValueError):
        return 126
    control = control or Control()
    started = last_pulse = time.monotonic()
    child = None
    try:
        with (
            (output / "stdout.log").open("wb") as stdout,
            (output / "stderr.log").open("wb") as stderr,
        ):
            child = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                env={
                    "PATH": "/usr/local/bin:/usr/bin:/bin",
                    "LANG": "C.UTF-8",
                    "PYTHONDONTWRITEBYTECODE": "1",
                },
                cwd=output,
                start_new_session=True,
            )
            while True:
                now = time.monotonic()
                if now - last_pulse >= watchdog_seconds or now - started >= timeout_seconds:
                    return 124
                for line in control.read(0.05):
                    if line != "pulse":
                        return 124
                    last_pulse = time.monotonic()
                if output_size(output) > max_output_bytes:
                    return 125
                code = child.poll()
                if code is not None:
                    # The last write can race the preceding scan. Host checks again
                    # after PID1 has exited and all namespace descendants are gone.
                    if output_size(output) > max_output_bytes:
                        return 125
                    return code if code >= 0 else 128 - code
    except (EOFError, ValueError):
        return 124
    except OSError:
        return 126
    finally:
        control.close()
        if child is not None:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait(timeout=2)


def main() -> int:
    if sys.platform != "linux" or os.getpid() != 1 or os.getuid() == 0:
        return 126
    # Fixed positional metadata followed by a construction-time trusted argv.
    try:
        memory, timeout = int(sys.argv[1]), int(sys.argv[2])
        command = sys.argv[3:]
        if not 1 <= memory <= 2048 or not 1 <= timeout <= 900 or not command:
            return 126
        values = {key: (CGROUP / key).read_text().strip() for key in LIMIT_KEYS}
        verify_limits(values, memory)
        print(
            json.dumps(
                {
                    "event": "ready",
                    "limits": values,
                    "bootstrap_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                }
            ),
            flush=True,
        )
        control = Control()
        try:
            deadline = time.monotonic() + WATCHDOG_SECONDS
            while time.monotonic() < deadline:
                lines = control.read(0.05)
                if lines:
                    first = lines[0]
                    if first == "go":
                        binding_sha256 = None
                    elif first.startswith("go:") and re.fullmatch(r"go:[0-9a-f]{64}", first):
                        binding_sha256 = first[3:]
                    else:
                        return 124
                    if any(line != "pulse" for line in lines[1:]):
                        return 124
                    # Preserve an incomplete pulse already read from the byte stream.
                    # Complete post-go pulses were just observed, so supervision starts
                    # with a fresh deadline and the same control buffer/selector.
                    return supervise(
                        command,
                        Path("/output"),
                        timeout,
                        control=control,
                        parent_binding_sha256=binding_sha256,
                    )
            else:
                return 124
        finally:
            control.close()
    except (OSError, ValueError, KeyError, EOFError):
        return 126


if __name__ == "__main__":
    # os._exit guarantees PID1 death even if an unexpected Python thread appears.
    os._exit(main())
