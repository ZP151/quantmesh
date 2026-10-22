"""Synthetic installed trees exercise real lock/RECORD guards, not native admission."""

import base64
import hashlib
import importlib.metadata
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from qm_research_agent import runtime

from tools import research_service_gate as gate

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux parent contract")
ROOT = Path(__file__).parents[3]
SECURE_SHA = "0de42c60394ad96a6a052b1e24a8cb88f14c87f0690b3b1e2467bf857afb7ea6"
HISTORICAL_SHA = "07f4e7ec64805a375e0bdc707d0158fbdb08bd07d02aa569e2d119496b32592a"
EXPECTED = "a" * 40


@pytest.fixture
def parent_tree(tmp_path, monkeypatch, request):
    historical = getattr(request, "param", "secure") == "historical"
    input_lock = ROOT / (
        "tests/fixtures/worker-admission/linux-cp312-legacy.lock"
        if historical
        else "services/research_agent/requirements.linux-cp312.lock"
    )
    raw = input_lock.read_bytes()
    digest = HISTORICAL_SHA if historical else SECURE_SHA
    assert hashlib.sha256(raw).hexdigest() == digest
    pins = gate.read_lock(input_lock)  # Real parser, never replaced by a test pin.
    assert len(pins) == 81
    root, prefix = tmp_path / "source", tmp_path / "prefix"
    lock = root / "services/research_agent/requirements.linux-cp312.lock"
    lock.parent.mkdir(parents=True)
    lock.write_bytes(raw)
    site = prefix / "lib/python3.12/site-packages"
    site.mkdir(parents=True)
    distributions, members = {}, {}
    for name, version in pins.items():
        member = site / (name.replace("-", "_") + ".py")
        member.write_text("VALUE = 1\n")
        info = site / f"{name}-{version}.dist-info"
        info.mkdir()
        meta = info / "METADATA"
        meta.write_text(f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n")
        rows = []
        for path in (member, meta):
            data = path.read_bytes()
            hashed = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip("=")
            rows.append(f"{path.relative_to(site).as_posix()},sha256={hashed},{len(data)}")
        rows.append(f"{info.name}/RECORD,,")
        (info / "RECORD").write_text("\n".join(rows) + "\n")
        distributions[name] = importlib.metadata.Distribution.at(info)
        members[name] = member

    def distribution(name):
        if name not in distributions:
            raise importlib.metadata.PackageNotFoundError(name)
        return distributions[name]

    imports, licensed, sources = [], [], []

    def source(actual_root, expected):
        assert actual_root == root and expected == EXPECTED
        sources.append(actual_root)
        return expected

    def licenses(selected):
        assert selected == pins
        licensed.append(selected)
        return [], []  # License policy is separately tested, not qualified here.

    monkeypatch.setattr(
        runtime, "__file__", str(root / "services/research_agent/src/qm_research_agent/runtime.py")
    )
    monkeypatch.setattr(runtime, "_admit_source", source)
    monkeypatch.setattr(runtime, "_native_filesystem", lambda path: True)
    monkeypatch.setattr(gate, "license_inventory", licenses)
    monkeypatch.setattr(
        runtime,
        "metadata",
        SimpleNamespace(
            distribution=distribution,
            PackageNotFoundError=importlib.metadata.PackageNotFoundError,
        ),
    )
    monkeypatch.setattr(runtime, "importlib", SimpleNamespace(import_module=imports.append))
    monkeypatch.setattr(
        runtime,
        "sys",
        SimpleNamespace(
            prefix=str(prefix),
            base_prefix=str(tmp_path / "base"),
            version_info=(3, 12, 3),
            modules={"fixture_loaded": SimpleNamespace(__file__=str(members["certifi"]))},
            path=[str(site)],
        ),
    )
    return SimpleNamespace(
        prefix=prefix,
        lock=lock,
        pins=pins,
        members=members,
        distributions=distributions,
        imports=imports,
        licensed=licensed,
        sources=sources,
    )


def test_secure_parent_admits_actual_lock_and_recorded_members(parent_tree):
    assert runtime._admit_runtime(EXPECTED) == (EXPECTED, SECURE_SHA)
    assert len(parent_tree.licensed) == 1 and len(parent_tree.sources) == 1
    assert parent_tree.imports == [
        "fastapi",
        "uvicorn",
        "pg8000",
        "qm_research_agent.app",
        "qm_research_agent.store",
    ]


@pytest.mark.parametrize("parent_tree", ["historical"], indirect=True)
def test_coherent_historical_parent_refuses_before_imports(parent_tree):
    with pytest.raises(runtime.RuntimeRejected, match="^runtime_unqualified$"):
        runtime._admit_runtime(EXPECTED)
    assert len(parent_tree.sources) == 1
    assert parent_tree.licensed == [] and parent_tree.imports == []


@pytest.mark.parametrize("name", ["certifi", "anyio"])
def test_secure_parent_rejects_stale_recorded_member(parent_tree, name):
    assert runtime._admit_runtime(EXPECTED) == (EXPECTED, SECURE_SHA)
    parent_tree.imports.clear()
    parent_tree.members[name].write_text("VALUE = 2\n")
    with pytest.raises(runtime.RuntimeRejected, match="^runtime_unqualified$"):
        runtime._admit_runtime(EXPECTED)
    assert parent_tree.imports == []


def test_secure_parent_rejects_old_certifi_metadata(parent_tree):
    assert runtime._admit_runtime(EXPECTED) == (EXPECTED, SECURE_SHA)
    parent_tree.imports.clear()
    info = Path(parent_tree.distributions["certifi"]._path)
    metadata = info / "METADATA"
    metadata.write_text(metadata.read_text().replace("2026.10.19", "2026.7.22"))
    with pytest.raises(runtime.RuntimeRejected, match="^runtime_unqualified$"):
        runtime._admit_runtime(EXPECTED)
    assert parent_tree.imports == []
