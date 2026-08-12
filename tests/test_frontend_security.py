"""Deterministic frontend dependency security gates."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
LOCK = REPO / "frontend" / "package-lock.json"
REVIEW = REPO / "tools" / "npm_license_review.py"


def _review_module():
    spec = importlib.util.spec_from_file_location("npm_license_review", REVIEW)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_frozen_frontend_lock_has_only_allowed_licenses() -> None:
    review = _review_module()
    document = json.loads(LOCK.read_text(encoding="utf-8"))

    inventory = review.review_lock_document(document)

    assert len(inventory) == 646
    assert inventory["node_modules/react"]["license"] == "MIT"


@pytest.mark.parametrize("license_name", [None, "GPL-3.0-only", "SEE LICENSE IN X"])
def test_frontend_license_review_fails_closed(license_name: str | None) -> None:
    review = _review_module()
    package = {
        "name": "unsafe",
        "version": "1.0.0",
        "resolved": "https://registry.npmjs.org/unsafe/-/unsafe-1.0.0.tgz",
        "integrity": "sha512-test",
    }
    if license_name is not None:
        package["license"] = license_name
    document = {
        "lockfileVersion": 3,
        "packages": {"": {}, "node_modules/unsafe": package},
    }

    with pytest.raises(review.FrontendLicenseError):
        review.review_lock_document(document)


def test_frontend_audit_and_license_review_are_release_and_ci_gates() -> None:
    release_gate = (REPO / "tools" / "release_gate.py").read_text(encoding="utf-8")
    ci = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    security = (REPO / ".github" / "workflows" / "security.yml").read_text(
        encoding="utf-8"
    )

    for surface in (release_gate, ci, security):
        assert "npm_license_review.py" in surface
        assert "npm audit --audit-level=high" in surface
    assert "frontend/package.json" in security
    assert "frontend/package-lock.json" in security
