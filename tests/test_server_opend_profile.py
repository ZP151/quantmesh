"""Noncredential candidate policy and blocked-install gates, no vendor login."""

import copy
import hashlib
import json
from importlib import import_module, util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "deploy" / "aws" / "opend"


def profile():
    path = ROOT / "gateway-profile.json"
    assert path.is_file(), "noncredential gateway profile is absent"
    return json.loads(path.read_text(encoding="utf-8"))


def validate(value, **kwargs):
    module = "deploy.aws.opend.validate_profile"
    assert util.find_spec(module), "gateway admission validator is absent"
    return import_module(module).validate_profile(value, **kwargs)


def test_candidate_has_actual_fixed_artifact_and_requires_qualification():
    value = profile()
    validate(value)
    assert value["artifact"]["version"] == "10.10.7008"
    assert value["artifact"]["sha256"] == (
        "72eaa6e47b5cb8905306427b5e3679d591408243492e3e7acbc3a7d46f09a0aa"
    )
    assert value["sdk"]["version"] == "10.10.7008"
    with pytest.raises(ValueError, match="qualification"):
        validate(value, require_qualified=True)


@pytest.mark.parametrize(
    "path,replacement",
    [
        (("endpoint", "host"), "0.0.0.0"),
        (("endpoint", "port"), 11111),
        (("artifact", "sha256"), None),
        (("artifact", "url"), "https://example.com/OpenD.tar.gz"),
        (("runtime", "executable"), "/usr/bin/OpenD"),
        (("runtime", "executable"), "/opt/quantmesh/opend/10.10.7008/../../OpenD"),
        (("runtime", "user"), "root"),
        (("runtime", "state_dir"), "/home/ubuntu/.com.moomoo.OpenD"),
        (("runtime", "inherit_windows_state"), True),
        (("runtime", "argv"), ["-login_pwd=credential"]),
        (("runtime", "argv"), ["-login_account=100000", "-login_by_remember=1"]),
        (("runtime", "argv"), ["-api_ip=0.0.0.0"]),
        (("runtime", "auto_hold_quote_right"), True),
        (("runtime", "trade_enabled"), True),
        (("runtime", "auto_login"), True),
        (("authentication", "method"), "password_argument"),
        (("authentication", "capture_session"), True),
        (("sdk", "version"), "latest"),
    ],
)
def test_unsafe_or_unpinned_candidates_fail_closed(path, replacement):
    value = copy.deepcopy(profile())
    value[path[0]][path[1]] = replacement
    with pytest.raises(ValueError):
        validate(value)


def test_credential_fields_and_unknown_configuration_are_not_admitted():
    value = profile()
    value["authentication"]["password"] = "not-a-real-secret"
    with pytest.raises(ValueError, match="fields"):
        validate(value)


def test_unit_is_gated_dedicated_loopback_without_credential_args_or_logging():
    path = ROOT / "quantmesh-opend.service"
    assert path.is_file(), "gated service template is absent"
    unit = path.read_text(encoding="utf-8")
    assert "User=quantmesh-opend" in unit
    assert "ExecCondition=" in unit and "--require-qualified" in unit
    assert "-api_ip=127.0.0.1" in unit and "-api_port=11112" in unit
    assert "-auto_hold_quote_right=0" in unit and "-no_monitor=1" in unit
    assert "StandardOutput=tty" in unit and "StandardError=tty" in unit
    assert "TTYPath=/run/quantmesh-opend/operator-tty" in unit
    assert "NoNewPrivileges=true" in unit and "UMask=0077" in unit
    assert "-login_" not in unit and "EnvironmentFile=" not in unit


def qualified_fixture():
    """Synthetic approval flags exercise admission, never production evidence."""
    value = profile()
    value["qualification"].update(
        state="qualified",
        install_allowed=True,
        operator_approved=True,
        server_startup_verified=True,
    )
    value["sdk"]["wire_compatibility_verified"] = True
    value["authentication"]["private_input_verified"] = True
    return value


def config_bytes():
    module = import_module("deploy.aws.opend.validate_profile")
    assert hasattr(module, "reviewed_configuration"), "no pinned noncredential config boundary"
    return module.reviewed_configuration()


def test_qualified_admission_requires_actual_reviewed_configuration():
    value = qualified_fixture()
    with pytest.raises(ValueError, match="configuration"):
        validate(value, require_qualified=True)
    payload = config_bytes()
    assert hashlib.sha256(payload).hexdigest() == value["runtime"]["config_sha256"]
    validate(value, require_qualified=True, config_bytes=payload)


@pytest.mark.parametrize(
    "unsafe",
    [
        b"<ip>0.0.0.0</ip>",
        b"<websocket_port>33333</websocket_port>",
        b"<telnet_port>33334</telnet_port>",
        b"<login_by_remember>1</login_by_remember>",
        b"<login_pwd>not-a-real-secret</login_pwd>",
    ],
)
def test_configuration_drift_cannot_start_approved_binary(unsafe):
    payload = config_bytes().replace(b"</moomoo_opend>", unsafe + b"</moomoo_opend>")
    with pytest.raises(ValueError, match="configuration"):
        validate(qualified_fixture(), require_qualified=True, config_bytes=payload)
