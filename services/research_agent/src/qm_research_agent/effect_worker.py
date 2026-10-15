"""Private child entry point; only bounded_complete writes its trusted pipe."""

import json
import os
import pickle
import sys


def limits(budget):
    if os.name != "nt":
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (budget.memory_mib * 1024**2,) * 2)
        resource.setrlimit(resource.RLIMIT_CPU, (budget.timeout_seconds,) * 2)
        if hasattr(os, "sched_setaffinity"):
            os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
        return None
    import ctypes
    from ctypes import wintypes

    from tools.framework_bakeoff.process import _ExtendedLimitInformation

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    handle = kernel.CreateJobObjectW(None, None)
    info = _ExtendedLimitInformation()
    info.BasicLimitInformation.LimitFlags = 0x2000 | 0x200
    info.JobMemoryLimit = budget.memory_mib * 1024**2

    class Cpu(ctypes.Structure):
        _fields_ = [("flags", wintypes.DWORD), ("rate", wintypes.DWORD)]

    cpu = Cpu(1 | 4, max(1, int(10000 * budget.cpu_limit / (os.cpu_count() or 1))))
    if (
        not handle
        or not kernel.SetInformationJobObject(handle, 9, ctypes.byref(info), ctypes.sizeof(info))
        or not kernel.SetInformationJobObject(handle, 15, ctypes.byref(cpu), ctypes.sizeof(cpu))
        or not kernel.AssignProcessToJobObject(handle, kernel.GetCurrentProcess())
    ):
        raise RuntimeError("owned model containment unavailable")
    return handle  # process owns it until exit; OS closes it on parent termination


if __name__ == "__main__":
    stage = "configuration"
    try:
        if os.name != "nt":
            import ctypes
            import signal

            libc = ctypes.CDLL(None, use_errno=True)
            if libc.prctl(1, signal.SIGKILL) != 0 or os.getppid() != int(
                os.environ["QM_EFFECT_OWNER_PID"]
            ):
                raise RuntimeError("owned model containment unavailable")
        if "QM_EFFECT_SCOPE_REQUIRED" in os.environ:
            stage = "containment"
            if os.environ["QM_EFFECT_SCOPE_REQUIRED"] != "1":
                raise RuntimeError("owned model containment unavailable")
            from qm_research_agent.effect_filesystem import deny_filesystem_writes

            deny_filesystem_writes()
        # Trusted server-created configuration; never exposed as a public route.
        gateway, request, budget = pickle.loads(sys.stdin.buffer.read(2 * 1024 * 1024))
        stage = "containment"
        handle = limits(budget)
        stage = "effect"
        response = gateway.complete(request)
        from quantmesh.ai.transport import ScriptedModelTransport

        receipt = {
            "response": response.model_dump(),
            "scripted_seen": gateway._transport._seen
            if isinstance(gateway._transport, ScriptedModelTransport)
            else None,
        }
        raw = json.dumps(receipt).encode()
        if len(raw) > 1024 * 1024:
            raise ValueError("effect response too large")
        sys.stdout.buffer.write(raw)
        sys.stdout.buffer.flush()
    except BaseException as exc:
        sys.stdout.buffer.write(
            json.dumps(
                {"error": "model_effect_unavailable", "stage": stage, "type": type(exc).__name__}
            ).encode()
        )
        sys.stdout.buffer.flush()
        sys.exit(1)
