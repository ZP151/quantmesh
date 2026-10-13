import hashlib
import json
import shutil
import tarfile
from pathlib import Path

repo = Path('/mnt/c/Users/15492/.codex-clean/worktrees/a718/QuantMesh')
phase = repo / 'output/172-task2-software-checkpoint1-20261013'
owned = Path('/var/tmp/quantmesh-linux-native-90afdbee6add43169483520e384539ae')
assert json.loads((owned / 'ownership.json').read_text())['nonce'] == '90afdbee6add43169483520e384539ae'
source_names = [
    'src/quantmesh/research/worker_build.py',
    'src/quantmesh/research/job_runner.py',
    'tests/test_worker_build.py',
    'tests/test_research_job_runner.py',
    'docs/runbooks/linux-research-worker.md',
    'docs/superpowers/plans/2026-10-13-linux-numerical-worker.md',
]
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def size(path):
    return sum(p.stat().st_size for p in path.rglob('*') if p.is_file() and not p.is_symlink())
def observation():
    files = size(owned / 'task2-tests')
    source = sum((repo / n).stat().st_size for n in source_names)
    evidence = size(phase)
    value = dict(test_fixture_bytes=files, source_bytes=source, evidence_bytes=evidence,
                 introduced_logical_upper_bound=files + 2 * source + evidence + 50000,
                 free_c_bytes=shutil.disk_usage('/mnt/c').free)
    assert value['introduced_logical_upper_bound'] <= 10000000
    assert value['free_c_bytes'] >= 50000000000
    return value
before = observation()
freeze = Path('/mnt/c/Users/15492/.codex-clean/worktrees/0038-research-integration/QuantMesh/output/0038-linux-native-admission/root-task2-interface-freeze.json')
(phase / 'root-task2-interface-freeze.json').write_bytes(freeze.read_bytes())
sources = {}
for name in source_names:
    entry = dict(sha256=sha(repo / name), bytes=(repo / name).stat().st_size)
    if name.endswith('.py'):
        entry['tested_overlay_sha256'] = sha(owned / 'source' / name)
        assert entry['sha256'] == entry['tested_overlay_sha256']
    sources[name] = entry
(phase / 'source-seal.json').write_text(json.dumps(dict(
    head='042fb0b491c13f4535bddbb61290b191d29b1790',
    head_tree='06c80ca3427808c558ea0ef65ff3865ddfff52ec',
    branch='codex/0038-linux-worker-jobs', uncommitted=True,
    qualification='review-incomplete/remaining-loaded-dependency-origin-P2',
    source_semantics='four-file targeted overlay on prior owned c545 clone; not whole042 clean checkout',
    files=sources), indent=2) + '\n')
archive = phase / 'checkpoint1-review-stop.tar.gz'
assert not archive.exists()
excluded = {archive.name, 'HASHINDEX.json', 'seal-observation.json'}
inputs = [(p, 'evidence/' + p.name) for p in sorted(phase.iterdir()) if p.is_file() and p.name not in excluded]
inputs.extend((repo / name, 'source/' + name) for name in source_names)
with tarfile.open(archive, 'w:gz') as tf:
    for path, name in inputs:
        tf.add(path, arcname=name, recursive=False)
with tarfile.open(archive, 'r:gz') as tf:
    members = tf.getmembers()
    assert len(members) == len(inputs)
    expected = {name: sha(path) for path, name in inputs}
    for member in members:
        assert member.isfile() and hashlib.sha256(tf.extractfile(member).read()).hexdigest() == expected[member.name]
index = dict(archive=dict(name=archive.name, bytes=archive.stat().st_size, sha256=sha(archive), members=len(inputs)),
             files={p.name: dict(bytes=p.stat().st_size, sha256=sha(p)) for p in sorted(phase.iterdir()) if p.is_file() and p.name not in {'HASHINDEX.json', 'seal-observation.json'}})
(phase / 'HASHINDEX.json').write_text(json.dumps(index, indent=2) + '\n')
after = observation()
(phase / 'seal-observation.json').write_text(json.dumps(dict(before=before, after=after,
    software_gate='logical<=10MB/freeC>=50GB', prior_whole_C_5GB_gate='PENDING',
    archive_members_verified=True, current_source_equals_tested_overlay=True,
    no_commit_push_or_native_certificate=True), indent=2) + '\n')
print(json.dumps(dict(archive=index['archive'], observation=after)))
