"""Independent observations of only the fixed fresh synthetic processes."""
import hashlib
import json
import os
from pathlib import Path
import select
import stat
import subprocess
import sys
import time

CHECKOUT = Path(__file__).resolve().parent
sys.path.insert(0, str(CHECKOUT))
from tools import qualify_opend_private_terminal as terminal

created = []
release_checks = []
wait_checks = []
original_popen = subprocess.Popen
original_release = terminal._OwnedChild.release
original_wait = terminal._OwnedChild.wait

def capture(*args, **kwargs):
    proc = original_popen(*args, **kwargs)
    created.append((proc, args[0][7]))
    return proc

def inspect_release(child, slave=None):
    assert not select.select([child.pidfd], [], [], 0)[0]
    fdinfo = Path(f'/proc/self/fdinfo/{child.pidfd}').read_text()
    fields = dict(line.split(':', 1) for line in fdinfo.splitlines() if ':' in line)
    assert int(fields['Pid'].strip()) == child.proc.pid
    witness = {'pidfd_kernel_pid_matches': True, 'before_release_live': True,
               'registered_uid': child.identity['uid'], 'stdio_verified': False}
    if child.admission is not None:
        metadata = [os.stat(f'/proc/{child.proc.pid}/fd/{fd}') for fd in (0, 1, 2)]
        assert len({(s.st_dev, s.st_ino, s.st_rdev) for s in metadata}) == 1
        admitted = child.admission['descriptors'][0]
        for info in metadata:
            assert stat.S_ISCHR(info.st_mode)
            assert stat.S_IMODE(info.st_mode) == 0o600
            assert info.st_uid == os.getuid()
            assert (info.st_dev, info.st_ino, info.st_rdev) == (
                admitted['device'], admitted['inode'], admitted['rdev'])
        import termios
        attrs = termios.tcgetattr(slave)
        assert not attrs[3] & (termios.ECHO | termios.ECHONL)
        witness['stdio_verified'] = True
    release_checks.append(witness)
    return original_release(child, slave)

def inspect_wait(child):
    code = original_wait(child)
    assert select.select([child.pidfd], [], [], 0)[0]
    assert child.proc.returncode is not None
    wait_checks.append({'pidfd_kernel_terminal': True, 'retained_popen_reaped': True,
                        'returncode': code})
    return code

subprocess.Popen = capture
terminal._OwnedChild.release = inspect_release
terminal._OwnedChild.wait = inspect_wait
started = time.monotonic()
receipt = terminal.run_owned_fixture()
elapsed = time.monotonic() - started
assert receipt['status'] == 'passed'
assert elapsed < 90
assert len(created) == 8
assert len(release_checks) == 5
assert sum(check['stdio_verified'] for check in release_checks) == 4
assert all(proc.returncode is not None for proc, role in created)
assert all(case['sibling_survived'] for case in receipt['cases'].values())
assert not Path(receipt['root']).exists()
assert receipt['input']['accepted_bytes'] == 65
assert receipt['input']['marker_not_echoed'] and receipt['input']['digest_matched']
assert receipt['input']['observed_bytes'] == 4
for key in ['production_release_qualified', 'source_host_private_input_verified',
            'private_input_verified', 'sdk_wire_verified', 'server_startup_verified',
            'operator_authenticated', 'installation_approved', 'market_verified']:
    assert receipt[key] is False
proof = {'status': 'passed', 'scope': 'OWNED_LOCAL_PRIVATE_TERMINAL_FIXTURE',
         'elapsed_seconds': elapsed, 'owned_child_count': len(created),
         'all_retained_children_reaped': True, 'root_removed_independently': True,
         'release_kernel_checks': release_checks, 'wait_kernel_checks': wait_checks,
         'children': [{'role': role, 'returncode': proc.returncode} for proc, role in created],
         'receipt': receipt,
         'import_path': str(Path(terminal.__file__).resolve()),
         'import_sha256': hashlib.sha256(Path(terminal.__file__).read_bytes()).hexdigest()}
print(json.dumps(proof, sort_keys=True))
