"""Trusted local startup after independent IVV input acceptance, never an HTTP API.

Root prepares an existing ObjectStore with the immutable input-set and originals,
then supplies an independently pinned config. This tool does not capture data,
review its own inputs, or issue the Root GO. Port 18954 is fixed loopback only.
"""

import argparse
from pathlib import Path

from quantmesh.data.objects import ObjectStore, is_reparse_point
from quantmesh.research import ivv_admission as gate
from quantmesh.research import native_daily_real as daily


def _safe_path(value):
    path = Path(value)
    if not path.is_absolute() or any(is_reparse_point(p) for p in (path, *path.parents)):
        raise ValueError("ivv_startup_path")
    return path


def service_from_config(config_path, expected_sha256):
    config_path = _safe_path(config_path)
    metadata = config_path.stat()
    if not config_path.is_file() or metadata.st_nlink != 1 or not 1 <= metadata.st_size <= 8192:
        raise ValueError("ivv_startup_config")
    raw = config_path.read_bytes()
    if daily.digest(raw) != expected_sha256:
        raise ValueError("ivv_startup_pin")
    config = daily._loads(raw)
    if (
        not isinstance(config, dict)
        or set(config)
        != {"schema_id", "scope_id", "inputs_root", "study_root", "input_set_ref", "proofs"}
        or config["schema_id"] != "qm.ivv.startup.v1"
        or config["scope_id"] != gate.SCOPE_ID
    ):
        raise ValueError("ivv_startup_config")
    inputs, study = _safe_path(config["inputs_root"]), _safe_path(config["study_root"])
    if not inputs.is_dir() or inputs == study:
        raise ValueError("ivv_startup_inputs")
    proofs = gate.TrustedIVVProofs.model_validate(config["proofs"])
    registration = gate.bind_reviewed_ivv_input(
        ObjectStore(inputs),
        input_set_ref=daily.ObjectRef.model_validate(config["input_set_ref"]),
        proofs=proofs,
        output_root=study,
    )
    return daily.NativeDailyService(study, registered=(registration,))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--config-sha256", required=True)
    args = parser.parse_args()
    service = service_from_config(args.config, args.config_sha256)
    try:
        import uvicorn

        from quantmesh.api.watchlist import WatchlistStore
        from quantmesh.api.workstation import create_workstation_app
        from quantmesh.execution.accounting import PaperAccount

        app = create_workstation_app(
            account=PaperAccount(cash=0),
            marks={},
            watchlist=WatchlistStore(service.root / "watchlists"),
            native_daily_service=service,
            host="127.0.0.1",
        )
        uvicorn.run(app, host="127.0.0.1", port=18954, access_log=False, log_level="error")
    finally:
        service.close()


if __name__ == "__main__":
    main()
