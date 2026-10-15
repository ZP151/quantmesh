"""A service certificate must use the measured platform's dependency lock."""

import pytest

from tools import research_service_gate as gate


@pytest.mark.parametrize(
    ("system", "version", "machine", "profile", "filename"),
    [
        ("Windows", (3, 13), "AMD64", "windows-cp313-x86_64", "requirements.lock"),
        ("Linux", (3, 12), "x86_64", "linux-cp312-x86_64", "requirements.linux-cp312.lock"),
    ],
)
def test_gate_selects_the_lock_for_its_actual_runtime(system, version, machine, profile, filename):
    select = getattr(gate, "runtime_lock", None)
    assert callable(select), "runtime-bound lock selection is missing"
    selected_profile, path = select(system=system, version=version, machine=machine)
    assert selected_profile == profile
    assert path == gate.SERVICE / filename


@pytest.mark.parametrize(
    ("system", "version", "machine"),
    [
        ("Linux", (3, 13), "x86_64"),
        ("Linux", (3, 12), "aarch64"),
        ("Windows", (3, 12), "AMD64"),
        ("Windows", (3, 13), "ARM64"),
        ("Darwin", (3, 12), "x86_64"),
    ],
)
def test_gate_cannot_substitute_a_known_lock_for_an_unqualified_runtime(system, version, machine):
    select = getattr(gate, "runtime_lock", None)
    assert callable(select), "runtime-bound lock selection is missing"
    with pytest.raises(ValueError, match="unqualified service runtime"):
        select(system=system, version=version, machine=machine)


def test_non_cpython_cannot_use_the_cpython_lock():
    with pytest.raises(ValueError, match="unqualified service runtime"):
        gate.runtime_lock(system="Linux", version=(3, 12), machine="x86_64", implementation="PyPy")
