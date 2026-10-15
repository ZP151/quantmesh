import json
import threading
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import succeeded
from pydantic import SecretStr
from qm_research_agent import advisory_runtime as runtime
from qm_research_agent.budgets import EffectLedger, PortfolioBudgetPolicy
from qm_research_agent.linux_effect_scope import EffectScopeRejected
from qm_research_agent.orchestrator import AdvisoryRunner

UNIT = "quantmesh-research-advisory.service"
DIGEST = "a" * 64


def _private_file(path: Path, raw: bytes):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    path.write_bytes(raw)
    path.chmod(0o600)
    return path


def _config_data(tmp_path):
    return {
        "schema_version": 1,
        "service_config": str(tmp_path / "service.json"),
        "unit": UNIT,
        "model": runtime.DEFAULT_MODEL,
        "price_version": runtime.PRICE_VERSION,
        "remote_consent": True,
        "key_file": str(tmp_path / "private" / "openai_key"),
        "allowed_report_digests": [DIGEST],
    }


def _save_config(tmp_path, data):
    return _private_file(
        tmp_path / "private" / "advisory.json",
        json.dumps(data, separators=(",", ":")).encode(),
    )


def test_private_config_rejects_duplicate_unknown_and_coerced_values(tmp_path):
    base = _config_data(tmp_path)
    config_path = _save_config(tmp_path, base)
    assert runtime.load_advisory_config(config_path).allowed_report_digests == frozenset({DIGEST})

    for raw in (
        json.dumps(base | {"extra": "ignored"}).encode(),
        json.dumps(base | {"schema_version": "1"}).encode(),
        json.dumps(base | {"remote_consent": 1}).encode(),
        json.dumps(base | {"allowed_report_digests": [DIGEST, DIGEST]}).encode(),
        json.dumps(base | {"unit": "other.service"}).encode(),
        (json.dumps(base)[:-1] + ',"unit":"other.service"}').encode(),
    ):
        _private_file(config_path, raw)
        with pytest.raises(runtime.RuntimeRejected, match="configuration_invalid"):
            runtime.load_advisory_config(config_path)


def test_default_preflight_does_not_read_model_key_or_start_any_effect(tmp_path, monkeypatch):
    config_path = _save_config(tmp_path, _config_data(tmp_path))
    runtime_calls = []
    monkeypatch.setattr(
        runtime,
        "load_runtime",
        lambda path: (
            runtime_calls.append(path)
            or SimpleNamespace(preflight=lambda: {"capabilities": {"model": "unavailable"}})
        ),
    )
    monkeypatch.setattr(runtime, "_run_canary", lambda *args, **kwargs: pytest.fail("canary"))
    monkeypatch.setattr(runtime, "_make_store", lambda *args: pytest.fail("SQL"))
    monkeypatch.setattr(runtime, "_read_model_key", lambda *args: pytest.fail("key"))
    monkeypatch.setattr(runtime, "_make_provider", lambda *args: pytest.fail("model"))

    assert runtime.main(["--config", str(config_path)]) == 0
    assert runtime_calls == [Path(_config_data(tmp_path)["service_config"])]


def test_opt_in_is_required_for_once_mode(tmp_path, monkeypatch, capsys):
    config_path = _save_config(tmp_path, _config_data(tmp_path))
    monkeypatch.setattr(runtime, "_run_canary", lambda *args: pytest.fail("canary"))
    assert runtime.main(["--config", str(config_path), "--once"]) == 2
    assert capsys.readouterr().err.strip() == "configuration_invalid"


def test_containment_refusal_has_no_service_sql_key_or_provider_effects(
    tmp_path, monkeypatch, capsys
):
    config_path = _save_config(tmp_path, _config_data(tmp_path))
    service_config = SimpleNamespace()
    admitted = []

    def reject_scope(config):
        raise EffectScopeRejected()

    monkeypatch.setattr(runtime, "_run_canary", reject_scope)
    monkeypatch.setattr(
        runtime,
        "load_runtime",
        lambda *args: admitted.append("admit") or service_config,
    )
    monkeypatch.setattr(runtime, "_make_store", lambda *args: pytest.fail("SQL"))
    monkeypatch.setattr(runtime, "_read_model_key", lambda *args: pytest.fail("key"))
    monkeypatch.setattr(runtime, "_make_provider", lambda *args: pytest.fail("provider"))
    assert runtime.main(["--config", str(config_path), "--run", "--once"]) == 3
    assert capsys.readouterr().err.strip() == "effect scope unavailable"
    assert admitted == ["admit"]


def test_source_admission_failure_prevents_canary_and_later_effects(tmp_path, monkeypatch):
    config_path = _save_config(tmp_path, _config_data(tmp_path))

    def reject_source(*args):
        raise runtime.RuntimeRejected("source_unqualified")

    monkeypatch.setattr(runtime, "load_runtime", reject_source)
    monkeypatch.setattr(runtime, "_run_canary", lambda *args: pytest.fail("canary"))
    monkeypatch.setattr(runtime, "_make_store", lambda *args: pytest.fail("SQL"))
    monkeypatch.setattr(runtime, "_read_model_key", lambda *args: pytest.fail("key"))
    monkeypatch.setattr(runtime, "_make_provider", lambda *args: pytest.fail("provider"))
    assert runtime.main(["--config", str(config_path), "--run", "--once"]) == 2


def test_synthetic_canary_calls_bounded_path_with_scripted_transport_and_fixed_unit(monkeypatch):
    from qm_research_agent import bounded

    from quantmesh.ai.transport import ScriptedModelTransport

    observed = []

    def bounded_fixture(gateway, request, budget, *, effect_scope_unit=None):
        observed.append((gateway, request, budget, effect_scope_unit))

    monkeypatch.setattr(bounded, "bounded_complete", bounded_fixture)
    config = runtime.AdvisoryRuntimeConfig(
        Path("/private/service.json"),
        UNIT,
        runtime.DEFAULT_MODEL,
        runtime.PRICE_VERSION,
        True,
        Path("/private/key"),
        frozenset({DIGEST}),
    )
    runtime._run_canary(config)
    gateway, request, budget, unit = observed[0]
    assert isinstance(gateway._transport, ScriptedModelTransport)
    assert gateway._transport._records == [{"content": "ADVISORY_SCOPE_CANARY"}]
    assert request.messages[0].content == "fixed containment canary"
    assert budget.max_model_calls == 0 and budget.max_estimated_model_usd == 0
    assert unit == UNIT


def test_runtime_admitted_before_canary_then_readmitted_before_sql_key_and_model(
    tmp_path, monkeypatch
):
    config_path = _save_config(tmp_path, _config_data(tmp_path))
    order = []
    service_config = SimpleNamespace(
        config=SimpleNamespace(
            portfolio_policy=SimpleNamespace(
                operating_monthly_usd=Decimal("50"), development_total_usd=Decimal("200")
            ),
            portfolio_category="development",
            operator_id="operator",
        ),
        postgres_dsn=SecretStr("postgresql://private"),
        actual_build="a" * 40,
        lock_sha256="b" * 64,
    )
    monkeypatch.setattr(runtime, "_run_canary", lambda config: order.append("canary"))
    monkeypatch.setattr(
        runtime,
        "load_runtime",
        lambda path: order.append("admit") or service_config,
    )
    store = object()
    effects = object()
    monkeypatch.setattr(
        runtime,
        "_make_store",
        lambda loaded: order.append("sql") or (store, effects),
    )
    monkeypatch.setattr(
        runtime,
        "_read_model_key",
        lambda path: order.append("key") or SecretStr("test-secret"),
    )

    class Runner:
        def run_next(self, owner, operator, gateway):
            order.append("run_next")
            return None

    gateway = object()

    def make_provider(store_arg, effects_arg, key, config):
        order.append("model")
        assert config.allowed_report_digests == frozenset({DIGEST})
        return Runner(), gateway

    monkeypatch.setattr(runtime, "_make_provider", make_provider)
    assert runtime.main(["--config", str(config_path), "--run", "--once"]) == 0
    assert order == ["admit", "canary", "admit", "sql", "key", "model", "run_next"]


def test_run_refuses_missing_required_portfolio_policy_after_canary_before_sql(
    tmp_path, monkeypatch
):
    config_path = _save_config(tmp_path, _config_data(tmp_path))
    service_config = SimpleNamespace(
        config=SimpleNamespace(portfolio_policy=None, portfolio_category=None)
    )
    calls = []
    monkeypatch.setattr(runtime, "_run_canary", lambda config: calls.append("canary"))
    monkeypatch.setattr(runtime, "load_runtime", lambda path: service_config)
    monkeypatch.setattr(runtime, "_make_store", lambda loaded: pytest.fail("SQL"))
    assert runtime.main(["--config", str(config_path), "--run", "--once"]) != 0
    assert calls == ["canary"]


@pytest.mark.parametrize(
    ("monthly", "development"),
    [("50.01", "200"), ("50", "200.01"), ("0", "200")],
)
def test_existing_portfolio_policy_must_stay_within_fixed_caps(monthly, development):
    loaded = SimpleNamespace(
        config=SimpleNamespace(
            portfolio_policy=SimpleNamespace(
                operating_monthly_usd=Decimal(monthly),
                development_total_usd=Decimal(development),
            ),
            portfolio_category="development",
        )
    )
    with pytest.raises(runtime.RuntimeRejected, match="configuration_invalid"):
        runtime._validate_portfolio(loaded)


def test_once_runs_at_most_one_claim_and_forwards_scope_and_digest_allowlist(tmp_path, monkeypatch):
    config_path = _save_config(tmp_path, _config_data(tmp_path))
    service_config = SimpleNamespace(
        config=SimpleNamespace(
            portfolio_policy=SimpleNamespace(
                operating_monthly_usd=Decimal("50"), development_total_usd=Decimal("200")
            ),
            portfolio_category="development",
            operator_id="operator",
        ),
        postgres_dsn=SecretStr("postgresql://private"),
        actual_build="a" * 40,
        lock_sha256="b" * 64,
    )
    monkeypatch.setattr(runtime, "_run_canary", lambda config: None)
    monkeypatch.setattr(runtime, "load_runtime", lambda path: service_config)
    monkeypatch.setattr(runtime, "_make_store", lambda loaded: (object(), object()))
    monkeypatch.setattr(runtime, "_read_model_key", lambda path: SecretStr("test-secret"))
    calls = []

    class Runner:
        def run_next(self, owner, operator, gateway):
            calls.append((owner, operator, gateway))
            return None

    runner, gateway = Runner(), object()
    monkeypatch.setattr(runtime, "_make_provider", lambda *args: (runner, gateway))
    assert runtime.main(["--config", str(config_path), "--run", "--once"]) == 0
    assert calls == [(runtime.OWNER, "operator", gateway)]


def test_pre_set_stop_event_skips_all_startup(tmp_path, monkeypatch):
    config_path = _save_config(tmp_path, _config_data(tmp_path))
    config = runtime.load_advisory_config(config_path)
    loaded = SimpleNamespace(
        config=SimpleNamespace(
            portfolio_policy=SimpleNamespace(
                operating_monthly_usd=Decimal("50"), development_total_usd=Decimal("200")
            ),
            portfolio_category="development",
            operator_id="operator",
        ),
        postgres_dsn=SecretStr("postgresql://private"),
    )
    calls = []

    monkeypatch.setattr(runtime, "_run_canary", lambda config: calls.append("canary"))
    monkeypatch.setattr(runtime, "load_runtime", lambda path: calls.append("admit") or loaded)
    monkeypatch.setattr(
        runtime,
        "_make_store",
        lambda loaded: calls.append("store") or (object(), object()),
    )
    monkeypatch.setattr(runtime, "_read_model_key", lambda path: calls.append("key"))

    class Runner:
        def run_next(self, *args):
            calls.append("run_next")

    monkeypatch.setattr(
        runtime,
        "_make_provider",
        lambda *args: calls.append("provider") or (Runner(), object()),
    )
    stop = threading.Event()
    stop.set()
    runtime.run(config, once=False, stop=stop)
    assert calls == []


@pytest.mark.parametrize(
    ("stop_stage", "expected"),
    [
        ("first_admit", ["first_admit"]),
        ("canary", ["first_admit", "canary"]),
        ("readmit", ["first_admit", "canary", "readmit"]),
        ("store", ["first_admit", "canary", "readmit", "store"]),
        ("key", ["first_admit", "canary", "readmit", "store", "key"]),
    ],
)
def test_stop_set_during_startup_stops_before_later_stages(
    tmp_path, monkeypatch, stop_stage, expected
):
    config_path = _save_config(tmp_path, _config_data(tmp_path))
    config = runtime.load_advisory_config(config_path)
    stop = threading.Event()
    calls = []
    loaded = SimpleNamespace(
        config=SimpleNamespace(
            portfolio_policy=SimpleNamespace(
                operating_monthly_usd=Decimal("50"), development_total_usd=Decimal("200")
            ),
            portfolio_category="development",
            operator_id="operator",
        ),
        postgres_dsn=SecretStr("postgresql://private"),
    )

    def stage(name):
        calls.append(name)
        if name == stop_stage:
            stop.set()

    admissions = 0

    def admit(path):
        nonlocal admissions
        admissions += 1
        stage("first_admit" if admissions == 1 else "readmit")
        return loaded

    monkeypatch.setattr(runtime, "load_runtime", admit)
    monkeypatch.setattr(runtime, "_run_canary", lambda config: stage("canary"))

    def make_store(loaded):
        stage("store")
        return object(), object()

    def read_key(path):
        stage("key")
        return SecretStr("fixture")

    monkeypatch.setattr(runtime, "_make_store", make_store)
    monkeypatch.setattr(runtime, "_read_model_key", read_key)
    monkeypatch.setattr(
        runtime,
        "_make_provider",
        lambda *args: stage("provider") or (object(), object()),
    )

    runtime.run(config, once=False, stop=stop)
    assert calls == expected


def test_runner_factory_forwards_scope_and_digest_whitelist(local, tmp_path):
    store, _, _ = local
    config = runtime.AdvisoryRuntimeConfig(
        tmp_path / "service.json",
        UNIT,
        runtime.DEFAULT_MODEL,
        runtime.PRICE_VERSION,
        True,
        tmp_path / "key",
        frozenset({DIGEST}),
    )
    runner, gateway = runtime._make_provider(
        store,
        EffectLedger(store),
        SecretStr("offline-fixture-secret"),
        config,
    )
    assert isinstance(runner, AdvisoryRunner)
    assert runner.effect_scope_unit == UNIT
    assert runner.allowed_report_digests == frozenset({DIGEST})
    assert gateway.model_name == runtime.DEFAULT_MODEL


def test_nonallowlisted_report_is_refused_before_reservation(local, monkeypatch):
    store, lake, clock = local
    job, report = succeeded(store, lake)
    effects = EffectLedger(
        store,
        policy=PortfolioBudgetPolicy("advisory-runtime-fixture", Decimal("50"), Decimal("200")),
        category="development",
    )
    config = runtime.AdvisoryRuntimeConfig(
        Path("/private/service.json"),
        UNIT,
        runtime.DEFAULT_MODEL,
        runtime.PRICE_VERSION,
        True,
        Path("/private/key"),
        frozenset({DIGEST}),
    )
    runner, gateway = runtime._make_provider(
        store,
        effects,
        SecretStr("offline-fixture-secret"),
        config,
    )
    lease = store.claim_analysis("runner", clock[0])
    result = runner.run_analysis(job, report, gateway, lease=lease)
    assert result.error_code == "model_unavailable"
    assert effects.read(job.job_id, report.sha256) is None


def test_scope_rejection_propagates_and_retains_reserved_effect(local, monkeypatch):
    store, lake, clock = local
    job, report = succeeded(store, lake)
    effects = EffectLedger(
        store,
        policy=PortfolioBudgetPolicy("advisory-runtime-fixture", Decimal("50"), Decimal("200")),
        category="development",
    )
    config = runtime.AdvisoryRuntimeConfig(
        Path("/private/service.json"),
        UNIT,
        runtime.DEFAULT_MODEL,
        runtime.PRICE_VERSION,
        True,
        Path("/private/key"),
        frozenset({report.sha256}),
    )
    runner, gateway = runtime._make_provider(
        store,
        effects,
        SecretStr("offline-fixture-secret"),
        config,
    )
    bounded_calls = []

    def reject_scope(*args, **kwargs):
        bounded_calls.append((args, kwargs))
        raise EffectScopeRejected()

    monkeypatch.setattr("qm_research_agent.orchestrator.bounded_complete", reject_scope)
    lease = store.claim_analysis("runner", clock[0])
    with pytest.raises(EffectScopeRejected, match="effect scope unavailable"):
        runner.run_analysis(job, report, gateway, lease=lease)
    assert effects.read(job.job_id, report.sha256)[0] == "reserved"
    assert len(bounded_calls) == 1
    assert bounded_calls[0][1]["effect_scope_unit"] == UNIT
