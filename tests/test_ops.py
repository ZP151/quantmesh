"""M10 Phase A tests (issue #58): metrics on the ADR-0006 discipline,
reliability/drawdown limits with alert emission through the M7
AlertLedger, the structured log formatter, the key-file store seam,
signed audit exports (verify / tamper-refusal drill), the ops CLI,
and the incident-runbook doc test.
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from quantmesh.ai.decisions import DecisionLog, DecisionRecord, ModelMeta
from quantmesh.ai.roles import AnalystReport
from quantmesh.domain.models import (
    Instrument,
    InstrumentType,
    OrderRequest,
    Quote,
    Side,
    Venue,
)
from quantmesh.events.mapping import (
    MAPPINGS_FILE,
    EvidenceKind,
    MappingEvidence,
    MappingLedger,
    MappingRecord,
    MappingStatus,
    pair_key,
)
from quantmesh.execution import OrderJournal
from quantmesh.execution.accounting import FeeModel, PaperAccount, PaperMatcher
from quantmesh.ops.export import BundleVerificationError, export_audit_bundle, verify_audit_bundle
from quantmesh.ops.limits import (
    EQUITY_METRIC,
    MISMATCH_METRIC,
    ReliabilityLimits,
    evaluate_limits,
    record_breach_alerts,
)
from quantmesh.ops.logging_fmt import StructuredFormatter
from quantmesh.ops.metrics import METRICS_FILE, Metric, MetricsStore, metric_id
from quantmesh.ops.secrets import KeyFileStore
from quantmesh.research.drift import AlertLedger

T0 = datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC)
KEY = b"k" * 32
INSTRUMENT = Instrument(
    symbol="AAPL", venue=Venue.INTERNAL, instrument_type=InstrumentType.EQUITY
)


def _metric(name: str, value: float, at: datetime = T0) -> Metric:
    return Metric(
        id=metric_id(name=name, measured_at=at),
        name=name,
        kind="gauge",
        unit="usd",
        value=value,
        measured_at=at,
    )


def _order() -> object:
    account = PaperAccount(
        cash=10_000.0,
        fee_model=FeeModel(fee_bps=10),
        matcher=PaperMatcher(slippage_bps=0.0),
    )
    quote = Quote(instrument=INSTRUMENT, timestamp=T0, bid=99.0, ask=100.0, volume=100)
    return account.submit(
        OrderRequest(instrument=INSTRUMENT, side=Side.BUY, quantity=10),
        quote,
        now=T0,
    ).order


def _mapping_record() -> MappingRecord:
    return MappingRecord(
        pair_key=pair_key("a", "b"),
        status=MappingStatus.PENDING,
        evidence=[MappingEvidence(kind=EvidenceKind.TITLE, detail="same title")],
        commit="cafe1234567",
        recorded_at=T0,
    )


def _decision_record() -> DecisionRecord:
    return DecisionRecord.for_stage(
        run_id="a" * 16,
        role="analyst",
        model=ModelMeta(name="fixture-model", version="v1.0", endpoint_kind="scripted"),
        prompt="redacted analyst context",
        schema_id="analyst-report-v1",
        output=AnalystReport(claims=[]),
        recorded_at=T0,
    )


class TestMetricModel:
    def test_id_matches_setup(self) -> None:
        metric = _metric("equity", 1000.0)
        assert metric.id == metric_id(name="equity", measured_at=T0)
        assert len(metric.id) == 16

    def test_wrong_id_refused(self) -> None:
        with pytest.raises(ValueError, match="does not match"):
            Metric.model_validate(
                {
                    "id": "f" * 16,
                    "name": "equity",
                    "kind": "gauge",
                    "unit": "usd",
                    "value": 1.0,
                    "measured_at": T0,
                }
            )

    def test_non_identifier_name_refused(self) -> None:
        with pytest.raises(ValueError, match="snake_case"):
            _metric("Equity Value", 1.0)

    def test_non_finite_value_refused(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            _metric("equity", float("nan"))

    def test_naive_timestamp_refused(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            Metric(
                id=metric_id(name="equity", measured_at=datetime(2026, 8, 8, 12)),
                name="equity",
                kind="gauge",
                unit="usd",
                value=1.0,
                measured_at=datetime(2026, 8, 8, 12),
            )

    def test_timestamp_normalized_to_utc(self) -> None:
        aware = datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC)
        metric = _metric("equity", 1.0, at=aware)
        assert metric.measured_at == aware


class TestMetricsStore:
    def test_round_trip_and_cross_instance(self, tmp_path: Path) -> None:
        store = MetricsStore(tmp_path / "metrics")
        first = store.record(_metric("equity", 1000.0))
        second = store.record(_metric("equity", 990.0, at=datetime(2026, 8, 8, 12, 1, tzinfo=UTC)))
        reloaded = MetricsStore(tmp_path / "metrics").all()
        assert [item.id for item in reloaded] == [first.id, second.id]
        assert [item.value for item in reloaded] == [1000.0, 990.0]

    def test_missing_store_reads_empty(self, tmp_path: Path) -> None:
        assert MetricsStore(tmp_path / "none").all() == []

    def test_root_not_a_directory_refused(self, tmp_path: Path) -> None:
        root = tmp_path / "metrics"
        root.write_text("not a dir", encoding="utf-8")
        with pytest.raises(ValueError, match="is not a directory"):
            MetricsStore(root).all()

    def test_duplicate_id_refused_before_write(self, tmp_path: Path) -> None:
        store = MetricsStore(tmp_path / "metrics")
        store.record(_metric("equity", 1000.0))
        with pytest.raises(ValueError, match="already recorded"):
            store.record(_metric("equity", 1000.0))
        assert len(store.all()) == 1

    def test_corrupt_line_attribution(self, tmp_path: Path) -> None:
        root = tmp_path / "metrics"
        root.mkdir()
        (root / METRICS_FILE).write_text('{"broken": true}\n', encoding="utf-8")
        with pytest.raises(ValueError, match=f"{METRICS_FILE} line 1 is invalid"):
            MetricsStore(root).all()

    def test_duplicate_ids_in_file_attribution(self, tmp_path: Path) -> None:
        root = tmp_path / "metrics"
        root.mkdir()
        metric = _metric("equity", 1000.0)
        (root / METRICS_FILE).write_text(
            metric.model_dump_json() + "\n" + metric.model_dump_json() + "\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="share a record id"):
            MetricsStore(root).all()


class TestLimits:
    def _series(self, values: list[float]) -> list[Metric]:
        return [
            _metric(EQUITY_METRIC, value, at=datetime(2026, 8, 8, 12, i, tzinfo=UTC))
            for i, value in enumerate(values)
        ]

    def test_drawdown_breach_detected(self) -> None:
        # Peak 1000 -> trough 500 = 50% drawdown, beyond the 25% limit.
        breaches = evaluate_limits(
            self._series([1000.0, 900.0, 500.0, 600.0]), ReliabilityLimits()
        )
        assert len(breaches) == 1
        assert breaches[0].limit == "max_drawdown_fraction"
        assert breaches[0].measured == pytest.approx(0.5)
        assert breaches[0].limit_value == 0.25

    def test_drawdown_within_limit_no_breach(self) -> None:
        breaches = evaluate_limits(
            self._series([1000.0, 950.0, 980.0]), ReliabilityLimits()
        )
        assert breaches == []

    def test_drawdown_ignores_prior_peak_outside_window(self) -> None:
        # The window starts at 500: no prior peak is visible, so the
        # run-up from 500 to 600 has no drawdown at all.
        breaches = evaluate_limits(
            self._series([500.0, 600.0]),
            ReliabilityLimits(),
            since=datetime(2026, 8, 8, 12, 0, tzinfo=UTC),
        )
        assert breaches == []

    def test_mismatch_limit_breach(self) -> None:
        metrics = [_metric(MISMATCH_METRIC, 4.0, at=T0), _metric(MISMATCH_METRIC, 6.0)]
        breaches = evaluate_limits(metrics, ReliabilityLimits())
        assert len(breaches) == 1
        assert breaches[0].limit == "max_consecutive_mismatches"
        assert breaches[0].measured == 6.0

    def test_zero_limit_breaches_on_any_sample(self) -> None:
        metrics = [_metric(MISMATCH_METRIC, 1.0, at=T0)]
        breaches = evaluate_limits(metrics, ReliabilityLimits(max_consecutive_mismatches=0))
        assert len(breaches) == 1
        assert breaches[0].limit_value == 0


class TestBreachAlerts:
    def test_breach_records_ops_alert(self, tmp_path: Path) -> None:
        ledger = AlertLedger(root=tmp_path / "alerts")
        breaches = evaluate_limits(
            [_metric(EQUITY_METRIC, 1000.0), _metric(EQUITY_METRIC, 400.0)],
            ReliabilityLimits(),
        )
        recorded = record_breach_alerts(ledger, breaches, now=T0)
        assert len(recorded) == 1
        alert = recorded[0]
        assert alert.kind == "reliability_limit"
        assert alert.source == "ops:limits"
        assert alert.observed["limit"] == "max_drawdown_fraction"
        assert alert.observed["measured"] == pytest.approx(0.6)
        assert AlertLedger(root=tmp_path / "alerts").all()[0].id == alert.id

    def test_identical_redetection_refused_by_ledger(self, tmp_path: Path) -> None:
        ledger = AlertLedger(root=tmp_path / "alerts")
        breaches = evaluate_limits(
            [_metric(EQUITY_METRIC, 1000.0), _metric(EQUITY_METRIC, 400.0)],
            ReliabilityLimits(),
        )
        record_breach_alerts(ledger, breaches, now=T0)
        with pytest.raises(ValueError, match="already recorded"):
            record_breach_alerts(ledger, breaches, now=T0)


class TestStructuredFormatter:
    def test_json_line_shape(self) -> None:
        record = logging.LogRecord(
            "quantmesh.ops", logging.INFO, __file__, 1, "reconciled", None, None
        )
        line = StructuredFormatter().format(record)
        payload = json.loads(line)
        assert payload["level"] == "INFO"
        assert payload["logger"] == "quantmesh.ops"
        assert payload["message"] == "reconciled"
        assert payload["fields"] == {}

    def test_fields_passthrough(self) -> None:
        record = logging.LogRecord(
            "quantmesh.ops", logging.WARNING, __file__, 1, "limit crossed", None, None
        )
        record.fields = {"drawdown": 0.5}
        payload = json.loads(StructuredFormatter().format(record))
        assert payload["fields"] == {"drawdown": 0.5}

    def test_non_serializable_field_repr_fallback(self) -> None:
        record = logging.LogRecord(
            "quantmesh.ops", logging.INFO, __file__, 1, "shapes", None, None
        )
        record.fields = {"blob": object()}
        payload = json.loads(StructuredFormatter().format(record))
        assert "object at" in payload["fields"]["blob"]


class TestKeyFileStore:
    def test_round_trip_and_delete(self, tmp_path: Path) -> None:
        store = KeyFileStore(tmp_path / "keys")
        store.put("audit-signing", KEY)
        assert store.get("audit-signing") == KEY
        store.delete("audit-signing")
        assert store.get("audit-signing") is None

    def test_missing_key_reads_none(self, tmp_path: Path) -> None:
        assert KeyFileStore(tmp_path / "keys").get("absent") is None

    def test_path_traversal_refused(self, tmp_path: Path) -> None:
        store = KeyFileStore(tmp_path / "keys")
        with pytest.raises(ValueError, match="safe filename"):
            store.get("../../etc/passwd")

    def test_key_path_is_directory_refused(self, tmp_path: Path) -> None:
        root = tmp_path / "keys"
        (root / "audit-signing").mkdir(parents=True)
        with pytest.raises(ValueError, match="is not a file"):
            KeyFileStore(root).get("audit-signing")


class TestAuditExport:
    def _journals(self, tmp_path: Path) -> None:
        """Populate the four surfaces through their own APIs where
        possible; the mapping ledger's record() takes a report, not a
        record, so its record line is written directly (a valid record
        reads back identically — the ledger read discipline is
        exercised by its own suite)."""
        root = tmp_path / "surfaces"
        OrderJournal(root=root / "orders").record(_order())
        mappings = root / "mappings"
        mappings.mkdir(parents=True, exist_ok=True)
        (mappings / MAPPINGS_FILE).write_text(
            _mapping_record().model_dump_json() + "\n", encoding="utf-8"
        )
        DecisionLog(root=root / "decisions").record(_decision_record())
        MetricsStore(root=root / "metrics").record(_metric("equity", 1000.0))

    def _bundle(self, tmp_path: Path) -> Path:
        root = tmp_path / "surfaces"
        self._journals(tmp_path)
        return export_audit_bundle(
            tmp_path / "audit" / "bundle.json",
            orders=OrderJournal(root=root / "orders").all(),
            mappings=MappingLedger(root=root / "mappings").all(),
            decisions=DecisionLog(root=root / "decisions").all(),
            metrics=MetricsStore(root=root / "metrics").all(),
            key=KEY,
            exported_at=T0,
        )

    def test_export_verify_round_trip(self, tmp_path: Path) -> None:
        content = verify_audit_bundle(self._bundle(tmp_path), key=KEY)
        assert set(content) == {"orders", "mappings", "decisions", "metrics"}
        assert len(content["orders"]) == 1
        assert len(content["mappings"]) == 1
        assert len(content["decisions"]) == 1
        assert len(content["metrics"]) == 1

    def test_tampered_value_refused(self, tmp_path: Path) -> None:
        path = self._bundle(tmp_path)
        bundle = json.loads(path.read_text(encoding="utf-8"))
        bundle["content"]["metrics"][0]["value"] = 999.0
        path.write_text(json.dumps(bundle), encoding="utf-8")
        with pytest.raises(BundleVerificationError, match="digest"):
            verify_audit_bundle(path, key=KEY)

    def test_tampered_digest_refused(self, tmp_path: Path) -> None:
        path = self._bundle(tmp_path)
        bundle = json.loads(path.read_text(encoding="utf-8"))
        bundle["digest"] = "f" * 64
        path.write_text(json.dumps(bundle), encoding="utf-8")
        with pytest.raises(BundleVerificationError, match="digest"):
            verify_audit_bundle(path, key=KEY)

    def test_tampered_signature_refused(self, tmp_path: Path) -> None:
        path = self._bundle(tmp_path)
        bundle = json.loads(path.read_text(encoding="utf-8"))
        bundle["signature"] = "f" * 64
        path.write_text(json.dumps(bundle), encoding="utf-8")
        with pytest.raises(BundleVerificationError, match="signature"):
            verify_audit_bundle(path, key=KEY)

    def test_wrong_key_refused(self, tmp_path: Path) -> None:
        with pytest.raises(BundleVerificationError, match="signature"):
            verify_audit_bundle(self._bundle(tmp_path), key=b"j" * 32)

    def test_missing_bundle_refused(self, tmp_path: Path) -> None:
        with pytest.raises(BundleVerificationError, match="cannot read"):
            verify_audit_bundle(tmp_path / "absent.json", key=KEY)


class TestOpsCli:
    def _cli(self) -> object:
        from quantmesh.ops.cli import main

        return main

    def test_export_then_verify_round_trip(self, tmp_path: Path) -> None:
        main = self._cli()
        root = tmp_path / "surfaces"
        keys = tmp_path / "keys"
        keys.mkdir()
        (keys / "audit-signing").write_bytes(KEY)
        # Real surfaces through their own APIs first.
        TestAuditExport._journals(self, tmp_path)
        assert (
            main(
                [
                    "export-audit",
                    "--out",
                    str(tmp_path / "bundle.json"),
                    "--key-file",
                    str(keys / "audit-signing"),
                    "--orders-dir",
                    str(root / "orders"),
                    "--mappings-dir",
                    str(root / "mappings"),
                    "--decisions-dir",
                    str(root / "decisions"),
                    "--metrics-dir",
                    str(root / "metrics"),
                ]
            )
            == 0
        )
        assert (
            main(
                [
                    "verify-export",
                    "--bundle",
                    str(tmp_path / "bundle.json"),
                    "--key-file",
                    str(keys / "audit-signing"),
                ]
            )
            == 0
        )

    def test_export_missing_key_file_exits_2(self, tmp_path: Path) -> None:
        assert (
            self._cli()(
                [
                    "export-audit",
                    "--out",
                    str(tmp_path / "bundle.json"),
                    "--key-file",
                    str(tmp_path / "absent-key"),
                ]
            )
            == 2
        )

    def test_verify_after_tamper_exits_1(self, tmp_path: Path) -> None:
        main = self._cli()
        root = tmp_path / "surfaces"
        keys = tmp_path / "keys"
        keys.mkdir()
        (keys / "audit-signing").write_bytes(KEY)
        # Real surfaces with one recorded metric, so the tamper below
        # actually changes the exported content.
        TestAuditExport._journals(self, tmp_path)
        assert (
            main(
                [
                    "export-audit",
                    "--out",
                    str(tmp_path / "bundle.json"),
                    "--key-file",
                    str(keys / "audit-signing"),
                    "--orders-dir",
                    str(root / "orders"),
                    "--mappings-dir",
                    str(root / "mappings"),
                    "--decisions-dir",
                    str(root / "decisions"),
                    "--metrics-dir",
                    str(root / "metrics"),
                ]
            )
            == 0
        )
        bundle = json.loads((tmp_path / "bundle.json").read_text(encoding="utf-8"))
        bundle["content"]["metrics"] = []
        (tmp_path / "bundle.json").write_text(json.dumps(bundle), encoding="utf-8")
        assert (
            main(
                [
                    "verify-export",
                    "--bundle",
                    str(tmp_path / "bundle.json"),
                    "--key-file",
                    str(keys / "audit-signing"),
                ]
            )
            == 1
        )

    def test_record_metric_round_trip(self, tmp_path: Path) -> None:
        main = self._cli()
        assert (
            main(
                [
                    "record-metric",
                    "--name",
                    "equity",
                    "--kind",
                    "gauge",
                    "--unit",
                    "usd",
                    "--value",
                    "1000.5",
                    "--at",
                    "2026-08-08T12:00:00Z",
                    "--root",
                    str(tmp_path / "metrics"),
                ]
            )
            == 0
        )
        assert MetricsStore(tmp_path / "metrics").all()[0].value == 1000.5


class TestRunbooks:
    def test_incident_runbooks_present_and_structured(self) -> None:
        runbooks = Path(__file__).resolve().parents[1] / "docs" / "runbooks"
        expected = [
            "incident-disk-exhaustion.md",
            "incident-journal-corruption.md",
            "incident-reconciliation-mismatch.md",
            "incident-kill-switch-engaged.md",
        ]
        for name in expected:
            path = runbooks / name
            assert path.is_file(), f"runbook {name} is missing"
            text = path.read_text(encoding="utf-8")
            for section in ("## Symptoms", "## Checks", "## Recovery"):
                assert section in text, f"{name} lacks {section}"
            assert len(text.splitlines()) >= 15, f"{name} is suspiciously thin"
