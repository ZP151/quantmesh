import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from tools.framework_bakeoff import nautilus as nautilus_module
from tools.framework_bakeoff.nautilus import (
    NAUTILUS_LICENSE_SHA256,
    NAUTILUS_PIN,
    IsolatedRunMetadata,
    run_nautilus,
    write_evidence,
)

FIXTURE = (
    Path(__file__).parents[1]
    / "src"
    / "quantmesh"
    / "hyperliquid"
    / "fixtures"
    / "wire_candles.json"
)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def _canonical_payload(config: dict[str, object]) -> tuple[list[dict], list[dict], dict]:
    expected = config["quantmesh_expected"]
    assert isinstance(expected, dict)
    intent = config["order_intent"]
    assert isinstance(intent, dict)
    order_id = str(intent["order_id"])
    fill_id = str(intent["fill_id"])
    source = {
        "fixture": "src/quantmesh/hyperliquid/fixtures/wire_candles.json",
        "sequence_source": "quantmesh-fixture-order",
    }
    events = []
    for mode in ("backtest", "sandbox"):
        events.extend(
            [
                {
                    "event_id": f"{mode}-event-001",
                    "mode": mode,
                    "order_id": order_id,
                    "paper": True,
                    "replay_ordinal": 0,
                    "source": source,
                    "status": "submitted",
                    "venue": "hyperliquid",
                },
                {
                    "event_id": f"{mode}-event-002",
                    "mode": mode,
                    "order_id": order_id,
                    "paper": True,
                    "replay_ordinal": 0,
                    "source": source,
                    "status": "accepted",
                    "venue": "hyperliquid",
                },
                {
                    "event_id": f"{mode}-event-003",
                    "fill_id": fill_id,
                    "mode": mode,
                    "order_id": order_id,
                    "paper": True,
                    "replay_ordinal": 1,
                    "source": source,
                    "status": "filled",
                    "venue": "hyperliquid",
                },
            ]
        )
    events.sort(key=lambda row: (row["replay_ordinal"], row["mode"], row["event_id"]))
    fills = [
        {
            "fill_id": fill_id,
            "mode": mode,
            "order_id": order_id,
            "paper": True,
            "price": expected["fill_price"],
            "quantity": expected["fill_quantity"],
            "replay_ordinal": 1,
            "source": source,
            "venue": "hyperliquid",
        }
        for mode in ("backtest", "sandbox")
    ]
    account_view = {
        "account_delta": expected["account_delta"],
        "cash": expected["cash"],
        "fill_price": expected["fill_price"],
        "fill_quantity": expected["fill_quantity"],
        "order_id": order_id,
        "position_quantity": expected["position_quantity"],
        "status_transitions": ["submitted", "accepted", "filled"],
    }
    account = {
        "comparison": {"mismatches": []},
        "nautilus_backtest": account_view,
        "nautilus_sandbox": {
            **account_view,
            "config": {
                "account_type": "MARGIN",
                "bar_execution": True,
                "oms_type": "NETTING",
                "trade_execution": True,
                "use_random_ids": False,
                "use_reduce_only": True,
                "venue": "HYPERLIQUID",
            },
            "supported": True,
        },
        "paper": True,
        "quantmesh": account_view,
        "source": source,
        "starting_cash": expected["starting_cash"],
        "venue": "hyperliquid",
    }
    return events, fills, account


def fake_nautilus_runner(
    *,
    input_path: Path,
    config_path: Path,
    output_roots: tuple[Path, Path],
    work_root: Path,
) -> IsolatedRunMetadata:
    rows = [json.loads(line) for line in input_path.read_text(encoding="utf-8").splitlines()]
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert len(rows) == 6
    assert [row["replay_ordinal"] for row in rows] == [0, 1, 2, 3, 4, 5]
    assert {row["sequence_source"] for row in rows} == {"quantmesh-fixture-order"}
    assert all("sequence" not in row for row in rows)
    assert [row["source_row"]["n"] for row in rows] == [12, 9, 15, 11, 18, 7]
    assert config["paper"] is True
    assert config["symbol"] == "BTC"
    assert config["interval"] == "1m"

    events, fills, account = _canonical_payload(config)
    for output_root in output_roots:
        output_root.mkdir(parents=True, exist_ok=True)
        (output_root / "events.jsonl").write_text(
            "".join(
                json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
                for row in events
            ),
            encoding="utf-8",
        )
        _write_json(output_root / "fills.json", fills)
        _write_json(output_root / "account.json", account)

    environment = work_root / "environment"
    environment.mkdir(parents=True, exist_ok=True)
    (environment / "commands.json").write_text("[]\n", encoding="utf-8")
    (environment / "pip-check.txt").write_text(
        "No broken requirements found.\n", encoding="utf-8"
    )
    (environment / "pip-freeze.txt").write_text(
        "nautilus_trader==1.231.0\n", encoding="utf-8"
    )
    return IsolatedRunMetadata(
        revision=NAUTILUS_PIN,
        version="1.231.0",
        license_sha256=NAUTILUS_LICENSE_SHA256,
        duration_seconds=0.25,
        peak_rss_mb=24.0,
        environment_bytes=2048,
        commands=("{python} {quantmesh}/tools/framework_bakeoff/nautilus_driver.py",),
        environment_artifacts={
            "commands": "environment/commands.json",
            "pip_check": "environment/pip-check.txt",
            "pip_freeze": "environment/pip-freeze.txt",
        },
        pip_check_exit_code=0,
        limitations=("isolated LGPL comparator; not runtime-admitted",),
    )


def test_fake_runner_preserves_fixture_order_provenance_and_portable_artifacts(
    tmp_path: Path,
) -> None:
    work_root = tmp_path / "work"

    result = run_nautilus(FIXTURE, work_root, runner=fake_nautilus_runner)

    assert result.framework == "nautilus-trader"
    assert result.revision == NAUTILUS_PIN
    assert result.status == "passed"
    assert result.deterministic is True
    assert result.output_digest is not None
    assert result.checks == {
        "chronological_split": True,
        "contract_mapping": True,
        "deterministic": True,
        "license": True,
        "no_leakage": True,
        "paper_only": True,
        "windows_install": True,
    }
    assert result.artifacts["events"] == "outputs/run-1/events.jsonl"
    assert result.artifacts["fills"] == "outputs/run-1/fills.json"
    assert result.artifacts["account"] == "outputs/run-1/account.json"
    assert all(not Path(value).is_absolute() for value in result.artifacts.values())

    exported = [
        json.loads(line)
        for line in (work_root / "input.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [row["replay_ordinal"] for row in exported] == list(range(6))
    assert all(row["sequence_source"] == "quantmesh-fixture-order" for row in exported)
    assert all("sequence" not in row for row in exported)
    assert exported[0]["source_row"]["n"] == 12
    assert exported[0]["source"] == "quantmesh-hyperliquid-wire-fixture"

    fills = json.loads(
        (work_root / result.artifacts["fills"]).read_text(encoding="utf-8")
    )
    assert [row["replay_ordinal"] for row in fills] == [1, 1]
    assert {row["venue"] for row in fills} == {"hyperliquid"}
    assert all(row["paper"] is True for row in fills)
    assert len({row["order_id"] for row in fills}) == 1
    assert len({row["fill_id"] for row in fills}) == 1

    account = json.loads(
        (work_root / result.artifacts["account"]).read_text(encoding="utf-8")
    )
    assert account["comparison"]["mismatches"] == []
    assert account["quantmesh"]["cash"] == pytest.approx(99_989.53955)
    assert account["quantmesh"]["position_quantity"] == pytest.approx(0.1)


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        (lambda rows: rows.__setitem__(1, {**rows[1], "s": "ETH"}), "symbol"),
        (lambda rows: rows.__setitem__(1, {**rows[1], "i": "5m"}), "interval"),
        (lambda rows: rows.__setitem__(1, {**rows[1], "t": rows[0]["t"]}), "timestamp"),
        (
            lambda rows: rows.__setitem__(1, {**rows[1], "t": rows[1]["t"] + 60_000}),
            "gap",
        ),
    ],
)
def test_fixture_validation_fails_closed_before_runner(
    tmp_path: Path, mutation, match: str
) -> None:
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    mutation(rows)
    fixture = tmp_path / "candles.json"
    _write_json(fixture, rows)
    called = False

    def forbidden_runner(**_kwargs: object) -> IsolatedRunMetadata:
        nonlocal called
        called = True
        raise AssertionError("invalid fixture reached runner")

    result = run_nautilus(fixture, tmp_path / "work", runner=forbidden_runner)

    assert result.status == "failed"
    assert result.deterministic is False
    assert called is False
    assert any(match in limitation.lower() for limitation in result.limitations)


def test_unmarked_one_minute_gap_is_rejected_without_fabricating_a_gap_flag(
    tmp_path: Path,
) -> None:
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for index in range(3, len(rows)):
        rows[index]["t"] += 60_000
        rows[index]["T"] += 60_000
    fixture = tmp_path / "gapped.json"
    _write_json(fixture, rows)

    result = run_nautilus(fixture, tmp_path / "work", runner=fake_nautilus_runner)

    assert result.status == "failed"
    exported = tmp_path / "work" / "input.jsonl"
    assert not exported.exists() or "sequence_gap" not in exported.read_text(
        encoding="utf-8"
    )
    assert any("unmarked 1m gap" in item for item in result.limitations)


def test_two_run_digest_difference_fails_the_deterministic_gate(tmp_path: Path) -> None:
    def nondeterministic_runner(**kwargs: object) -> IsolatedRunMetadata:
        metadata = fake_nautilus_runner(**kwargs)  # type: ignore[arg-type]
        output_roots = kwargs["output_roots"]
        assert isinstance(output_roots, tuple)
        fills_path = output_roots[1] / "fills.json"
        fills = json.loads(fills_path.read_text(encoding="utf-8"))
        fills[0]["price"] = 999.0
        _write_json(fills_path, fills)
        return metadata

    result = run_nautilus(
        FIXTURE, tmp_path / "work", runner=nondeterministic_runner
    )

    assert result.status == "failed"
    assert result.deterministic is False
    assert result.checks["deterministic"] is False
    assert result.output_digest is None
    assert "canonical output digests differ" in result.limitations


def test_semantic_mismatch_is_retained_and_fails_contract_mapping(tmp_path: Path) -> None:
    def mismatching_runner(**kwargs: object) -> IsolatedRunMetadata:
        metadata = fake_nautilus_runner(**kwargs)  # type: ignore[arg-type]
        output_roots = kwargs["output_roots"]
        assert isinstance(output_roots, tuple)
        for output_root in output_roots:
            account_path = output_root / "account.json"
            account = json.loads(account_path.read_text(encoding="utf-8"))
            account["nautilus_sandbox"]["fill_price"] = 104.0
            account["comparison"]["mismatches"] = [
                "sandbox fill_price 104.0 != quantmesh 104.5"
            ]
            _write_json(account_path, account)
        return metadata

    result = run_nautilus(FIXTURE, tmp_path / "work", runner=mismatching_runner)

    assert result.status == "failed"
    assert result.deterministic is True
    assert result.output_digest is not None
    assert result.checks["contract_mapping"] is False
    assert any("sandbox fill_price" in item for item in result.limitations)


def test_nonzero_pip_check_fails_windows_install(tmp_path: Path) -> None:
    def broken_runner(**kwargs: object) -> IsolatedRunMetadata:
        return replace(
            fake_nautilus_runner(**kwargs),  # type: ignore[arg-type]
            pip_check_exit_code=1,
        )

    result = run_nautilus(FIXTURE, tmp_path / "work", runner=broken_runner)

    assert result.status == "failed"
    assert result.checks["windows_install"] is False
    assert "pip check failed with exit code 1" in result.limitations


def test_evidence_is_portable_and_excludes_local_identity(tmp_path: Path) -> None:
    work_root = tmp_path / "work-volatile-8f26"
    evidence_path = tmp_path / "nautilus-run.json"
    result = run_nautilus(FIXTURE, work_root, runner=fake_nautilus_runner)

    write_evidence(evidence_path, result)

    payload = evidence_path.read_text(encoding="utf-8")
    assert str(work_root) not in payload
    assert "C:\\Users" not in payload
    assert os.environ.get("USERNAME", "forbidden-username") not in payload
    assert "8f26" not in payload
    assert "outputs/run-1/events.jsonl" in payload


def test_unmarked_nonempty_work_root_is_preserved_and_rejected(tmp_path: Path) -> None:
    work_root = tmp_path / "unknown-work"
    work_root.mkdir()
    sentinel = work_root / "operator-file.txt"
    sentinel.write_text("preserve me", encoding="utf-8")

    result = run_nautilus(FIXTURE, work_root, runner=fake_nautilus_runner)

    assert result.status == "failed"
    assert sentinel.read_text(encoding="utf-8") == "preserve me"
    assert result.limitations == [
        "failure_stage=work-root-preparation",
        "failure_type=WorkRootOwnershipError",
        "failure_code=work-root-ownership",
    ]


def test_owned_work_root_removes_stale_outputs_and_environment(tmp_path: Path) -> None:
    work_root = tmp_path / "owned-work"
    assert run_nautilus(FIXTURE, work_root, runner=fake_nautilus_runner).status == "passed"
    (work_root / "outputs" / "run-1" / "stale.json").write_text(
        "stale", encoding="utf-8"
    )
    site_packages = work_root / "venv" / "Lib" / "site-packages"
    site_packages.mkdir(parents=True)
    (site_packages / "injected.pth").write_text("bad", encoding="utf-8")

    def clean_runner(**kwargs: object) -> IsolatedRunMetadata:
        assert not (work_root / "venv").exists()
        output_roots = kwargs["output_roots"]
        assert isinstance(output_roots, tuple)
        assert all(not any(root.iterdir()) for root in output_roots)
        return fake_nautilus_runner(**kwargs)  # type: ignore[arg-type]

    result = run_nautilus(FIXTURE, work_root, runner=clean_runner)

    assert result.status == "passed"


def test_repository_root_is_rejected_as_sensitive_work_root() -> None:
    repository_root = Path(nautilus_module.__file__).parents[2]

    result = run_nautilus(FIXTURE, repository_root, runner=fake_nautilus_runner)

    assert result.status == "failed"
    assert result.limitations == [
        "failure_stage=work-root-resolution",
        "failure_type=WorkRootOwnershipError",
        "failure_code=work-root-sensitive-location",
    ]


@pytest.mark.parametrize(
    "lexeme",
    [
        r"\\?\C:\scratch",
        r"\\.\C:\scratch",
        r"\??\C:\scratch",
        r"\\server\share\scratch",
        "//server/share/scratch",
    ],
)
def test_windows_namespace_and_network_roots_fail_closed(lexeme: str) -> None:
    result = run_nautilus(FIXTURE, lexeme, runner=fake_nautilus_runner)

    assert result.status == "failed"
    assert result.limitations[-1] == "failure_code=work-root-unsupported-namespace"


def test_hard_link_artifact_aliases_are_both_omitted(tmp_path: Path) -> None:
    def hard_link_runner(**kwargs: object) -> IsolatedRunMetadata:
        metadata = fake_nautilus_runner(**kwargs)  # type: ignore[arg-type]
        work_root = kwargs["work_root"]
        assert isinstance(work_root, Path)
        original = work_root / "environment" / "physical.txt"
        alias = work_root / "environment" / "physical-alias.txt"
        original.write_text("one inode", encoding="utf-8")
        try:
            os.link(original, alias)
        except (NotImplementedError, OSError) as error:
            pytest.skip(f"filesystem cannot create a hard link: {error}")
        return replace(
            metadata,
            environment_artifacts={
                **metadata.environment_artifacts,
                "physical": "environment/physical.txt",
                "physical_alias": "environment/physical-alias.txt",
            },
        )

    result = run_nautilus(FIXTURE, tmp_path / "work", runner=hard_link_runner)

    assert result.status == "passed"
    assert "physical" not in result.artifacts
    assert "physical_alias" not in result.artifacts


def test_canonical_runs_must_not_share_physical_files(tmp_path: Path) -> None:
    def aliased_runs(**kwargs: object) -> IsolatedRunMetadata:
        metadata = fake_nautilus_runner(**kwargs)  # type: ignore[arg-type]
        output_roots = kwargs["output_roots"]
        assert isinstance(output_roots, tuple)
        for name in ("events.jsonl", "fills.json", "account.json"):
            second = output_roots[1] / name
            second.unlink()
            try:
                os.link(output_roots[0] / name, second)
            except (NotImplementedError, OSError) as error:
                pytest.skip(f"filesystem cannot create a hard link: {error}")
        return metadata

    result = run_nautilus(FIXTURE, tmp_path / "work", runner=aliased_runs)

    assert result.status == "failed"
    assert result.deterministic is False
    assert result.checks["deterministic"] is False
    assert "canonical runs share physical files" in result.limitations


def test_runner_metadata_cannot_leak_nonportable_paths(tmp_path: Path) -> None:
    windows_secret = r"C:\Operators\private-user\profile.txt"
    posix_secret = "/home/private-user/profile.txt"

    def poisoned_runner(**kwargs: object) -> IsolatedRunMetadata:
        return replace(
            fake_nautilus_runner(**kwargs),  # type: ignore[arg-type]
            version=windows_secret,
            license_sha256=posix_secret,
            commands=(windows_secret,),
            limitations=(posix_secret,),
        )

    result = run_nautilus(FIXTURE, tmp_path / "work", runner=poisoned_runner)
    payload = result.model_dump_json()

    assert result.status == "failed"
    assert result.checks["license"] is False
    assert result.checks["windows_install"] is False
    assert windows_secret not in payload
    assert posix_secret not in payload
    assert "private-user" not in payload


def test_driver_source_has_no_quantmesh_or_live_adapter_imports() -> None:
    source = (
        Path(__file__).parents[1]
        / "tools"
        / "framework_bakeoff"
        / "nautilus_driver.py"
    ).read_text(encoding="utf-8")

    assert "import quantmesh" not in source
    assert "from quantmesh" not in source
    assert "nautilus_trader.adapters.hyperliquid" not in source
    assert "os.environ" not in source
