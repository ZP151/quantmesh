import io
import os
from pathlib import Path

from tools import release_gate


class Cp1252Console(io.StringIO):
    encoding = "cp1252"

    def write(self, value: str) -> int:
        value.encode(self.encoding, errors="strict")
        return super().write(value)


def test_console_summary_replaces_unencodable_log_characters() -> None:
    console = Cp1252Console()

    release_gate.print_console("golden path: 60 checks � PASSED", file=console)

    assert console.getvalue() == "golden path: 60 checks ? PASSED\n"


def test_venv_script_resolves_platform_console_entrypoint() -> None:
    path = release_gate._venv_script(Path("acceptance-venv"), "quantmesh-data")

    if os.name == "nt":
        assert path == Path("acceptance-venv/Scripts/quantmesh-data.exe")
    else:
        assert path == Path("acceptance-venv/bin/quantmesh-data")


def test_release_install_is_constrained_by_the_frozen_audit_closure() -> None:
    python = Path("release-venv/python")

    assert release_gate._build_tool_install_command(python) == [
        str(python),
        "-m",
        "pip",
        "install",
        "-q",
        "-r",
        "requirements-build.txt",
    ]
    assert release_gate._release_install_command(python) == [
        str(python),
        "-m",
        "pip",
        "install",
        "-q",
        "-c",
        "requirements-audit.txt",
        "--no-build-isolation",
        "-e",
        ".[dev,research,e2e,moomoo]",
    ]
