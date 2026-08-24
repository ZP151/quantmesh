import json
import subprocess
from pathlib import Path

import pytest

import tools.soak_daily as soak_daily


@pytest.mark.parametrize(
    ("moomoo_output", "expected_error"),
    (
        pytest.param(
            json.dumps(
                {
                    "provider": "moomoo-opend",
                    "read_only": True,
                    "status": "unavailable",
                    "reason_code": "daemon-unavailable",
                    "detail": "local OpenD is unavailable",
                    "manifest_ids": [],
                }
            ),
            "moomoo collect unavailable: daemon-unavailable",
            id="typed-unavailable",
        ),
        pytest.param(
            json.dumps(
                {
                    "provider": "moomoo-opend",
                    "read_only": True,
                    "status": "published",
                    "reason_code": None,
                    "detail": None,
                    "manifest_ids": [],
                }
            ),
            "moomoo collect failed: invalid result contract",
            id="published-without-manifests",
        ),
        pytest.param(
            "not-json",
            "moomoo collect failed: invalid result contract",
            id="malformed-output",
        ),
    ),
)
def test_daily_soak_stops_before_observe_when_moomoo_result_is_not_qualifying(
    monkeypatch,
    tmp_path: Path,
    capsys,
    moomoo_output: str,
    expected_error: str,
) -> None:
    calls: list[list[str]] = []
    results = iter(
        (
            subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=json.dumps(
                    {
                        "provider": "hyperliquid-public",
                        "read_only": True,
                        "publications": [{"manifest_ids": ["a" * 64]}],
                    }
                ),
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=moomoo_output,
                stderr="",
            ),
        )
    )

    def fake_run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess:
        del cwd
        calls.append([str(item) for item in command])
        return next(results)

    monkeypatch.setattr(soak_daily, "_run", fake_run)

    result = soak_daily.main(
        [
            "--repo",
            str(tmp_path),
            "--data-root",
            str(tmp_path / "data"),
            "--evidence-root",
            str(tmp_path / "evidence"),
        ]
    )

    assert result == 1
    assert len(calls) == 2
    assert "tools\\trusted_data_soak.py" not in " ".join(calls[-1])
    assert expected_error in capsys.readouterr().err


def test_daily_soak_observes_after_qualifying_moomoo_publication(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    calls: list[list[str]] = []
    results = iter(
        (
            subprocess.CompletedProcess(args=[], returncode=0, stdout="{}", stderr=""),
            subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=json.dumps(
                    {
                        "provider": "moomoo-opend",
                        "read_only": True,
                        "status": "published",
                        "reason_code": None,
                        "detail": None,
                        "manifest_ids": ["a" * 64],
                    }
                ),
                stderr="",
            ),
            subprocess.CompletedProcess(args=[], returncode=0, stdout="report", stderr=""),
        )
    )

    def fake_run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess:
        del cwd
        calls.append([str(item) for item in command])
        return next(results)

    monkeypatch.setattr(soak_daily, "_run", fake_run)

    result = soak_daily.main(
        [
            "--repo",
            str(tmp_path),
            "--data-root",
            str(tmp_path / "data"),
            "--evidence-root",
            str(tmp_path / "evidence"),
        ]
    )

    assert result == 0
    assert len(calls) == 3
    assert "tools\\trusted_data_soak.py" in " ".join(calls[-1])
    assert capsys.readouterr().out.strip() == "report"
