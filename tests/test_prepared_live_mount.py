"""Static mount facts are modeled; files, reservations and tiny DuckDB are real.

No test here mounts a filesystem or issues a production physical proof.
"""

import copy
import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest

from quantmesh.live import buffer as buffer_module
from quantmesh.live.buffer import HotCacheBudget, LiveBuffer
from tests.test_market_history_hot_cache import budget_spec, candles


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    import importlib

    root = tmp_path / "hot"
    live = root / "live"
    live.mkdir(parents=True)
    (live / "lost+found").mkdir()
    spec = budget_spec(root, operations=4)
    core_sha = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()

    def metadata(path, dev, mode, uid=0, gid=42):
        return {
            "dev": dev,
            "ino": path.stat().st_ino,
            "uid": uid,
            "gid": gid,
            "mode": mode,
            "kind": "directory",
        }

    view = {
        "root": metadata(root, 1, 0o1770),
        "live": metadata(live, 7, 0o1770),
        "lost_found": {**metadata(live / "lost+found", 7, 0o700, gid=0), "nlink": 2},
        "app_uid": 999,
        "app_gid": 42,
        "boot_id": "fixture-boot",
        "unit_cgroup": "/system.slice/fixture-hot.service",
        "deployment": {"fixture": "modeled deployment only"},
        "loop": {
            "major": 7,
            "minor": 1,
            "offset": 0,
            "sizelimit": 16777216,
            "capacity": 16777216,
            "backing_path": "/root/fixture-hot.ext4",
        },
        "filesystem": {"frsize": 4096, "blocks": 4096, "fsid": 123},
        "mount": {
            "filesystem": "ext4",
            "root": "/",
            "point": str(live),
            "options": ["rw", "nodev", "nosuid", "noexec"],
        },
        "namespace": [10, 20],
        "root_mount_id": 11,
        "live_mount_id": 12,
    }
    facts = {
        k: copy.deepcopy(v)
        for k, v in view.items()
        if k not in {"namespace", "root_mount_id", "live_mount_id"}
    }
    record = {
        "schema_version": 1,
        "core_budget_sha256": core_sha,
        "deployment_receipt_sha256": "d" * 64,
        "expires_at_utc": (datetime.now(UTC) + timedelta(minutes=10)).isoformat(),
        "unit_restart": "no",
        "facts": facts,
        "filesystem_uuid": "12345678-1234-1234-1234-123456789abc",
        "backing": {
            "dev": 1,
            "ino": 876,
            "uid": 0,
            "mode": 0o600,
            "nlink": 1,
            "size": 16777216,
            "allocated": 16777216,
            "path": "/root/fixture-hot.ext4",
        },
        "underlying": {
            "dev": 1,
            "ino": 987,
            "uid": 0,
            "gid": 0,
            "mode": 0o555,
            "kind": "directory",
            "nlink": 2,
        },
        "lost_found_entries": [],
    }
    receipt = tmp_path / "receipt.json"

    def save():
        raw = json.dumps(record, sort_keys=True).encode()
        receipt.write_bytes(raw)
        spec["prepared_live_receipt_sha256"] = hashlib.sha256(raw).hexdigest()

    save()
    # Import only when the feature exists, so the initial RED is the real
    # merged budget/initialization refusal, not a missing helper import.
    try:
        module = importlib.import_module("quantmesh.live.prepared_mount")
    except ModuleNotFoundError:
        module = None
    if module is not None:
        monkeypatch.setattr(module, "_read_receipt", lambda path: receipt.read_bytes())

        def observe(path):
            observed = copy.deepcopy(view)
            observed["root_names"] = sorted(p.name for p in root.iterdir())
            observed["live_names"] = sorted(p.name for p in live.iterdir())
            return observed

        monkeypatch.setattr(module, "_observe", observe)
    monkeypatch.setattr(HotCacheBudget, "_require_directory_sync", lambda self: None)
    return root, spec, view, record, save, receipt


def test_prepared_mount_first_start_writes_only_real_admission(prepared):
    root, spec, *_ = prepared
    budget = HotCacheBudget(root, spec)
    assert sorted(p.name for p in root.iterdir()) == ["live"]
    with LiveBuffer.open_bounded_hot(root, budget) as hot:
        assert not hot.read_only
        assert len(list(root.glob("budget-intent-*.json"))) == 1
        assert (root / "budget-spec.json").exists()
        assert (root / "budget-session-000001.json").exists()
        hot.append(candles()[0])
    assert (root / "budget-closed-000001.json").exists()
    with LiveBuffer.open_bounded_hot(root, HotCacheBudget(root, spec)) as hot:
        assert not hot.read_only and len(hot.replay()) == 1
    assert len(list(root.glob("budget-intent-*.json"))) == 3


def test_legacy_header_bytes_and_existing_directory_refusal_are_unchanged(tmp_path):
    root = tmp_path / "legacy"
    spec = budget_spec(root)
    budget = HotCacheBudget(root, spec)
    assert budget.header == json.dumps(spec, sort_keys=True).encode()
    (root / "live").mkdir()
    with pytest.raises(buffer_module.LiveCapacityExceeded):
        budget.start_session()
    assert not list(root.glob("budget-intent-*.json"))
    foreign = tmp_path / "foreign"
    (foreign / "live").mkdir(parents=True)
    with pytest.raises(ValueError):
        HotCacheBudget(foreign, {**spec, "root": str(foreign)})


@pytest.mark.parametrize(
    "fault",
    [
        "device",
        "inode",
        "namespace",
        "mount_id",
        "ordinary_dir",
        "loop_capacity",
        "loop_path",
        "root_owner",
        "lostfound_mode",
        "root_mode",
        "deployment",
        "cgroup",
        "boot",
    ],
)
def test_changed_actual_mount_or_deployment_is_refused(prepared, fault):
    root, spec, view, *_ = prepared
    budget = HotCacheBudget(root, spec)
    if fault == "device":
        view["live"]["dev"] += 1
    elif fault == "inode":
        view["live"]["ino"] += 1
    elif fault == "namespace":
        view["namespace"][1] += 1
    elif fault == "mount_id":
        view["live_mount_id"] += 1
    elif fault == "ordinary_dir":
        view["live_mount_id"] = view["root_mount_id"]
    elif fault == "loop_capacity":
        view["loop"]["capacity"] *= 2
    elif fault == "loop_path":
        view["loop"]["backing_path"] += "-foreign"
    elif fault == "root_owner":
        view["root"]["uid"] = 999
    elif fault == "root_mode":
        view["root"]["mode"] = 0o777
    elif fault == "lostfound_mode":
        view["lost_found"]["mode"] = 0o777
    elif fault == "deployment":
        view["deployment"]["fixture"] = "foreign"
    elif fault == "cgroup":
        view["unit_cgroup"] += "-foreign"
    else:
        view["boot_id"] = "other-boot"
    with LiveBuffer.open_bounded_hot(root, budget) as hot:
        assert hot.read_only
    assert not list(root.glob("budget-intent-*.json"))


@pytest.mark.parametrize(
    "fault",
    [
        "db",
        "extra",
        "lostfound_nonempty",
        "foreign_receipt",
        "partial_header",
        "partial_intent",
        "partial_session",
    ],
)
def test_nonempty_or_partial_prepared_state_is_never_adopted(prepared, fault):
    root, spec, _, record, save, receipt = prepared
    if fault == "db":
        (root / "live/updates.duckdb").write_bytes(b"foreign")
    elif fault == "extra":
        (root / "live/foreign-file").write_bytes(b"retain")
    elif fault == "lostfound_nonempty":
        record["lost_found_entries"] = ["retained-failure"]
        save()
    elif fault == "foreign_receipt":
        receipt.write_bytes(b"{}")
    else:
        name = {
            "partial_header": "budget-spec.json",
            "partial_intent": "budget-intent-000001.json",
            "partial_session": "budget-session-000001.json",
        }[fault]
        (root / name).write_bytes(b"{")
    with pytest.raises(ValueError):
        HotCacheBudget(root, spec)
    assert not (root / "budget-session-000001.json").exists() or fault == "partial_session"


def test_mount_loss_after_admission_stops_without_rearm(prepared):
    root, spec, view, *_ = prepared
    with LiveBuffer.open_bounded_hot(root, HotCacheBudget(root, spec)) as hot:
        hot.append(candles()[0])
        view["live"]["dev"] = view["root"]["dev"]
        with pytest.raises(buffer_module.LiveCapacityExceeded):
            hot.append(candles()[1])
        assert len(hot.replay()) == 1
    assert not (root / "budget-closed-000001.json").exists()
    assert len(list(root.glob("budget-intent-*.json"))) == 2


def test_crash_open_session_cannot_rearm_on_static_receipt(prepared):
    root, spec, *_ = prepared
    hot = LiveBuffer(root, retention_days=0, write_budget=HotCacheBudget(root, spec))
    hot.append(candles()[0])
    hot._con.close()  # Controlled unfinished session; not a physical crash claim.
    with LiveBuffer.open_bounded_hot(root, HotCacheBudget(root, spec)) as stopped:
        assert stopped.read_only and len(stopped.replay()) == 1
    assert len(list(root.glob("budget-intent-*.json"))) == 2


@pytest.mark.parametrize(
    "fault",
    [
        "root_mode",
        "root_owner",
        "live_mode",
        "lostfound_owner",
        "lostfound_link",
        "loop_oversize",
        "filesystem_oversize",
        "underlying_writable",
        "backing_link",
        "backing_owner",
        "backing_bool",
        "schema_bool",
        "unit_restart",
        "expired",
    ],
)
def test_signed_but_weaker_preparation_facts_are_rejected(prepared, fault):
    root, spec, view, record, save, _ = prepared
    if fault == "root_mode":
        view["root"]["mode"] = 0o777
    elif fault == "root_owner":
        view["root"]["uid"] = 999
    elif fault == "live_mode":
        view["live"]["mode"] = 0o777
    elif fault == "lostfound_owner":
        view["lost_found"]["uid"] = 999
    elif fault == "lostfound_link":
        view["lost_found"]["nlink"] = 3
    elif fault == "loop_oversize":
        view["loop"]["capacity"] *= 2
    elif fault == "filesystem_oversize":
        view["filesystem"]["blocks"] *= 2
    elif fault == "underlying_writable":
        record["underlying"]["mode"] = 0o777
    elif fault == "backing_link":
        record["backing"]["nlink"] = 2
    elif fault == "backing_owner":
        record["backing"]["uid"] = 999
    elif fault == "backing_bool":
        record["backing"]["nlink"] = True
    elif fault == "schema_bool":
        record["schema_version"] = True
    elif fault == "unit_restart":
        record["unit_restart"] = "on-failure"
    else:
        record["expires_at_utc"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    record["facts"] = {
        k: copy.deepcopy(v)
        for k, v in view.items()
        if k not in {"namespace", "root_mount_id", "live_mount_id"}
    }
    save()
    with pytest.raises(ValueError):
        HotCacheBudget(root, spec)
    assert not list(root.glob("budget-intent-*.json"))


def test_changed_static_receipt_after_load_cannot_admit(prepared):
    root, spec, _, _, _, receipt = prepared
    budget = HotCacheBudget(root, spec)
    receipt.write_bytes(b"{}")
    with LiveBuffer.open_bounded_hot(root, budget) as stopped:
        assert stopped.read_only
    assert not list(root.glob("budget-intent-*.json"))


@pytest.mark.parametrize("fault", ["uid", "gid", "mode", "link", "directory", "large", "empty"])
def test_receipt_file_trust_checks_never_accept_weaker_metadata(fault):
    import stat
    from types import SimpleNamespace

    from quantmesh.live.prepared_mount import _check_receipt_stat

    values = dict(st_mode=stat.S_IFREG | 0o444, st_uid=0, st_gid=0, st_nlink=1, st_size=512)
    key, value = {
        "uid": ("st_uid", 999),
        "gid": ("st_gid", 42),
        "mode": ("st_mode", stat.S_IFREG | 0o644),
        "link": ("st_nlink", 2),
        "directory": ("st_mode", stat.S_IFDIR | 0o444),
        "large": ("st_size", 16385),
        "empty": ("st_size", 0),
    }[fault]
    values[key] = value
    with pytest.raises(ValueError):
        _check_receipt_stat(SimpleNamespace(**values))


@pytest.mark.parametrize(
    "target",
    [
        "intent_before",
        "intent_after",
        "header_before",
        "header_after",
        "session_before",
        "session_after",
    ],
)
def test_failed_first_admission_retains_effects_and_never_automatically_retries(
    prepared, monkeypatch, target
):
    root, spec, *_ = prepared
    budget = HotCacheBudget(root, spec)
    original = budget._write_once
    filename = {
        "intent": "budget-intent-000001.json",
        "header": "budget-spec.json",
        "session": "budget-session-000001.json",
    }[target.split("_")[0]]

    def write(path, raw):
        if path.name == filename:
            if target.endswith("after"):
                original(path, raw)
            raise OSError("controlled first-admission write failure")
        original(path, raw)

    monkeypatch.setattr(budget, "_write_once", write)
    with LiveBuffer.open_bounded_hot(root, budget) as stopped:
        assert stopped.read_only
    assert not (root / "live/updates.duckdb").exists()
    before = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    try:
        again = HotCacheBudget(root, spec)
    except ValueError:
        pass  # Existing partial evidence is explicit unavailable, never repaired.
    else:
        with LiveBuffer.open_bounded_hot(root, again) as stopped:
            assert stopped.read_only
    assert {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()} == before
    assert not (root / "live/updates.duckdb").exists()


def test_preseeded_header_zero_intent_still_refuses_prepared_mount(prepared):
    root, spec, *_ = prepared
    header = json.dumps(spec, sort_keys=True).encode()
    (root / "budget-spec.json").write_bytes(header)
    with LiveBuffer.open_bounded_hot(root, HotCacheBudget(root, spec)) as stopped:
        assert stopped.read_only
    assert not list(root.glob("budget-intent-*.json"))


def test_actual_process_crash_keeps_unclosed_prepared_session(prepared, tmp_path):
    import subprocess
    import sys

    root, spec, view, _, _, receipt = prepared
    view_path = tmp_path / "modeled-view.json"
    view_path.write_text(json.dumps(view), encoding="utf-8")
    script = "\n".join(
        [
            "import json, os, sys",
            "from pathlib import Path",
            "from quantmesh.live import prepared_mount as pm",
            "from quantmesh.live.buffer import HotCacheBudget, LiveBuffer",
            "from quantmesh.live.contract import MarketUpdate",
            "root = Path(sys.argv[1]); receipt = Path(sys.argv[3])",
            "view = json.loads(Path(sys.argv[4]).read_bytes())",
            "pm._read_receipt = lambda path: receipt.read_bytes()",
            "def observe(path):",
            "    result = dict(view)",
            "    result['root_names'] = sorted(p.name for p in root.iterdir())",
            "    result['live_names'] = sorted(p.name for p in (root/'live').iterdir())",
            "    return result",
            "pm._observe = observe  # explicit mount model; no actual mount is performed",
            "HotCacheBudget._require_directory_sync = lambda self: None",
            "budget = HotCacheBudget(root, json.loads(sys.argv[2]))",
            "hot = LiveBuffer(root, retention_days=0, write_budget=budget)",
            "hot.append(MarketUpdate.model_validate_json(sys.argv[5]))",
            "os._exit(0)",
        ]
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(root),
            json.dumps(spec),
            str(receipt),
            str(view_path),
            candles()[0].model_dump_json(),
        ],
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    with LiveBuffer.open_bounded_hot(root, HotCacheBudget(root, spec)) as stopped:
        assert stopped.read_only
        if not stopped.read_unavailable:
            assert len(stopped.replay()) == 1
    assert not (root / "budget-closed-000001.json").exists()
    assert len(list(root.glob("budget-intent-*.json"))) == 2


def test_missing_receipt_never_starts_prepared_mode(prepared, monkeypatch):
    from quantmesh.live import prepared_mount as module

    root, spec, *_ = prepared

    def missing(path):
        raise FileNotFoundError("controlled missing protected receipt")

    monkeypatch.setattr(module, "_read_receipt", missing)
    with pytest.raises(ValueError):
        HotCacheBudget(root, spec)
    assert sorted(p.name for p in root.iterdir()) == ["live"]


def test_duplicate_receipt_key_is_rejected_even_with_matching_digest(prepared):
    root, spec, _, _, _, receipt = prepared
    raw = b'{"schema_version":1,' + receipt.read_bytes()[1:]
    receipt.write_bytes(raw)
    spec["prepared_live_receipt_sha256"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError):
        HotCacheBudget(root, spec)


def test_self_consistent_ordinary_directory_is_not_a_prepared_mount(prepared):
    root, spec, view, record, save, _ = prepared
    view["live_mount_id"] = view["root_mount_id"]
    record["facts"] = {
        k: copy.deepcopy(v)
        for k, v in view.items()
        if k not in {"namespace", "root_mount_id", "live_mount_id"}
    }
    save()
    with pytest.raises(ValueError):
        HotCacheBudget(root, spec)


def test_real_untrusted_receipt_path_is_never_accepted(tmp_path):
    from quantmesh.live.prepared_mount import _read_receipt

    path = tmp_path / "not-root-controlled.json"
    path.write_bytes(b"{}")
    with pytest.raises(ValueError):
        _read_receipt(path)


def test_foreign_filesystem_lostfound_is_not_standard_lostfound(prepared):
    root, spec, view, record, save, _ = prepared
    view["lost_found"]["dev"] += 1
    record["facts"] = {
        k: copy.deepcopy(v)
        for k, v in view.items()
        if k not in {"namespace", "root_mount_id", "live_mount_id"}
    }
    save()
    with pytest.raises(ValueError):
        HotCacheBudget(root, spec)
