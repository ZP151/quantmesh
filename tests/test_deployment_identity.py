"""Opt-in staging identity for the private AWS acceptance station."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from quantmesh import __version__
from quantmesh.api.app import _health, create_app
from quantmesh.execution.accounting import PaperAccount
from quantmesh.settings import Settings, settings

EXACT_BUILD_REF = "0123456789abcdef0123456789abcdef01234567"


@pytest.mark.parametrize(
    "build_ref",
    [
        None,
        "",
        "0123456",
        "0123456789ABCDEF0123456789ABCDEF01234567",
        "z123456789abcdef0123456789abcdef01234567",
        "0123456789abcdef0123456789abcdef012345678",
    ],
)
def test_staging_refuses_a_missing_or_non_exact_commit(build_ref: str | None) -> None:
    """A typo or branch name must not let the station misidentify its build."""
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="staging", build_ref=build_ref)


def test_unknown_deployment_environment_is_rejected() -> None:
    """Adding a new hosting authority requires a deliberate settings change."""
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="production", build_ref=EXACT_BUILD_REF)


def test_local_settings_need_no_build_ref() -> None:
    local = Settings(_env_file=None)

    assert local.environment == "local"
    assert local.build_ref is None


def test_staging_accepts_one_exact_commit() -> None:
    staging = Settings(
        _env_file=None,
        environment="staging",
        build_ref=EXACT_BUILD_REF,
    )

    assert staging.environment == "staging"
    assert staging.build_ref == EXACT_BUILD_REF


def test_local_health_contract_is_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "environment", "local")
    monkeypatch.setattr(settings, "build_ref", None, raising=False)

    assert _health() == {
        "status": "ok",
        "project": "QuantMesh",
        "version": __version__,
        "paper_mode": True,
        "live_trading": False,
    }


def test_staging_health_identifies_the_exact_build_on_both_mounts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "environment", "staging")
    monkeypatch.setattr(settings, "build_ref", EXACT_BUILD_REF, raising=False)
    client = TestClient(create_app(account=PaperAccount(cash=100_000.0)))

    for path in ("/health", "/api/health"):
        response = client.get(path)

        assert response.status_code == 200
        assert response.json() == {
            "status": "ok",
            "project": "QuantMesh",
            "version": __version__,
            "paper_mode": True,
            "live_trading": False,
            "deployment": {
                "environment": "staging",
                "build_ref": EXACT_BUILD_REF,
            },
            "runtime_mode": "operator",
        }
