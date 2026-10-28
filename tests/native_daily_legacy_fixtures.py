"""Explicit constructed archive shapes for retired-profile reader/proof tests.

Never executes submit/calculate or bypasses a production gate. These v2/v3 records
are controlled historical-shape fixtures, not genuine historical publications.
The separate genuine v1 byte bag remains unchanged in test_spy_sample_evidence.
"""

from datetime import timedelta

from quantmesh.data.objects import ObjectStore
from quantmesh.research import spy_replay as replay


def seed_archive(service, value, key, *, state="succeeded", calculation=None):
    protocol, frame, _ = value.verified()
    evidence = value.evidence(protocol, frame)
    if value.policy_exception is not None:
        source = ObjectStore(value.source_root)
        for name, ref in value.proof_refs.items():
            limit = (
                replay.MAX_OBJECT
                if name in {"protocol.json", "freeze.json"}
                else replay.once.MAX_PROOF
            )
            raw = replay.once.read_object(source, ref, limit=limit)
            assert service.objects.put_bytes(ref.media_type, raw) == ref
    request = replay.ReplayRequest(
        snapshot_digest=value.snapshot_digest, protocol_digest=replay.digest(value.protocol_bytes)
    )
    at = value.frozen_at_utc + timedelta(minutes=1)
    report = None
    implementation = replay.digest(b"CONSTRUCTED ARCHIVED SYNTHETIC PROFILE; NOT EXECUTED")
    if state == "succeeded":
        body = dict(
            schema_version=3 if value.policy_exception is not None else 2,
            job_id=str(key),
            request_digest=replay.digest(replay.canonical(request.model_dump())),
            **request.model_dump(),
            implementation_digest=implementation,
            evidence_kind=value.evidence_kind,
            engine=dict(
                original_sha256=replay.engine.ORIGINAL_ENGINE_SHA256,
                packaged_sha256=replay.engine.LEGACY_PACKAGED_SHA256,
            ),
            runtime={"basis": "constructed_archive_not_execution"},
            window=protocol["window"],
            costs=protocol["costs"],
            sample_evidence=evidence.model_dump(mode="json"),
            calculation=calculation
            if calculation is not None
            else {
                "constructed_archive_only": True,
                "scenarios": {
                    "base5": {
                        "strategy": {
                            "metrics": {
                                "terminal_equity": 118491.8415,
                                "total_return": 0.184918415,
                            }
                        }
                    }
                },
            },
            financial_qualification="INSUFFICIENT",
            paper_allowed=False,
            limitations=value.summary().limitations,
        )
        report = service.objects.put_bytes("application/json", replay.canonical(body))
    terminal = state != "running"
    job = replay._StoredJob(
        job_id=str(key),
        request=request,
        request_digest=replay.digest(replay.canonical(request.model_dump())),
        state=state,
        created_at=at,
        updated_at=at,
        completed_at=at if terminal else None,
        report=report,
        error_code="computation_failed" if state == "failed" else None,
        implementation_digest=implementation,
    )
    service._store.write([*service._records(), job])
    return service.get(key)
