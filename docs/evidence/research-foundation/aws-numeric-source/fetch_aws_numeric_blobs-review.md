# Bounded OCI byte-intake pre-execution review

One actionable P2 remains; no P1 found in the inspected request/credential/path logic.

[P2] The claimed strict 180-second bound does not fully cover DNS. fetch invokes urllib opener.open, which resolves hostnames through socket.getaddrinfo. CPython calls libc getaddrinfo with the GIL released; a Python SIGALRM callback need not execute until that C call returns. The socket timeout passed to opener.open does not supply a deadline to getaddrinfo. A resolver call begun near the deadline can therefore continue beyond it before the Python exception is processed. The comment claiming DNS interruption is stronger than the implementation proves. Use a qualified bounded resolver, or place only the nonroot downloader in an owned worker process with an independent parent wall-clock watchdog and verified termination/reaping. This does not require Docker, sudo, a daemon, or a container. No resolver failure or real-host overrun was reproduced in this read-only review. Sources: [Python signal handling](https://docs.python.org/3.12/library/signal.html), [pinned CPython socket implementation](https://raw.githubusercontent.com/python/cpython/v3.12.15/Modules/socketmodule.c).

Within the remaining reviewed scope, this replacement removes the earlier privileged Docker CLI/daemon lifetime issue. It requests only pinned public OCI material, explicitly disables proxy discovery, validates HTTPS destinations against the fixed registry/CDN policy and strips Authorization on every manual redirect. Manifest/config/layers are bounded and hashed before being recorded as verified artifacts. The fresh nonce root and exclusive blob creation keep writes in the owned intake directory; failures retain partial files and record file sizes/free bytes/delta without emitting request URLs, headers, tokens or raw exceptions. It contains no Docker/subprocess/container execution or credential/config/group mutation. Receipt flags explicitly keep Engine image, runtime notices and numerical qualification false.

Actual reviewed script SHA-256: dd6ad79b3f4c78b4f2d94a732a712f93fa376846db3ef2a5735306e5fb155242.

Review method: local source read plus official CPython source/documentation only. No remote execution, download, test, source modification, runtime/image/native certification or repeated architectural review. This file is the only review artifact written.

## Watchdog correction closeout

The DNS P2 is addressed in the new watchdog version by static inspection. No new substantive P1/P2 found in this correction. Network/DNS/HTTP work runs only in the exact nonroot fork child; the parent independently checks its wall deadline and disk limits. The parent is the sole waitpid owner under the checked default SIGCHLD policy. Cancellation uses the child's pidfd; if pidfd capture failed, only that still-unreaped direct child is signalled, so its PID is not available for reuse by another process. Child termination has a separate five-second reaping budget; failure to reap is labelled NOT_PROVEN and retains exit 1 rather than claiming quiescence.

The fixed --watchdog-counterexample selects a two-second deadline and pauses before the first network request. Its source reaches the actual cancellation/reaping path without Docker, sudo, subprocess descendants or network intake. No actual fixture run or outcome is asserted here. Parent receipts are written after the cleanup attempt and include reaping state, retained blob sizes, current free bytes and delta; the child result is bounded before reading. Runtime/image/native qualification remains false.

Actual reviewed corrected SHA-256: 3ebbba8e896d28297c32cfa4d70bc54ab14b3401edb00992e1cfb4960c9557c9.

Only the watchdog correction was inspected; no download, remote execution, test, source change, old architectural review or runtime/image/native certification performed.
