"""Test-owned free-space facts for HotCacheBudget's real admission predicate."""

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from quantmesh.live import buffer as buffer_module


@contextmanager
def modeled_hot_space(temporary_root, *, free=80_000_000_000):
    owned = temporary_root.resolve(strict=True)

    def disk_usage(probe):
        if not Path(probe).resolve(strict=True).is_relative_to(owned):
            raise AssertionError("capacity probe escaped the test temporary directory")
        return SimpleNamespace(free=free)

    # Rebind only the buffer module's dependency. Other shutil users see the host.
    with patch.object(buffer_module, "shutil", SimpleNamespace(disk_usage=disk_usage)):
        yield


@pytest.fixture
def ample_hot_space(tmp_path):
    with modeled_hot_space(tmp_path):
        yield
