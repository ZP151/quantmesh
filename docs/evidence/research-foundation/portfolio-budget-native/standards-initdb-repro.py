import json
import os
import signal
import sys
import tempfile
import time
from pathlib import Path

borrowed_root = Path('/var/tmp/quantmesh-portfolio-witness-r_a4n26m')
sys.path.insert(0, str(borrowed_root / 'checkout'))
from tools import qualify_portfolio_budgets as q

os.umask(0o077)
output = Path(tempfile.mkdtemp(prefix='quantmesh-portfolio-standards-initdb-', dir='/var/tmp'))
runner = q.Commands(borrowed_root, output)
password = output / 'password'
q.owned.write_private(password, b'owned-disposable-standards-repro')
binary = borrowed_root / 'prefix/bin/initdb'
postgres = borrowed_root / 'prefix/bin/postgres'
handle = runner.spawn([str(binary), '-D', str(output / 'data'), '-L', str(borrowed_root / 'prefix/share/postgresql'), '--username=fixture_standards', '--pwfile=' + str(password), '--auth=scram-sha-256', '--no-locale', '--encoding=UTF8'], q.environment(borrowed_root), output)
identities = {}
paused = None
result = {'scope': 'OWNED_INITDB_TIMEOUT_DESCENDANT_REPRO_ONLY', 'output': str(output), 'initdb_pid': handle.pid}

def identity(pid):
    proc = Path('/proc') / str(pid)
    return {'pid': pid, 'ticks': q.owned.process_ticks(pid), 'uid': proc.stat().st_uid, 'exe': str((proc / 'exe').resolve()), 'nonce': b'QM_BACKUP_COMMAND_OWNER=' + handle.nonce.encode() in (proc / 'environ').read_bytes().split(b'\0')}

try:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        descendants = {handle.pid}
        for _ in range(3):
            for entry in Path('/proc').iterdir():
                if not entry.name.isdecimal():
                    continue
                try:
                    fields = (entry / 'stat').read_text().rsplit(')', 1)[1].split()
                    if int(fields[1]) in descendants:
                        descendants.add(int(entry.name))
                except (OSError, ValueError):
                    pass
        for pid in descendants - {handle.pid}:
            try:
                item = identity(pid)
                if item['uid'] == os.getuid() and item['nonce']:
                    identities[pid] = item
                    if item['exe'] == str(postgres):
                        paused = pid
                        os.kill(pid, signal.SIGSTOP)
                        break
            except OSError:
                pass
        if paused:
            break
        time.sleep(0.002)
    result['owned_bootstrap_paused_pid'] = paused
    if paused:
        try:
            runner.collect(handle, 'initdb-paused-bootstrap-repro', timeout=0.2)
        except (ValueError, OSError) as exc:
            result['collect_error'] = str(exc)
        result['initdb_terminal_exit'] = handle.process.poll()
        try:
            current = identity(paused)
            result['bootstrap_after_parent_cleanup'] = current
            result['bootstrap_alive_after_parent_cleanup'] = current == identities[paused]
        except OSError:
            result['bootstrap_alive_after_parent_cleanup'] = False
    else:
        result['not_reproduced'] = 'bootstrap phase not observed'
finally:
    # Signal only children positively owned by this repro, never unknown PIDs.
    for pid, saved in identities.items():
        try:
            if identity(pid) == saved:
                os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    handle.close()
    password.unlink(missing_ok=True)
    time.sleep(0.1)
    result['repro_owned_cleanup_issued'] = True
    q.durable(output / 'result.json', q.owned.canonical(result))
    print(json.dumps(result))
