# Owned terminal backend audit

Issue #169, local prerequisite only. Completed native verifier13a1 made no
tracked changes. Its clean Git head remains5aab2346; do not redispatch it.
The coordinator independently reparsed the signed metadata, source/package
hashes, complete executing closure, mappings and kernel/cleanup receipts:
216 checks passed, exit0. The root checker writes only new root receipts;
it does not rerun tmux or mutate the original receipts/socket.

Exact Ubuntu tmux3.4-1ubuntu0.1 amd64 package SHA256 is
2913e17aa61879d1f905aab6f374f153f1ece63aefba1b996e387325d1d5338d;
executable SHA256 is034b15c64035f783d43862f2775eb4828f61571ca62c8199796000b97d556ecd.
Five Ubuntu-signed indices support20 packages,17 source groups and27 executing
ELF files, plus authenticated UTF8 locale data. Exact older libevent is retained
from the signed September24 snapshot for reproducibility. This does not certify
current security suitability for a production host. External unmodified LGPL
OS/helper dependencies are audited separately from permissive application
admission; source, notices and redistribution obligations remain retained.

One fresh owned user/net/mount/PID namespace fixture proves foreground tmux
continues after its detached creation client exits. Two separate metadata
clients see the same live server/pane. This is not an interactive SSH detach
witness. Actual pane0600/echo-off attributes are set by the synthetic pane,
not guaranteed by tmux. Server exit0, pane HUP/reap, owned namespace termination,
two sibling-survival checks and identity-bound socket cleanup pass within
0.679403 seconds including cleanup. No terminal bytes are read or injected.

Earlier acquisition/parser/notice/runtime/socket failures remain failures.
libutempter writes only the fixture's private utmp/wtmp; libsystemd has no real
manager here. Actual host global-record suppression, systemd/cgroup ownership,
descendant cleanup, private human input, vendor/SDK/authentication and market
source acceptance all remain pending. Every production/source/auth flag is false.

`sha256.json` covers45 raw byte streams, including root verification provenance.
`SHA256SUMS.json` retains the complete4457-file external audit inventory. Packages,
source archives/code, binary indices, extracted executables and native fixtures
remain outside Git in the ignored13a1 audit and `/tmp/quantmesh-tmux-audit-85vknab4`.
Neither worktree nor full external archive is authorized for removal. This archive
is not a host installation, authentication window or release permit.
