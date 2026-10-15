"""Inherited write denial for a trusted Linux advisory effect, before decode.

No filesystem write grants are needed by the report-only HTTPS gateway. Pipes
remain usable. This is not an arbitrary-code sandbox or a network policy.
"""

import ctypes
import os
import platform


def deny_filesystem_writes():
    """Require Landlock ABI3+ on the admitted x86_64 Linux runtime, or reject."""
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise RuntimeError("effect filesystem unavailable")
    descriptor = None
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        libc.syscall.restype = ctypes.c_long
        # x86_64 syscall numbers; no other architecture is admitted above.
        abi = libc.syscall(ctypes.c_long(444), None, ctypes.c_size_t(0), ctypes.c_uint(1))
        if abi < 3:
            raise RuntimeError
        # WRITE_FILE and all mutation rights through ABI3 TRUNCATE. No read,
        # execute or network rights are handled by this filesystem-only layer.
        handled = (1 << 1) | sum(1 << bit for bit in range(4, 15))
        attributes = ctypes.c_uint64(handled)
        descriptor = libc.syscall(
            ctypes.c_long(444), ctypes.byref(attributes), ctypes.c_size_t(8), ctypes.c_uint(0)
        )
        if descriptor < 0:
            descriptor = None
            raise RuntimeError
        if libc.prctl(38, 1, 0, 0, 0) != 0:
            raise RuntimeError
        if libc.syscall(ctypes.c_long(446), ctypes.c_int(descriptor), ctypes.c_uint(0)) != 0:
            raise RuntimeError
    except (OSError, RuntimeError, AttributeError):
        raise RuntimeError("effect filesystem unavailable") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
