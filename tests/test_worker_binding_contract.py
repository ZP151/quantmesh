import hashlib
import json

import pytest

from quantmesh.research.worker_build import ParentBindingContract, parse_parent_binding


def _binding() -> dict[str, object]:
    return {
        "schema": 1,
        "engine_id": "engine-0123456789abcdef",
        "image_id": "sha256:" + "a" * 64,
        "image_config_sha256": "b" * 64,
        "container_id": "c" * 64,
        "owner_nonce": "d" * 32,
        "manifest_sha256": "e" * 64,
        "inventory_sha256": "f" * 64,
        "dependency_lock_sha256": "0" * 64,
        "python_executable_sha256": "1" * 64,
        "entry_sha256": "2" * 64,
        "observer_sha256": "3" * 64,
        "expected_prefix": "/usr/local",
        "python_version": "3.12.15",
        "kernel_profile_sha256": "4" * 64,
    }


def test_parent_binding_contract_parses_exact_canonical_bytes_without_granting_qualification():
    raw = json.dumps(_binding(), sort_keys=True, separators=(",", ":")).encode()

    parsed = parse_parent_binding(raw, expected_sha256=hashlib.sha256(raw).hexdigest())

    assert parsed.engine_id == "engine-0123456789abcdef"
    assert parsed.container_id == "c" * 64
    assert parsed.expected_prefix == "/usr/local"
    assert not hasattr(parsed, "qualified")
    assert not hasattr(parsed, "admitted")


def test_parent_binding_encoder_emits_exact_validated_bytes_and_digest():
    from quantmesh.research.worker_build import WorkerBuildRejected, encode_parent_binding

    contract = ParentBindingContract(**_binding())

    raw, digest = encode_parent_binding(contract)

    assert raw == json.dumps(_binding(), sort_keys=True, separators=(",", ":")).encode()
    assert digest == hashlib.sha256(raw).hexdigest()
    assert parse_parent_binding(raw, expected_sha256=digest) == contract

    with pytest.raises(WorkerBuildRejected, match="^worker binding rejected$"):
        encode_parent_binding(object())

    object.__setattr__(contract, "owner_nonce", "not-a-nonce")
    with pytest.raises(WorkerBuildRejected, match="^worker binding rejected$"):
        encode_parent_binding(contract)


def _parse(raw: bytes):
    return parse_parent_binding(raw, expected_sha256=hashlib.sha256(raw).hexdigest())


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.pop("schema"),
        lambda value: value.update(extra="field"),
        lambda value: value.update(schema=True),
        lambda value: value.update(image_id="sha256:" + "A" * 64),
        lambda value: value.update(container_id="../" + "c" * 61),
        lambda value: value.update(owner_nonce="d" * 31),
        lambda value: value.update(engine_id="bad\nengine"),
        lambda value: value.update(expected_prefix="/tmp/python"),
        lambda value: value.update(python_version="3.13.0"),
        lambda value: value.update(kernel_profile_sha256="not-a-digest"),
    ],
)
def test_parent_binding_contract_refuses_missing_extra_and_malformed_fields(mutate):
    from quantmesh.research.worker_build import WorkerBuildRejected

    value = _binding()
    mutate(value)
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()

    with pytest.raises(WorkerBuildRejected, match="^worker binding rejected$"):
        _parse(raw)


@pytest.mark.parametrize(
    "raw_factory",
    [
        lambda raw: raw.replace(b'"schema":1}', b'"schema":1,"schema":1}'),
        lambda raw: b" " + raw,
        lambda raw: raw + b" " * (16 * 1024),
    ],
)
def test_parent_binding_contract_refuses_duplicate_noncanonical_and_oversized_bytes(raw_factory):
    from quantmesh.research.worker_build import WorkerBuildRejected

    raw = json.dumps(_binding(), sort_keys=True, separators=(",", ":")).encode()
    malformed = raw_factory(raw)

    with pytest.raises(WorkerBuildRejected, match="^worker binding rejected$"):
        _parse(malformed)


def test_parent_binding_contract_refuses_digest_mismatch():
    from quantmesh.research.worker_build import WorkerBuildRejected

    raw = json.dumps(_binding(), sort_keys=True, separators=(",", ":")).encode()

    with pytest.raises(WorkerBuildRejected, match="^worker binding rejected$"):
        parse_parent_binding(raw, expected_sha256="0" * 64)
