"""Byte-only parent snapshots; arbitrary fixture bytes grant no content authority."""

import hashlib
import importlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from quantmesh.research import job_runner, strategy_registry
from quantmesh.research.jobs import (
    DatasetRejected,
    JobRecord,
    ResearchJobRequest,
    canonical_request_digest,
)
from quantmesh.research.strategy_registry import get_strategy


@pytest.fixture(autouse=True)
def snapshot_profile(request):
    if request.function.__name__ == "test_unsupported_snapshot_profile_precedes_fixture_io":
        return
    from quantmesh.research._fixture_handles import (
        UnsupportedSnapshotProfile,
        require_snapshot_profile,
    )

    try:
        require_snapshot_profile()
    except UnsupportedSnapshotProfile:
        pytest.skip("POSIX snapshot handles unavailable; Windows research Worker unsupported")


def small_job(tmp_path, raw=b"deliberately not Parquet"):
    source = tmp_path / "source"
    shard = source / "equities/1h/moomoo/AAA/2026-01-05/shard-0000.parquet"
    shard.parent.mkdir(parents=True)
    shard.write_bytes(raw)
    metadata = dict(
        schema_version=1,
        dataset="equities",
        source="fixture",
        license="test",
        timezone="UTC",
        revision=1,
        generated_at="2026-01-05T00:00:00Z",
        coverage=[
            dict(
                interval="1h",
                venue="moomoo",
                symbol="AAA",
                rows=3,
                start="2026-01-05T00:00:00Z",
                end="2026-01-05T02:00:00Z",
            )
        ],
    )
    manifest = source / "equities/manifest.json"
    manifest.write_text(json.dumps(metadata))
    export = json.dumps(
        [(shard.relative_to(source / "equities").as_posix(), hashlib.sha256(raw).hexdigest())],
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    request = ResearchJobRequest(
        strategy_id="momentum",
        strategy_version="1",
        dataset=dict(
            dataset_id="equities",
            revision=1,
            permission_class="fixture",
            manifest_digest=hashlib.sha256(manifest.read_bytes()).hexdigest(),
            export_digest=hashlib.sha256(export).hexdigest(),
        ),
        interval="1h",
        universe=[dict(venue="moomoo", symbol="AAA")],
        costs=dict(fee_bps=1, half_spread_bps=2, slippage_bps=3),
        window_spec=dict(train_bars=2, test_bars=1, step_bars=1),
    )
    job = JobRecord(
        job_id="job",
        operator_id="local",
        idempotency_key="small",
        request=request,
        request_digest=canonical_request_digest(request),
        implementation_digest=get_strategy("momentum", "1").implementation_digest,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    return job, source, tmp_path / "destination", shard, manifest


def helper():
    assert importlib.util.find_spec("quantmesh.research.fixture_snapshot"), (
        "bounded parent snapshot helper missing"
    )
    return importlib.import_module("quantmesh.research.fixture_snapshot")


@pytest.mark.skipif(os.name != "posix", reason="actual POSIX rename/symlink association fixture")
@pytest.mark.parametrize("role", ["source", "target", "metadata"])
def test_transient_ancestor_swap_keeps_intended_parent_handle(tmp_path, monkeypatch, role):
    api = helper()
    job, source, destination, shard, _ = small_job(tmp_path)
    if role == "metadata":
        root = tmp_path / "metadata"
        root.mkdir()
        file = root / "runtime.json"
        file.write_bytes(b"{}")
        ancestor = root
    else:
        file = shard if role == "source" else destination / shard.relative_to(source)
        ancestor = (source if role == "source" else destination) / "equities/1h"
    moved = tmp_path / ("moved-" + role)
    original = os.open
    observed = []

    def opening(path, flags, *args, **kwargs):
        parent_fd = kwargs.get("dir_fd")
        actual = (
            Path(os.readlink(f"/proc/self/fd/{parent_fd}")) / os.fsdecode(path)
            if parent_fd is not None
            else Path(path)
        )
        if actual == file and not observed:
            intended = file.parent.stat()
            held = os.fstat(parent_fd) if parent_fd is not None else None
            bound = held is not None and (held.st_dev, held.st_ino, held.st_uid, held.st_gid) == (
                intended.st_dev,
                intended.st_ino,
                intended.st_uid,
                intended.st_gid,
            )
            ancestor.rename(moved)
            ancestor.symlink_to(moved, target_is_directory=True)
            try:
                fd = original(path, flags, *args, **kwargs)
                observed.append((fd, bound, os.fsdecode(path) == file.name))
                return fd
            finally:
                ancestor.unlink()
                moved.rename(ancestor)
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", opening)
    try:
        if role == "metadata":
            job_runner._read_child_file(root, file, 8)
        else:
            api.copy_fixture_snapshot(job, source, destination)
    except (ValueError, DatasetRejected):
        pass  # A changed namespace may refuse; ctime is not a no-follow guarantee.
    assert observed, "the real open must reach the intended transient namespace"
    for fd, bound, relative in observed:
        assert bound and relative, "actual I/O must use the pre-acquired intended parent dir_fd"
        with pytest.raises(OSError):
            os.fstat(fd)


@pytest.mark.parametrize("role", ["source", "target", "metadata"])
def test_persistent_directory_membership_change_refuses(tmp_path, monkeypatch, role):
    api = helper()
    job, source, destination, shard, _ = small_job(tmp_path)
    if role == "metadata":
        root = tmp_path / "metadata"
        root.mkdir()
        file = root / "runtime.json"
        file.write_bytes(b"{}")
        ancestor = root
    else:
        file = shard if role == "source" else destination / shard.relative_to(source)
        ancestor = (source if role == "source" else destination) / "equities/1h"
    moved, replacement = tmp_path / "moved", tmp_path / "replacement"
    original = os.open
    observed = []

    def opening(path, flags, *args, **kwargs):
        parent_fd = kwargs.get("dir_fd")
        actual = (
            Path(os.readlink(f"/proc/self/fd/{parent_fd}")) / os.fsdecode(path)
            if parent_fd is not None
            else Path(path)
        )
        fd = original(path, flags, *args, **kwargs)
        if actual == file and not observed:
            observed.append(fd)
            ancestor.rename(moved)
            ancestor.mkdir()
        return fd

    monkeypatch.setattr(os, "open", opening)
    try:
        with pytest.raises(ValueError if role == "metadata" else DatasetRejected):
            if role == "metadata":
                job_runner._read_child_file(root, file, 8)
            else:
                api.copy_fixture_snapshot(job, source, destination)
    finally:
        if observed:
            ancestor.rename(replacement)
            moved.rename(ancestor)
    assert observed
    for fd in observed:
        with pytest.raises(OSError):
            os.fstat(fd)


@pytest.mark.parametrize("operation", ["snapshot", "metadata"])
def test_unsupported_snapshot_profile_precedes_fixture_io(tmp_path, monkeypatch, operation):
    from quantmesh.research import _fixture_handles

    api = helper()
    source, destination, runtime = (
        tmp_path / "source",
        tmp_path / "target",
        tmp_path / "runtime.json",
    )
    monkeypatch.setattr(_fixture_handles, "_SUPPORTED", False)

    def io(*args, **kwargs):
        pytest.fail("unsupported profile reached fixture I/O")

    for name in ("open", "stat", "lstat", "mkdir", "scandir"):
        monkeypatch.setattr(os, name, io)
    with pytest.raises(
        _fixture_handles.UnsupportedSnapshotProfile, match="fixture_snapshot_profile_unsupported"
    ):
        if operation == "snapshot":
            api.copy_fixture_snapshot(None, source, destination)
        else:
            job_runner._read_child_file(tmp_path, runtime, 8)


def test_all_opens_are_handle_relative_and_finally_closed(tmp_path, monkeypatch):
    job, source, destination, _, _ = small_job(tmp_path)
    api = helper()
    original = os.open
    opened = []

    def opening(path, flags, *args, **kwargs):
        if kwargs.get("dir_fd") is None:
            assert os.fsdecode(path) == "/", "only the filesystem anchor may be absolute"
        else:
            assert "/" not in os.fsdecode(path)
        fd = original(path, flags, *args, **kwargs)
        opened.append(fd)
        return fd

    monkeypatch.setattr(os, "open", opening)
    api.copy_fixture_snapshot(job, source, destination)
    assert job_runner._read_child_file(
        destination, destination / "equities/manifest.json", 256 * 1024
    )
    assert opened
    for fd in opened:
        with pytest.raises(OSError):
            os.fstat(fd)


def test_descriptor_bound_refuses_and_closes_all_acquired_handles(tmp_path, monkeypatch):
    from quantmesh.research import _fixture_handles

    api = helper()
    job, source, destination, _, _ = small_job(tmp_path)
    monkeypatch.setattr(_fixture_handles, "MAX_FDS", 2)
    original = os.open
    opened = []

    def opening(*args, **kwargs):
        fd = original(*args, **kwargs)
        opened.append(fd)
        return fd

    monkeypatch.setattr(os, "open", opening)
    with pytest.raises(DatasetRejected):
        api.copy_fixture_snapshot(job, source, destination)
    assert len(opened) == 2
    for fd in opened:
        with pytest.raises(OSError):
            os.fstat(fd)


def repin_manifest(job, manifest, raw):
    manifest.write_bytes(raw)
    ref = job.request.dataset.model_copy(
        update={"manifest_digest": hashlib.sha256(raw).hexdigest()}
    )
    request = job.request.model_copy(update={"dataset": ref})
    return job.model_copy(
        update={"request": request, "request_digest": canonical_request_digest(request)}
    )


def test_parent_copies_pinned_arbitrary_bytes_without_content_parser(tmp_path, monkeypatch):
    job, source, destination, shard, manifest = small_job(tmp_path)

    def decoder(*args, **kwargs):
        pytest.fail("parent reached content decoder")

    monkeypatch.setattr(job_runner, "validate_dataset", decoder)
    monkeypatch.setattr(strategy_registry, "pin_fixture_dataset", decoder)
    job_runner._snapshot(job, source, destination)
    copied = destination / shard.relative_to(source)
    assert copied.read_bytes() == b"deliberately not Parquet"
    assert (destination / manifest.relative_to(source)).read_bytes() == manifest.read_bytes()


@pytest.mark.parametrize(
    "fault",
    ["digest", "duplicate", "nonfinite", "overflow", "coverage", "symlink", "hardlink", "fifo"],
)
def test_parent_rejects_pinned_metadata_and_file_faults(tmp_path, fault):
    api = helper()
    job, source, destination, shard, manifest = small_job(tmp_path)
    if fault == "digest":
        shard.write_bytes(b"changed content")
    elif fault in {"duplicate", "nonfinite", "overflow", "coverage"}:
        raw = manifest.read_bytes()
        if fault == "duplicate":
            raw = raw[:-1] + b',"revision":1}'
        elif fault == "nonfinite":
            raw = raw[:-1] + b',"unknown":NaN}'
        elif fault == "overflow":
            raw = raw[:-1] + b',"unknown":1e9999}'
        else:
            value = json.loads(raw)
            value["coverage"] *= 65
            raw = json.dumps(value).encode()
        job = repin_manifest(job, manifest, raw)
    else:
        preserved = shard.with_suffix(".preserved")
        shard.rename(preserved)
        if fault == "symlink":
            shard.symlink_to(preserved)
        elif fault == "hardlink":
            os.link(preserved, shard)
        elif hasattr(os, "mkfifo"):
            os.mkfifo(shard)
        else:
            pytest.skip("FIFO unavailable on this platform")
    with pytest.raises(DatasetRejected):
        api.copy_fixture_snapshot(job, source, destination)


def test_sparse_shard_limit_precedes_file_read(tmp_path, monkeypatch):
    api = helper()
    job, source, destination, shard, _ = small_job(tmp_path)
    monkeypatch.setattr(api, "MAX_SHARD_BYTES", 8)
    with shard.open("wb") as stream:
        stream.truncate(9)
    original = api.os.read

    def read(fd, count):
        if os.fstat(fd).st_size == 9:
            pytest.fail("oversized sparse shard reached read")
        return original(fd, count)

    monkeypatch.setattr(api.os, "read", read)
    with pytest.raises(DatasetRejected):
        api.copy_fixture_snapshot(job, source, destination)


def test_shard_count_and_deadline_stop_discovery(tmp_path, monkeypatch):
    api = helper()
    job, source, destination, shard, _ = small_job(tmp_path)
    extra = shard.parent.with_name("2026-01-06")
    extra.mkdir()
    (extra / shard.name).write_bytes(b"extra")
    monkeypatch.setattr(api, "MAX_SHARDS", 1)
    with pytest.raises(DatasetRejected):
        api.copy_fixture_snapshot(job, source, destination)
    monkeypatch.setattr(api, "MAX_SHARDS", 4096)
    ticks = iter([0.0, 11.0])
    monkeypatch.setattr(api.time, "monotonic", lambda: next(ticks, 11.0))
    with pytest.raises(DatasetRejected):
        api.copy_fixture_snapshot(job, source, destination)


def test_same_size_mutation_during_stream_refuses(tmp_path, monkeypatch):
    api = helper()
    job, source, destination, shard, _ = small_job(tmp_path)
    original = api.os.read
    changed = []

    def read(fd, count):
        data = original(fd, count)
        if data == b"deliberately not Parquet" and not changed:
            changed.append(True)
            shard.write_bytes(b"X" * len(data))
        return data

    monkeypatch.setattr(api.os, "read", read)
    with pytest.raises(DatasetRejected):
        api.copy_fixture_snapshot(job, source, destination)


@pytest.mark.parametrize("fault", ["manifest", "aggregate"])
def test_metadata_and_aggregate_limits_precede_read(tmp_path, monkeypatch, fault):
    api = helper()
    job, source, destination, shard, manifest = small_job(tmp_path)
    if fault == "manifest":
        monkeypatch.setattr(api, "MAX_MANIFEST_BYTES", manifest.stat().st_size - 1)
        blocked_size = manifest.stat().st_size
    else:
        monkeypatch.setattr(api, "MAX_SNAPSHOT_BYTES", manifest.stat().st_size + 1)
        blocked_size = shard.stat().st_size
    original = api.os.read

    def read(fd, count):
        if os.fstat(fd).st_size == blocked_size:
            pytest.fail("over-limit file reached read")
        return original(fd, count)

    monkeypatch.setattr(api.os, "read", read)
    with pytest.raises(DatasetRejected):
        api.copy_fixture_snapshot(job, source, destination)


@pytest.mark.parametrize("fault", ["list", "symbol", "interval", "rights", "revision", "schema"])
def test_typed_manifest_paths_and_declarations_refuse(tmp_path, fault):
    api = helper()
    job, source, destination, _, manifest = small_job(tmp_path)
    value = json.loads(manifest.read_bytes())
    if fault == "list":
        value = [value]
    elif fault in {"symbol", "interval"}:
        value["coverage"][0][fault] = "../escape"
    elif fault == "rights":
        value["license"] = "unapproved"
    elif fault == "revision":
        value["revision"] = 2
    else:
        value["schema_version"] = True
    job = repin_manifest(job, manifest, json.dumps(value).encode())
    with pytest.raises(DatasetRejected, match="^dataset rejected: fixture_snapshot_invalid$"):
        api.copy_fixture_snapshot(job, source, destination)
    assert not destination.exists()


@pytest.mark.parametrize("fault", ["extra", "source_inode", "destination_inode"])
def test_membership_and_inode_changes_after_copy_refuse(tmp_path, monkeypatch, fault):
    api = helper()
    job, source, destination, shard, _ = small_job(tmp_path)
    original = api._Copy.stream
    changed = []

    def stream(self, path, limit, **kwargs):
        result = original(self, path, limit, **kwargs)
        if path == shard and kwargs.get("target") is not None and not changed:
            changed.append(True)
            if fault == "extra":
                extra = shard.parent.with_name("2026-01-06")
                extra.mkdir()
                (extra / shard.name).write_bytes(b"extra")
            else:
                replaced = shard if fault == "source_inode" else kwargs["target"]
                replacement = replaced.with_suffix(".replacement")
                replacement.write_bytes(replaced.read_bytes())
                os.replace(replacement, replaced)
        return result

    monkeypatch.setattr(api._Copy, "stream", stream)
    with pytest.raises(DatasetRejected):
        api.copy_fixture_snapshot(job, source, destination)
    assert changed


def test_real_fixture_child_validates_twice_and_preserves_canonical_numerics(tmp_path, monkeypatch):
    from quantmesh.research.baselines import run_baseline_report
    from quantmesh.research.job_artifacts import _canonical, canonical_result
    from quantmesh.research.reports import ReportRegistry
    from tests.research_fixtures import pinned_lake

    job, source, attempt, _, _ = small_job(tmp_path)
    pinned_lake(source, n=20)
    request = job.request.model_copy(
        update={"dataset": strategy_registry.pin_fixture_dataset(source, "equities")}
    )
    job = job.model_copy(
        update={"request": request, "request_digest": canonical_request_digest(request)}
    )
    job_runner._snapshot(job, source, attempt / "inputs")
    runtime = dict(
        build_digest="b" * 64,
        dependency_digest="d" * 64,
        git_commit="c" * 40,
        python_version="test-only host roundtrip; no runtime admission",
        python_executable_digest="e" * 64,
    )
    (attempt / "runtime.json").write_bytes(_canonical(runtime))
    (attempt / "job.json").write_text(job.model_dump_json())
    monkeypatch.setattr(job_runner, "runtime_fingerprint", lambda **kwargs: dict(runtime))
    validate = job_runner.validate_dataset
    validations = []

    def checked(*args):
        validate(*args)
        validations.append(True)

    monkeypatch.setattr(job_runner, "validate_dataset", checked)
    if job_runner.sys.platform == "linux":
        # Linux's descriptor-pinned fixture reader snapshots the attempt
        # directory as an ancestor of inputs. Keep child output outside that
        # tree: creating the report registry inside attempt changes the
        # ancestor ctime while the reader is open and correctly invalidates
        # the sealed input snapshot.
        output = tmp_path / "child-output"
        output.mkdir()
        job_runner._child_main(
            str(attempt),
            output_directory=str(output),
            build_manifest=tmp_path / "test-manifest.json",
            manifest_sha256="a" * 64,
        )
    else:
        output = attempt
        job_runner._child_main(str(attempt))
    assert validations == [True, True]
    expected = run_baseline_report(
        dataset="equities",
        revision=request.dataset.revision,
        strategy=request.strategy_id,
        interval=request.interval,
        universe=request.universe,
        window_spec=request.window_spec,
        costs=request.costs,
        commit=job.implementation_digest,
        registry=ReportRegistry(tmp_path / "direct", lake_root=source),
    )
    expected.evidence.update(
        request_digest=job.request_digest,
        manifest_digest=request.dataset.manifest_digest,
        export_digest=request.dataset.export_digest,
        build_digest=runtime["build_digest"],
        dependency_digest=runtime["dependency_digest"],
    )
    assert (output / "result.json").read_bytes() == canonical_result(expected)
