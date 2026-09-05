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
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
STEPS: list[tuple[str, str]] = []
FULL_PYTEST_TIMEOUT_SECONDS = 5400


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


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")


def run_step(
    name: str,
    cmd: list[str],
    cwd: Path,
    logs: Path,
    timeout: int = 1800,
) -> tuple[bool, float]:
    """Run one gate step; stream a header, capture output to the log
    file, and print the failure tail if it fails. Returns
    ``(ok, seconds)``."""
    print(f"== {name} ==", flush=True)
    started = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        output = proc.stdout + proc.stderr
        ok = proc.returncode == 0
    except subprocess.TimeoutExpired as error:
        output = f"TIMEOUT after {timeout}s\n" + (error.stdout or "") + (error.stderr or "")
        ok = False
    elapsed = time.monotonic() - started
    (logs / f"{len(STEPS) + 1:02d}-{name.replace(' ', '-').replace('/', '-')}.log").write_text(
        output, encoding="utf-8"
    )
    minutes, seconds = divmod(int(elapsed), 60)
    if ok:
        print(f"ok — {minutes}:{seconds:02d}", flush=True)
    else:
        tail = "\n".join(output.splitlines()[-60:])
        print(f"FAILED after {minutes}:{seconds:02d}; last output:", flush=True)
        print(tail, flush=True)
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
            ["cmd", "/c", "npm", "ci"],
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
            ["cmd", "/c", "npm", "audit", "--audit-level=high"],
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
            ["cmd", "/c", "npx", "vitest", "run"],
            checkout / "frontend",
            900,
        ),
        step(
            "full pytest suite",
            [
                _venv_python(temp / "release-venv"),
                "-m",
                "pytest",
                "-q",
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
        lines = [
            line for line in pytest_log.read_text(encoding="utf-8").splitlines() if line.strip()
        ]
        counts = _counts(lines[-1])
        printed = ", ".join(
            f"{counts[k]} {k}" for k in ("passed", "failed", "skipped", "error") if k in counts
        )
        print(f"  pytest: {printed}")
    golden_logs = tuple(logs.glob("*-golden-path-*.log"))
    if golden_logs:
        golden_log = golden_logs[0]
        for line in golden_log.read_text(encoding="utf-8").splitlines():
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
