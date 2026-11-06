"""One-command clean-checkout release gate (iteration 0013 Phase C).

Proves the release in a fresh deterministic environment, from any
clean checkout of the release commit:

  python tools/release_gate.py

Steps, all under a temporary root:

  1. Refuse to run from a dirty source checkout (the release commit
     must be exactly what Git records).
  2. Clone the current commit into the temporary root.
  3. Release-version consistency (``tools/check_release_version.py``):
     pyproject and ``__init__`` agree, the newest release-notes file
     declares the same version, and any version tag at HEAD matches —
     the rc2 rejection (tag ``v0.1.0-rc2`` vs metadata ``0.1.0rc1``)
     closed this hole in the gate.
  4. Create a fresh venv there and install the release extras
     ``.[dev,research,e2e,moomoo]``.
  5. Ruff over ``src tests tools``.
  6. Verify the installed ``quantmesh-data`` console entry point.
  7. License review (the closure contract: every pinned package
     installed and allowed, nothing untracked installed).
  8. pip-audit over ``requirements-audit.txt`` from an *isolated*
     tooling venv, so the scanner's own CLI dependencies never enter
     the release environment. ``--disable-pip``: the lock is already
     the frozen resolution, so the audit reads the pins directly with
     no re-resolution (pip's resolver would try to rebuild the
     Linux-only closure members on Windows).
  9. ``npm ci``, deterministic npm license review, and ``npm audit``
     over the exact frontend lock, followed by frontend build/tests.
 10. Full pytest suite (E2E tests use the shared Playwright browser
     cache and are reported as skipped when it is unavailable).
 11. The golden path (``tools/golden_path.py``: fixture -> data lake
     -> strategy reports -> internal paper -> all 13 workstation
     screens -> restart recovery with every audit ledger re-read).
 12. Clean-checkout proof: ``git status --porcelain`` in the clone
     must be empty after all of the above.

All generated state lives under the temporary root. On success it is
removed (keep it with ``--keep`` to inspect); on failure it is kept
and its path printed. A summary table records the commit, per-step
durations and counts.

Never run against a checkout with uncommitted changes; never installs
into the ambient environment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import traceback
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
STEPS: list[tuple[str, str]] = []
FULL_PYTEST_TIMEOUT_SECONDS = 10800
DEFAULT_PROGRESS_INTERVAL_SECONDS = 600
_PYTEST_PERCENTAGE = re.compile(r"(?<!\d)(100|[1-9]?\d)%")
_PYTEST_FAILURE_MARKER = re.compile(r"\b(?:FAILED|FAILURES|ERROR)\b")
_PYTEST_QUIET_STATUS_ROW = re.compile(
    r"(?m)^[ \t]*([.FEsxX]+)[ \t]*\[\s*(?:100|[1-9]?\d)%\][ \t]*\r?$",
)
_PROFILE_TARGETS = (
    "tests/test_decision_session_e2e.py::test_nvda_aapl_refresh_is_bounded_and_exact_results_survive_reconstruction",
    "tests/test_packet_reviews.py::test_risk_refusal_and_operator_invoked_watch_coverage_remain_exact",
)
_PROFILE_PREFIX = b"CI_PROFILE "
_PROFILE_LINE_LIMIT = 8192
_PROFILE_FIELDS = {
    "nodeid",
    "scope",
    "timing_note",
    "functions",
    "calendar_calls",
    "calendar_wall_seconds",
    "calendar_unique_arguments",
    "calendar_arguments",
    "calendar_identity_errors",
    "calendar_overflow_calls",
}


def print_console(value: object = "", *, file=None, flush: bool = False) -> None:
    """Print a summary line without crashing on a narrow Windows console.

    Step logs are decoded fail-soft so diagnostics survive a child's encoding
    mismatch.  A replacement character in that retained evidence must not make
    an otherwise completed release gate exit non-zero while printing its final
    summary.
    """

    stream = sys.stdout if file is None else file
    text = str(value)
    encoding = getattr(stream, "encoding", None) or "utf-8"
    safe = text.encode(encoding, errors="replace").decode(encoding)
    print(safe, file=stream, flush=flush)


def _venv_python(venv: Path) -> Path:
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def _venv_script(venv: Path, name: str) -> Path:
    if os.name == "nt":
        return venv / "Scripts" / f"{name}.exe"
    return venv / "bin" / name


def _node_command(argv: list[str], *, platform: str | None = None) -> list[str]:
    """Use Windows batch dispatch only on Windows; Linux runs native Node CLIs."""
    platform = os.name if platform is None else platform
    return (["cmd", "/c"] if platform == "nt" else []) + argv


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")


def _kill_step_process(proc: subprocess.Popen) -> None:
    """Stop the owned step tree, including Windows venv launcher children."""
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=30,
            )
        else:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait()


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _emit_event(events_path: Path, event: str, **fields: object) -> None:
    """Append one flushed, machine-readable lifecycle event to diagnostics."""
    payload = {"timestamp": _timestamp(), "event": event, **fields}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    with events_path.open("a", encoding="utf-8") as events:
        events.write(f"{encoded}\n")
        events.flush()
    # Lifecycle lines are intentionally sparse: start/end, first failure, and
    # at most one useful progress update per configured interval.
    print_console(encoded, flush=True)


@dataclass
class StepLogObserver:
    """Consume each step log incrementally without losing early failure text."""

    offset: int = 0
    carry: str = ""
    percentage: int | None = None
    file_identity: tuple[int, int] | None = None
    anchor_start: int = 0
    anchor: bytes = b""
    carry_starts_line: bool = True
    node_carry: str = ""
    last_node: str | None = None
    environment: dict[str, str] | None = None

    def reset(self) -> None:
        self.offset = 0
        self.carry = ""
        self.percentage = None
        self.anchor_start = 0
        self.anchor = b""
        self.carry_starts_line = True
        self.node_carry = ""
        self.last_node = None
        self.environment = None

    def _is_new_generation(self, log_path: Path, identity: tuple[int, int], size: int) -> bool:
        if self.file_identity is not None and identity != self.file_identity:
            return True
        if not self.offset or size < self.offset:
            return size < self.offset
        with log_path.open("rb") as log:
            log.seek(self.anchor_start)
            return log.read(len(self.anchor)) != self.anchor

    def sample(self, log_path: Path) -> tuple[int, int | None, bool]:
        stat = log_path.stat()
        identity = (stat.st_dev, stat.st_ino)
        if self._is_new_generation(log_path, identity, stat.st_size):
            self.reset()
        self.file_identity = identity
        with log_path.open("rb") as log:
            log.seek(self.offset)
            text = log.read().decode("utf-8", errors="replace")
            self.offset = log.tell()
            self.anchor_start = max(0, self.offset - 256)
            log.seek(self.anchor_start)
            self.anchor = log.read(self.offset - self.anchor_start)
        size = log_path.stat().st_size
        node_text = self.node_carry + text
        for line in node_text.splitlines():
            node = re.match(
                r"^(\S+?\.py(?:::[^\r\n]*?)+?)(?:\s+(?:PASSED|FAILED|SKIPPED|XFAIL|XPASS|ERROR)(?:\s.*)?|\s*)$",
                line,
            )
            if node and len(node[1]) <= 4096:
                self.last_node = node[1]
            environment = re.match(
                r"platform (\w{1,32}) -- Python ([0-9][\w.+-]{0,31}), pytest-([0-9][\w.+-]{0,31})",
                line,
            )
            if environment:
                self.environment = dict(zip(("platform", "python", "pytest"), environment.groups()))
        self.node_carry = node_text.rsplit("\n", 1)[-1][-8192:]
        observed = self.carry + text
        status_text = observed if self.carry_starts_line else f"\0{observed}"
        percentages = _PYTEST_PERCENTAGE.findall(observed)
        if percentages:
            self.percentage = int(percentages[-1])
        saw_quiet_failure = any(
            "F" in statuses or "E" in statuses
            for statuses in _PYTEST_QUIET_STATUS_ROW.findall(status_text)
        )
        saw_failure = bool(_PYTEST_FAILURE_MARKER.search(observed) or saw_quiet_failure)
        if len(observed) > 256:
            self.carry_starts_line = observed[-257] == "\n"
            self.carry = observed[-256:]
        else:
            self.carry = observed
        return size, self.percentage, saw_failure


class PytestStepFeedback:
    """Parent-only metadata from verbose stdout and pytest's built-in terminal XML."""

    def __init__(self, log_path: Path, started: float):
        self.log = log_path
        self.events = log_path.with_suffix(".pytest.jsonl")
        self.current = log_path.with_suffix(".pytest.current.json")
        self.junit = log_path.with_suffix(".pytest.xml")
        self.started = started
        self.node = None
        self.count = 0

    def emit(self, event: str, status: str, **fields: object) -> None:
        row = {
            "schema": "qm.ci.external-pytest-feedback.v1",
            "event": event,
            "status": status,
            "elapsed_seconds": round(time.monotonic() - self.started, 6),
            "nodeid": self.node,
            "phase": "UNOBSERVED",
            "node_evidence": "LAST_VERBOSE_NODE",
            "log": self.log.name,
            "junit": self.junit.name,
            **fields,
        }
        encoded = json.dumps(row, sort_keys=True, ensure_ascii=True) + "\n"
        if len(encoded.encode()) > 16384:
            raise ValueError("pytest feedback metadata bound exceeded")
        temporary = self.current.with_suffix(".tmp")
        temporary.write_text(encoded, encoding="utf-8")
        temporary.replace(self.current)
        # Reserve final first-failure/terminal events while keeping a single
        # current snapshot accurate even after sparse history reaches its cap.
        if event != "current_node" or self.count < 252:
            with self.events.open("a", encoding="utf-8") as stream:
                stream.write(encoded)
                stream.flush()
            self.count += 1
            print_console(encoded.rstrip(), flush=True)

    def prepare(self, command: list[str]) -> list[str]:
        self.events.open("x", encoding="utf-8").close()
        self.junit.open("xb").close()
        command = [value for value in command if value != "-q"]
        if "-vv" not in command:
            command.append("-vv")
        command += [
            "--junitxml=" + str(self.junit.resolve()),
            "-o",
            "junit_family=xunit1",
            "-o",
            "junit_logging=no",
        ]
        self.emit(
            "stage",
            "STARTING",
            controller_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            command_sha256=hashlib.sha256(
                json.dumps([str(v) for v in command]).encode()
            ).hexdigest(),
        )
        return command

    def observe(self, observer: StepLogObserver) -> None:
        if observer.last_node != self.node:
            self.node = observer.last_node
            self.emit("current_node", "RUNNING")

    def _passed_subtests(self, counts: dict[str, int]) -> int:
        """Reconcile only explicit subpasses with independently matching primary counts."""
        with self.log.open("rb") as stream:
            stream.seek(max(0, self.log.stat().st_size - 65536))
            tail = stream.read(65536)
        if not tail.endswith(b"\n"):
            raise ValueError("missing complete pytest summary")
        line = tail.decode("utf-8", errors="replace").splitlines()[-1]
        if len(line) > 4096:
            raise ValueError("oversized pytest summary")
        match = re.fullmatch(r"=+ (.+) in [0-9]+(?:\.[0-9]+)?s(?: \([0-9:]+\))? =+", line)
        if match is None:
            raise ValueError("missing terminal pytest summary")
        summary = {}
        for part in match[1].split(", "):
            item = re.fullmatch(
                r"([1-9][0-9]{0,8}) (passed|failed|skipped|errors?|warnings?|subtests passed)", part
            )
            if item is None:
                raise ValueError("unknown pytest summary count")
            key = {"error": "errors", "warning": "warnings"}.get(item[2], item[2])
            if key in summary:
                raise ValueError("duplicate pytest summary count")
            summary[key] = int(item[1])
        expected = {
            "passed": counts["tests"] - counts["failures"] - counts["errors"] - counts["skipped"],
            "failed": counts["failures"],
            "errors": counts["errors"],
            "skipped": counts["skipped"],
        }
        if any(summary.get(key, 0) != value for key, value in expected.items()):
            raise ValueError("inconsistent pytest primary counts")
        subpassed = summary.get("subtests passed", 0)
        if subpassed == 0:
            raise ValueError("missing explicit passed subtests")
        return subpassed

    def finish(self, code: int, timed_out: bool, observer: StepLogObserver) -> bool:
        status, missing, failure, completed = "INFRASTRUCTURE_ERROR", [], None, None
        if timed_out:
            status, missing = "TIMEOUT", ["completed_pytest_result"]
        elif code not in (0, 1, 2):
            missing = ["trustworthy_test_failure_result"]
        else:
            try:
                if not 0 < self.junit.stat().st_size <= 8 * 1024 * 1024:
                    raise ValueError("missing or oversized JUnit")
                tree = ET.parse(self.junit)
                cases = tree.findall(".//testcase")
                suites = tree.findall("testsuite")
                if tree.getroot().tag != "testsuites" or not suites:
                    raise ValueError("missing JUnit suite")
                counts = {"tests": len(cases)}
                counts.update(
                    (field, sum(case.find(tag) is not None for case in cases))
                    for field, tag in (
                        ("failures", "failure"),
                        ("errors", "error"),
                        ("skipped", "skipped"),
                    )
                )
                declared = {
                    key: sum(int(suite.get(key, "-1")) for suite in suites) for key in counts
                }
                if any(declared[key] != counts[key] for key in ("failures", "errors", "skipped")):
                    raise ValueError("incomplete JUnit counts")
                if declared["tests"] != counts["tests"]:
                    # Pytest records passed subtests in suite.tests without emitting
                    # testcase elements. Never infer that difference from XML alone.
                    if (
                        len(suites) != 1
                        or declared["tests"] <= counts["tests"]
                        or declared["tests"] != counts["tests"] + self._passed_subtests(counts)
                    ):
                        raise ValueError("incomplete JUnit counts")
                nodes = set()
                outcomes = set()
                for case in cases:
                    filename, name = case.get("file", ""), case.get("name", "")
                    classname = case.get("classname", "")
                    module = filename.removesuffix(".py").replace("/", ".").replace("\\", ".")
                    classes = classname.removeprefix(module).strip(".") if module else ""
                    node = (
                        filename
                        + "::"
                        + (classes.replace(".", "::") + "::" if classes else "")
                        + name
                    )
                    failed, error = case.find("failure"), case.find("error")
                    phase = "call" if failed is not None else None
                    if error is not None:
                        message = error.get("message", "")
                        if message == "collection failure":
                            phase, node = "collection", filename
                        elif message.startswith("failed on setup with"):
                            phase = "setup"
                        elif message.startswith("failed on teardown with"):
                            phase = "teardown"
                        else:
                            raise ValueError("unobserved failure phase")
                    if (
                        not filename.strip()
                        or (phase != "collection" and not name.strip())
                        or any(ord(char) < 32 or ord(char) == 127 for char in node)
                        or (phase is not None and len(node) > 4096)
                    ):
                        raise ValueError("missing node identity")
                    if phase != "collection":
                        # Success parameters stay private to the bounded XML parser.
                        # Use the same identity for call/teardown reports of one node.
                        identity = hashlib.sha256(node.encode("utf-8")).digest()
                        if (identity, phase) in outcomes:
                            raise ValueError("duplicate JUnit node outcome")
                        outcomes.add((identity, phase))
                        nodes.add(identity)
                    if phase is not None and failure is None:
                        failure = {"nodeid": node, "phase": phase, "node_evidence": "JUNIT_RESULT"}
                completed = len(nodes)
                if not cases or (code == 0) != (failure is None):
                    raise ValueError("inconsistent terminal result")
                status = "PASSED" if code == 0 else "TEST_FAILED"
            except (OSError, ET.ParseError, ValueError):
                failure = None
                missing = ["complete_consistent_junit_result"]
        if status == "TEST_FAILED":
            self.emit("first_failure", status, **failure)
        self.emit(
            "terminal",
            status,
            exit_code=code,
            completed=completed,
            missing_evidence=missing,
            environment=observer.environment,
            first_failure=failure,
        )
        return status == "PASSED"


def _slow_tests(log_path: Path) -> list[str]:
    """Read the bounded pytest duration tail; unavailable summaries stay empty."""
    with log_path.open("rb") as log:
        log.seek(max(0, log_path.stat().st_size - 65536))
        tail = log.read().decode("utf-8", errors="replace")
    return re.findall(r"(?m)^\d+(?:\.\d+)?s\s+(?:call|setup|teardown)\s+.+$", tail)


def _profile_count(value: object, *, maximum: int = 1_000_000_000) -> bool:
    return type(value) is int and 0 <= value <= maximum


def _profile_seconds(value: object) -> bool:
    if type(value) is int:
        return 0 <= value <= 86400
    return type(value) is float and math.isfinite(value) and 0 <= value <= 86400


def _valid_profile(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != _PROFILE_FIELDS:
        return False
    if value["nodeid"] not in _PROFILE_TARGETS:
        return False
    if value["scope"] != "pytest-call-thread-cprofile; calendar-wrapper-all-threads":
        return False
    if value["timing_note"] != "cumulative times overlap; profiler and wrapper add overhead":
        return False
    if not all(
        _profile_count(value[key])
        for key in ("calendar_calls", "calendar_identity_errors", "calendar_overflow_calls")
    ):
        return False
    if not _profile_count(value["calendar_unique_arguments"], maximum=256):
        return False
    if not _profile_seconds(value["calendar_wall_seconds"]):
        return False
    functions = value["functions"]
    arguments = value["calendar_arguments"]
    if not isinstance(functions, list) or len(functions) > 12:
        return False
    if not isinstance(arguments, list) or len(arguments) > 12:
        return False
    for row in functions:
        if not isinstance(row, dict) or set(row) != {"function", "calls", "cumulative_seconds"}:
            return False
        label = row["function"]
        if not isinstance(label, str) or len(label) > 160:
            return False
        if any(ord(char) < 32 or char in "/\\" for char in label):
            return False
        if not _profile_count(row["calls"]) or not _profile_seconds(row["cumulative_seconds"]):
            return False
    digests = set()
    for row in arguments:
        if not isinstance(row, dict) or set(row) != {"sha256", "calls"}:
            return False
        digest = row["sha256"]
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            return False
        if digest in digests or not _profile_count(row["calls"]):
            return False
        digests.add(digest)
    if len(arguments) > value["calendar_unique_arguments"]:
        return False
    if sum(row["calls"] for row in arguments) > value["calendar_calls"]:
        return False
    if (
        value["calendar_identity_errors"] + value["calendar_overflow_calls"]
        > value["calendar_calls"]
    ):
        return False
    return True


def _unique_profile_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate profile key")
        result[key] = value
    return result


def _profile_exports(log_path: Path) -> list[dict[str, object]]:
    """Read only two bounded, exact-schema profile rows before gate cleanup."""
    profiles: dict[str, dict[str, object]] = {}
    invalid = False
    candidates = 0
    try:
        with log_path.open("rb") as log:
            while line := log.readline(_PROFILE_LINE_LIMIT + 1):
                if len(line) > _PROFILE_LINE_LIMIT:
                    if line.startswith(_PROFILE_PREFIX):
                        invalid = True
                    while line and not line.endswith(b"\n"):
                        line = log.readline(_PROFILE_LINE_LIMIT + 1)
                    continue
                if not line.startswith(_PROFILE_PREFIX):
                    continue
                candidates += 1
                if candidates > len(_PROFILE_TARGETS):
                    invalid = True
                    continue
                try:
                    profile = json.loads(
                        line[len(_PROFILE_PREFIX) :].decode("utf-8"),
                        object_pairs_hook=_unique_profile_keys,
                    )
                except (UnicodeError, ValueError, RecursionError):
                    invalid = True
                    continue
                if not _valid_profile(profile) or profile["nodeid"] in profiles:
                    invalid = True
                    continue
                profiles[profile["nodeid"]] = profile
    except OSError:
        invalid = True
    return [
        {"nodeid": nodeid, "status": "invalid" if invalid else "missing"}
        if invalid or nodeid not in profiles
        else {"nodeid": nodeid, "status": "ok", "profile": profiles[nodeid]}
        for nodeid in _PROFILE_TARGETS
    ]


def run_step(
    name: str,
    cmd: list[str],
    cwd: Path,
    logs: Path,
    timeout: int = 1800,
    progress_interval_seconds: float = DEFAULT_PROGRESS_INTERVAL_SECONDS,
) -> tuple[bool, float]:
    """Run one gate step; stream a header, write live output to the log
    file, and print the failure tail if it fails. Returns
    ``(ok, seconds)``."""
    if progress_interval_seconds <= 0:
        raise ValueError("progress_interval_seconds must be positive")

    print_console(f"== {name} ==", flush=True)
    started = time.monotonic()
    log_path = logs / f"{len(STEPS) + 1:02d}-{name.replace(' ', '-').replace('/', '-')}.log"
    events_path = logs / "events.jsonl"
    feedback = PytestStepFeedback(log_path, started) if "tools.ci_profile_plugin" in cmd else None
    timed_out = False
    # Direct unbuffered file output remains observable even without newlines;
    # no reader pipe/thread can hold up timeout cleanup or buffer pytest dots.
    with log_path.open("wb", buffering=0) as log:
        if feedback is not None:
            cmd = feedback.prepare(cmd)
        with subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=log,
            stderr=subprocess.STDOUT,
            env={**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"},
            start_new_session=os.name != "nt",
        ) as proc:
            last_progress_at = started
            last_progress_size = 0
            last_progress_percentage: int | None = None
            failure_seen = False
            observer = StepLogObserver()

            def observe() -> None:
                nonlocal failure_seen, last_progress_at
                nonlocal last_progress_percentage, last_progress_size
                now = time.monotonic()
                log_size, percentage, saw_failure = observer.sample(log_path)
                if feedback is not None:
                    feedback.observe(observer)
                elapsed = now - started
                if saw_failure and not failure_seen:
                    _emit_event(
                        events_path,
                        "step_failure_seen",
                        name=name,
                        elapsed_seconds=round(elapsed, 3),
                        log_path=str(log_path),
                    )
                    failure_seen = True
                progress_changed = (
                    log_size != last_progress_size or percentage != last_progress_percentage
                )
                if now - last_progress_at >= progress_interval_seconds and progress_changed:
                    _emit_event(
                        events_path,
                        "step_progress",
                        name=name,
                        elapsed_seconds=round(elapsed, 3),
                        log_size_bytes=log_size,
                        pytest_percentage=percentage,
                        log_path=str(log_path),
                    )
                    last_progress_at = now
                    last_progress_size = log_size
                    last_progress_percentage = percentage

            try:
                if feedback is not None:
                    feedback.emit("stage", "RUNNING", pid=proc.pid)
                _emit_event(
                    events_path,
                    "step_started",
                    name=name,
                    pid=proc.pid,
                    timeout_seconds=timeout,
                    log_path=str(log_path),
                )
                while True:
                    returncode = proc.poll()
                    if returncode is not None:
                        observe()
                        ok = returncode == 0
                        break
                    remaining = timeout - (time.monotonic() - started)
                    if remaining <= 0:
                        observe()
                        returncode = proc.poll()
                        if returncode is not None:
                            observe()
                            ok = returncode == 0
                            break
                        timed_out = True
                        _kill_step_process(proc)
                        log.write(f"\nTIMEOUT after {timeout}s\n".encode())
                        ok = False
                        break
                    # A small controller sleep makes the step observable
                    # without keeping callers busy-polling its process or
                    # repeatedly reading its log from outside the gate.
                    time.sleep(min(1.0, remaining, progress_interval_seconds))
                    observe()
                    returncode = proc.poll()
                    if returncode is not None:
                        observe()
                        ok = returncode == 0
                        break
                if feedback is not None:
                    ok = feedback.finish(proc.returncode, timed_out, observer) and ok
            except BaseException:
                _kill_step_process(proc)
                raise
            finally:
                _emit_event(
                    events_path,
                    "step_finished",
                    name=name,
                    exit_code=proc.returncode,
                    timed_out=timed_out,
                    slow_tests=_slow_tests(log_path),
                    elapsed_seconds=round(time.monotonic() - started, 3),
                    log_path=str(log_path),
                )
    elapsed = time.monotonic() - started
    minutes, seconds = divmod(int(elapsed), 60)
    if ok:
        print_console(f"ok — {minutes}:{seconds:02d}", flush=True)
    else:
        output = log_path.read_text(encoding="utf-8", errors="replace")
        tail = "\n".join(output.splitlines()[-60:])
        print_console(
            f"FAILED after {minutes}:{seconds:02d}; exit code {proc.returncode}; last output:",
            flush=True,
        )
        print_console(tail, flush=True)
    STEPS.append((name, f"{minutes}:{seconds:02d}"))
    return ok, elapsed


def _counts(summary_line: str) -> dict[str, int]:
    return {word: int(count) for count, word in re.findall(r"(\d+) (\w+)", summary_line)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="One-command clean-checkout release verification (iteration 0013 Phase C).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="keep the temporary gate root after a successful run",
    )
    args = parser.parse_args()

    # 1. A release gate proves the *commit*; a dirty checkout is refuse-able.
    status = _git(["status", "--porcelain"], REPO)
    if status.stdout.strip():
        print(
            "REFUSED: the source checkout is dirty — commit or stash before "
            "running the release gate:",
        )
        print(status.stdout)
        return 1
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], REPO).stdout.strip()
    commit = _git(["rev-parse", "HEAD"], REPO).stdout.strip()
    print(
        f"release gate over {branch} @ {commit[:12]} — source checkout clean, "
        "proceeding with a fresh deterministic environment",
        flush=True,
    )

    temp = Path(tempfile.mkdtemp(prefix="qmesh-release-gate-"))
    checkout = temp / "checkout"
    logs = temp / "logs"
    logs.mkdir()

    def step(name: str, cmd: list[str], cwd: Path, timeout: int) -> tuple:
        return (name, cmd, cwd, timeout)

    steps = (
        step(
            "clone current commit",
            ["git", "clone", "--no-hardlinks", "-q", ".", str(checkout)],
            REPO,
            600,
        ),
        step(
            "release version consistent (metadata, notes, tag)",
            [sys.executable, "tools/check_release_version.py"],
            checkout,
            120,
        ),
        step(
            "fresh venv",
            [sys.executable, "-m", "venv", str(temp / "release-venv")],
            temp,
            600,
        ),
        step(
            "install release extras .[dev,research,e2e,moomoo]",
            [
                _venv_python(temp / "release-venv"),
                "-m",
                "pip",
                "install",
                "-q",
                "-c",
                "requirements-audit.txt",
                "-e",
                ".[dev,research,e2e,moomoo]",
            ],
            checkout,
            1800,
        ),
        step(
            "ruff check src tests tools",
            [
                _venv_python(temp / "release-venv"),
                "-m",
                "ruff",
                "check",
                "src",
                "tests",
                "tools",
            ],
            checkout,
            600,
        ),
        step(
            "trusted data tooling installed",
            [str(_venv_script(temp / "release-venv", "quantmesh-data")), "--help"],
            checkout,
            120,
        ),
        step(
            "license review (closure contract)",
            [_venv_python(temp / "release-venv"), "tools/license_review.py"],
            checkout,
            600,
        ),
        step(
            "audit venv (isolated tooling)",
            [sys.executable, "-m", "venv", str(temp / "audit-venv")],
            temp,
            600,
        ),
        step(
            "install pip-audit (isolated)",
            [
                _venv_python(temp / "audit-venv"),
                "-m",
                "pip",
                "install",
                "-q",
                "pip-audit",
            ],
            temp,
            600,
        ),
        step(
            "pip-audit over requirements-audit.txt",
            [
                _venv_python(temp / "audit-venv"),
                "-m",
                "pip_audit",
                "-r",
                "requirements-audit.txt",
                "--no-deps",
                # The lock IS the resolution; --disable-pip audits the
                # pins directly instead of re-resolving (which would
                # try to build uvloop on Windows).
                "--disable-pip",
            ],
            checkout,
            900,
        ),
        step(
            "npm ci (frontend deps)",
            _node_command(["npm", "ci"]),
            checkout / "frontend",
            1800,
        ),
        step(
            "frontend license review (locked closure)",
            [_venv_python(temp / "release-venv"), "tools/npm_license_review.py"],
            checkout,
            120,
        ),
        step(
            "npm audit --audit-level=high",
            _node_command(["npm", "audit", "--audit-level=high"]),
            checkout / "frontend",
            600,
        ),
        step(
            "frontend bundle current (build_frontend --check)",
            [_venv_python(temp / "release-venv"), "tools/build_frontend.py", "--check"],
            checkout,
            1800,
        ),
        step(
            "frontend unit tests (vitest)",
            _node_command(["npx", "vitest", "run"]),
            checkout / "frontend",
            900,
        ),
        step(
            "full pytest suite",
            [
                _venv_python(temp / "release-venv"),
                "-m",
                "pytest",
                "-p",
                "tools.ci_profile_plugin",
                # Keep exact failing/running node IDs if a native signal stops
                # pytest before its terminal assertion summary is printed.
                "-vv",
                "--maxfail=1",
                "--durations=50",
                # Do not let pytest touch the shared Windows TEMP root:
                # a locked pytest-current symlink can make an otherwise
                # green release suite fail during pytest's final cleanup.
                # Keep the test root adjacent to (never inside) checkout,
                # because commit-resolution tests intentionally expect a
                # temp path outside the repository's .git ancestry.
                "--basetemp",
                str(temp / "pytest-tmp"),
            ],
            checkout,
            FULL_PYTEST_TIMEOUT_SECONDS,
        ),
        step(
            "golden path (walk)",
            [_venv_python(temp / "release-venv"), "tools/golden_path.py"],
            checkout,
            900,
        ),
        step(
            "clean-checkout proof",
            ["git", "status", "--porcelain"],
            checkout,
            120,
        ),
    )

    try:
        results: dict[str, tuple[bool, float]] = {}
        for name, cmd, cwd, timeout in steps:
            ok, elapsed = run_step(name, cmd, cwd, logs, timeout)
            results[name] = (ok, elapsed)
            if not ok:
                break

        summary = _git(["status", "--porcelain"], checkout)
        clean = not summary.stdout.strip()
        clone_head = _git(["rev-parse", "HEAD"], checkout).stdout.strip()
        if clone_head and clone_head != commit:
            # The clone must prove the exact source commit; a mismatch
            # is treated as a failed clone.
            elapsed = results.get("clone current commit", (False, 0.0))[1]
            results["clone current commit"] = (False, elapsed)
            print(f"clone HEAD {clone_head[:12]} does not match source {commit[:12]}")
        passed = all(results.get(name, (False, 0.0))[0] for name, *_ in steps)
    except Exception:
        # Never die silently: any crash keeps the diagnostics root.
        traceback.print_exc()
        print(f"\nRELEASE GATE CRASHED — diagnostics kept at {temp}", flush=True)
        return 1

    print("\n=== release gate summary ===")
    print(f"branch: {branch}   commit: {commit}")
    print("source checkout clean at start: yes")
    for name, (ok, elapsed) in results.items():
        print(f"  {'PASS' if ok else 'FAIL':4}  {elapsed:7.1f}s  {name}")
    print(f"clone clean at end (no generated state): {'yes' if clean else 'NO'}")

    # Counts worth recording in the iteration evidence.
    pytest_logs = tuple(logs.glob("*-full-pytest-suite.log"))
    if pytest_logs:
        pytest_log = pytest_logs[0]
        for export in _profile_exports(pytest_log):
            print_console("CI_PROFILE_EXPORT " + json.dumps(export, sort_keys=True))
        lines = [
            line
            for line in pytest_log.read_text(encoding="utf-8", errors="replace").splitlines()
            if line.strip()
        ]
        counts = _counts(lines[-1])
        printed = ", ".join(
            f"{counts[k]} {k}" for k in ("passed", "failed", "skipped", "error") if k in counts
        )
        print(f"  pytest: {printed}")
    golden_logs = tuple(logs.glob("*-golden-path-*.log"))
    if golden_logs:
        golden_log = golden_logs[0]
        for line in golden_log.read_text(encoding="utf-8", errors="replace").splitlines():
            if "checks" in line and ("PASSED" in line or "FAILED" in line):
                print_console(f"  golden path: {line.strip()}")
    playwright_cache = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"
    if playwright_cache.exists():
        print("  playwright browser cache: present (E2E tests ran)")
    else:
        print("  playwright browser cache: absent (E2E tests skipped)")

    if passed and clean:
        print(
            "\nRELEASE GATE PASSED — the release is verified in a fresh deterministic environment.",
            flush=True,
        )
        if not args.keep:
            shutil.rmtree(temp, ignore_errors=True)
            print(f"temporary gate root removed ({temp})")
        else:
            print(f"temporary gate root kept ({temp})")
        return 0
    print(f"\nRELEASE GATE FAILED — diagnostics kept at {temp}", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
