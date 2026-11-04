"""Scoped publication barriers and failure ordering; no power-loss claim."""

import json
from pathlib import Path

import pytest
from pydantic import BaseModel
from test_ivv_transaction_recovery_product import transaction_registration

from quantmesh import _fs
from quantmesh.data.objects import ObjectStore
from quantmesh.persistence.jsonl import JsonlStore
from quantmesh.research import native_daily_real as daily


class Row(BaseModel):
    key: str


def ledger(root, **kwargs):
    return JsonlStore(
        root,
        filename="jobs.jsonl",
        model=Row,
        label="test",
        id_label="row",
        key=lambda r: r.key,
        **kwargs,
    )


def test_real_filesystem_durable_new_ancestors_objects_and_jsonl(tmp_path):
    root = tmp_path / "new" / "ancestor" / "study"
    objects = ObjectStore(root, durable=True)
    ref = objects.put_bytes("application/json", b'{"authored":true}')
    assert objects.get_bytes(ref) == b'{"authored":true}'
    objects.confirm_durable(ref)
    records = ledger(root, durable=True)
    records.write([Row(key="intent")])
    assert ledger(root).read() == [Row(key="intent")]
    records.write([Row(key="committed")])
    assert ledger(root).read() == [Row(key="committed")]
    assert not list(root.rglob("*.tmp"))


def test_jsonl_payload_barrier_precedes_namespace_publication_and_failure_is_sticky(
    tmp_path, monkeypatch
):
    from quantmesh.persistence import jsonl

    events = []
    fsync = jsonl.os.fsync
    replace = jsonl.atomic_replace

    def sync(fd):
        events.append("file-fsync")
        return fsync(fd)

    def publish(source, target, **kw):
        assert kw == {"durable": True}
        assert "file-fsync" in events
        events.append("namespace")
        raise OSError("authored publication uncertainty")

    monkeypatch.setattr(jsonl.os, "fsync", sync)
    monkeypatch.setattr(jsonl, "atomic_replace", publish)
    store = ledger(tmp_path, durable=True)
    with pytest.raises(OSError):
        store.write([Row(key="intent")])
    assert events[-1] == "namespace"
    monkeypatch.setattr(jsonl, "atomic_replace", replace)
    with pytest.raises(OSError):
        store.write([Row(key="must-not-continue")])
    assert not store.path.exists()


def test_object_barrier_failure_cannot_return_reference_or_continue(tmp_path, monkeypatch):
    objects = ObjectStore(tmp_path / "objects", durable=True)

    def uncertain(*a, **k):
        raise OSError("authored object namespace failure")

    monkeypatch.setattr(_fs, "atomic_replace", uncertain)
    with pytest.raises(OSError):
        objects.put_bytes("application/json", b"authored")
    assert objects.durability_uncertain
    with pytest.raises(OSError):
        objects.put_bytes("application/json", b"successor")


def test_intent_publication_failure_prevents_compute_and_cold_recheck_can_recover(
    tmp_path, monkeypatch
):
    store, root, key, registration = transaction_registration(tmp_path)
    service = daily.NativeDailyService(root, registered=(registration,))
    calculated = []
    monkeypatch.setattr(service, "_compute", lambda *a: calculated.append(True))
    replace = _fs.atomic_replace

    def uncertain(source, target, **kw):
        if Path(target).name == "jobs.jsonl":
            replace(source, target, **kw)
            raise OSError("authored visible-but-uncertain intent")
        return replace(source, target, **kw)

    monkeypatch.setattr(_fs, "atomic_replace", uncertain)
    # JsonlStore's named import must still consume the actual barrier primitive.
    from quantmesh.persistence import jsonl

    monkeypatch.setattr(jsonl, "atomic_replace", uncertain)
    try:
        with pytest.raises((OSError, daily.NativeError)):
            service.submit(registration.request, key)
        assert calculated == []
        with pytest.raises((OSError, daily.NativeError)):
            service.submit(registration.request, key)
        assert calculated == []
    finally:
        service.close()
    monkeypatch.setattr(_fs, "atomic_replace", replace)
    monkeypatch.setattr(jsonl, "atomic_replace", replace)
    cold = daily.NativeDailyService(root, registered=(registration,))
    try:
        assert cold.read(key)["state"] == "interrupted"
        assert len(cold._records()[0].transaction.attempts) == 1
    finally:
        cold.close()


@pytest.mark.parametrize("phase", ["report-object", "prepared", "committed"])
def test_uncertain_result_publication_blocks_success_and_cold_rechecks_full_dependencies(
    tmp_path, monkeypatch, phase
):
    store, root, key, registration = transaction_registration(tmp_path)
    service = daily.NativeDailyService(root, registered=(registration,))
    original_compute = service._compute
    computed = []
    seen = []
    report_digest = []

    def compute(*args):
        assert "intent" in seen
        computed.append(True)
        raw = original_compute(*args)
        report_digest.append(daily.digest(raw))
        return raw

    monkeypatch.setattr(service, "_compute", compute)
    replace = _fs.atomic_replace

    def publish(source, target, **kw):
        stage = None
        if Path(target).name == "jobs.jsonl":
            value = json.loads(Path(source).read_text(encoding="utf-8").strip())
            stage = (
                "committed"
                if value["state"] == "succeeded"
                else "prepared"
                if value["transaction"]["prepared_report"]
                else "intent"
            )
            if stage == "prepared":
                assert value["transaction"]["prepared_report"]["digest"] in seen
        replace(source, target, **kw)
        seen.append(stage or Path(target).name)
        if stage == phase or (phase == "report-object" and Path(target).name in report_digest):
            raise OSError("authored result publication uncertainty")

    monkeypatch.setattr(_fs, "atomic_replace", publish)
    from quantmesh.persistence import jsonl

    monkeypatch.setattr(jsonl, "atomic_replace", publish)
    try:
        with pytest.raises((OSError, daily.NativeError)):
            service.submit(registration.request, key)
        assert computed == [True]
        with pytest.raises((OSError, daily.NativeError)):
            service.submit(registration.request, key)
        assert computed == [True]
        if phase == "report-object":
            assert "prepared" not in seen
        if phase == "prepared":
            assert "committed" not in seen
    finally:
        service.close()
    monkeypatch.setattr(_fs, "atomic_replace", replace)
    monkeypatch.setattr(jsonl, "atomic_replace", replace)
    from quantmesh.research import native_daily_candidate as native

    monkeypatch.setattr(
        native, "_calculate_matrix", lambda *a, **k: pytest.fail("cold barrier cannot calculate")
    )
    cold = daily.NativeDailyService(root)
    try:
        assert cold.read(key)["state"] == (
            "interrupted" if phase == "report-object" else "succeeded"
        )
        assert len(cold._records()[0].transaction.attempts) == 1
    finally:
        cold.close()
