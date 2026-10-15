"""Invoke one trusted configured gateway in a capped, owned process.

Configuration crosses a private pipe, never a file, prompt or log. There is no
untrusted code upload surface. Windows child owns a kill-on-close Job Object;
Linux supports an explicitly admitted aggregate cgroup in addition to its
process group. Only this invocation is terminated on timeout; runtime activation
must require the qualified aggregate boundary.
"""

import json
import os
import pickle
import subprocess
import sys
from pathlib import Path

from quantmesh.ai.transport import ScriptedModelTransport
from quantmesh.ai.wire import ModelResponse, build_chat_body


def bounded_complete(gateway, request, budget, *, effect_scope_unit=None):
    scripted = isinstance(gateway._transport, ScriptedModelTransport)
    payload = pickle.dumps((gateway, request, budget))
    env = {name: os.environ[name] for name in ("SystemRoot", "TEMP", "TMP") if name in os.environ}
    env["PYTHONPATH"] = os.pathsep.join(str(Path(path).resolve()) for path in sys.path if path)
    # Core contracts use Path.home() for defaults. Child defaults must resolve
    # to an owned, empty service home, never the operator's credentials/config.
    child_home = Path(__file__).resolve().parents[2] / ".child-home"
    child_home.mkdir(exist_ok=True)
    env["USERPROFILE"] = str(child_home)
    env["HOME"] = str(child_home)  # isolated child only; no parent/global mutation
    env["QM_EFFECT_OWNER_PID"] = str(os.getpid())
    # Sanitizing the environment must not let the child invalidate the admitted
    # source/dependency closure by creating executable bytecode on first import.
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    scope = None
    if effect_scope_unit is not None:
        if sys.platform != "linux":
            raise RuntimeError("owned model containment unavailable")
        from qm_research_agent.linux_effect_scope import EffectScope

        scope = EffectScope(effect_scope_unit, budget)
        env["QM_EFFECT_SCOPE_REQUIRED"] = "1"
    process = None
    job = None
    try:
        process = subprocess.Popen(
            [sys.executable, "-B", "-m", "qm_research_agent.effect_worker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
            creationflags=(subprocess.CREATE_NO_WINDOW | 0x00000004) if os.name == "nt" else 0,
            start_new_session=os.name != "nt",
            cwd=child_home,
        )
        if os.name == "nt":
            from tools.framework_bakeoff.process import (
                _assign_kill_on_close_job,
                _resume_windows_process,
            )

            job = _assign_kill_on_close_job(process)
            if job is None or not _resume_windows_process(process):
                raise RuntimeError("owned model containment unavailable")
        elif scope is not None:
            scope.attach(process)
        if scripted:
            gateway._transport.seen_bodies.append(
                build_chat_body(model_name=gateway.model_name, request=request)
            )
        raw, _ = process.communicate(payload, timeout=budget.timeout_seconds)
        if process.returncode or len(raw) > 1024 * 1024:
            raise RuntimeError("model effect unavailable")
        receipt = json.loads(raw)
        if scripted:
            gateway._transport._seen = receipt["scripted_seen"]
        return ModelResponse.model_validate(receipt["response"])
    finally:
        try:
            if scope is not None:
                # Reap the entire scope even when its direct child already exited.
                scope.close()
        finally:
            if os.name == "nt" and job is not None:
                from tools.framework_bakeoff.process import _close_job

                _close_job(job)
            if process is not None:
                if process.poll() is None:
                    if os.name == "nt":
                        process.kill()  # child-owned Job Object closes and kills descendants
                    else:
                        import signal

                        os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
                if process.stdin:
                    process.stdin.close()
                if process.stdout:
                    process.stdout.close()
