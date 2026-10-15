"""Real held Linux metadata handoff; no container, image or native certificate."""

import os
import stat

import pytest

from quantmesh.research.worker_bundle import WorkerBundleRejected, handoff_worker_bundle

pytestmark = pytest.mark.skipif(os.name != "posix", reason="qualified fd-relative Linux handoff")


@pytest.fixture
def bundle(tmp_path):
    root = tmp_path / "bundle"
    root.mkdir(mode=0o700)
    (root / "inputs").mkdir(mode=0o700)
    (root / "inputs" / "shard.parquet").write_bytes(b"bounded opaque fixture; never decoded here")
    (root / "job.json").write_text("{}")
    return root


def test_same_uid_handoff_changes_only_owned_metadata_without_reading_content(bundle, monkeypatch):
    files = [bundle / "job.json", bundle / "inputs" / "shard.parquet"]
    before = {p: p.read_bytes() for p in files}
    ancestor = bundle.parent.stat()
    with monkeypatch.context() as patch:
        patch.setattr(os, "read", lambda *args: pytest.fail("handoff decoded/read file content"))
        handoff_worker_bundle(bundle, os.geteuid(), os.getegid())
    assert {p: p.read_bytes() for p in files} == before
    for path in [bundle, bundle / "inputs", *files]:
        info = path.lstat()
        assert (info.st_uid, info.st_gid) == (os.geteuid(), os.getegid())
        assert stat.S_IMODE(info.st_mode) == (
            0o700 if path == bundle else 0o500 if path.is_dir() else 0o400
        )
    after = bundle.parent.stat()
    assert (ancestor.st_mode, ancestor.st_uid, ancestor.st_gid) == (
        after.st_mode,
        after.st_uid,
        after.st_gid,
    )


@pytest.mark.parametrize("fault", ["symlink", "hardlink", "fifo", "nonprivate"])
def test_unsafe_preflight_refuses_before_any_metadata_change(bundle, tmp_path, monkeypatch, fault):
    sibling = tmp_path / "sibling"
    sibling.write_bytes(b"untouched")
    if fault == "symlink":
        (bundle / "link").symlink_to(sibling)
    elif fault == "hardlink":
        os.link(bundle / "job.json", bundle / "alias")
    elif fault == "fifo":
        os.mkfifo(bundle / "pipe")
    else:
        bundle.chmod(0o755)
    calls = []
    monkeypatch.setattr(os, "fchown", lambda *args: calls.append("chown"))
    monkeypatch.setattr(os, "fchmod", lambda *args: calls.append("chmod"))
    with pytest.raises(WorkerBundleRejected, match="^worker bundle rejected$"):
        handoff_worker_bundle(bundle, os.geteuid(), os.getegid())
    assert not calls and sibling.read_bytes() == b"untouched"


def test_replaced_ancestor_never_hands_off_a_borrowed_sibling(bundle, tmp_path, monkeypatch):
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    borrowed = outside / "shard.parquet"
    borrowed.write_bytes(b"not this job")
    borrowed_before = borrowed.stat()
    original = os.fchown
    switched = []

    def replace(fd, uid, gid):
        if not switched:
            (bundle / "inputs").rename(bundle / "held-inputs")
            (bundle / "inputs").symlink_to(outside, target_is_directory=True)
            switched.append(True)
        return original(fd, uid, gid)

    monkeypatch.setattr(os, "fchown", replace)
    with pytest.raises(WorkerBundleRejected):
        handoff_worker_bundle(bundle, os.geteuid(), os.getegid())
    assert switched
    after = borrowed.stat()
    assert (borrowed_before.st_uid, borrowed_before.st_gid, borrowed_before.st_mode) == (
        after.st_uid,
        after.st_gid,
        after.st_mode,
    )
    assert borrowed.read_bytes() == b"not this job"


def test_invalid_target_or_exhausted_entry_bound_has_no_mutation(bundle, monkeypatch):
    import quantmesh.research.worker_bundle as api

    calls = []
    monkeypatch.setattr(os, "fchown", lambda *args: calls.append("chown"))
    for uid, gid in [(0, os.getegid()), (True, os.getegid()), (os.geteuid(), 65536)]:
        with pytest.raises(WorkerBundleRejected):
            handoff_worker_bundle(bundle, uid, gid)
    monkeypatch.setattr(api, "_MAX_NODES", 1)
    with pytest.raises(WorkerBundleRejected):
        handoff_worker_bundle(bundle, os.geteuid(), os.getegid())
    assert not calls


def test_directory_queue_limit_stops_before_enumerating_all_children(tmp_path, monkeypatch):
    import quantmesh.research.worker_bundle as api

    root = tmp_path / "bounded"
    root.mkdir(mode=0o700)
    names = {f"folder{n}" for n in range(5)}
    for name in names:
        (root / name).mkdir(mode=0o700)
    monkeypatch.setattr(api, "_MAX_NODES", 2)
    opened, observed = [], set()
    directory, original_stat = api.DirectoryHandles.directory, os.stat

    def track_directory(self, path, *args, **kwargs):
        fd = directory(self, path, *args, **kwargs)
        if path == root:
            opened.append(fd)
        return fd

    def track_stat(path, *args, **kwargs):
        if path in names and opened and kwargs.get("dir_fd") == opened[0]:
            observed.add(path)
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(api.DirectoryHandles, "directory", track_directory)
    monkeypatch.setattr(os, "stat", track_stat)
    with pytest.raises(WorkerBundleRejected):
        handoff_worker_bundle(root, os.geteuid(), os.getegid())
    assert len(observed) <= 1, "queued directories must count before further enumeration"
