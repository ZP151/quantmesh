import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

root = Path('/home/ubuntu/quantmesh-pg-tls-qualification-576db8859b72410b8fe8895845b2ae6e')
assert root.resolve() == root and root.stat().st_uid == os.getuid() != 0
protocol = json.loads((root / 'protocol/protocol-receipt.json').read_text())
capture = json.loads((root / 'protocol-capture-failure/protocol-receipt.json').read_text())
assert protocol['exit'] == 0 and protocol['owned_postmaster_stopped']
assert capture['exit'] == 1 and capture['owned_postmaster_stopped']
assert capture['failure']['phase'] == 'forced_ownership_capture_failure'
own_live = []
for item in Path('/proc').iterdir():
    if not item.name.isdigit():
        continue
    try:
        if str((item / 'exe').resolve(strict=True)).startswith(str(root / 'prefix/bin') + '/'):
            own_live.append(int(item.name))
    except (OSError, RuntimeError):
        pass
assert own_live == []
tail = json.loads(subprocess.run(['tailscale', 'status', '--json'], capture_output=True,
                                text=True, timeout=10, check=True).stdout)
assert tail['BackendState'] == 'Running' and tail['Self']['Online']
assert tail['Self']['DNSName'].rstrip('.') == 'quantmesh-research-8gb.tail99d23c.ts.net'
owner = json.loads((root / 'ownership.json').read_text())
free = shutil.disk_usage('/').free
introduced = owner['free_before'] - free
assert free >= 50000000000 and introduced <= 5000000000
assert not (root / 'protocol/data/postmaster.pid').exists()
assert not (root / 'protocol-capture-failure/data/postmaster.pid').exists()
receipt = dict(at_utc=datetime.now(timezone.utc).isoformat(), private_SSH=True,
               tailnet_running=True, tailnet_online=True, own_live_postmasters=own_live,
               owned_pid_files_removed=True, whole_host_introduced_bytes=introduced,
               host_free_bytes=free, protocol_checks=len(protocol['checks']),
               protocol_exit=0, capture_counterexample_exit=1,
               production_services_enabled=False, full_option_A_complete=False)
(root / 'after-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt))
