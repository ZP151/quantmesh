"""Validate one pinned, noncredential gateway candidate; never install or log in."""

import argparse
import hashlib
import json
from pathlib import Path

VERSION = "10.10.7008"
URL = f"https://softwaredownload.moomoo.com/moomoo_OpenD_{VERSION}_Ubuntu18.04.tar.gz"
SHA256 = "72eaa6e47b5cb8905306427b5e3679d591408243492e3e7acbc3a7d46f09a0aa"
EXECUTABLE_SHA256 = "e05b901dbe9107061b954a7fe3c059916c4a1e580d8f0a57277d402438898601"
ARGV = [
    "-cfg_file=/etc/quantmesh/opend/OpenD.xml",
    "-api_ip=127.0.0.1",
    "-api_port=11112",
    "-auto_hold_quote_right=0",
    "-no_monitor=1",
    "-simulate_trade=disable",
    "-console=1",
    "-log_level=no",
]
_REVIEWED_CONFIGURATION = b"""<?xml version="1.0" encoding="UTF-8"?>
<moomoo_opend>
  <ip>127.0.0.1</ip>
  <api_port>11112</api_port>
  <lang>en</lang>
  <log_level>no</log_level>
  <push_proto_type>0</push_proto_type>
  <auto_hold_quote_right>0</auto_hold_quote_right>
</moomoo_opend>
"""


def reviewed_configuration() -> bytes:
    """QuantMesh-owned fixed noncredential XML; no imported vendor state."""
    return _REVIEWED_CONFIGURATION


def _fields(value, names):
    if not isinstance(value, dict) or set(value) != set(names.split()):
        raise ValueError("profile fields are not admitted")


def _exact(value, required):
    for name, expected in required.items():
        if type(value[name]) is not type(expected) or value[name] != expected:
            raise ValueError("profile candidate violates pinned policy")


def validate_profile(
    value: dict,
    *,
    require_qualified: bool = False,
    config_bytes: bytes | None = None,
) -> None:
    _fields(value, "schema_version artifact sdk endpoint runtime authentication qualification")
    _exact(value, {"schema_version": 1})
    artifact = value["artifact"]
    _fields(
        artifact, "url version sha256 size_bytes executable_sha256 platform distribution_target"
    )
    _exact(
        artifact,
        {
            "url": URL,
            "version": VERSION,
            "sha256": SHA256,
            "size_bytes": 466932458,
            "executable_sha256": EXECUTABLE_SHA256,
            "platform": "linux-x86_64",
            "distribution_target": "Ubuntu18.04",
        },
    )
    sdk = value["sdk"]
    _fields(
        sdk,
        "package version vendor_minimum_opend version_floor_verified wire_compatibility_verified",
    )
    _exact(
        sdk,
        {
            "package": "moomoo-api",
            "version": VERSION,
            "vendor_minimum_opend": VERSION,
            "version_floor_verified": True,
        },
    )
    _fields(value["endpoint"], "host port")
    _exact(value["endpoint"], {"host": "127.0.0.1", "port": 11112})
    runtime = value["runtime"]
    _fields(
        runtime,
        "user install_dir executable home state_dir config_file config_sha256 "
        "inherit_windows_state "
        "auto_hold_quote_right trade_enabled auto_login argv",
    )
    _exact(
        runtime,
        {
            "user": "quantmesh-opend",
            "install_dir": f"/opt/quantmesh/opend/{VERSION}",
            "executable": f"/opt/quantmesh/opend/{VERSION}/OpenD",
            "home": "/var/lib/quantmesh-opend",
            "state_dir": "/var/lib/quantmesh-opend/.com.moomoo.OpenD",
            "config_file": "/etc/quantmesh/opend/OpenD.xml",
            "config_sha256": hashlib.sha256(_REVIEWED_CONFIGURATION).hexdigest(),
            "inherit_windows_state": False,
            "auto_hold_quote_right": False,
            "trade_enabled": False,
            "auto_login": False,
            "argv": ARGV,
        },
    )
    auth = value["authentication"]
    _fields(
        auth,
        "method capture_session tty_path new_device_approval_required "
        "market_right_transfer_approval_required private_input_verified",
    )
    _exact(
        auth,
        {
            "method": "operator_private_pty",
            "capture_session": False,
            "tty_path": "/run/quantmesh-opend/operator-tty",
            "new_device_approval_required": True,
            "market_right_transfer_approval_required": True,
        },
    )
    qualification = value["qualification"]
    _fields(
        qualification,
        "state install_allowed reason isolated_platform operator_approved server_startup_verified",
    )
    for container, keys in (
        (sdk, ("wire_compatibility_verified",)),
        (auth, ("private_input_verified",)),
        (qualification, ("install_allowed", "operator_approved", "server_startup_verified")),
    ):
        if any(type(container[key]) is not bool for key in keys):
            raise ValueError("qualification flags must be boolean")
    qualified = (
        qualification["state"] == "qualified"
        and qualification["install_allowed"]
        and qualification["operator_approved"]
        and qualification["server_startup_verified"]
        and sdk["wire_compatibility_verified"]
        and auth["private_input_verified"]
    )
    if qualification["state"] not in {"blocked", "qualified"}:
        raise ValueError("unknown qualification state")
    if qualification["install_allowed"] and not qualified:
        raise ValueError("qualification evidence incomplete")
    if require_qualified and not qualified:
        raise ValueError("qualification is blocked")
    if require_qualified and config_bytes is None:
        raise ValueError("reviewed configuration bytes are required")
    if config_bytes is not None and (
        hashlib.sha256(config_bytes).hexdigest() != runtime["config_sha256"]
    ):
        raise ValueError("reviewed configuration digest differs")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--require-qualified", action="store_true")
    parser.add_argument("--verify-executable", action="store_true")
    parser.add_argument("--print-config", action="store_true")
    args = parser.parse_args()
    try:
        profile = json.loads(args.profile.read_text(encoding="utf-8"))
        validate_profile(profile)
        if args.require_qualified:
            # Only this new, reviewed noncredential path is admitted. Never
            # read a personal vendor-state configuration or echo file bytes.
            configuration = Path(profile["runtime"]["config_file"]).read_bytes()
            validate_profile(profile, require_qualified=True, config_bytes=configuration)
        if args.verify_executable:
            with Path(profile["runtime"]["executable"]).open("rb") as executable:
                actual = hashlib.file_digest(executable, "sha256").hexdigest()
            if actual != EXECUTABLE_SHA256:
                raise ValueError("executable digest differs")
    except (ValueError, OSError):
        # Validation details must never echo input containing a credential.
        return 1
    if args.print_config:
        import sys

        sys.stdout.buffer.write(_REVIEWED_CONFIGURATION)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
