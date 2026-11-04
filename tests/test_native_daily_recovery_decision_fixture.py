"""Actual v1 decision serializer over an explicitly authored archive lookup seed.

Admission/report are the existing frontend engineering fixture envelopes, not
accepted real inputs. No authority reader, calculation, SDK or private originals.
"""

import json
from pathlib import Path

from quantmesh.research import native_daily_real as daily

FIXTURE = (
    Path(__file__).parents[1]
    / "frontend/src/screens/fixtures/native-daily-recovery-decision-v1.json"
)
REASON = "Authored recovery decision; engineering evidence only."


def produce_decision(root, monkeypatch, packet):
    service = daily.NativeDailyService(root)
    public = packet["job"]
    try:
        request = daily.NativeRequest.model_validate(public["request"])
        assert (
            daily.digest(daily.canonical(request.model_dump(mode="json")))
            == public["request_digest"]
        )
        for kind in ("admission", "report"):
            raw = packet["artifacts"][kind].encode("utf-8")
            reference = service.objects.put_bytes("application/json", raw)
            assert reference.model_dump() == public[kind]
            value = json.loads(raw)
            assert (value["job_id"], value["request_digest"]) == (
                public["job_id"],
                public["request_digest"],
            )
        seeded = daily.NativeJob(
            **{
                k: v
                for k, v in public.items()
                if k in daily.NativeJob.model_fields and k != "decision"
            },
            consumed_grant=request.grant_ref.digest,
        )
        records = [seeded]
        # Lookup seam only: this seed is NOT passed off as admitted real input.
        monkeypatch.setattr(service, "_records", lambda: list(records))
        write = service._store.write

        def capture(values):
            values = list(values)
            write(values)
            records[:] = values

        monkeypatch.setattr(service._store, "write", capture)
        monkeypatch.setattr(daily, "_now", lambda: "2026-11-05T00:00:00Z")
        decision = daily.NativeDecisionRequest(
            request_digest=seeded.request_digest,
            admission_digest=seeded.admission.digest,
            report_digest=seeded.report.digest,
            disposition="watch",
            reason=REASON,
        )
        saved, created = service.decide(seeded.job_id, decision, packet["decision_key"])
        assert created
        reference = daily.ObjectRef.model_validate(saved["decision"])
        raw = service.objects.get_bytes(reference)
        repeated, created = service.decide(seeded.job_id, decision, packet["decision_key"])
        assert not created and repeated == saved
        assert service.objects.get_bytes(reference) == raw
        value = json.loads(raw)
        assert value["schema_id"] == "qm.native-daily.research-decision.v1"
        assert "use_basis" not in value
        assert (value["admission_digest"], value["report_digest"]) == (
            seeded.admission.digest,
            seeded.report.digest,
        )
        return raw, saved
    finally:
        service.close()


def test_recovery_decision_consumer_fixture_is_actual_backend_v1_bytes(tmp_path, monkeypatch):
    packet = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw, saved = produce_decision(tmp_path, monkeypatch, packet)
    assert raw == packet["artifacts"]["decision"].encode("utf-8")
    assert saved["decision"] == packet["job"]["decision"]
