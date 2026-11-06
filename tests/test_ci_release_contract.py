"""Static public release closure; private operational publication is a separate gate."""

import hashlib
import subprocess
from pathlib import Path

import pytest

from tools import quality_gate
from tools.research import ivv_trusted_runner


def test_actual_git_release_sources_and_abi():
    pins = quality_gate.validate_release_sources()
    assert len(pins) == 7
    assert all(len(value) == 64 for value in pins.values())


@pytest.mark.parametrize("change", ["helper", "abi", "manifest"])
def test_release_closure_refuses_unreviewed_pin_abi_or_missing_role(monkeypatch, change):
    repository = Path(__file__).resolve().parents[1]
    original_read = Path.read_bytes
    original_git = subprocess.check_output
    original_sources = ivv_trusted_runner._sources
    helper_path = "tools/research/capture_opend_ivv_daily.py"
    helper = original_git(["git", "show", "HEAD:" + helper_path], cwd=repository)
    if change == "manifest":

        def missing(mode):
            value = original_sources(mode)
            value.pop("native_producer_sha256")
            return value

        monkeypatch.setattr(ivv_trusted_runner, "_sources", missing)
    else:
        updated = helper + b"\n# unreviewed helper change\n"
        if change == "abi":
            updated = helper.replace(
                b"def capture_trusted_once(\n    plan_path,",
                b"def capture_trusted_once(\n    changed_plan,",
            )
        issuer = original_git(
            ["git", "show", "HEAD:tools/research/ivv_dev_diagnostic.py"], cwd=repository
        )
        if change == "abi":
            issuer = issuer.replace(
                hashlib.sha256(helper).hexdigest().encode(),
                hashlib.sha256(updated).hexdigest().encode(),
            )
        replacements = {helper_path: updated, "tools/research/ivv_dev_diagnostic.py": issuer}

        def git(command, **kwargs):
            relative = command[-1].removeprefix("HEAD:")
            return replacements.get(relative) or original_git(command, **kwargs)

        def read(path):
            relative = path.relative_to(repository).as_posix()
            return replacements.get(relative) or original_read(path)

        monkeypatch.setattr(subprocess, "check_output", git)
        monkeypatch.setattr(Path, "read_bytes", read)
    with pytest.raises(ValueError, match="release (issuer|ABI|manifest)"):
        quality_gate.validate_release_sources(repository)


@pytest.mark.parametrize(
    ("function", "argument", "replacement"),
    [
        ("run_once", "startup_ref", "*, startup_ref"),
        ("run_once", "startup_ref", "startup_ref, /"),
        ("run_once", "startup_ref", "startup_ref=None"),
        ("capture_trusted_once", "expected_go_sha256,", "expected_go_sha256=None,"),
    ],
    ids=["keyword-only", "positional-only", "positional-default", "keyword-default"],
)
def test_release_closure_refuses_argument_kind_or_required_default_drift(
    monkeypatch, function, argument, replacement
):
    repository = Path(__file__).resolve().parents[1]
    original_read, original_git = Path.read_bytes, subprocess.check_output
    relative = "tools/research/" + (
        "ivv_trusted_runner.py" if function == "run_once" else "capture_opend_ivv_daily.py"
    )
    raw = original_git(["git", "show", "HEAD:" + relative], cwd=repository)
    start = raw.index(f"def {function}(".encode())
    end = raw.index(b"):", start) + 2
    signature = raw[start:end]
    assert signature.count(argument.encode()) == 1
    updated = raw[:start] + signature.replace(argument.encode(), replacement.encode()) + raw[end:]
    replacements = {relative: updated}
    if function == "capture_trusted_once":
        issuer_path = "tools/research/ivv_dev_diagnostic.py"
        issuer = original_git(["git", "show", "HEAD:" + issuer_path], cwd=repository)
        replacements[issuer_path] = issuer.replace(
            hashlib.sha256(raw).hexdigest().encode(),
            hashlib.sha256(updated).hexdigest().encode(),
        )

    def git(command, **kwargs):
        return replacements.get(command[-1].removeprefix("HEAD:")) or original_git(
            command, **kwargs
        )

    def read(path):
        return replacements.get(path.relative_to(repository).as_posix()) or original_read(path)

    monkeypatch.setattr(subprocess, "check_output", git)
    monkeypatch.setattr(Path, "read_bytes", read)
    with pytest.raises(ValueError, match="release ABI differs: " + function):
        quality_gate.validate_release_sources(repository)
