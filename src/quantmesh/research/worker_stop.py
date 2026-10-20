"""Internal first-cause Worker stop token; ordinary Events never imply handoff."""

from __future__ import annotations

import signal
from threading import Condition, RLock


class _WorkerStop:
    """Event-compatible stop with a first-wins signal/failure distinction.

    A reentrant condition also permits a Python signal handler to reenter the
    main thread while it records an ordinary failure. The first recorded cause
    is immutable; a later signal cannot upgrade an uncontrolled stop.
    """

    def __init__(self) -> None:
        self._condition = Condition(RLock())
        self._causes: dict[str, int | str] = {}

    def _request(self, cause: int | str) -> None:
        with self._condition:
            # One atomic insertion also survives signal reentry between Python
            # bytecodes: never use a check followed by an overwriting assignment.
            self._causes.setdefault("first", cause)
            self._condition.notify_all()

    def request_signal(self, signum: int) -> None:
        if signum not in (signal.SIGTERM, signal.SIGINT):
            self.set()
            return
        self._request(signum)

    def set(self) -> None:
        self._request("uncontrolled")

    def is_set(self) -> bool:
        with self._condition:
            return bool(self._causes)

    def wait(self, timeout: float | None = None) -> bool:
        with self._condition:
            return self._condition.wait_for(lambda: bool(self._causes), timeout)

    @property
    def controlled(self) -> bool:
        with self._condition:
            return self._causes.get("first") in (signal.SIGTERM, signal.SIGINT)
