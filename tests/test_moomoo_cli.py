"""`quantmesh-moomoo` operator command tests (issues #25/#28, Phases A/D).

``probe`` is the only way to reach a real local OpenD instance, and it
must be an explicit operator action: it probes capabilities and prints a
redacted report to stdout, writes nothing to disk, reads no credentials,
and exits with a typed status code per failure class.

``paper-order`` and ``reconcile`` are fixture-first: they place simulated
orders against a deterministic script and reconcile the journal against
it. The live simulated-account path is Phase E-gated and refuses any
invocation without ``--fixture``.
"""

import json
from pathlib import Path

import pytest

from quantmesh.execution import OrderJournal
from quantmesh.moomoo import cli
from quantmesh.moomoo.opend import (
    OpenDAuthRequiredError,
    OpenDCapabilities,
    OpenDSdkMissingError,
    OpenDUnavailableError,
)
from quantmesh.moomoo.readiness import ReadinessReport, SymbolReadiness


class StubClient:
    def __init__(
        self, caps: OpenDCapabilities | None = None, error: Exception | None = None
    ) -> None:
        self.caps = caps
        self.error = error
        self.closed = False

    def probe(self) -> OpenDCapabilities:
        if self.error is not None:
            raise self.error
        default = OpenDCapabilities(True, True, True, True, False)
        return self.caps if self.caps is not None else default

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def stub_client(monkeypatch: pytest.MonkeyPatch) -> StubClient:
    client = StubClient()
    monkeypatch.setattr(cli, "_build_client", lambda _settings: client)
    return client


def test_probe_prints_redacted_report(
    stub_client: StubClient, capsys: pytest.CaptureFixture
) -> None:
    assert cli.main(["probe"]) == 0
    out = capsys.readouterr().out
    assert "quote=True" in out
    assert "order=True" in out
    assert "auth_required=False" in out
    assert stub_client.closed is True


def test_probe_unavailable_exits_1(
    stub_client: StubClient, capsys: pytest.CaptureFixture
) -> None:
    stub_client.error = OpenDUnavailableError("connection refused")
    assert cli.main(["probe"]) == 1
    assert "unavailable" in capsys.readouterr().err.lower()


def test_probe_auth_required_exits_2(
    stub_client: StubClient, capsys: pytest.CaptureFixture
) -> None:
    stub_client.error = OpenDAuthRequiredError("account locked")
    assert cli.main(["probe"]) == 2
    assert "auth" in capsys.readouterr().err.lower()


def test_probe_sdk_missing_exits_3(
    stub_client: StubClient, capsys: pytest.CaptureFixture
) -> None:
    stub_client.error = OpenDSdkMissingError("vendor sdk not importable")
    assert cli.main(["probe"]) == 3
    assert "sdk" in capsys.readouterr().err.lower()


def test_probe_rejects_unknown_command(stub_client: StubClient) -> None:
    with pytest.raises(SystemExit):
        cli.main(["unlock"])
    assert stub_client.closed is False


def test_probe_closes_client_on_failure(stub_client: StubClient) -> None:
    stub_client.error = OpenDUnavailableError("down")
    cli.main(["probe"])
    assert stub_client.closed is True


def _readiness_report(status: str) -> ReadinessReport:
    symbol_status = "ready" if status == "ready" else "partial"
    return ReadinessReport(
        status=status,
        capabilities=OpenDCapabilities(True, True, True, True, False),
        symbols=(
            SymbolReadiness(
                code="US.AAPL",
                status=symbol_status,
                quote_status="ready",
                history_status="ready" if status == "ready" else "unavailable",
                history_detail=None if status == "ready" else "history unavailable",
                history_rows=1 if status == "ready" else 0,
            ),
        ),
        interval="1d",
    )


def test_readiness_route_unavailable_stops_before_sdk(monkeypatch, capsys) -> None:
    def fail_build(_settings):
        raise AssertionError("SDK client must not be built for a closed route")

    monkeypatch.setattr(cli, "_build_client", fail_build)
    monkeypatch.setattr(cli, "_check_opend_route", lambda _settings: (False, "connection refused"))

    code = cli.main(["readiness", "--json"])

    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "route_unavailable"
    assert payload["order_checked"] is False
    assert payload["requested_symbols"] == ["US.AAPL", "US.NVDA"]


def test_readiness_json_reports_codes_and_never_checks_orders(
    monkeypatch, stub_client: StubClient, capsys
) -> None:
    calls: list[list[str]] = []

    def fake_run(client, codes, *, interval):
        assert client is stub_client
        calls.append(codes)
        assert interval == "1d"
        return _readiness_report("ready")

    monkeypatch.setattr(cli, "_check_opend_route", lambda _settings: (True, None))
    monkeypatch.setattr(cli, "run_readiness", fake_run)

    code = cli.main(["readiness", "--json"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ready"
    assert payload["symbols"][0]["code"] == "US.AAPL"
    assert payload["order_checked"] is False
    assert calls == [["US.AAPL", "US.NVDA"]]
    assert stub_client.closed is True


def test_readiness_partial_exits_one(monkeypatch, stub_client: StubClient, capsys) -> None:
    monkeypatch.setattr(cli, "_check_opend_route", lambda _settings: (True, None))
    monkeypatch.setattr(
        cli, "run_readiness", lambda *_args, **_kwargs: _readiness_report("partial")
    )

    assert cli.main(["readiness", "--json", "--symbols", "AAPL"]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "partial"
    assert stub_client.closed is True


@pytest.mark.parametrize(
    ("error", "expected_code", "expected_status"),
    [
        (OpenDAuthRequiredError("account locked"), 2, "auth_required"),
        (OpenDSdkMissingError("sdk missing"), 3, "sdk_missing"),
    ],
)
def test_readiness_maps_typed_provider_failures(
    monkeypatch, stub_client: StubClient, capsys, error, expected_code, expected_status
) -> None:
    stub_client.error = error
    monkeypatch.setattr(cli, "_check_opend_route", lambda _settings: (True, None))

    assert cli.main(["readiness", "--json"]) == expected_code
    assert json.loads(capsys.readouterr().out)["status"] == expected_status
    assert stub_client.closed is True


# --- paper-order / reconcile: fixture-first simulated trading -------------------------

_P1 = {
    "now": "2026-08-08T13:30:00+00:00",
    "orders": [],
    "deals": [],
    "positions": [],
    "lost_acks": ["B-1"],
}
_P2 = {
    "now": "2026-08-08T13:31:00+00:00",
    "orders": [
        {
            "order_id": "B-1",
            "code": "US.AAPL",
            "qty": 100,
            "price": 210.0,
            "order_status": "SUBMITTED",
            "trd_side": "BUY",
            "create_time": "2026-08-08 09:30:00",
            "updated_time": "2026-08-08 09:30:01",
            "remark": "QM-1",
        }
    ],
    "deals": [],
    "positions": [],
}
_P3 = {
    "now": "2026-08-08T13:32:00+00:00",
    "orders": [
        {
            "order_id": "B-1",
            "code": "US.AAPL",
            "qty": 100,
            "price": 210.0,
            "dealt_qty": 100,
            "dealt_avg_price": 210.0,
            "order_status": "FILLED_ALL",
            "trd_side": "BUY",
            "create_time": "2026-08-08 09:30:00",
            "updated_time": "2026-08-08 09:30:01",
            "remark": "QM-1",
        }
    ],
    "deals": [
        {
            "deal_id": "D-1",
            "order_id": "B-1",
            "code": "US.AAPL",
            "qty": 100,
            "price": 210.0,
            "trd_side": "BUY",
            "create_time": "2026-08-08 09:30:01",
            "fee": 0.5,
        }
    ],
    "positions": [{"code": "US.AAPL", "qty": 100}],
}


def script_file(tmp_path: Path, *phases: dict, name: str = "drill.jsonl") -> Path:
    path = tmp_path / name
    path.write_text("\n".join(json.dumps(phase) for phase in phases), encoding="utf-8")
    return path


def test_paper_order_without_fixture_is_phase_e_gated(tmp_path: Path, capsys) -> None:
    code = cli.main(
        [
            "paper-order", "--symbol", "AAPL", "--market", "US", "--qty", "100",
            "--orders-dir", str(tmp_path / "orders"),
        ]
    )

    assert code == 3
    assert "Phase E" in capsys.readouterr().err


def test_reconcile_without_fixture_is_phase_e_gated(tmp_path: Path, capsys) -> None:
    code = cli.main(["reconcile", "--orders-dir", str(tmp_path / "orders")])

    assert code == 3
    assert "Phase E" in capsys.readouterr().err


def test_paper_order_records_the_placed_order(tmp_path: Path) -> None:
    fixture = script_file(tmp_path, {**_P1, "lost_acks": []})
    orders_dir = tmp_path / "orders"

    code = cli.main([
        "paper-order", "--symbol", "AAPL", "--market", "US", "--qty", "100",
        "--price", "210", "--client-order-id", "QM-1",
        "--fixture", str(fixture), "--orders-dir", str(orders_dir),
    ])

    assert code == 0
    journal = OrderJournal(root=orders_dir)
    order = journal.get("QM-1")
    assert order.broker_order_id == "B-1"
    assert order.status.value == "pending"


def test_paper_order_with_lost_ack_records_unacknowledged(tmp_path: Path, capsys) -> None:
    fixture = script_file(tmp_path, _P1)
    orders_dir = tmp_path / "orders"

    code = cli.main([
        "paper-order", "--symbol", "AAPL", "--market", "US", "--qty", "100",
        "--price", "210", "--client-order-id", "QM-1",
        "--fixture", str(fixture), "--orders-dir", str(orders_dir),
    ])

    assert code == 0
    assert "recorded unacknowledged order QM-1" in capsys.readouterr().out
    order = OrderJournal(root=orders_dir).get("QM-1")
    assert order.broker_order_id is None


def test_paper_order_rejects_unknown_market(tmp_path: Path, capsys) -> None:
    fixture = script_file(tmp_path, {**_P1, "lost_acks": []})

    code = cli.main([
        "paper-order", "--symbol", "AAPL", "--market", "EU", "--qty", "100",
        "--fixture", str(fixture), "--orders-dir", str(tmp_path / "orders"),
    ])

    assert code == 1
    assert "invalid market" in capsys.readouterr().err


def test_reconcile_is_report_only_by_default(tmp_path: Path, capsys) -> None:
    fixture = script_file(tmp_path, _P1, _P2)
    orders_dir = tmp_path / "orders"
    cli.main([
        "paper-order", "--symbol", "AAPL", "--market", "US", "--qty", "100",
        "--price", "210", "--client-order-id", "QM-1",
        "--fixture", str(fixture), "--orders-dir", str(orders_dir),
    ])

    code = cli.main(["reconcile", "--fixture", str(fixture), "--orders-dir", str(orders_dir)])

    assert code == 0
    out = capsys.readouterr().out
    assert "1 pending" in out
    assert "recovered via remark" in out
    # Report-only: the broker id was not adopted.
    assert OrderJournal(root=orders_dir).get("QM-1").broker_order_id is None


def test_reconcile_apply_adopts_and_converges(tmp_path: Path, capsys) -> None:
    first = script_file(tmp_path, _P1, _P2, name="first.jsonl")
    full = script_file(tmp_path, _P1, _P2, _P3, name="full.jsonl")
    orders_dir = tmp_path / "orders"
    cli.main([
        "paper-order", "--symbol", "AAPL", "--market", "US", "--qty", "100",
        "--price", "210", "--client-order-id", "QM-1",
        "--fixture", str(first), "--orders-dir", str(orders_dir),
    ])

    code = cli.main(
        ["reconcile", "--fixture", str(first), "--orders-dir", str(orders_dir), "--apply"]
    )
    assert code == 0
    assert OrderJournal(root=orders_dir).get("QM-1").broker_order_id == "B-1"

    code = cli.main(
        ["reconcile", "--fixture", str(full), "--orders-dir", str(orders_dir), "--apply"]
    )
    assert code == 1  # blocking position finding pre-adoption
    order = OrderJournal(root=orders_dir).get("QM-1")
    assert order.status.value == "filled"
    assert order.fills[0].broker_fill_id == "D-1"

    code = cli.main(["reconcile", "--fixture", str(full), "--orders-dir", str(orders_dir)])
    assert code == 0
    assert "1 matched" in capsys.readouterr().out


def test_reconcile_at_replays_an_earlier_phase(tmp_path: Path) -> None:
    full = script_file(tmp_path, _P1, _P2, _P3)
    orders_dir = tmp_path / "orders"
    cli.main([
        "paper-order", "--symbol", "AAPL", "--market", "US", "--qty", "100",
        "--price", "210", "--client-order-id", "QM-1",
        "--fixture", str(full), "--orders-dir", str(orders_dir),
    ])

    code = cli.main([
        "reconcile", "--fixture", str(full), "--at", "2026-08-08T13:31:00+00:00",
        "--orders-dir", str(orders_dir),
    ])

    assert code == 0
    assert OrderJournal(root=orders_dir).get("QM-1").broker_order_id is None


def test_reconcile_tolerances_absorb_fixture_drift(tmp_path: Path) -> None:
    drifted = script_file(
        tmp_path,
        {**_P1, "lost_acks": []},
        {
            **_P3,
            "orders": [{**_P3["orders"][0], "qty": 101, "price": 211.0}],
            "positions": [],
        },
    )
    orders_dir = tmp_path / "orders"
    cli.main([
        "paper-order", "--symbol", "AAPL", "--market", "US", "--qty", "100",
        "--price", "210", "--client-order-id", "QM-1",
        "--fixture", str(drifted), "--orders-dir", str(orders_dir),
    ])

    strict = cli.main(["reconcile", "--fixture", str(drifted), "--orders-dir", str(orders_dir)])
    lenient = cli.main([
        "reconcile", "--fixture", str(drifted), "--orders-dir", str(orders_dir),
        "--qty-bps", "200", "--price-bps", "500",
    ])

    assert strict == 1
    assert lenient == 0
