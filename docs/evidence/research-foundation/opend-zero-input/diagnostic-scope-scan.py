import json
import os
from pathlib import Path

scope = '/var/tmp/quantmesh-opend-zero-input-f88g68z1/'
matched, inaccessible = [], 0
for path in Path('/proc').iterdir():
    if not path.name.isdigit() or int(path.name) == os.getpid():
        continue
    try:
        if path.stat().st_uid != os.getuid():
            continue
        executable = os.readlink(path / 'exe')
    except FileNotFoundError:
        continue
    except PermissionError:
        inaccessible += 1
        continue
    if executable.startswith(scope):
        matched.append(int(path.name))
receipt = {'scope':scope, 'uid':os.getuid(), 'owned_executable_pids':matched,
           'inaccessible_same_uid_processes':inaccessible,
           'scope_complete':inaccessible==0,
           'no_readable_owned_executable_remaining':not matched,
           'initial_scan_error':'non-owned-/proc/1/exe-permission-denied'}
out = Path('/mnt/c/Users/15492/.codex-clean/worktrees/6e1e/QuantMesh/output/0038-opend-zero-input')
(out/'scope-scan.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
print(json.dumps(receipt))
