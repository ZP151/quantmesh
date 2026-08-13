"""Bounded JSON subprocess boundary for synchronous provider SDKs."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from quantmesh.data.objects import is_reparse_point

_REQUEST_MARKER = "{request}"
_OUTPUT_MARKER = "{output}"
_MAX_OUTPUT_BYTES = 64 * 1024 * 1024
_INHERITED_ENVIRONMENT = {
    "COMSPEC",
    "PATH",
    "PATHEXT",
    "SYSTEMDRIVE",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "WINDIR",
}


class CollectionProcessError(RuntimeError):
    """A provider worker failed without producing trustworthy staged output."""


class CollectionProcessTimeout(CollectionProcessError):
    """A provider worker exceeded its whole-process deadline and was stopped."""


def _child_environment() -> dict[str, str]:
    environment = {
        name: value
        for name, value in os.environ.items()
        if name.upper() in _INHERITED_ENVIRONMENT
    }
    environment.update(
        {
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
            "PYTHONUTF8": "1",
        }
    )
    return environment


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def run_bounded_json_process(
    command: Sequence[str],
    *,
    request: dict[str, Any],
    timeout_seconds: float,
    scratch_root: Path,
) -> dict[str, Any]:
    """Run a no-stdin worker and accept only its bounded staged JSON result.

    The command must contain one ``{request}`` and one ``{output}`` argument.
    The worker has no inherited proxy, token, password or API-key variables.
    Staged output is removed on every return path and is never a manifest.
    """
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if command.count(_REQUEST_MARKER) != 1 or command.count(_OUTPUT_MARKER) != 1:
        raise ValueError("command must contain one request and one output marker")
    candidate_root = Path(scratch_root)
    if is_reparse_point(candidate_root):
        raise ValueError("scratch root must not be a symlink or reparse point")
    root = candidate_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if is_reparse_point(root) or not root.is_dir():
        raise ValueError("scratch root must be a real directory")

    with tempfile.TemporaryDirectory(dir=root, prefix=".collection-") as temporary:
        stage = Path(temporary)
        request_path = stage / "request.json"
        output_path = stage / "output.json"
        request_path.write_text(
            json.dumps(request, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        argv = [
            str(request_path) if item == _REQUEST_MARKER else
            str(output_path) if item == _OUTPUT_MARKER else item
            for item in command
        ]
        creation_flags = (
            subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
            if os.name == "nt"
            else 0
        )
        process = subprocess.Popen(
            argv,
            cwd=root,
            env=_child_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creation_flags,
            start_new_session=os.name != "nt",
        )
        try:
            _, stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as error:
            _terminate_process_tree(process)
            raise CollectionProcessTimeout(
                f"collection worker exceeded {timeout_seconds:g}-second process deadline"
            ) from error
        if process.returncode != 0:
            summary = " ".join(stderr.strip().splitlines())[-500:]
            detail = f": {summary}" if summary else ""
            raise CollectionProcessError(
                f"collection worker exited with code {process.returncode}{detail}"
            )
        if not output_path.is_file():
            raise CollectionProcessError("collection worker produced no staged output")
        size = output_path.stat().st_size
        if size <= 0 or size > _MAX_OUTPUT_BYTES:
            raise CollectionProcessError("collection worker output size is invalid")
        try:
            payload = json.loads(output_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CollectionProcessError("collection worker output is invalid JSON") from error
        if not isinstance(payload, dict):
            raise CollectionProcessError("collection worker output must be a JSON object")
        return payload
