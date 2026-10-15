"""Explicit private bootstrap for the separately managed advisory runner.

Import and default preflight are inert. Model access requires ``--run`` and a
private, exact configuration. The current API bootstrap stays model-unavailable.
"""

from __future__ import annotations

import argparse
import json
import re
import signal
import sys
import threading
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from pydantic import SecretStr

from qm_research_agent.runtime import RuntimeRejected, _read_private, _unique_object, load_runtime

EFFECT_SCOPE_UNIT = "quantmesh-research-advisory.service"
DEFAULT_MODEL = "gpt-6.1-sol"
PRICE_VERSION = "openai-gpt-6.1-sol-standard-2026-10-13"
OPENAI_ORIGINS = frozenset({"https://api.openai.com"})
OWNER = "quantmesh-advisory-runtime"
POLL_SECONDS = 5
CANARY_MODEL = "advisory-containment-canary"


@dataclass(frozen=True, repr=False)
class AdvisoryRuntimeConfig:
    service_config: Path = field(repr=False)
    unit: str
    model: str
    price_version: str
    remote_consent: bool
    key_file: Path = field(repr=False)
    allowed_report_digests: frozenset[str]

    def __repr__(self):
        return "<AdvisoryRuntimeConfig private>"


def _absolute_path(value):
    if not isinstance(value, str):
        raise ValueError
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError
    return path


def load_advisory_config(path: Path) -> AdvisoryRuntimeConfig:
    """Read one owner-private JSON file and reject every unspecified field."""
    try:
        raw = _read_private(path, 65536)
        data = json.loads(raw, object_pairs_hook=_unique_object)
        expected = {
            "schema_version",
            "service_config",
            "unit",
            "model",
            "price_version",
            "remote_consent",
            "key_file",
            "allowed_report_digests",
        }
        if not isinstance(data, dict) or set(data) != expected:
            raise ValueError
        if type(data["schema_version"]) is not int or data["schema_version"] != 1:
            raise ValueError
        if (
            data["unit"] != EFFECT_SCOPE_UNIT
            or data["model"] != DEFAULT_MODEL
            or data["price_version"] != PRICE_VERSION
            or data["remote_consent"] is not True
        ):
            raise ValueError
        digests = data["allowed_report_digests"]
        if (
            not isinstance(digests, list)
            or not digests
            or any(
                not isinstance(item, str) or not re.fullmatch(r"[0-9a-f]{64}", item)
                for item in digests
            )
            or len(set(digests)) != len(digests)
        ):
            raise ValueError
        return AdvisoryRuntimeConfig(
            service_config=_absolute_path(data["service_config"]),
            unit=data["unit"],
            model=data["model"],
            price_version=data["price_version"],
            remote_consent=True,
            key_file=_absolute_path(data["key_file"]),
            allowed_report_digests=frozenset(digests),
        )
    except RuntimeRejected:
        raise
    except (ValueError, OSError, TypeError, UnicodeError):
        raise RuntimeRejected("configuration_invalid") from None


def _run_canary(config: AdvisoryRuntimeConfig):
    """Prove actual child admission and write guard before database/key effects."""
    from qm_research_agent.bounded import bounded_complete
    from quantmesh.ai.gateway import ModelGateway
    from quantmesh.ai.transport import ScriptedModelTransport
    from quantmesh.ai.wire import ChatMessage, ModelRequest
    from quantmesh.research.jobs import RunBudget

    gateway = ModelGateway(
        ScriptedModelTransport([{"content": "ADVISORY_SCOPE_CANARY"}]),
        model_name=CANARY_MODEL,
    )
    request = ModelRequest(messages=[ChatMessage(role="user", content="fixed containment canary")])
    budget = RunBudget(
        timeout_seconds=30,
        memory_mib=256,
        cpu_limit=1,
        max_model_calls=0,
        max_estimated_model_usd=0,
    )
    bounded_complete(gateway, request, budget, effect_scope_unit=config.unit)


def _validate_portfolio(loaded):
    config = loaded.config
    policy = config.portfolio_policy
    category = config.portfolio_category
    if policy is None or category not in {"operating", "development"}:
        raise RuntimeRejected("configuration_invalid")
    if not Decimal("0") < policy.operating_monthly_usd <= Decimal("50") or not Decimal(
        "0"
    ) < policy.development_total_usd <= Decimal("200"):
        raise RuntimeRejected("configuration_invalid")


def _make_store(loaded):
    from qm_research_agent.budgets import EffectLedger
    from qm_research_agent.store import PostgresJobStore

    _validate_portfolio(loaded)
    config = loaded.config
    store = PostgresJobStore(
        loaded.postgres_dsn,
        lake_root=config.lake_root,
        artifact_root=config.artifact_root,
    )
    effects = EffectLedger(
        store,
        policy=config.portfolio_policy.authority(),
        category=config.portfolio_category,
    )
    return store, effects


def _read_model_key(path: Path) -> SecretStr:
    try:
        value = _read_private(path, 4096).decode("ascii")
        if (
            not value
            or len(value) > 4096
            or any(ord(char) < 33 or ord(char) > 126 for char in value)
        ):
            raise ValueError
        return SecretStr(value)
    except RuntimeRejected:
        raise
    except (UnicodeError, ValueError):
        raise RuntimeRejected("credential_invalid") from None


def _make_provider(store, effects, key, config: AdvisoryRuntimeConfig):
    from qm_research_agent.openai_responses import make_openai_advisory as make_runner

    return make_runner(
        store,
        effects,
        key=key,
        allowed_origins=OPENAI_ORIGINS,
        remote_consent=config.remote_consent,
        model=config.model,
        price_version=config.price_version,
        effect_scope_unit=config.unit,
        allowed_report_digests=config.allowed_report_digests,
    )


def run(
    config: AdvisoryRuntimeConfig,
    *,
    once: bool,
    stop: threading.Event,
) -> None:
    # Admit the source/runtime before launching any child. Repeat admission after
    # the canary so the database/provider phase is bound to current source bytes.
    if stop.is_set():
        return
    load_runtime(config.service_config)
    if stop.is_set():
        return
    _run_canary(config)
    if stop.is_set():
        return
    loaded = load_runtime(config.service_config)
    if stop.is_set():
        return
    _validate_portfolio(loaded)
    if stop.is_set():
        return
    store, effects = _make_store(loaded)
    if stop.is_set():
        return
    key = _read_model_key(config.key_file)
    if stop.is_set():
        return
    runner, gateway = _make_provider(store, effects, key, config)
    if stop.is_set():
        return
    while not stop.is_set():
        runner.run_next(OWNER, loaded.config.operator_id, gateway)
        if once or stop.wait(POLL_SECONDS):
            break


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise RuntimeRejected("configuration_invalid")


def main(argv=None) -> int:
    parser = _Parser(description="Private advisory runner; preflight is the default.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--once", action="store_true")
    try:
        args = parser.parse_args(argv)
        if args.once and not args.run:
            raise RuntimeRejected("configuration_invalid")
        config = load_advisory_config(args.config)
        if not args.run:
            loaded = load_runtime(config.service_config)
            print(json.dumps(loaded.preflight(), sort_keys=True))
            return 0

        stop = threading.Event()
        previous = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
        try:
            run(config, once=args.once, stop=stop)
        finally:
            signal.signal(signal.SIGTERM, previous)
        return 0
    except RuntimeRejected as error:
        print(str(error), file=sys.stderr)
        return 2
    except Exception as error:
        from qm_research_agent.linux_effect_scope import EffectScopeRejected

        if isinstance(error, EffectScopeRejected):
            print("effect scope unavailable", file=sys.stderr)
            return 3
        print("service_unavailable", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
