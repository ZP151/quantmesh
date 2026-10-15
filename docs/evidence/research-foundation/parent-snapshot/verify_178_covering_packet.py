"""Read sealed bytes only; does not rerun tests or grant native admission."""
import hashlib
import json
import tarfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
packet = root/'output/178-worker-directory-association-20261014'
files = {
    'src/quantmesh/research/_fixture_handles.py',
    'src/quantmesh/research/fixture_snapshot.py',
    'src/quantmesh/research/job_runner.py',
    'tests/test_fixture_snapshot.py',
    'tests/test_research_job_runner.py',
}
seal_path = packet/'SHA256.json'
assert seal_path.stat().st_size <= 65536
seal = json.loads(seal_path.read_bytes())
assert isinstance(seal,dict) and 1 <= len(seal) <= 64
for name,row in seal.items():
    path = Path(name)
    assert not path.is_absolute() and '..' not in path.parts
    p = packet/path
    assert not p.is_symlink() and p.is_file() and p.stat().st_size <= 262144
    raw = p.read_bytes()
    assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256']
pins = json.loads((packet/'source-hashes.json').read_bytes())
assert pins['base']=='f0093aa6d7853ebad9f70f938fbfae7500b4e1b1'
assert set(pins['files'])==files
for name,row in pins['files'].items():
    raw = (root/name).read_bytes()
    assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256']
with tarfile.open(packet/'source.tar.gz',mode='r:gz') as archive:
    members=archive.getmembers()
    assert len(members)==5 and {m.name for m in members}==files
    for m in members:
        assert m.isfile() and m.size<=131072
        raw = archive.extractfile(m).read(131073)
        assert raw==(root/m.name).read_bytes()
for name in ('planner-cover','receipt-fix','windows-final','lint','format','diff-check'):
    assert int((packet/(name+'.exit')).read_text())==0
assert int((packet/'red.exit').read_text())!=0
assert int((packet/'affected.exit').read_text())!=0
for name in ('planner-cover-resources.json','windows-final-receipt.json'):
    receipt=json.loads((packet/name).read_bytes())
    assert receipt['source_hashes']=={p: pins['files'][p]['sha256'] for p in files}
oldseal=root/'output/177-worker-parent-snapshot-20261014/SHA256.json'
assert hashlib.sha256(oldseal.read_bytes()).hexdigest()==pins['old177_seal']
resource=json.loads((packet/'resource-receipt.json').read_bytes())
assert resource['scope_upper_with_metadata_reserve']<=600000
assert resource['measured']['owned_test_bytes']<=2000000
assert resource['measured']['full_upper']<=24000000
text = (packet/'planner-cover.log').read_text()
assert '43 passed, 1 deselected' in text
assert '5 passed' in (packet/'receipt-fix.log').read_text()
assert '3 passed' in (packet/'windows-final.log').read_text()
assert '2 failed, 32 passed, 21 skipped' in (packet/'affected.log').read_text()
result = dict(exit=0,sealed_members=len(seal),source_members=5,
    current_source_and_packet_hashes_match=True,
    final_Linux_covering='43passed/1deselected',leaf_refusal_covering='5passed',
    Windows_unsupported_profile_guard='3passed/0skip',
    original_affected='2failed/32passed/21skipped retained; specific corrections separately verified',
    tests_rerun=False,native_or_numerical_or_production_certificate=False,
    P2_disposition='held no-follow intended objects/relative I/O and persistent membership refusal covered',
    full_Option_A_complete=False)
(root/'output/0038-parent-snapshot-covering-accepted.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
