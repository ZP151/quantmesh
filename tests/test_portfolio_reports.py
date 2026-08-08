"""M7 Phase D tests: scenario reports on the M5 report stack (issue #42).

A scenario report pins the full setup — commit, scenario timeline,
holdings universe, account configuration — with the deterministic
replay outcomes as results. The id is setup-only and the artifacts are
byte-stable, so the same setup reproduces byte-identically across
independent roots; the registry follows the M6 forecast discipline
(no lake pin, JSONL, atomic appends, fail-closed reads, duplicate
refusal).
"""

import re
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from quantmesh.domain.models import Instrument, InstrumentType, OrderRequest, Quote, Side, Venue
from quantmesh.execution.accounting import (
    FeeModel,
    PaperAccount,
    PaperMatcher,
)
from quantmesh.execution.accounting import (
    RiskLimits as AccountingRiskLimits,
)
from quantmesh.portfolio import (
    AccountConfig,
    FundingShock,
    PortfolioHolding,
    Scenario,
    ScenarioReport,
    ScenarioReportRegistry,
    ScenarioStep,
    account_config,
    run_scenario_report,
    scenario_id,
    scenario_report_id,
)

T0 = datetime(2026, 1, 1, tzinfo=UTC)
COMMIT = "a1b2c3d4e5f67890"


def _instrument(symbol="AAA", venue=Venue.MOOMOO) -> Instrument:
    return Instrument(symbol=symbol, venue=venue, instrument_type=InstrumentType.EQUITY)


def _quote(symbol="AAA") -> Quote:
    return Quote(
        instrument=_instrument(symbol),
        timestamp=T0,
        bid=95.0,
        ask=105.0,
        last=92.5,
        volume=8000.0,
    )


def _order() -> OrderRequest:
    return OrderRequest(
        instrument=_instrument(),
        side=Side.BUY,
        quantity=8000.0,
        limit_price=105.0,
    )


def _holding(weight=1.0) -> PortfolioHolding:
    return PortfolioHolding(venue=Venue.MOOMOO, symbol="AAA", asset_class="equity", weight=weight)


def _scenario() -> Scenario:
    """The drill scenario: buy 8000 AAA at the 105 ask, then a 1%
    funding charge on the position."""
    steps = [
        ScenarioStep(at=T0, orders=[_order()]),
        ScenarioStep(
            at=datetime(2026, 1, 1, 0, 0, 10, tzinfo=UTC),
            shocks=[FundingShock(venue=Venue.MOOMOO, symbol="AAA", rate=0.01)],
        ),
    ]
    return Scenario(steps=steps, id=scenario_id(steps=steps))


def _account() -> PaperAccount:
    return PaperAccount(cash=1_000_000.0)


class TestScenarioReportDrill:
    def test_full_drill(self, tmp_path) -> None:
        registry = ScenarioReportRegistry(root=tmp_path / "reports")
        report = run_scenario_report(
            scenario=_scenario(),
            universe=[_holding()],
            account=_account(),
            quotes={"moomoo:AAA": _quote()},
            commit=COMMIT,
            registry=registry,
        )
        assert re.fullmatch(r"[0-9a-f]{16}", report.id)
        assert report.commit == COMMIT
        assert report.scenario.id == _scenario().id
        assert registry.path.is_file()
        directory = registry.root / report.id
        assert (directory / "report.json").is_file()
        assert (directory / "windows.csv").is_file()
        assert registry.get(report.id) == report
        assert registry.all() == [report]
        assert report.metrics == {
            "n_steps": 2.0,
            "final_equity": 890_760.0,
            "max_drawdown": 0.10924,
            "n_fills": 1.0,
            "n_rejections": 0.0,
            "n_liquidation_rounds": 0.0,
        }

    def test_report_json_excludes_created_at(self, tmp_path) -> None:
        registry = ScenarioReportRegistry(root=tmp_path / "reports")
        report = run_scenario_report(
            scenario=_scenario(),
            universe=[_holding()],
            account=_account(),
            quotes={"moomoo:AAA": _quote()},
            commit=COMMIT,
            registry=registry,
        )
        text = (registry.root / report.id / "report.json").read_text(encoding="utf-8")
        assert f'"id": "{report.id}"' in text
        assert "created_at" not in text
        assert '"scenario"' in text

    def test_windows_csv_shape(self, tmp_path) -> None:
        registry = ScenarioReportRegistry(root=tmp_path / "reports")
        report = run_scenario_report(
            scenario=_scenario(),
            universe=[_holding()],
            account=_account(),
            quotes={"moomoo:AAA": _quote()},
            commit=COMMIT,
            registry=registry,
        )
        path = registry.root / report.id / "windows.csv"
        lines = path.read_text(encoding="utf-8").splitlines()
        header = "index,at,cash,equity,event_value,total_fees,total_funding,fills,rejections"
        assert lines[0] == header
        assert lines[1] == "0,2026-01-01T00:00:00+00:00,159160.0,899160.0,0.0,840.0,0.0,1,"
        assert lines[2] == "1,2026-01-01T00:00:10+00:00,150760.0,890760.0,0.0,840.0,8400.0,0,"

    def test_artifacts_byte_identical_across_roots(self, tmp_path) -> None:
        """The same setup reproduces byte-identically in independent
        roots: setup-only identity, deterministic outcomes, and
        created_at excluded from the artifacts."""
        first = ScenarioReportRegistry(root=tmp_path / "a")
        second = ScenarioReportRegistry(root=tmp_path / "b")
        report_a = run_scenario_report(
            scenario=_scenario(),
            universe=[_holding()],
            account=_account(),
            quotes={"moomoo:AAA": _quote()},
            commit=COMMIT,
            registry=first,
        )
        report_b = run_scenario_report(
            scenario=_scenario(),
            universe=[_holding()],
            account=_account(),
            quotes={"moomoo:AAA": _quote()},
            commit=COMMIT,
            registry=second,
        )
        assert report_a.id == report_b.id
        for name in ("report.json", "windows.csv"):
            path_a = first.root / report_a.id / name
            path_b = second.root / report_b.id / name
            assert path_a.read_bytes() == path_b.read_bytes()


class TestScenarioReportRegistry:
    def _record(self, tmp_path) -> tuple[ScenarioReportRegistry, ScenarioReport]:
        registry = ScenarioReportRegistry(root=tmp_path / "reports")
        report = run_scenario_report(
            scenario=_scenario(),
            universe=[_holding()],
            account=_account(),
            quotes={"moomoo:AAA": _quote()},
            commit=COMMIT,
            registry=registry,
        )
        return registry, report

    def test_duplicate_refused(self, tmp_path) -> None:
        registry, report = self._record(tmp_path)
        with pytest.raises(ValueError, match="already recorded"):
            registry.record(report)

    def test_corrupted_line_attributed(self, tmp_path) -> None:
        registry, _ = self._record(tmp_path)
        with registry.path.open("a", encoding="utf-8") as handle:
            handle.write("not a report line\n")
        with pytest.raises(ValueError, match="line 2 is invalid"):
            registry.get("0" * 16)

    def test_shared_id_refused(self, tmp_path) -> None:
        registry, report = self._record(tmp_path)
        with registry.path.open("a", encoding="utf-8") as handle:
            handle.write(report.model_dump_json() + "\n")
        with pytest.raises(ValueError, match="share a report id"):
            registry.get(report.id)

    def test_root_must_be_a_directory(self, tmp_path) -> None:
        """A file in the root position fails closed before anything is
        written: the guard runs ahead of artifact creation."""
        not_a_dir = tmp_path / "file.txt"
        not_a_dir.write_text("i am a file", encoding="utf-8")
        registry = ScenarioReportRegistry(root=not_a_dir)
        with pytest.raises(ValueError, match="is not a directory"):
            run_scenario_report(
                scenario=_scenario(),
                universe=[_holding()],
                account=_account(),
                quotes={"moomoo:AAA": _quote()},
                commit=COMMIT,
                registry=registry,
            )


class TestReportIdentity:
    def test_id_must_match_setup(self, tmp_path) -> None:
        registry = ScenarioReportRegistry(root=tmp_path / "reports")
        report = run_scenario_report(
            scenario=_scenario(),
            universe=[_holding()],
            account=_account(),
            quotes={"moomoo:AAA": _quote()},
            commit=COMMIT,
            registry=registry,
        )
        with pytest.raises(ValidationError, match="does not match its setup"):
            ScenarioReport.model_validate({**report.model_dump(), "id": "0" * 16})

    def test_id_sensitive_to_setup(self) -> None:
        scenario = _scenario()
        account = account_config(_account())
        base = scenario_report_id(
            commit=COMMIT, scenario=scenario, universe=[_holding()], account=account
        )
        assert base == scenario_report_id(
            commit=COMMIT, scenario=scenario, universe=[_holding()], account=account
        )
        assert base != scenario_report_id(
            commit=COMMIT, scenario=scenario, universe=[_holding(0.5)], account=account
        )
        funded = AccountConfig(
            starting_cash=1_000_000.0,
            fee_bps=20.0,
            min_fee=0.0,
            slippage_bps=5.0,
            max_quote_age_s=30,
        )
        assert base != scenario_report_id(
            commit=COMMIT, scenario=scenario, universe=[_holding()], account=funded
        )
        other = Scenario(
            steps=[ScenarioStep(at=T0)],
            id=scenario_id(steps=[ScenarioStep(at=T0)]),
        )
        assert base != scenario_report_id(
            commit=COMMIT, scenario=other, universe=[_holding()], account=account
        )


class TestAccountConfig:
    def test_snapshot_of_kernel_account(self) -> None:
        account = PaperAccount(
            cash=500_000.0,
            fee_model=FeeModel(fee_bps=2.0, min_fee=0.01),
            matcher=PaperMatcher(slippage_bps=1.0, max_quote_age=timedelta(seconds=45)),
            risk_limits=AccountingRiskLimits(max_notional=1_000_000.0),
            kill_switch=True,
        )
        config = account_config(account)
        assert isinstance(config, AccountConfig)
        assert config.starting_cash == 500_000.0
        assert config.fee_bps == 2.0
        assert config.min_fee == 0.01
        assert config.slippage_bps == 1.0
        assert config.max_quote_age_s == 45
        assert config.risk_limits == {
            "max_order_quantity": None,
            "max_notional": 1_000_000.0,
            "max_position_quantity": None,
        }
        assert config.kill_switch is True

    def test_defaults_snapshot(self) -> None:
        config = account_config(_account())
        assert config.starting_cash == 1_000_000.0
        assert config.fee_bps == 10.0
        assert config.slippage_bps == 5.0
        assert config.max_quote_age_s == 30
        assert config.kill_switch is False
