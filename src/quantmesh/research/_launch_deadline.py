"""Original job launch deadline; never applies to owned cleanup operations."""

import time
from contextvars import ContextVar

_launch_deadline: ContextVar[float | None] = ContextVar("worker_launch_deadline", default=None)


class LaunchDeadlineExceeded(TimeoutError):
    """Preparation consumed the original budget before a launch side effect."""


def _check_launch_deadline(deadline: float | None = None) -> None:
    value = _launch_deadline.get() if deadline is None else deadline
    if value is not None and time.monotonic() >= value:
        raise LaunchDeadlineExceeded("worker launch deadline exceeded")
