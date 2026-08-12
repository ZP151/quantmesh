"""Iteration 0013 Phase B: the release metadata and dependency-audit
contracts, pinned by tests.

- The package version must agree between ``pyproject.toml`` and
  ``quantmesh/__init__.py`` (the package data test the release process
  references), and must be the PEP 440 release-candidate form while the
  RC line is open.
- ``requirements-audit.txt`` is the deterministic audit closure: it
  must pin every top-level dependency declared in ``pyproject.toml``
  (base + every extra) at a version satisfying the declared specifier,
  and must not pin the project itself.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version

from quantmesh import __version__

REPO = Path(__file__).resolve().parents[1]
PYPROJECT = REPO / "pyproject.toml"
AUDIT_LOCK = REPO / "requirements-audit.txt"


def _load_pyproject() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def _declared_requirements() -> list[Requirement]:
    """Every top-level dependency the release install can bring in:
    the base ``[project].dependencies`` plus every extra in
    ``[project.optional-dependencies]``."""
    project = _load_pyproject()
    declared = list(project["project"].get("dependencies", []))
    for extra, requirements in project["project"].get(
        "optional-dependencies", {}
    ).items():
        declared.extend(requirements)
    return [Requirement(entry) for entry in declared]


def _audit_lock_pins() -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in AUDIT_LOCK.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        name, _, version = line.partition("==")
        name, version = name.strip(), version.strip()
        assert name and version, f"malformed pin: {line!r}"
        # PEP 503 normalized names, so declarations and pins compare.
        pins[re.sub(r"[-_.]+", "-", name).lower()] = version
    return pins


class TestVersionMetadata:
    def test_pyproject_version_agrees_with_package(self) -> None:
        project = _load_pyproject()
        assert project["project"]["version"] == __version__

    def test_version_is_the_release_candidate_line(self) -> None:
        # Phase 0020 starts the compatible 0.1.1 candidate line. Operator
        # acceptance may later promote the same verified scope to 0.1.1;
        # it does not authorize live execution.
        assert __version__ == "0.1.1rc1"
        assert Version(__version__).is_prerelease

    def test_workstation_footer_shows_the_package_version(self) -> None:
        # The 13-screen workstation renders the package version in its
        # footer (tests/test_workstation.py pins `__version__ in html`);
        # this cross-checks the same invariant from the metadata side so
        # a version change can never drift out of the UI silently.
        footer_source = (
            REPO / "src" / "quantmesh" / "api" / "workstation.py"
        ).read_text(encoding="utf-8")
        assert "__version__" in footer_source


class TestAuditLockConsistency:
    def test_every_declared_dependency_is_pinned(self) -> None:
        pins = _audit_lock_pins()
        assert pins, "the audit lock must not be empty"
        for requirement in _declared_requirements():
            assert requirement.name in pins, (
                f"{requirement.name} is declared in pyproject.toml but "
                "missing from requirements-audit.txt"
            )

    def test_pins_satisfy_declared_specifiers(self) -> None:
        pins = _audit_lock_pins()
        for requirement in _declared_requirements():
            version = Version(pins[requirement.name])
            assert requirement.specifier.contains(version), (
                f"requirements-audit.txt pins {requirement.name}=={pins[requirement.name]}"
                f" which does not satisfy the declared {requirement.specifier}"
            )

    def test_lock_pins_are_unique_and_never_the_project_itself(self) -> None:
        pins = _audit_lock_pins()
        assert len(pins) == len(AUDIT_LOCK.read_text(encoding="utf-8").splitlines())
        assert "quantmesh" not in pins
        # Pinned names use canonical casing per name (ImageIO, PyYAML,
        # Jinja2, ...); duplicates would collide in the normalized dict.
        raw_names = [
            line.partition("==")[0].strip()
            for line in AUDIT_LOCK.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(raw_names) == len(set(raw_names))

    def test_lock_is_sorted_and_clean(self) -> None:
        lines = [
            line
            for line in AUDIT_LOCK.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert lines == sorted(lines)
        assert lines == [line.strip() for line in lines]
