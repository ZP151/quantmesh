"""Fixed synthetic independent observer, no vendor/backend/network execution."""
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path('/mnt/c/Users/15492/.codex-clean/worktrees/0038-research-integration/QuantMesh')
STAGE = ROOT / 'deploy/aws/opend/stage_console.py'
FILES = ['deploy/aws/opend/stage_console.py', 'deploy/aws/opend/quantmesh-opend-stage@.service',
         'tests/test_opend_staging_window.py', 'docs/runbooks/opend-staging-window.md']
started = time.monotonic()
proof = {'reviewed_commit': 'b623a56891a5058d8f86eac8387f6bb88acef5b8', 'checks': {},
         'scope': 'OWNED_SYNTHETIC_INDEPENDENT_OBSERVER', 'production_release_qualified': False,
         'root_manager_backend_source_host': 'mocked_or_absent',
         'file_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in FILES}}
proc = handle = None
with tempfile.TemporaryDirectory(prefix='quantmesh-stage-observer-', dir='/var/tmp') as root:
    try:
        os.chmod(root, 0o700)
        # Only fixed stdlib auxiliary sibling; self-expiry bounds unavailable-handle cleanup.
        proc = subprocess.Popen([sys.executable, '-I', '-S', '-B', '-c',
            'import signal,time; signal.alarm(75); time.sleep(75)'],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env={'PATH': '/usr/bin:/bin', 'HOME': root, 'TMPDIR': root}, cwd=root)
        handle = os.pidfd_open(proc.pid)
        default = subprocess.run([sys.executable, '-I', '-S', '-B', str(STAGE)],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=10, cwd=root, env={'PATH': '/usr/bin:/bin', 'HOME': root, 'TMPDIR': root})
        assert default.returncode == 2 and default.stderr == b''
        preflight = json.loads(default.stdout)
        assert preflight['scope'] == 'PREFLIGHT_NO_EFFECT'
        proof['checks']['default_pending_exit2'] = True
        fixture = subprocess.run([sys.executable, '-I', '-S', '-B', str(STAGE), '--owned-fixture'],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=80, cwd=root, env={'PATH': '/usr/bin:/bin', 'HOME': root, 'TMPDIR': root})
        assert fixture.returncode == 0 and fixture.stderr == b''
        receipt = json.loads(fixture.stdout)
        assert receipt['status'] == 'passed' and receipt['all_owned_children_terminal']
        assert receipt['owned_root_removed'] and not Path(receipt['root']).exists()
        assert receipt['elapsed_seconds'] < 90
        flags = ['production_release_qualified', 'source_host_private_input_verified',
                 'private_input_verified', 'sdk_wire_verified', 'server_startup_verified',
                 'operator_authenticated', 'installation_approved', 'market_verified']
        assert all(receipt[name] is False for name in flags)
        proof['checks']['all_qualification_flags_false'] = True
        expected = {'expiry': -signal.SIGALRM, 'hup': -signal.SIGHUP,
                    'parent_loss': -signal.SIGKILL, 'blocked': -signal.SIGTERM,
                    'missing_handle': 40, 'registration_interrupted': 40}
        pids = {receipt['sibling_identity']['pid']}
        for name, code in expected.items():
            case = receipt['cases'][name]
            assert case['terminal'] and case['sibling_survived'] and case['returncode'] == code
            if name in {'missing_handle', 'registration_interrupted'}:
                assert case['released'] is False
            pids.add(case['identity']['pid'] if 'identity' in case else case['pid'])
            proof['checks'][name] = True
        assert len(pids) == 7
        assert all(not Path('/proc', str(pid)).exists() for pid in pids)
        assert not select.select([handle], [], [], 0)[0] and proc.poll() is None
        proof['checks']['seven_reported_fixture_pids_absent'] = True
        proof['checks']['independent_known_sibling_survived'] = True
        proof['fixture_receipt'] = receipt
        proof['limits'] = ['root/manager/backend/source-host absent', 'intermediary parent is reaped internally, not independently sampled',
                           'no actual tmux, cgroup, SSH detach, vendor, login, SDK or market evidence']
    finally:
        if proc is not None:
            if handle is not None:
                if not select.select([handle], [], [], 0)[0]:
                    signal.pidfd_send_signal(handle, signal.SIGTERM)
                proc.wait(timeout=4)
                proof['checks']['independent_sibling_reaped'] = bool(select.select([handle], [], [], 0)[0])
                os.close(handle)
            else:
                proc.wait(timeout=80)
    proof['elapsed_seconds'] = round(time.monotonic() - started, 6)
    assert proof['elapsed_seconds'] < 90
    proof['status'] = 'passed'
print(json.dumps(proof, sort_keys=True))
