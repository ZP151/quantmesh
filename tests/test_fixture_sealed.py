"""Software-only syscall tests for the sealed fixture shard stream."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from quantmesh.research import _fixture_sealed as sealed
from quantmesh.research._fixture_handles import UnsupportedSnapshotProfile
from quantmesh.research.jobs import DatasetRejected


class FakeKernel:
    def __init__(
        self,
        data: bytes,
        *,
        platform="linux",
        chunk=3,
        seals=47,
        mode=0o100400,
        refuse_seals=False,
    ):
        self.data = data
        self.platform = platform
        self.chunk = chunk
        self.seals = seals
        self.mode = mode
        self.refuse_seals = refuse_seals
        self.fail_memfd_close = False
        self.write_zero = False
        self.memfd_attrs = {}
        self.memfd_inode = 40
        self.nextfd = 40
        self.buffers = {}
        self.closed = []
        self.reads = 0
        self.source = SimpleNamespace(
            st_dev=1,
            st_ino=2,
            st_mode=stat.S_IFREG | 0o400,
            st_nlink=1,
            st_size=len(data),
            st_mtime_ns=3,
            st_ctime_ns=4,
            st_uid=1000,
            st_gid=5,
        )

    def install(self, monkeypatch):
        real_os = os

        def read(fd, count):
            self.reads += 1
            if fd == 10:
                offset = self.source_offset
                part = self.data[offset : offset + min(count, self.chunk)]
                self.source_offset += len(part)
                return part
            return real_os.read(fd, count)

        def write(fd, value):
            if fd >= 40:
                if self.write_zero:
                    return 0
                take = min(2, len(value))
                self.buffers[fd].extend(value[:take])
                return take
            return real_os.write(fd, value)

        def pread(fd, count, offset):
            if fd >= 40:
                return bytes(self.buffers[fd][offset : offset + count])
            return real_os.pread(fd, count, offset)

        def fstat(fd):
            if fd == 10:
                return self.source
            if fd in self.buffers:
                return SimpleNamespace(
                    st_dev=8,
                    st_ino=self.memfd_inode,
                    st_mode=self.memfd_attrs.get("mode", self.mode),
                    st_nlink=self.memfd_attrs.get("nlink", 0),
                    st_size=len(self.buffers[fd]),
                    st_mtime_ns=3,
                    st_ctime_ns=4,
                    st_uid=self.memfd_attrs.get("uid", 1000),
                    st_gid=5,
                )
            return real_os.fstat(fd)

        def memfd_create(name, flags):
            assert flags == 11
            fd = self.nextfd
            self.nextfd += 1
            self.buffers[fd] = bytearray()
            return fd

        fake_os = SimpleNamespace(**{name: getattr(real_os, name) for name in dir(real_os)})
        fake_os.name = "posix"
        fake_os.read, fake_os.write, fake_os.pread, fake_os.fstat = read, write, pread, fstat
        fake_os.memfd_create = memfd_create
        fake_os.getuid, fake_os.getpid = lambda: 1000, lambda: 123
        fake_os.fchmod = lambda fd, mode: setattr(self, "mode", stat.S_IFREG | mode)

        def close(fd):
            self.closed.append(fd)
            if fd >= 40 and self.fail_memfd_close:
                raise OSError("memfd close failed")

        fake_os.close = close
        fake_os.O_RDONLY = getattr(real_os, "O_RDONLY", 0)
        fake_os.O_NONBLOCK = getattr(real_os, "O_NONBLOCK", 0x800)
        monkeypatch.setattr(sealed, "os", fake_os)
        monkeypatch.setattr(sealed, "sys", SimpleNamespace(platform=self.platform))
        monkeypatch.setattr(
            sealed,
            "fcntl",
            SimpleNamespace(
                F_ADD_SEALS=1033,
                F_GET_SEALS=1034,
                fcntl=lambda fd, op, arg=None: self._fcntl(fd, op, arg),
            ),
        )
        self.source_offset = 0
        self.seal_calls = []

    def _fcntl(self, fd, op, arg):
        if op == 1033:
            self.seal_calls.append(arg)
            if not self.refuse_seals:
                self.seals = arg
            return 0
        return self.seals


class Handles:
    def __init__(self, kernel):
        self.kernel = kernel
        self.files = set()
        self.checks = 0
        self.mutate_on_verify = False
        self.fail_close = False
        self.close_calls = 0

    def open_file(self, path, flags, role):
        assert role == "source" and flags & getattr(sealed.os, "O_NONBLOCK", 0x800)
        self.files.add(10)
        return 10

    def file_stat(self, path, role):
        return self.kernel.source

    def verify(self):
        self.checks += 1
        if self.mutate_on_verify and self.checks == 2:
            self.kernel.source.st_ctime_ns += 1

    def check(self):
        pass

    def close_file(self, fd):
        self.close_calls += 1
        try:
            if self.fail_close:
                raise OSError("source close failed")
        finally:
            self.files.remove(fd)
            self.kernel.closed.append(fd)


def parquet(data=b"payload"):
    return b"PAR1" + data + (1).to_bytes(4, "little") + b"PAR1"


def test_streams_partial_writes_into_sealed_memfd_and_holds_fd_for_context(monkeypatch):
    data = parquet()
    kernel = FakeKernel(data)
    kernel.install(monkeypatch)
    handles = Handles(kernel)
    with sealed.sealed_shard(handles, Path("/fixture/day.parquet"), 9999999999) as result:
        assert result.alias == "/proc/123/fd/40"
        assert result.sha256 == hashlib.sha256(data).hexdigest()
        assert result.size == len(data) and result.footer_length == 1
        assert 40 not in kernel.closed and 10 in kernel.closed
        assert kernel.seal_calls == [47]
    assert 40 in kernel.closed


@pytest.mark.parametrize("data", [b"", b"PAR1short", parquet()[:-1]])
def test_rejects_empty_short_or_invalid_framing_and_closes_descriptors(monkeypatch, data):
    kernel = FakeKernel(data)
    kernel.install(monkeypatch)
    with pytest.raises(DatasetRejected):
        with sealed.sealed_shard(Handles(kernel), Path("/fixture/a.parquet"), 9999999999):
            pytest.fail("invalid shard yielded")
    assert 10 in kernel.closed
    assert (40 in kernel.closed) == bool(kernel.buffers)


def test_unsupported_windows_profile_refuses_before_opening_handles(monkeypatch):
    kernel = FakeKernel(parquet(), platform="win32")
    kernel.install(monkeypatch)
    handles = Handles(kernel)
    with pytest.raises(UnsupportedSnapshotProfile, match="fixture_sealed_profile_unsupported"):
        with sealed.sealed_shard(handles, Path("/fixture/a.parquet"), 9999999999):
            pass
    assert not handles.files and kernel.nextfd == 40 and kernel.reads == 0


def test_body_exception_is_preserved_while_owned_memfd_closes(monkeypatch):
    kernel = FakeKernel(parquet())
    kernel.install(monkeypatch)
    error = RuntimeError("consumer")
    with pytest.raises(RuntimeError, match="consumer"):
        with sealed.sealed_shard(Handles(kernel), Path("/fixture/a.parquet"), 9999999999):
            raise error
    assert 10 in kernel.closed and 40 in kernel.closed


def test_oversize_source_is_rejected_before_memfd_creation(monkeypatch):
    kernel = FakeKernel(parquet())
    kernel.install(monkeypatch)
    kernel.source.st_size = 100
    with pytest.raises(DatasetRejected):
        with sealed.sealed_shard(Handles(kernel), Path("/fixture/a.parquet"), 9999999999, limit=20):
            pass
    assert kernel.nextfd == 40 and 10 in kernel.closed


def test_refuses_when_kernel_does_not_apply_required_seals(monkeypatch):
    kernel = FakeKernel(parquet(), seals=31, refuse_seals=True)
    kernel.install(monkeypatch)
    with pytest.raises(DatasetRejected):
        with sealed.sealed_shard(Handles(kernel), Path("/fixture/a.parquet"), 9999999999):
            pass
    assert 10 in kernel.closed and 40 in kernel.closed


def test_expired_deadline_rejects_before_opening_source(monkeypatch):
    kernel = FakeKernel(parquet())
    kernel.install(monkeypatch)
    with pytest.raises(DatasetRejected):
        with sealed.sealed_shard(Handles(kernel), Path("/fixture/a.parquet"), -1):
            pass
    assert not kernel.buffers and not kernel.reads


def test_source_stat_change_after_copy_is_rejected_and_cleaned(monkeypatch):
    kernel = FakeKernel(parquet())
    kernel.install(monkeypatch)
    handles = Handles(kernel)
    handles.mutate_on_verify = True
    with pytest.raises(DatasetRejected):
        with sealed.sealed_shard(handles, Path("/fixture/a.parquet"), 9999999999):
            pass
    assert 10 in kernel.closed and 40 in kernel.closed


def test_sealed_bytes_are_rechecked_after_consumer_returns(monkeypatch):
    kernel = FakeKernel(parquet())
    kernel.install(monkeypatch)
    with pytest.raises(DatasetRejected):
        with sealed.sealed_shard(Handles(kernel), Path("/fixture/a.parquet"), 9999999999):
            kernel.buffers[40][4] ^= 1
    assert 10 in kernel.closed and 40 in kernel.closed


@pytest.mark.parametrize("size_delta", [-1, 1])
def test_rejects_short_source_and_extra_eof_data(monkeypatch, size_delta):
    data = parquet()
    kernel = FakeKernel(data)
    kernel.install(monkeypatch)
    kernel.source.st_size += size_delta
    with pytest.raises(DatasetRejected):
        with sealed.sealed_shard(Handles(kernel), Path("/fixture/a.parquet"), 9999999999):
            pass
    assert 10 in kernel.closed and 40 in kernel.closed


def test_zero_write_is_rejected_and_cleaned(monkeypatch):
    kernel = FakeKernel(parquet())
    kernel.install(monkeypatch)
    kernel.write_zero = True
    with pytest.raises(DatasetRejected):
        with sealed.sealed_shard(Handles(kernel), Path("/fixture/a.parquet"), 9999999999):
            pass
    assert 10 in kernel.closed and 40 in kernel.closed


def test_deadline_expiring_during_copy_closes_both_descriptors(monkeypatch):
    kernel = FakeKernel(parquet())
    kernel.install(monkeypatch)
    ticks = iter((0.0, 0.1, 0.2, 0.3))
    monkeypatch.setattr(sealed, "time", SimpleNamespace(monotonic=lambda: next(ticks)))
    with pytest.raises(DatasetRejected):
        with sealed.sealed_shard(Handles(kernel), Path("/fixture/a.parquet"), 0.25):
            pass
    assert kernel.reads > 0 and 10 in kernel.closed and 40 in kernel.closed


@pytest.mark.parametrize(
    "attribute,value", [("mode", stat.S_IFREG | 0o600), ("uid", 1001), ("nlink", 1)]
)
def test_post_consumer_memfd_metadata_changes_are_rejected(monkeypatch, attribute, value):
    kernel = FakeKernel(parquet())
    kernel.install(monkeypatch)
    with pytest.raises(DatasetRejected):
        with sealed.sealed_shard(Handles(kernel), Path("/fixture/a.parquet"), 9999999999):
            kernel.memfd_attrs[attribute] = value
    assert 40 in kernel.closed


def test_post_consumer_memfd_identity_change_is_rejected(monkeypatch):
    kernel = FakeKernel(parquet())
    kernel.install(monkeypatch)
    with pytest.raises(DatasetRejected):
        with sealed.sealed_shard(Handles(kernel), Path("/fixture/a.parquet"), 9999999999):
            kernel.memfd_inode = 99
    assert 40 in kernel.closed


def test_source_close_failure_is_not_retried_and_rejects(monkeypatch):
    kernel = FakeKernel(parquet())
    kernel.install(monkeypatch)
    handles = Handles(kernel)
    handles.fail_close = True
    with pytest.raises(DatasetRejected):
        with sealed.sealed_shard(handles, Path("/fixture/a.parquet"), 9999999999):
            pytest.fail("source close was not verified")
    assert handles.close_calls == 1 and kernel.closed.count(10) == 1
    assert 40 in kernel.closed


def test_memfd_close_failure_refuses_normal_body_success(monkeypatch):
    kernel = FakeKernel(parquet())
    kernel.install(monkeypatch)
    kernel.fail_memfd_close = True
    with pytest.raises(DatasetRejected):
        with sealed.sealed_shard(Handles(kernel), Path("/fixture/a.parquet"), 9999999999):
            pass
    assert kernel.closed.count(40) == 1


def test_consumer_error_survives_source_and_memfd_cleanup_failures(monkeypatch):
    kernel = FakeKernel(parquet())
    kernel.install(monkeypatch)
    kernel.fail_memfd_close = True
    handles = Handles(kernel)
    error = RuntimeError("consumer original")
    with pytest.raises(RuntimeError, match="consumer original"):
        with sealed.sealed_shard(handles, Path("/fixture/a.parquet"), 9999999999):
            raise error
    assert kernel.closed.count(40) == 1
