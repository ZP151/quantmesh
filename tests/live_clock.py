"""Align retained-lake replay fixtures with the buffer's real retention clock."""

from datetime import datetime

import pytest


def freeze_buffer_clock(monkeypatch: pytest.MonkeyPatch, instant: datetime) -> None:
    """Keep retention enabled and evaluate it at a fixture's aware timestamp."""
    if instant.tzinfo is None:
        raise ValueError("buffer fixture clock must be timezone-aware")

    class BufferClock(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return instant.astimezone().replace(tzinfo=None)
            return instant.astimezone(tz)

    monkeypatch.setattr("quantmesh.live.buffer.datetime", BufferClock)
