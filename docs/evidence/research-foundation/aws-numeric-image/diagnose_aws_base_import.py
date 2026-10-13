"""Read-only exact failed import diagnosis; no import, tag or execution."""
import json,subprocess,stat,os
from pathlib import Path
ROOT=Path('/home/ubuntu/quantmesh-numeric-materialization-4e00a5cecd0047fa9d5aa71c020a077a')
PHASE=ROOT/'engine-import'
assert ROOT.resolve()==ROOT and ROOT.stat().st_uid==os.getuid()
def read(p,n):
    assert p.resolve()==p and stat.S_ISREG(p.lstat().st_mode) and p.stat().st_uid==os.getuid() and p.stat().st_size<=n
    return p.read_text()
def query(args):
    r=subprocess.run(['sudo','-n','/usr/bin/timeout','-k','2s','10s','/usr/bin/env','-i',
        'PATH=/usr/sbin:/usr/bin:/sbin:/bin','/usr/bin/docker','--config',str(PHASE/'empty-config'),
        '--host','unix:///var/run/docker.sock',*args],capture_output=True,timeout=15)
    assert len(r.stdout)<=65536 and len(r.stderr)<=65536
    return dict(exit=r.returncode,stdout=r.stdout.decode(),stderr=r.stderr.decode())
tag='quantmesh-numeric-base:4e00a5cecd0047fa9d5aa71c020a077a'
identity='sha256:2ed6491b93cd49272ee6de2b5a38440c3448360322c089fc23e370722d74179d'
out=dict(read_only=True,load=read(PHASE/'load.log',65536),
    retained_receipt=json.loads(read(PHASE/'import-receipt.json',16384)),
    tag=query(['image','inspect',tag]),
    identity=query(['image','inspect',identity]),
    images=query(['image','ls','--no-trunc','--format','{{json .}}']))
print(json.dumps(out))
