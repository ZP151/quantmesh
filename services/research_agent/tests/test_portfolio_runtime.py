"""Policy config only; filesystem admission retains separate native witnesses."""

from decimal import Decimal

import pytest
from pydantic import ValidationError
from qm_research_agent import runtime


@pytest.fixture
def config_data(tmp_path, monkeypatch):
    # Isolate config validation from Linux-only private filesystem admission.
    monkeypatch.setattr(runtime, "_directory", lambda path: path)
    return {
        "operator_id": "fixture",
        "expected_build": "a" * 40,
        "lake_root": tmp_path / "lake",
        "artifact_root": tmp_path / "artifacts",
        "credential_directory": tmp_path / "credentials",
    }


def configured(data, **updates):
    return runtime.ServiceRuntimeConfig.model_validate({**data, **updates})


def test_runtime_policy_is_optional_and_does_not_advertise_model(config_data):
    config = configured(config_data)
    assert hasattr(config, "portfolio_policy"), "missing optional portfolio configuration"
    assert config.portfolio_policy is None and config.portfolio_category is None
    instance = runtime.ServiceRuntime(config, None, None, "a" * 40, "b" * 64)
    assert instance.preflight()["capabilities"]["model"] == "unavailable"
    assert instance.preflight()["live"] is False


def test_runtime_accepts_explicit_string_decimal_policy(config_data):
    config = configured(
        config_data,
        portfolio_policy={
            "policy_id": "fixture",
            "operating_monthly_usd": "50",
            "development_total_usd": "200",
        },
        portfolio_category="development",
    )
    assert config.portfolio_policy.operating_monthly_usd == Decimal("50")
    assert config.portfolio_category == "development"


@pytest.mark.parametrize(
    "updates",
    [
        {"portfolio_category": "operating"},
        {
            "portfolio_policy": {
                "policy_id": "fixture",
                "operating_monthly_usd": "1",
                "development_total_usd": "2",
            }
        },
        {"portfolio_category": "scripted"},
        {
            "portfolio_policy": {
                "policy_id": "fixture",
                "operating_monthly_usd": 1.0,
                "development_total_usd": "2",
            },
            "portfolio_category": "operating",
        },
        {
            "portfolio_policy": {
                "policy_id": "fixture",
                "operating_monthly_usd": "51",
                "development_total_usd": "2",
            },
            "portfolio_category": "operating",
        },
        {
            "portfolio_policy": {
                "policy_id": "fixture",
                "operating_monthly_usd": "1",
                "development_total_usd": "2",
                "unknown": True,
            },
            "portfolio_category": "operating",
        },
    ],
)
def test_runtime_rejects_unpaired_coerced_or_expanded_policy(config_data, updates):
    with pytest.raises((ValueError, ValidationError)):
        configured(config_data, **updates)


def test_runtime_build_binds_policy_without_starting_model(config_data, local, monkeypatch):
    from pydantic import SecretStr
    from qm_research_agent import store as service_store
    from qm_research_agent.budgets import EffectLedger, PortfolioBudgetPolicy

    config = configured(
        config_data,
        portfolio_policy={
            "policy_id": "fixture",
            "operating_monthly_usd": "1",
            "development_total_usd": "2",
        },
        portfolio_category="operating",
    )
    monkeypatch.setattr(runtime, "_admit_runtime", lambda expected: ("a" * 40, "b" * 64))
    monkeypatch.setattr(service_store, "PostgresJobStore", lambda *args, **kwargs: local[0])
    instance = runtime.ServiceRuntime(
        config, SecretStr("fixture-private-token"), SecretStr("unused"), "a" * 40, "b" * 64
    )
    assert runtime.build_app(instance) is not None
    # A different identity cannot become a fresh authority after bootstrap.
    with pytest.raises(ValueError):
        EffectLedger(
            local[0],
            policy=PortfolioBudgetPolicy("other", Decimal("1"), Decimal("2")),
            category="operating",
        )
