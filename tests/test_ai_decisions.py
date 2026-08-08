"""Phase D decision-log tests (M8, issue #48).

Content addressing (any difference is a new id; identical replay is a
refused duplicate), `for_stage` digest building from the wire values,
refusals on tamper and shape, and the ADR-0006 ledger discipline
(atomic appends, fail-closed reads with line attribution, duplicate-id
refusal, root-not-dir).
"""

import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from quantmesh.ai.decisions import DECISIONS_FILE, DecisionLog, DecisionRecord, ModelMeta
from quantmesh.ai.retrieval import Citation
from quantmesh.ai.roles import AnalystReport, CriticVerdict, PortfolioReview, RiskReview

MODEL = ModelMeta(name="fixture-model", version="v1.0", endpoint_kind="scripted")
PROMPT = "redacted analyst context"
SCHEMA_ID = "analyst-report-v1"


def _record(**overrides) -> DecisionRecord:
    fields = {
        "run_id": "a" * 16,
        "role": "analyst",
        "model": MODEL,
        "prompt": PROMPT,
        "schema_id": SCHEMA_ID,
        "output": AnalystReport(claims=[]),
    }
    fields.update(overrides)
    return DecisionRecord.for_stage(**fields)


def _write_log(root, lines: list[str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / DECISIONS_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")


class TestModelMeta:
    def test_extra_fields_refused(self) -> None:
        with pytest.raises(ValidationError):
            ModelMeta(name="x", version="1", endpoint_kind="scripted", api_key="secret")

    def test_empty_name_refused(self) -> None:
        with pytest.raises(ValidationError):
            ModelMeta(name="", version="1", endpoint_kind="scripted")

    def test_bad_endpoint_kind_refused(self) -> None:
        with pytest.raises(ValidationError):
            ModelMeta(name="x", version="1", endpoint_kind="mainnet")


class TestForStage:
    def test_digests_match_prompt_and_output(self) -> None:
        record = _record()
        expected_prompt = hashlib.sha256(PROMPT.encode("utf-8")).hexdigest()
        expected_output = hashlib.sha256(
            AnalystReport(claims=[]).model_dump_json().encode("utf-8")
        ).hexdigest()
        assert record.prompt_digest == expected_prompt
        assert record.output_digest == expected_output

    def test_critic_verdict_extracted(self) -> None:
        record = DecisionRecord.for_stage(
            run_id="a" * 16,
            role="critic",
            model=MODEL,
            prompt="redacted critic context",
            schema_id="critic-gate-v1",
            output=CriticVerdict(verdict="pass"),
        )
        assert record.verdict == "pass"

    def test_risk_and_portfolio_posture_extracted(self) -> None:
        risk = DecisionRecord.for_stage(
            run_id="a" * 16,
            role="risk",
            model=MODEL,
            prompt="redacted risk context",
            schema_id="risk-review-v1",
            output=RiskReview(posture="aligned", referenced_verdicts=["v-1"]),
        )
        assert risk.verdict == "aligned"
        portfolio = DecisionRecord.for_stage(
            run_id="a" * 16,
            role="portfolio",
            model=MODEL,
            prompt="redacted portfolio context",
            schema_id="portfolio-review-v1",
            output=PortfolioReview(posture="within_constraints", referenced_inputs=["i-1"]),
        )
        assert portfolio.verdict == "within_constraints"

    def test_unknown_role_refused(self) -> None:
        with pytest.raises(ValueError, match="unknown research role"):
            DecisionRecord.for_stage(
                run_id="a" * 16,
                role="trader",
                model=MODEL,
                prompt=PROMPT,
                schema_id=SCHEMA_ID,
                output=AnalystReport(claims=[]),
            )

    def test_refusal_recorded(self) -> None:
        record = _record(refusal="refused: output shape not recognized")
        assert record.refusal == "refused: output shape not recognized"

    def test_citations_recorded(self) -> None:
        record = _record(
            citations=[
                Citation(source_kind="document", source_id="d-1"),
                Citation(source_kind="experiment", source_id="e-1"),
            ]
        )
        assert [citation.source_id for citation in record.citations] == ["d-1", "e-1"]


class TestContentAddressing:
    def test_identity_ignores_recorded_at(self) -> None:
        first = _record(recorded_at=datetime(2026, 8, 1, 12, 0, tzinfo=UTC))
        second = _record(recorded_at=datetime(2026, 8, 2, 12, 0, tzinfo=UTC))
        assert first.decision_id == second.decision_id
        assert first.recorded_at != second.recorded_at

    def test_any_content_difference_changes_id(self) -> None:
        base = _record()
        assert _record(prompt="different prompt").decision_id != base.decision_id
        assert (
            _record(output=AnalystReport(claims=[]), schema_id="other-schema").decision_id
            != base.decision_id
        )
        assert (
            _record(refusal="refused").decision_id != base.decision_id
        )
        assert _record(role="critic").decision_id != base.decision_id

    def test_identical_replay_is_duplicate(self, tmp_path) -> None:
        log = DecisionLog(root=tmp_path / "decisions")
        first = _record()
        log.record(first)
        with pytest.raises(ValueError, match="already recorded"):
            log.record(_record())
        assert len(log.all()) == 1

    def test_ids_are_16_hex(self) -> None:
        import re

        assert re.fullmatch(r"[0-9a-f]{16}", _record().decision_id)


class TestRecordValidation:
    def test_tampered_decision_id_refused(self) -> None:
        record = _record()
        tampered = record.model_copy(
            update={"decision_id": "f" * 16, "recorded_at": record.recorded_at}
        )
        with pytest.raises(ValidationError, match="does not match"):
            DecisionRecord.model_validate(tampered.model_dump())

    def test_tampered_output_digest_refused(self) -> None:
        record = _record()
        tampered = record.model_copy(
            update={"output_digest": "0" * 64, "recorded_at": record.recorded_at}
        )
        with pytest.raises(ValidationError, match="does not match"):
            DecisionRecord.model_validate(tampered.model_dump())

    def test_extra_fields_refused(self) -> None:
        with pytest.raises(ValidationError):
            DecisionRecord.model_validate(
                {**_record().model_dump(), "order_id": "o-1"}
            )

    def test_shape_refusals(self) -> None:
        record = _record().model_dump()
        with pytest.raises(ValidationError):
            DecisionRecord.model_validate({**record, "run_id": "x" * 16})
        with pytest.raises(ValidationError):
            DecisionRecord.model_validate({**record, "role": "trader"})
        with pytest.raises(ValidationError):
            DecisionRecord.model_validate({**record, "verdict": ""})
        with pytest.raises(ValidationError):
            DecisionRecord.model_validate({**record, "refusal": ""})
        with pytest.raises(ValidationError):
            DecisionRecord.model_validate(
                {**record, "recorded_at": datetime(2026, 8, 1, 12, 0).isoformat()}
            )

    def test_recorded_at_normalized_to_utc(self) -> None:
        shifted = datetime(2026, 8, 1, 12, 0, tzinfo=UTC) + timedelta(hours=9)
        record = _record(recorded_at=shifted)
        assert record.recorded_at.tzinfo is not None
        assert record.recorded_at.utcoffset() == timedelta(0)


class TestDecisionLog:
    def test_round_trip_and_get(self, tmp_path) -> None:
        log = DecisionLog(root=tmp_path / "decisions")
        record = _record()
        log.record(record)
        assert log.get(record.decision_id) == record
        assert log.all() == [record]

    def test_new_log_instance_sees_record(self, tmp_path) -> None:
        root = tmp_path / "decisions"
        DecisionLog(root=root).record(_record())
        assert len(DecisionLog(root=root).all()) == 1

    def test_get_missing_refused(self, tmp_path) -> None:
        log = DecisionLog(root=tmp_path / "decisions")
        with pytest.raises(ValueError, match="no decision recorded"):
            log.get("a" * 16)

    def test_missing_root_reads_empty(self, tmp_path) -> None:
        assert DecisionLog(root=tmp_path / "missing").all() == []

    def test_corrupt_line_attributed(self, tmp_path) -> None:
        root = tmp_path / "decisions"
        _write_log(root, ["this is not json"])
        with pytest.raises(ValueError, match="line 1 is invalid"):
            DecisionLog(root=root).all()

    def test_duplicate_ids_across_lines_attributed(self, tmp_path) -> None:
        root = tmp_path / "decisions"
        first = _record()
        replay = _record()  # same content, different recorded_at: same id
        assert first.decision_id == replay.decision_id
        _write_log(root, [first.model_dump_json(), replay.model_dump_json()])
        with pytest.raises(ValueError, match="share a decision id"):
            DecisionLog(root=root).all()

    def test_root_not_directory_refused(self, tmp_path) -> None:
        path = tmp_path / "decisions"
        path.write_text("not a dir", encoding="utf-8")
        with pytest.raises(ValueError, match="not a directory"):
            DecisionLog(root=path).all()

    def test_unreadable_file_refused(self, tmp_path) -> None:
        root = tmp_path / "decisions"
        root.mkdir()
        path = root / DECISIONS_FILE
        path.write_bytes(b"\xff\xfe\x00garbage")
        with pytest.raises(ValueError, match="unreadable"):
            DecisionLog(root=root).all()

    def test_appended_records_preserve_order(self, tmp_path) -> None:
        log = DecisionLog(root=tmp_path / "decisions")
        first = _record(prompt="first prompt")
        second = _record(prompt="second prompt")
        log.record(first)
        log.record(second)
        assert [entry.decision_id for entry in log.all()] == [
            first.decision_id,
            second.decision_id,
        ]

    def test_file_is_jsonl(self, tmp_path) -> None:
        root = tmp_path / "decisions"
        log = DecisionLog(root=root)
        record = _record()
        log.record(record)
        raw = (root / DECISIONS_FILE).read_text(encoding="utf-8").strip()
        assert json.loads(raw)["decision_id"] == record.decision_id
