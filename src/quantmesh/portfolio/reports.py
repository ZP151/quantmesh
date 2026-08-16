"""Scenario reports on the M5 report stack (M7 Phase D, issue #42).

A scenario report records the full setup — commit, the scenario
timeline (shocks + orders), the holdings universe and the account
configuration — with the deterministic replay outcomes as results.
The id is setup-only: it pins the scenario id (itself setup-only over
the timeline), the sorted universe and the account config, never the
outcomes. The registry follows the M6 forecast precedent (no lake
pin: the recorded universe IS the setup) with the shared discipline —
JSONL, atomic temp+replace appends, fail-closed reads with line
attribution, duplicate refusal — and byte-stable artifacts
(report.json excluding ``created_at``, windows.csv) that reproduce
byte-identically across independent roots.
"""

import csv
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

from quantmesh.execution.accounting import PaperAccount
from quantmesh.persistence.jsonl import JsonlStore
from quantmesh.portfolio.exposure import PortfolioHolding
from quantmesh.portfolio.scenarios import (
    Scenario,
    ScenarioRunWindow,
    run_scenario,
)
from quantmesh.research.reports import Parameter, current_commit

SCENARIOS_FILE = "scenarios.jsonl"
ID_PATTERN = "^[0-9a-f]{16}$"
COMMIT_PATTERN = "^[0-9a-f]{7,64}$"


class AccountConfig(BaseModel):
    """The M2 kernel configuration a scenario runs against — the part
    of the account that is setup (outcomes are results)."""

    starting_cash: float = Field(ge=0)
    fee_bps: float = Field(ge=0)
    min_fee: float = Field(ge=0)
    slippage_bps: float = Field(ge=0)
    max_quote_age_s: int = Field(ge=0)
    risk_limits: dict[str, Parameter] = Field(default_factory=dict)
    kill_switch: bool = False


def account_config(account: PaperAccount) -> AccountConfig:
    """Canonical setup snapshot of a paper account."""
    return AccountConfig(
        starting_cash=account.starting_cash if account.starting_cash is not None else account.cash,
        fee_bps=account.fee_model.fee_bps,
        min_fee=account.fee_model.min_fee,
        slippage_bps=account.matcher.slippage_bps,
        max_quote_age_s=int(account.matcher.max_quote_age.total_seconds()),
        risk_limits=account.risk_limits.model_dump(),
        kill_switch=account.kill_switch,
    )


def scenario_report_id(
    *,
    commit: str,
    scenario: Scenario,
    universe: list[PortfolioHolding],
    account: AccountConfig,
) -> str:
    """Setup-only 16-hex id: commit + scenario id (timeline) + sorted
    universe + account config — never outcomes."""
    members = sorted(
        (
            member.venue.value,
            member.symbol,
            member.asset_class,
            member.event_key,
            member.held_probability,
            member.weight,
        )
        for member in universe
    )
    setup = {
        "commit": commit,
        "scenario": scenario.id,
        "universe": members,
        "account": account.model_dump(mode="json"),
    }
    canonical = json.dumps(setup, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"scenario-report\0{canonical}".encode()).hexdigest()[:16]


class ScenarioReport(BaseModel):
    """One recorded scenario run: pinned setup plus observed outcomes."""

    id: str = Field(pattern=ID_PATTERN)
    commit: str = Field(pattern=COMMIT_PATTERN)
    scenario: Scenario
    universe: list[PortfolioHolding] = Field(min_length=1)
    account: AccountConfig
    created_at: datetime
    windows: list[ScenarioRunWindow] = Field(min_length=1)
    metrics: dict[str, Parameter] = Field(default_factory=dict)

    @model_validator(mode="after")
    def report_is_consistent(self) -> "ScenarioReport":
        expected = scenario_report_id(
            commit=self.commit,
            scenario=self.scenario,
            universe=self.universe,
            account=self.account,
        )
        if self.id != expected:
            raise ValueError(
                f"scenario report id {self.id!r} does not match its setup "
                f"(expected {expected!r})"
            )
        return self


def scenario_report_artifact_paths(root: Path, report: ScenarioReport) -> dict[str, Path]:
    """Deterministic artifact locations (ADR-0005 decision 7, applied)."""
    directory = root / report.id
    return {
        "report.json": directory / "report.json",
        "windows.csv": directory / "windows.csv",
    }


def _write_artifacts(root: Path, report: ScenarioReport) -> None:
    """Byte-stable artifacts: ``report.json`` excludes ``created_at``
    and serializes to JSON (mode="json" — the M6 report idiom);
    ``windows.csv`` writes every window row in order with a fixed
    newline convention."""
    if root.exists() and not root.is_dir():
        raise ValueError(f"scenario registry root {root} is not a directory")
    directory = root / report.id
    directory.mkdir(parents=True, exist_ok=True)
    body = report.model_dump(mode="json", exclude={"created_at"})
    (directory / "report.json").write_bytes(
        json.dumps(body, indent=2, sort_keys=True).encode() + b"\n"
    )
    with (directory / "windows.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            [
                "index",
                "at",
                "cash",
                "equity",
                "event_value",
                "total_fees",
                "total_funding",
                "fills",
                "rejections",
            ]
        )
        for window in report.windows:
            writer.writerow(
                [
                    window.index,
                    window.at.isoformat(),
                    window.cash,
                    window.equity,
                    window.event_value,
                    window.total_fees,
                    window.total_funding,
                    window.fills,
                    ";".join(window.rejections),
                ]
            )


class ScenarioReportRegistry:
    """Append-only JSONL registry for scenario reports (the M6
    forecast discipline: the recorded universe is the setup, so there
    is no lake pin to dangle)."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else Path.home() / ".quantmesh" / "reports"
        self._store = JsonlStore(
            self.root,
            filename=SCENARIOS_FILE,
            model=ScenarioReport,
            label="scenario registry",
            id_label="report",
            record_label="scenario report",
            key=lambda report: report.id,
        )

    @property
    def path(self) -> Path:
        return self.root / SCENARIOS_FILE

    def record(self, report: ScenarioReport) -> ScenarioReport:
        return self._store.append(report)

    def get(self, report_id_value: str) -> ScenarioReport:
        matches = [item for item in self._store.read() if item.id == report_id_value]
        if not matches:
            raise ValueError(f"no scenario report recorded with id {report_id_value!r}")
        return matches[0]

    def all(self) -> list[ScenarioReport]:
        return self._store.read()


def run_scenario_report(
    *,
    scenario: Scenario,
    universe: list[PortfolioHolding],
    account: PaperAccount,
    quotes: dict[str, Any],
    commit: str | None = None,
    registry: ScenarioReportRegistry | None = None,
) -> ScenarioReport:
    """Replay the scenario and record the report (artifacts written
    before the registry append, so a crash leaves at worst an
    unreferenced orphan — the M3 discipline)."""
    if registry is None:
        registry = ScenarioReportRegistry()
    if commit is None:
        commit = current_commit()
    run = run_scenario(account, scenario, quotes=quotes, holdings=universe)
    report = ScenarioReport(
        id=scenario_report_id(
            commit=commit,
            scenario=scenario,
            universe=universe,
            account=account_config(account),
        ),
        commit=commit,
        scenario=scenario,
        universe=universe,
        account=account_config(account),
        created_at=datetime.now(UTC),
        windows=run.windows,
        metrics=run.metrics,
    )
    _write_artifacts(registry.root, report)
    registry.record(report)
    return report
