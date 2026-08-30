import json
import tomllib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from quantmesh.data import cli as data_cli
from quantmesh.data.artifacts import ManifestStore
from quantmesh.data.cli import cli
from quantmesh.data.collection_receipts import (
    CollectionReceiptIntegrityError,
    derive_collection_receipt,
)
from tests.test_artifact_manifests import _manifest
from tests.test_overlap_resolutions import T_BASELINE, _evidence, _raw_manifest


def _publish(root: Path):
    store = ManifestStore(root)
    manifest = _manifest(store, close=100.0, revision=1)
    store.publish(manifest, expected_current=None)
    return manifest


def test_replay_refuses_tampered_object(tmp_path: Path, capsys) -> None:
    manifest = _publish(tmp_path)
    store = ManifestStore(tmp_path)
    reference = manifest.objects[0]
    store.objects.path_for(reference).write_bytes(b"tampered")

    assert cli(["replay", "--root", str(tmp_path), "--manifest", manifest.manifest_id]) == 1
    assert "hash mismatch" in capsys.readouterr().err


def test_replay_outputs_only_after_hash_and_typed_contract_verification(
    tmp_path: Path, capsys
) -> None:
    manifest = _publish(tmp_path)

    assert cli(["replay", "--root", str(tmp_path), "--manifest", manifest.manifest_id]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["verified"] is True
    assert payload["manifest_id"] == manifest.manifest_id
    assert payload["object_digests"] == [item.digest for item in manifest.objects]
    assert payload["row_count"] == len(manifest.row_identities)


def test_inspect_empty_catalog_is_explicit_and_non_mutating(tmp_path: Path, capsys) -> None:
    assert cli(["inspect", "--root", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out) == {"datasets": []}
    assert list(tmp_path.iterdir()) == []


def test_collect_rejects_unbounded_hyperliquid_window_before_network(
    tmp_path: Path, capsys
) -> None:
    result = cli(
        [
            "collect",
            "--root",
            str(tmp_path),
            "--provider",
            "hyperliquid",
            "--symbols",
            "BTC",
            "--interval",
            "1m",
            "--window",
            "2026-08-01T00:00:00Z/2026-08-05T00:00:00Z",
        ]
    )

    assert result == 2
    assert "5,000-candle limit" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_clean_install_entrypoint_and_release_gate_probe_are_declared() -> None:
    root = Path(__file__).resolve().parents[1]
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    release_gate = (root / "tools" / "release_gate.py").read_text(encoding="utf-8")

    assert pyproject["project"]["scripts"]["quantmesh-data"] == "quantmesh.data.cli:main"
    assert '"trusted data tooling installed"' in release_gate
    assert '"quantmesh-data"' in release_gate
    assert '"--help"' in release_gate


def test_collection_commit_refuses_a_dirty_checkout(monkeypatch) -> None:
    responses = iter(
        (
            SimpleNamespace(stdout="a" * 40 + "\n"),
            SimpleNamespace(stdout=" M src/quantmesh/data/cli.py\n"),
        )
    )
    monkeypatch.setattr(data_cli.subprocess, "run", lambda *args, **kwargs: next(responses))

    with pytest.raises(ValueError, match="clean Git checkout"):
        data_cli._repository_commit()


def test_collection_receipt_rejects_empty_current_collection(tmp_path: Path) -> None:
    with pytest.raises(CollectionReceiptIntegrityError, match="empty"):
        derive_collection_receipt(
            root=tmp_path,
            provider="hyperliquid-public",
            code_commit="a" * 40,
            collection_cycle="2026-08-31",
            manifest_ids=(),
            targets=("BTC", "ETH", "SOL"),
            interval="1m",
        )


def test_collect_cli_emits_receipt_derived_from_exact_returned_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_ids = tuple(character * 64 for character in "abcd")
    publication = SimpleNamespace(
        manifest_ids=manifest_ids,
        model_dump=lambda **_kwargs: {"manifest_ids": list(manifest_ids)},
    )
    captured: dict[str, object] = {}

    class FakeCollector:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def collect_candles(self, *_args, **_kwargs):
            return (publication,)

    def receipt(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            model_dump=lambda **_kwargs: {"contract": "collection-cycle-receipt-v1"}
        )

    monkeypatch.setattr(data_cli, "HyperliquidCollector", FakeCollector)
    monkeypatch.setattr(data_cli, "derive_collection_receipt", receipt)
    monkeypatch.setattr(data_cli, "_repository_commit", lambda: "f" * 40)

    payload = data_cli._collect(
        SimpleNamespace(
            root=tmp_path,
            provider="hyperliquid",
            symbols="BTC,ETH,SOL",
            interval="1m",
            window="2026-08-31T00:00:00Z/2026-08-31T00:02:00Z",
            collection_cycle="2026-08-31",
        )
    )

    assert captured["manifest_ids"] == manifest_ids
    assert captured["targets"] == ("BTC", "ETH", "SOL")
    assert payload["collection_receipt"] == {
        "contract": "collection-cycle-receipt-v1"
    }


def test_collect_cli_rejects_partial_formal_target_set_before_collection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        data_cli,
        "_repository_commit",
        lambda: pytest.fail("partial request reached collection setup"),
    )

    with pytest.raises(CollectionReceiptIntegrityError, match="exact provider target"):
        data_cli._collect(
            SimpleNamespace(
                root=tmp_path,
                provider="hyperliquid",
                symbols="BTC",
                interval="1m",
                window="2026-08-31T00:00:00Z/2026-08-31T00:02:00Z",
                collection_cycle="2026-08-31",
            )
        )


def test_overlap_inspect_emits_exact_failed_evidence_without_mutation(
    tmp_path: Path, capsys
) -> None:
    baseline, candidate, _, failed, report, conflicts = _evidence(tmp_path)

    assert (
        cli(["overlap", "inspect", "--root", str(tmp_path), "--evaluation", failed.evaluation_id])
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["failed_evaluation_id"] == failed.evaluation_id
    assert payload["failed_report_id"] == report.report_id
    assert payload["policy_id"] == failed.policy_id
    assert payload["dataset_id"] == candidate.dataset_id
    assert payload["baseline_manifest_id"] == baseline.manifest_id
    assert payload["candidate_manifest_id"] == candidate.manifest_id
    assert payload["conflicts"] == [item.model_dump(mode="json") for item in conflicts]
    assert not (tmp_path / ".trusted-data-v2" / "quality" / "overlap-resolutions").exists()


def test_overlap_resolve_requires_exact_repeated_ids_and_fingerprint(
    tmp_path: Path, capsys
) -> None:
    baseline, candidate, _, failed, report, conflicts = _evidence(tmp_path)
    command = [
        "overlap",
        "resolve",
        "--root",
        str(tmp_path),
        "--evaluation",
        failed.evaluation_id,
        "--report",
        report.report_id,
        "--policy",
        failed.policy_id,
        "--dataset",
        candidate.dataset_id,
        "--baseline-manifest",
        baseline.manifest_id,
        "--candidate-manifest",
        candidate.manifest_id,
        "--fingerprint",
        conflicts[0].fingerprint,
        "--reviewed-at",
        datetime(2026, 8, 24, tzinfo=UTC).isoformat(),
        "--operator",
        "local-operator",
        "--reason",
        "Moomoo revised one historical turnover value; canonical OHLCV is unchanged",
        "--attestation",
        "operator-acknowledged",
        "--use-policy",
        "ohlcv-derivatives-only",
    ]

    wrong = list(command)
    wrong[wrong.index(conflicts[0].fingerprint)] = "f" * 64
    assert cli(wrong) == 2
    assert "fingerprints" in capsys.readouterr().err

    assert cli(command) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["failed_evaluation_id"] == failed.evaluation_id
    assert payload["conflicts"][0]["fingerprint"] == conflicts[0].fingerprint
    assert payload["use_policy"] == "ohlcv-derivatives-only"


def test_overlap_inspect_ignores_uncommitted_same_revision_orphan(tmp_path: Path, capsys) -> None:
    baseline, _, _, failed, _, _ = _evidence(tmp_path)
    orphan = _raw_manifest(
        tmp_path,
        revision=baseline.compatibility_revision,
        known_at=T_BASELINE + timedelta(hours=1),
        turnover=180_500_000.0,
    )
    assert orphan.manifest_id != baseline.manifest_id

    assert (
        cli(["overlap", "inspect", "--root", str(tmp_path), "--evaluation", failed.evaluation_id])
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["baseline_manifest_id"] == baseline.manifest_id
