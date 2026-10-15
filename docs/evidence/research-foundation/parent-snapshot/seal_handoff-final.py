"""Final non-writing gates and a bounded five-file packet; no source staging."""
import gzip,hashlib,io,json,subprocess,sys,tarfile
from run_checks import FILES,OLD,OUT,ROOT,measure

def sha(raw):return hashlib.sha256(raw).hexdigest()
def write(name,value):
    with (OUT/name).open('x') as stream:stream.write(json.dumps(value,separators=(',',':'))+'\n')

before=measure()
sources={name:(ROOT/name).read_bytes() for name in FILES}
buffer=io.BytesIO()
with tarfile.open(fileobj=buffer,mode='w') as archive:
    for name,raw in sources.items():
        info=tarfile.TarInfo(name);info.size=len(raw);info.mode=0o644;info.mtime=0
        archive.addfile(info,io.BytesIO(raw))
packed=gzip.compress(buffer.getvalue(),mtime=0)
assert before['scope_upper']+2*len(packed)+30000<=600000
git=['/mnt/c/Program Files/Git/cmd/git.exe','-C','C:/Users/15492/.codex-clean/worktrees/0038-research-integration/QuantMesh']
base='f0093aa6d7853ebad9f70f938fbfae7500b4e1b1'
assert subprocess.check_output([*git,'rev-parse','HEAD'],text=True).strip()==base
assert not subprocess.check_output([*git,'diff','--cached','--name-only','--',*FILES])
for name,command in (
    ('lint',[sys.executable,'-B','-m','ruff','check','--no-cache',*FILES]),
    ('format',[sys.executable,'-B','-m','ruff','format','--no-cache','--check',*FILES]),
    ('diff-check',[*git,'diff','--check','--',*FILES]),
):
    with (OUT/(name+'.log')).open('xb') as log:
        result=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=30)
    (OUT/(name+'.exit')).write_text(str(result.returncode)+'\n');assert result.returncode==0

hashes={name:{'bytes':len(raw),'sha256':sha(raw)} for name,raw in sources.items()}
cover=json.loads((OUT/'planner-cover-resources.json').read_text())
assert cover['source_hashes']=={name:value['sha256'] for name,value in hashes.items()}
windows=json.loads((OUT/'windows-final-receipt.json').read_text())
assert windows['source_hashes']==cover['source_hashes']
assert sha((OLD/'SHA256.json').read_bytes())=='ffc83b331820803bc981d09205d897a733e0b0a8e2bfc11f6b16d45898c644fa'
oldindex=json.loads((OLD/'SHA256.json').read_text())
assert len(oldindex)==46
for name,record in oldindex.items():
    raw=(OLD/name).read_bytes();assert len(raw)==record['bytes'] and sha(raw)==record['sha256']
write('source-hashes.json',dict(base=base,files=hashes,old177_seal=sha((OLD/'SHA256.json').read_bytes())))

original=json.loads((ROOT.parent.parent/'a718/QuantMesh/output/176-worker-input-authority-20261014/source-pins.json').read_text())
pins={}
for name,record in original['pins'].items():
    raw=subprocess.check_output([*git,'show',base+':'+name]);assert sha(raw)==record[1]
    current=(ROOT/name).read_bytes()
    unchanged=current.replace(b'\r\n',b'\n')==raw.replace(b'\r\n',b'\n')
    assert unchanged or name=='src/quantmesh/research/job_runner.py'
    pins[name]=[record[1],sha(current),unchanged]
native=ROOT.parent.parent/'a718/QuantMesh'
# Protected173/174 WIP exact hashes come from the already-verified177 seal.
preserved=json.loads((OLD/'protected-source-pins.json').read_text())['preserved_a718']
for name,digest in preserved.items():assert sha((native/name).read_bytes())==digest
write('protected-source-pins.json',dict(original=pins,preserved_a718=preserved))
with (OUT/'source.tar.gz').open('xb') as stream:stream.write(packed)
with tarfile.open(fileobj=io.BytesIO(packed),mode='r:gz') as archive:
    assert archive.getnames()==FILES
    for name in FILES:assert archive.extractfile(name).read()==sources[name]

measured=measure()
receipt=dict(measured=measured,final_metadata_copy_reserve=12000,source_archive_bytes=len(packed),
             scope_upper_with_metadata_reserve=measured['scope_upper']+12000,
             old177_members_verified=len(oldindex),
             status='single fix pass ready for root covering acceptance; no whole affected GREEN',
             whole_C='PENDING;524611584B private crash capture unread/unmodified/separately disclosed')
assert receipt['scope_upper_with_metadata_reserve']<=600000
write('resource-receipt.json',receipt)
index={p.relative_to(OUT).as_posix():{'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())}
       for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='SHA256.json'}
write('SHA256.json',index)
after=measure();assert after['scope_upper']<=600000
print(json.dumps(dict(source_hashes=hashes,source_archive_bytes=len(packed),resources=after,seal_sha256=sha((OUT/'SHA256.json').read_bytes()))))
