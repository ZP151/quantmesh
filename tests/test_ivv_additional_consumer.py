"""Authored identity checks only; no actual capture, registration or trial."""

import pytest

from quantmesh.research import ivv_admission as gate
from quantmesh.research import native_daily_real as daily

AUTH = "595c2987fda4cc0275d785b91137b6e61824800888500e2f7c5a78ea7b5f5832"
DESCRIPTOR = "76944da09e615b0fec9c60a6ed7ea78d7fa364543684b4d4e5832618860dfa12"


def ref(value):
    return daily.ObjectRef(digest=value, byte_length=1, media_type="application/json")


def proofs():
    return gate.TrustedIVVProofs(
        scope_ref=ref(DESCRIPTOR),
        effect_ref=ref(AUTH),
        execution_ref=ref(AUTH),
        go_ref=ref("a" * 64),
        acceptance_ref=ref("b" * 64),
        windows_policy_ref=ref("c" * 64),
        expected_go_sha256="a" * 64,
        expected_acceptance_sha256="b" * 64,
        capture_policy_ref=ref("d" * 64),
        authorization_ref=ref(AUTH),
        expected_policy_sha256="d" * 64,
        expected_authorization_sha256=AUTH,
    )


@pytest.mark.parametrize("kind", ["root-go", "capture", "registration", "input-acceptance"])
def test_new_authority_is_explicit_family_not_legacy_dev(kind):
    assert gate._schema(proofs(), kind) == "qm.ivv." + kind + ".dev-additional-task.v1"


@pytest.mark.parametrize("field", ["scope_ref", "effect_ref", "execution_ref", "authorization_ref"])
def test_additional_family_rejects_cross_task_proof_slots(field):
    wrong = proofs().model_copy(update={field: ref("e" * 64)})
    with pytest.raises(ValueError, match="ivv_proof"):
        gate._schema(wrong, "root-go")


RESEARCH_SCOPE = "75bdbea142ca73c3c7964fd2fbcb7d2ded82aded73788c903a0d57d9528ebd0a"
STUDY = (
    "C:/Users/15492/.codex-clean/worktrees/latest-bootstrap/QuantMesh/output/"
    "ivv-additional-study-20261103-01"
)


def test_new_startup_routes_only_new_fixed_scope_and_root(tmp_path, monkeypatch):
    import runpy
    from pathlib import Path

    namespace = runpy.run_path(
        str(Path(__file__).parents[1] / "tools/research/open_ivv_workstation.py")
    )
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    calls = []
    sentinel = object()
    monkeypatch.setattr(
        gate, "bind_reviewed_ivv_input", lambda *a, **kw: calls.append(kw) or sentinel
    )
    monkeypatch.setattr(daily, "NativeDailyService", lambda root, registered: (root, registered))
    value = {
        "schema_id": "qm.ivv.startup.dev-additional-task.v1",
        "scope_id": RESEARCH_SCOPE,
        "inputs_root": str(inputs),
        "study_root": STUDY,
        "input_set_ref": ref("f" * 64).model_dump(),
        "proofs": proofs().model_dump(mode="json"),
    }
    path = tmp_path / "config.json"

    def call(config):
        raw = daily.canonical(config)
        path.write_bytes(raw)
        return namespace["service_from_config"](path, daily.digest(raw))

    assert call(value) == (Path(STUDY), (sentinel,))
    assert len(calls) == 1 and calls[0]["proofs"] == proofs()
    for changed in (
        {"schema_id": "qm.ivv.startup.v1"},
        {"scope_id": gate.SCOPE_ID},
        {"study_root": str(tmp_path / "alias")},
        {
            "proofs": proofs()
            .model_copy(update={"expected_authorization_sha256": gate.TRUSTED_AUTH})
            .model_dump(mode="json")
        },
    ):
        with pytest.raises(ValueError, match="ivv_"):
            call({**value, **changed})
    assert len(calls) == 1
    assert not (tmp_path / "alias").exists()


@pytest.mark.parametrize("mode", ["strict", "legacy-dev", "legacy-trusted"])
def test_legacy_family_dispatch_is_preserved(mode):
    value = proofs()
    if mode == "strict":
        value = value.model_copy(
            update={
                k: None
                for k in (
                    "capture_policy_ref",
                    "authorization_ref",
                    "expected_policy_sha256",
                    "expected_authorization_sha256",
                )
            }
        )
        suffix = ".v1"
    else:
        auth = gate.TRUSTED_AUTH if mode == "legacy-trusted" else "e" * 64
        value = value.model_copy(
            update={"authorization_ref": ref(auth), "expected_authorization_sha256": auth}
        )
        suffix = gate.TRUSTED_SUFFIX if mode == "legacy-trusted" else ".dev-diagnostic.v1"
    assert gate._schema(value, "capture") == "qm.ivv.capture" + suffix
