import ctypes
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "tools" / "soak_schedule.ps1"
HARNESS = Path(__file__).parent / "fixtures" / "soak_schedule_harness.ps1"
ROOT = Path(__file__).parents[1]


def test_scheduler_script_exposes_only_fail_closed_modes_and_no_schtasks() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "InstallDisabled" in source
    assert "GuardedEnable" in source
    assert "Verify" in source
    assert "Register-ScheduledTask" in source
    assert "Get-ScheduledTask" in source
    assert "Enable-ScheduledTask" in source
    assert "Disable-ScheduledTask" in source
    assert "schtasks" not in source.lower()


@pytest.mark.skipif(os.name != "nt", reason="PowerShell schedule contract is Windows-only")
def test_scheduler_script_parses_and_requires_explicit_mode(tmp_path: Path) -> None:
    quoted_script = str(SCRIPT).replace("'", "''")
    parsed = subprocess.run(
        (
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            f"$errors=$null; $tokens=$null; "
            f"[System.Management.Automation.Language.Parser]::ParseFile('{quoted_script}', "
            "[ref]$tokens, [ref]$errors) | Out-Null; "
            "if ($errors.Count) { $errors | ConvertTo-Json -Compress; exit 1 }",
        ),
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert parsed.returncode == 0, parsed.stdout + parsed.stderr

    missing = subprocess.run(
        ("powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(SCRIPT)),
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert missing.returncode != 0


def _contract() -> dict:
    return {
        "mode": "InstallDisabled",
        "accepted": True,
        "expected_state": "Disabled",
        "tasks": [
            {
                "task_name": "QuantMesh Daily Soak",
                "enabled": False,
                "trigger": {"kind": "daily", "at": "08:00", "timezone": "Asia/Singapore"},
                "settings": {
                    "restart_count": 3,
                    "restart_interval": "PT15M",
                    "execution_time_limit": "PT1H",
                    "multiple_instances": "IgnoreNew",
                },
            },
            {
                "task_name": "QuantMesh Connection Witness",
                "enabled": False,
                "trigger": {"kind": "repetition", "minute": 10, "interval": "PT2H"},
                "settings": {
                    "restart_count": 0,
                    "restart_interval": None,
                    "execution_time_limit": "PT15M",
                    "multiple_instances": "IgnoreNew",
                },
            },
        ],
        "drift_fields": [],
        "unsafe_enabled_tasks": [],
    }


def test_schedule_result_contract_fixture_covers_stagger_and_retry_policy() -> None:
    contract = json.loads(json.dumps(_contract(), sort_keys=True))

    assert contract["tasks"][0]["trigger"]["at"] == "08:00"
    assert contract["tasks"][0]["settings"]["restart_count"] == 3
    assert contract["tasks"][1]["trigger"]["minute"] == 10
    assert contract["tasks"][1]["settings"]["restart_count"] == 0


def _git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    shutil.copytree(ROOT / "src", repo / "src")
    (repo / "tools").mkdir()
    for relative in (
        "connection_witness.ps1",
        "connection_witness.py",
        "soak_daily.py",
        "trusted_data_soak_acceptance.py",
        "soak_witness_outbox.py",
    ):
        shutil.copy2(ROOT / "tools" / relative, repo / "tools" / relative)
    (repo / "pyproject.toml").write_text("[project]\nname='quantmesh'\n", encoding="utf-8")
    (repo / ".gitignore").write_text("__pycache__/\n*.pyc\n", encoding="utf-8")
    from importlib.metadata import version

    (repo / "requirements-audit.txt").write_text(
        f"quantmesh=={version('quantmesh')}\n", encoding="utf-8"
    )
    (repo / "requirements-build.txt").write_text(
        "pip==26.2.1\nsetuptools==84.0.0\nwheel==0.48.0\n",
        encoding="utf-8",
    )
    subprocess.run(("git", "init", "-b", "integration"), cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ("git", "config", "user.email", "test@quantmesh.invalid"),
        cwd=repo,
        check=True,
    )
    subprocess.run(("git", "config", "user.name", "QuantMesh Test"), cwd=repo, check=True)
    subprocess.run(("git", "add", "."), cwd=repo, check=True, capture_output=True)
    subprocess.run(("git", "commit", "-m", "fixture"), cwd=repo, check=True, capture_output=True)
    return repo


def _timezone_id() -> str:
    result = subprocess.run(
        (
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "[System.TimeZoneInfo]::Local.Id",
        ),
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _parameters(tmp_path: Path, repo: Path, mode: str) -> dict:
    return {
        "Mode": mode,
        "Repo": str(repo),
        "PythonPath": sys.executable,
        "DataRoot": str(tmp_path / "data root"),
        "EvidenceRoot": str(tmp_path / "evidence"),
        "DailyRunRoot": str(tmp_path / "daily-runs"),
        "ConnectionRunRoot": str(tmp_path / "connection-runs"),
        "OutboxRoot": str(tmp_path / "outbox"),
        "ManifestRoot": str(tmp_path / "manifests"),
        "RemoteRef": "integration",
        "Principal": "QUANTMESH\\fixture",
        "TimeZoneId": _timezone_id(),
    }


def _run_harness(
    tmp_path: Path,
    parameters: dict,
    *,
    seed: list[dict] | None = None,
    fail_enable: str | None = None,
    fail_disable: str | None = None,
) -> tuple[subprocess.CompletedProcess[str], dict, list[str]]:
    parameters_path = tmp_path / f"parameters-{parameters['Mode']}.json"
    parameters_path.write_text(json.dumps(parameters), encoding="utf-8")
    log_path = tmp_path / f"operations-{parameters['Mode']}.log"
    argv = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-File",
        str(HARNESS),
        "-ScheduleScript",
        str(SCRIPT),
        "-ParametersJson",
        str(parameters_path),
        "-LogPath",
        str(log_path),
    ]
    if seed is not None:
        seed_path = tmp_path / f"seed-{parameters['Mode']}.json"
        seed_path.write_text(json.dumps(seed), encoding="utf-8")
        argv.extend(("-SeedTasksJson", str(seed_path)))
    if fail_enable:
        argv.extend(("-FailEnableTask", fail_enable))
    if fail_disable:
        argv.extend(("-FailDisableTask", fail_disable))
    result = subprocess.run(
        argv,
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    payload = json.loads(lines[-1]) if lines else {}
    operations = log_path.read_text(encoding="utf-8-sig").splitlines() if log_path.exists() else []
    return result, payload, operations


def _windows_argv(command_line: str) -> list[str]:
    argc = ctypes.c_int()
    command_line_to_argv = ctypes.windll.shell32.CommandLineToArgvW
    command_line_to_argv.argtypes = (
        ctypes.c_wchar_p,
        ctypes.POINTER(ctypes.c_int),
    )
    command_line_to_argv.restype = ctypes.POINTER(ctypes.c_wchar_p)
    argv = command_line_to_argv(command_line, ctypes.byref(argc))
    if not argv:
        raise OSError("CommandLineToArgvW failed")
    try:
        return [argv[index] for index in range(argc.value)]
    finally:
        local_free = ctypes.windll.kernel32.LocalFree
        local_free.argtypes = (ctypes.c_void_p,)
        local_free.restype = ctypes.c_void_p
        local_free(argv)


@pytest.mark.skipif(os.name != "nt", reason="PowerShell schedule contract is Windows-only")
def test_install_disabled_registers_both_exact_staggered_tasks(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path)

    result, payload, operations = _run_harness(
        tmp_path, _parameters(tmp_path, repo, "InstallDisabled")
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "accepted" in payload, result.stdout + result.stderr
    assert payload["accepted"] is True, (
        json.dumps(payload, indent=2) + "\n" + result.stdout + result.stderr
    )
    assert [item["enabled"] for item in payload["tasks"]] == [False, False]
    assert payload["tasks"][0]["trigger"]["at"] == "08:00"
    assert payload["tasks"][0]["settings"]["restart_count"] == 3
    assert payload["tasks"][1]["trigger"]["minute"] == 10
    assert payload["tasks"][1]["trigger"]["interval"] == "PT2H"
    assert payload["tasks"][1]["trigger"]["duration"] is None
    assert payload["tasks"][1]["trigger"]["stop_at_duration_end"] is True
    assert payload["tasks"][1]["settings"]["restart_count"] == 0
    daily_argv = _windows_argv(payload["tasks"][0]["action"]["arguments"])
    assert daily_argv[:3] == [
        str(repo / "tools" / "soak_daily.py"),
        "--repo",
        str(repo),
    ]
    assert daily_argv[daily_argv.index("--data-root") + 1] == str(tmp_path / "data root")
    connection_argv = _windows_argv(payload["tasks"][1]["action"]["arguments"])
    assert connection_argv[:3] == [
        "-NoProfile",
        "-NonInteractive",
        "-File",
    ]
    assert connection_argv[3] == str(repo / "tools" / "connection_witness.ps1")
    assert connection_argv[connection_argv.index("-FormalTaskName") + 1] == (
        "QuantMesh Daily Soak"
    )
    assert connection_argv[connection_argv.index("-FormalTaskPath") + 1] == "\\QuantMesh\\"
    assert connection_argv[connection_argv.index("-ConnectionTaskName") + 1] == (
        "QuantMesh Connection Witness"
    )
    assert connection_argv[connection_argv.index("-ConnectionTaskPath") + 1] == (
        "\\QuantMesh\\"
    )
    assert sum(item.startswith("Register:") for item in operations) == 2
    assert [item for item in operations if item.startswith("RegisterEnabled:")] == [
        "RegisterEnabled:QuantMesh Daily Soak:False",
        "RegisterEnabled:QuantMesh Connection Witness:False",
    ]
    assert sum(item.startswith("Disable:") for item in operations) == 2
    assert not any(item.startswith("Enable:") for item in operations)


@pytest.mark.skipif(os.name != "nt", reason="PowerShell schedule contract is Windows-only")
def test_install_accepts_scheduler_local_account_name_normalization(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path)
    parameters = _parameters(tmp_path, repo, "InstallDisabled")
    identity = subprocess.run(
        (
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "[System.Security.Principal.WindowsIdentity]::GetCurrent().Name",
        ),
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()
    parameters["Principal"] = identity

    result, payload, _ = _run_harness(tmp_path, parameters)

    assert result.returncode == 0, result.stdout + result.stderr
    assert payload["accepted"] is True, json.dumps(payload, indent=2)
    assert {task["principal"]["user_id"] for task in payload["tasks"]} == {
        identity.lower()
    }


def _installed_seed(tmp_path: Path) -> tuple[Path, dict, list[dict]]:
    repo = _git_repo(tmp_path)
    parameters = _parameters(tmp_path, repo, "InstallDisabled")
    result, payload, _ = _run_harness(tmp_path, parameters)
    assert result.returncode == 0 and payload.get("accepted") is True, (
        result.stdout + result.stderr
    )
    return repo, parameters, payload["tasks"]


@pytest.mark.skipif(os.name != "nt", reason="PowerShell schedule contract is Windows-only")
def test_verify_is_read_only_and_names_exact_drift_fields(tmp_path: Path) -> None:
    repo, _, seed = _installed_seed(tmp_path)
    verify = _parameters(tmp_path, repo, "Verify")

    result, payload, operations = _run_harness(tmp_path, verify, seed=seed)

    assert result.returncode == 0, result.stdout + result.stderr
    assert payload["accepted"] is True, json.dumps(payload, indent=2)
    assert not any(
        item.startswith(("Register:", "Enable:", "Disable:")) for item in operations
    )

    drift_seed = json.loads(json.dumps(seed))
    drift_seed[0]["action"]["execute"] = str(tmp_path / "forged.exe")
    drift_dir = tmp_path / "drift"
    drift_dir.mkdir()
    result, payload, operations = _run_harness(drift_dir, verify, seed=drift_seed)

    assert result.returncode != 0
    assert payload["accepted"] is False
    assert payload["drift_fields"] == ["QuantMesh Daily Soak.action.execute"]
    assert not any(
        item.startswith(("Register:", "Enable:", "Disable:")) for item in operations
    )


@pytest.mark.skipif(os.name != "nt", reason="PowerShell schedule contract is Windows-only")
def test_guarded_enable_runs_argv_preflight_then_enables_and_reads_back(
    tmp_path: Path,
) -> None:
    repo, _, seed = _installed_seed(tmp_path)
    parameters = _parameters(tmp_path, repo, "GuardedEnable")
    parameters.update(
        PreflightExecutable=sys.executable,
        PreflightArguments=["-c", "raise SystemExit(0)"],
        PreflightTimeoutSeconds=10,
    )

    result, payload, operations = _run_harness(tmp_path, parameters, seed=seed)

    assert result.returncode == 0, result.stdout + result.stderr
    assert payload["accepted"] is True, (
        json.dumps(payload, indent=2) + "\n" + result.stdout + result.stderr
    )
    assert payload["preflight"]["returncode"] == 0
    assert [item["enabled"] for item in payload["tasks"]] == [True, True]
    assert [item for item in operations if item.startswith("Enable:")] == [
        "Enable:QuantMesh Daily Soak",
        "Enable:QuantMesh Connection Witness",
    ]


@pytest.mark.skipif(os.name != "nt", reason="PowerShell schedule contract is Windows-only")
def test_guarded_enable_failure_rolls_back_and_reports_unconfirmed_disable(
    tmp_path: Path,
) -> None:
    repo, _, seed = _installed_seed(tmp_path)
    parameters = _parameters(tmp_path, repo, "GuardedEnable")
    parameters.update(
        PreflightExecutable=sys.executable,
        PreflightArguments=["-c", "raise SystemExit(0)"],
        PreflightTimeoutSeconds=10,
    )

    confirmed_dir = tmp_path / "confirmed"
    confirmed_dir.mkdir()
    result, payload, operations = _run_harness(
        confirmed_dir,
        parameters,
        seed=seed,
        fail_enable="QuantMesh Connection Witness",
    )

    assert result.returncode != 0
    assert payload["rollback"]["status"] == "confirmed-disabled"
    assert payload["unsafe_enabled_tasks"] == []
    assert sum(item.startswith("Disable:") for item in operations) == 2

    unsafe_dir = tmp_path / "unsafe"
    unsafe_dir.mkdir()
    result, payload, _ = _run_harness(
        unsafe_dir,
        parameters,
        seed=seed,
        fail_enable="QuantMesh Connection Witness",
        fail_disable="QuantMesh Daily Soak",
    )

    assert result.returncode != 0
    assert payload["accepted"] is False
    assert payload["rollback"]["status"] == "unsafe-partial-enable"
    assert payload["unsafe_enabled_tasks"] == ["QuantMesh Daily Soak"]


@pytest.mark.skipif(os.name != "nt", reason="PowerShell schedule contract is Windows-only")
def test_verify_reports_unsafe_enabled_task_without_mutation(tmp_path: Path) -> None:
    repo, _, seed = _installed_seed(tmp_path)
    seed[0]["enabled"] = True

    result, payload, operations = _run_harness(
        tmp_path,
        _parameters(tmp_path, repo, "Verify"),
        seed=seed,
    )

    assert result.returncode != 0
    assert payload["unsafe_enabled_tasks"] == ["QuantMesh Daily Soak"]
    assert payload["drift_fields"] == ["QuantMesh Daily Soak.enabled"]
    assert not any(
        item.startswith(("Register:", "Enable:", "Disable:")) for item in operations
    )


@pytest.mark.skipif(os.name != "nt", reason="PowerShell schedule contract is Windows-only")
def test_preflight_nonzero_never_enables_and_confirms_disabled_readback(
    tmp_path: Path,
) -> None:
    repo, _, seed = _installed_seed(tmp_path)
    parameters = _parameters(tmp_path, repo, "GuardedEnable")
    parameters.update(
        PreflightExecutable=sys.executable,
        PreflightArguments=["-c", "raise SystemExit(7)"],
        PreflightTimeoutSeconds=10,
    )

    result, payload, operations = _run_harness(tmp_path, parameters, seed=seed)

    assert result.returncode != 0
    assert payload["accepted"] is False
    assert not any(item.startswith("Enable:") for item in operations)
    assert payload["rollback"]["status"] == "confirmed-disabled"


def _set_nested(value: dict, path: str, replacement: object) -> None:
    target = value
    parts = path.split(".")
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = replacement


@pytest.mark.skipif(os.name != "nt", reason="PowerShell schedule contract is Windows-only")
def test_verify_rejects_every_owned_action_trigger_principal_and_setting_drift(
    tmp_path: Path,
) -> None:
    repo, _, seed = _installed_seed(tmp_path)
    cases = (
        (0, "task_path", "\\Forged\\", "task_path"),
        (0, "action.execute", "C:\\forged.exe", "action.execute"),
        (0, "action.arguments", "--forged", "action.arguments"),
        (0, "action.working_directory", "C:\\forged", "action.working_directory"),
        (0, "trigger.class", "MSFT_TaskTimeTrigger", "trigger.class"),
        (0, "trigger.enabled", False, "trigger.enabled"),
        (0, "trigger.at", "09:00", "trigger.at"),
        (0, "trigger.days_interval", 2, "trigger.days_interval"),
        (0, "principal.user_id", "FORGED\\user", "principal.user_id"),
        (0, "principal.logon_type", "Password", "principal.logon_type"),
        (0, "principal.run_level", "Highest", "principal.run_level"),
        (0, "settings.wake_to_run", False, "settings.wake_to_run"),
        (0, "settings.start_when_available", False, "settings.start_when_available"),
        (
            0,
            "settings.disallow_start_on_battery",
            True,
            "settings.disallow_start_on_battery",
        ),
        (0, "settings.stop_on_battery", True, "settings.stop_on_battery"),
        (0, "settings.multiple_instances", "Parallel", "settings.multiple_instances"),
        (0, "settings.restart_count", 4, "settings.restart_count"),
        (0, "settings.restart_interval", "PT10M", "settings.restart_interval"),
        (0, "settings.execution_time_limit", "PT2H", "settings.execution_time_limit"),
        (1, "trigger.interval", "PT3H", "trigger.interval"),
        (
            1,
            "trigger.start_boundary",
            "2026-01-01T00:11:00",
            "trigger.minute",
        ),
        (
            1,
            "trigger.start_boundary",
            "2027-01-01T00:10:00",
            "trigger.start_boundary",
        ),
        (1, "trigger.duration", "P1D", "trigger.duration"),
        (1, "trigger.stop_at_duration_end", False, "trigger.stop_at_duration_end"),
        (1, "settings.execution_time_limit", "PT20M", "settings.execution_time_limit"),
    )
    verify = _parameters(tmp_path, repo, "Verify")
    for case_number, (task_index, path, replacement, expected_field) in enumerate(cases):
        drift_seed = json.loads(json.dumps(seed))
        _set_nested(drift_seed[task_index], path, replacement)
        case_dir = tmp_path / f"owned-drift-{case_number}"
        case_dir.mkdir()

        result, payload, operations = _run_harness(case_dir, verify, seed=drift_seed)

        task_name = seed[task_index]["task_name"]
        assert result.returncode != 0, path
        assert f"{task_name}.{expected_field}" in payload["drift_fields"], path
        assert not any(
            item.startswith(("Register:", "Enable:", "Disable:")) for item in operations
        ), path

    for field in ("extra_action", "extra_trigger"):
        drift_seed = json.loads(json.dumps(seed))
        drift_seed[0][field] = True
        case_dir = tmp_path / field
        case_dir.mkdir()

        result, payload, _ = _run_harness(case_dir, verify, seed=drift_seed)

        assert result.returncode != 0
        assert any(
            item.startswith("QuantMesh Daily Soak.") for item in payload["drift_fields"]
        )
