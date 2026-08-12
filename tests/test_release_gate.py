import io

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
