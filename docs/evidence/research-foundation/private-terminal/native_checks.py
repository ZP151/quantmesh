"""Local native evidence driver; no network or environment/credential reads."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tarfile

SOURCE = Path('/mnt/c/Users/15492/.codex-clean/worktrees/2088/QuantMesh')
EVIDENCE = SOURCE / 'output/169-private-terminal'
PYTEST = '/var/tmp/quantmesh-bootstrap-krfg8kx6/venv/bin/python'
phase = sys.argv[1]
root = Path(tempfile.mkdtemp(prefix='quantmesh-terminal-check-', dir='/var/tmp'))
os.chmod(root, 0o700)
if phase == 'final':
    with tarfile.open(EVIDENCE / 'candidate.tar') as archive:
        archive.extractall(root, filter='data')
else:
    for relative in ['tools/qualify_opend_private_terminal.py', 'tests/test_opend_private_terminal.py',
                     'pyproject.toml']:
        target = root / relative
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(SOURCE / relative, target)
shutil.copyfile(EVIDENCE / 'native_witness.py', root / 'native_witness.py')
files = {relative: hashlib.sha256((root / relative).read_bytes()).hexdigest()
         for relative in ['tools/qualify_opend_private_terminal.py', 'tests/test_opend_private_terminal.py']}
if phase == 'final':
    relative = 'docs/runbooks/opend-private-terminal-qualification.md'
    files[relative] = hashlib.sha256((root / relative).read_bytes()).hexdigest()
env = {'PATH': '/usr/bin:/bin', 'HOME': str(root), 'TMPDIR': str(root),
       'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'PYTHONDONTWRITEBYTECODE': '1'}
command = [PYTEST, '-B', '-m', 'pytest', 'tests/test_opend_private_terminal.py', '-q',
           '--basetemp', str(root / 'pytest-temp')]
with (EVIDENCE / (phase + '-native-tests.log')).open('wb') as log:
    result = subprocess.run(command, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT,
                            timeout=110, check=False)
(EVIDENCE / (phase + '-native-tests.exit')).write_text(str(result.returncode) + '\n')
(EVIDENCE / (phase + '-native-context.json')).write_text(json.dumps(
    {'root': str(root), 'uid': os.getuid(), 'mode': root.stat().st_mode & 0o777,
     'command': command, 'hashes': files, 'test_exit': result.returncode}, indent=2) + '\n')
print((EVIDENCE / (phase + '-native-tests.log')).read_text()[-7000:])
if phase != 'red' and result.returncode == 0:
    for label, arguments in [('preflight', []), ('fixture', ['--owned-fixture'])]:
        cmd = ['/usr/bin/python3.12', '-I', '-B', 'tools/qualify_opend_private_terminal.py', *arguments]
        with (EVIDENCE / (phase + '-' + label + '.json')).open('wb') as log:
            run = subprocess.run(cmd, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT,
                                 timeout=95, check=False)
        (EVIDENCE / (phase + '-' + label + '.exit')).write_text(str(run.returncode) + '\n')
        print(label, 'exit', run.returncode)
    if phase == 'final':
        cmd = ['/usr/bin/python3.12', '-I', '-B', str(root / 'native_witness.py')]
        with (EVIDENCE / 'final-independent-witness.json').open('wb') as log:
            run = subprocess.run(cmd, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT,
                                 timeout=95, check=False)
        (EVIDENCE / 'final-independent-witness.exit').write_text(str(run.returncode) + '\n')
        print('independent witness exit', run.returncode)
        if run.returncode != 0:
            sys.exit(run.returncode)
sys.exit(result.returncode)
