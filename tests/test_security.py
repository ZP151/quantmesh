"""M10 Phase D (issue #61): the threat model and the dependency
scanning surface, pinned by doc tests.

The threat model is a *contract*: every register row names a control
and a test that pins it, and this file verifies those citations
resolve to real tests, files and ADRs in the repo. The license
inventory is the same kind of contract (iteration 0013 Phase B made
it closure-deterministic): docs/licenses.md must inventory exactly the
pinned release closure in requirements-audit.txt and agree with
tools/license_review.py's classification of every installed member;
the audit lock must be a parseable pinned closure; and the review
must refuse installed packages outside the closure, so ambient
environment drift (e.g. pip-audit's license-expression/boolean.py
toolchain in a development venv) can never silently enter the
inventory.
"""

import importlib.util
import re
from pathlib import Path

import pytest

from quantmesh.ops.source_contract import PLATFORM_TOLERATED

REPO = Path(__file__).resolve().parents[1]
THREAT_MODEL = REPO / "docs" / "threat-model.md"
LICENSES = REPO / "docs" / "licenses.md"
AUDIT_LOCK = REPO / "requirements-audit.txt"
LICENSE_REVIEW = REPO / "tools" / "license_review.py"


def _load_license_review():
    spec = importlib.util.spec_from_file_location(
        "license_review", LICENSE_REVIEW
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestThreatModel:
    def test_threat_model_present_with_register(self) -> None:
        text = THREAT_MODEL.read_text(encoding="utf-8")
        assert "| ID | Threat | Control | Pinned by |" in text
        rows = [line for line in text.splitlines() if line.startswith("| T-")]
        assert len(rows) == 15, f"expected 15 threats, found {len(rows)}"
        assert "## Accepted residuals" in text

    def test_every_pinned_citation_resolves(self) -> None:
        """Every comma-separated 'Pinned by' token names a real test
        (present in the suite source), a real repo-relative path, or an
        ADR decision reference."""
        text = THREAT_MODEL.read_text(encoding="utf-8")
        register = text.split("## Per-threat detail")[0]
        rows = [
            line for line in register.splitlines() if line.startswith("| T-")
        ]
        # The suite source, once — tokens are substrings of it.
        suite_source = "\n".join(
            p.read_text(encoding="utf-8")
            for p in (REPO / "tests").glob("test_*.py")
        )
        for row in rows:
            # Four content cells: id, threat, control, pinned-by (the
            # leading and trailing table pipes produce edge empties).
            cells = [c.strip() for c in row.split("|")[1:-1]]
            assert len(cells) == 4, f"malformed register row: {row}"
            pinned = cells[3]
            assert pinned, f"empty Pinned by cell in row {cells[0]}"
            for token in (t.strip() for t in pinned.split(",")):
                if not token:
                    continue
                assert _token_resolves(token, suite_source), (
                    f"unresolved citation {token!r} in row {cells[1]}"
                )

    def test_threat_model_names_only_existing_files(self) -> None:
        text = THREAT_MODEL.read_text(encoding="utf-8")
        for path in re.findall(r"`([\w./-]+\.(?:py|txt|md))`", text):
            if path.startswith(("tests/", "docs/", "tools/", "src/")):
                assert (REPO / path).exists(), f"{path} is referenced but missing"


def _token_resolves(token: str, suite_source: str) -> bool:
    """A citation token resolves when it is (a) a test/class name in
    the suite source, (b) an existing repo-relative path, or (c) an
    ADR decision reference. A trailing ``*`` is a wildcard
    (``test_reconcile_detects_*``) and a trailing ``(N)`` is a count,
    neither part of the name."""
    bare = token.strip("`").strip()
    bare = re.sub(r"\s*\(\d+\)\s*$", "", bare)
    if match := re.fullmatch(r"ADR-(00\d\d) decision (\d)", bare):
        # An ADR decision citation resolves only against a real
        # `### Decision N` header in exactly one matching ADR file.
        adr_dir = REPO / "docs" / "adr"
        candidates = list(adr_dir.glob(f"{match.group(1)}-*.md"))
        if len(candidates) == 1:
            text = candidates[0].read_text(encoding="utf-8")
            if re.search(rf"^### Decision {match.group(2)}\b", text, re.MULTILINE):
                return True
        return False
    if bare.startswith(("tests/", "docs/", "tools/", "src/")) and (
        REPO / bare
    ).exists():
        return True
    if bare.endswith("*") and bare[:-1] in suite_source:
        return True
    if re.search(re.escape(bare), suite_source):
        return True
    # Compound tokens like "4 tamper drills in `tests/test_ops.py`"
    # resolve when they contain a resolvable citation.
    for embedded in re.findall(r"`([^`]+)`", token):
        if _token_resolves(embedded, suite_source):
            return True
    return False


class TestLicenseReview:
    def test_commons_clause_is_refused_before_apache_text(self) -> None:
        review = _load_license_review()
        text = (
            '“Commons Clause” License Condition v1.0 ... License: '
            "Apache 2.0 with Commons Clause ... Apache License Version "
            "2.0, January 2004"
        )
        assert review._from_text(text) is None

    def test_with_exception_qualifier_is_stripped(self) -> None:
        review = _load_license_review()
        resolved = review._from_expression(
            "BSD-2-Clause AND Apache-2.0 WITH LLVM-exception"
        )
        assert resolved == "Apache-2.0 | BSD-2-Clause"

    def test_permissive_spdx_members_are_allowed(self) -> None:
        review = _load_license_review()
        assert review._from_expression(
            "BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0"
        ) == "0BSD | BSD-3-Clause | CC0-1.0 | MIT | Zlib"
        assert review._from_expression("MIT-CMU") == "MIT-CMU"
        assert review._from_expression("Apache-2.0 AND CNRI-Python") == (
            "Apache-2.0 | CNRI-Python"
        )
        assert review._from_expression("NCSA") == "NCSA"

    def test_copyleft_expression_is_refused(self) -> None:
        review = _load_license_review()
        assert review._from_expression("GPL-3.0-only") is None
        assert review._from_expression("MIT OR GPL-3.0-only") is None

    def test_moomoo_closure_license_metadata_is_classified_conservatively(self) -> None:
        review = _load_license_review()
        assert review._from_text("3-Clause BSD License") == "BSD-3-Clause"
        simplejson = _FakeDist(
            "simplejson",
            "4.1.1",
            License="MIT OR AFL-2.1",
        )
        assert review.classify(simplejson) == "MIT (documented exception)"

    def test_every_installed_closure_member_classifies_allowed(
        self,
    ) -> None:
        """The closure contract: classification covers the pinned
        release closure (requirements-audit.txt), never the ambient
        environment. Installed closure members must classify to an
        allowed license; members absent on this platform (the
        documented Linux-only set) are tolerated."""
        review = _load_license_review()
        installed = {d.metadata["Name"]: d for d in review.md.distributions()}
        closure = review.read_closure()
        assert len(closure) >= 40, "the audit lock is suspiciously thin"
        for name in closure:
            if name in review.PLATFORM_TOLERATED and name not in installed:
                continue
            assert name in installed, (
                f"{name} is pinned in requirements-audit.txt but not "
                "installed — incomplete release environment"
            )
            key = review.classify(installed[name])
            assert not key.startswith("UNKNOWN"), (
                f"{name} {installed[name].version}: {key}"
            )

    def test_licenses_doc_inventories_exactly_the_closure(self) -> None:
        """docs/licenses.md is the closure inventory: its rows must
        match the pins in requirements-audit.txt exactly (names), and
        each installed member's row must agree with the review's
        classification of it."""
        review = _load_license_review()
        doc = LICENSES.read_text(encoding="utf-8")
        # A row is inventory when its middle cell is a version number
        # (multi-license cells contain a literal " | ", so the license
        # is everything after the version); the exceptions table's
        # middle cell is a license name, never a version.
        inventory = re.compile(r"^\| ([^|]+) \| ([^|]+) \| (.+) \|$")
        doc_rows: dict[str, str] = {}
        for line in doc.splitlines():
            match = inventory.match(line)
            if match and any(ch.isdigit() for ch in match.group(2)):
                doc_rows[match.group(1).strip()] = match.group(3).strip()
        assert doc_rows, "no inventory rows parsed from docs/licenses.md"
        closure = review.read_closure()
        assert set(doc_rows) == set(closure), (
            f"docs/licenses.md inventories {sorted(set(doc_rows) ^ set(closure))}"
            " — it must match requirements-audit.txt exactly"
        )
        installed = {d.metadata["Name"]: d for d in review.md.distributions()}
        for name, pinned in closure.items():
            if name not in installed:
                continue
            key = review.classify(installed[name])
            # Version numbers drift with the environment; the license
            # key is the contract.
            assert doc_rows[name] == key, (
                f"{name}: docs say {doc_rows[name]}, review says {key}"
            )


class _FakeMetadata(dict):
    def get_all(self, key: str, default=()) -> list[str]:
        value = self.get(key)
        if value is None:
            return list(default)
        return value if isinstance(value, list) else [value]


class _FakeDist:
    def __init__(self, name: str, version: str, **metadata) -> None:
        self.name = name
        self.version = version
        self.metadata = _FakeMetadata({"Name": name, **metadata})


class _FakeMetaModule:
    def __init__(self, dists: list[_FakeDist]) -> None:
        self._dists = dists

    def distributions(self):
        return self._dists


class TestClosureContract:
    """The deterministic-environment contract (iteration 0013 Phase B):
    the review refuses any installed distribution outside the pinned
    closure, and refuses pinned members that are not installed — so an
    ambient development environment (pip-audit's toolchain, leftover
    experiments) fails with a precise message instead of silently
    drifting into the inventory."""

    def test_untracked_installed_package_is_refused(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        review = _load_license_review()
        monkeypatch.setattr(
            review,
            "md",
            _FakeMetaModule(
                [
                    _FakeDist("pinnedpkg", "1.0", **{"License-Expression": "MIT"}),
                    # pip-audit 2.10.1's transitive toolchain, exactly
                    # the documented ambient drift:
                    _FakeDist(
                        "license-expression", "30.4.4",
                        **{"License-Expression": "Apache-2.0"},
                    ),
                    _FakeDist(
                        "boolean.py", "5.0",
                        **{"License-Expression": "BSD-2-Clause"},
                    ),
                ]
            ),
        )
        _, failures, untracked, _ = review.review({"pinnedpkg": "1.0"})
        assert not failures
        assert len(untracked) == 2
        assert any("license-expression" in line for line in untracked)
        assert any("boolean.py" in line for line in untracked)
        # The CLI refuses the drift end to end.
        closure_file = tmp_path / "closure.txt"
        closure_file.write_text("pinnedpkg==1.0\n", encoding="utf-8")
        assert review.main(["--closure", str(closure_file)]) == 1

    def test_pinned_but_missing_package_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        review = _load_license_review()
        monkeypatch.setattr(
            review,
            "md",
            _FakeMetaModule(
                [_FakeDist("pinnedpkg", "1.0", **{"License-Expression": "MIT"})]
            ),
        )
        _, failures, _, _ = review.review(
            {"pinnedpkg": "1.0", "never-installed": "9.9.9"}
        )
        assert len(failures) == 1
        assert "never-installed" in failures[0]

    def test_platform_tolerated_members_may_be_absent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        review = _load_license_review()
        monkeypatch.setattr(
            review,
            "md",
            _FakeMetaModule(
                [
                    _FakeDist("pinnedpkg", "1.0", **{"License-Expression": "MIT"}),
                    _FakeDist("cffi", "2.1.1", **{"License-Expression": "GPL-3.0-only"}),
                ]
            ),
        )
        closure = {"pinnedpkg": "1.0", "uvloop": "0.22.1"}
        _, failures, _, missing = review.review(closure)
        assert not failures
        assert len(missing) == 1 and "uvloop" in missing[0]
        # The tolerance covers absence only: a tolerated name that IS
        # installed gets classified like any closure member, and can
        # fail the gate; the still-absent member stays tolerated.
        closure["cffi"] = "2.1.1"
        _, failures, _, missing = review.review(closure)
        assert len(failures) == 1 and "cffi" in failures[0]
        assert len(missing) == 1 and "uvloop" in missing[0]

    def test_platform_tolerated_matches_the_documented_set(self) -> None:
        review = _load_license_review()
        assert review.PLATFORM_TOLERATED is PLATFORM_TOLERATED
        doc = LICENSES.read_text(encoding="utf-8")
        for name in sorted(review.PLATFORM_TOLERATED):
            assert name in doc, (
                f"{name} is platform-tolerated in the tool but missing from "
                "docs/licenses.md's Linux-only closure record"
            )


class TestAuditLock:
    def test_audit_lock_is_a_pinned_parseable_closure(self) -> None:
        lines = AUDIT_LOCK.read_text(encoding="utf-8").splitlines()
        assert len(lines) >= 40, "the audit lock is suspiciously thin"
        for line in lines:
            name, _, version = line.partition("==")
            assert name and version, f"malformed pin: {line!r}"
            assert re.fullmatch(r"[\w.-]+", name), f"bad package name: {name!r}"
            assert re.fullmatch(r"[\w.+-]+", version), f"bad version: {version!r}"
        assert not any("vectorbt" in line for line in lines)
        assert not any(line.startswith("quantmesh==") for line in lines)

    @pytest.mark.parametrize(
        "unresolved",
        [
            "GPL-3.0-only",
            "LGPL-3.0-or-later",
            "Apache-2.0 WITH Commons-Clause",
            "Proprietary",
        ],
    )
    def test_refused_licenses_stay_refused(self, unresolved: str) -> None:
        review = _load_license_review()
        assert review._from_expression(unresolved) is None
