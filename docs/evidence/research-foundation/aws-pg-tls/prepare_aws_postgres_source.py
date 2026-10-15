"""New approved research host: own source/tool intake, no DB/service start."""
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

SOURCE_SHA = '555610c24d53e4316da5b7d3fc25c279d96856d5e0e23ee308c328c5fa881d9f'
SOURCE_URL = 'https://ftp.postgresql.org/pub/source/v18.6/postgresql-18.6.tar.bz2'
status = json.loads(subprocess.run(['sudo','tailscale','status','--json'],capture_output=True,check=True,timeout=10).stdout)
assert status['BackendState']=='Running' and status['Self']['HostName']=='quantmesh-research-8gb'
assert status['Self']['DNSName']=='quantmesh-research-8gb.tail99d23c.ts.net.'
assert os.getuid()!=0 and shutil.disk_usage('/').free>=50000000000
nonce = uuid.uuid4().hex
owned = Path('/home/ubuntu') / ('quantmesh-pg-tls-qualification-'+nonce)
owned.mkdir(mode=0o700)
assert owned.stat().st_uid==os.getuid() and not owned.is_symlink()
free_before = shutil.disk_usage('/').free
receipt = dict(nonce=nonce,root=str(owned),uid=os.getuid(),free_before=free_before,
               at_utc=datetime.now(timezone.utc).isoformat(),host_identity='verified research8GB private Tailnet',
               source_sha256=SOURCE_SHA,introduced_limit_bytes=5000000000,free_floor_bytes=50000000000)
(owned/'ownership.json').write_text(json.dumps(receipt,indent=2)+'\n')
archive = owned/'postgresql-18.6.tar.bz2'
with urllib.request.urlopen(SOURCE_URL,timeout=30) as response:
    assert response.status==200 and response.geturl()==SOURCE_URL
    with archive.open('xb') as stream:
        length=0
        while chunk:=response.read(1024*1024):
            length+=len(chunk)
            assert length<=30000000
            stream.write(chunk)
assert hashlib.sha256(archive.read_bytes()).hexdigest()==SOURCE_SHA
with tarfile.open(archive,'r:bz2') as packet:
    members=packet.getmembers()
    assert len(members)<=20000 and sum(m.size for m in members)<=300000000
    for member in members:
        parts=Path(member.name).parts
        assert parts and parts[0]=='postgresql-18.6' and '..' not in parts
        assert not Path(member.name).is_absolute() and (member.isfile() or member.isdir())
    packet.extractall(owned,filter='data')
source=owned/'postgresql-18.6'
assert hashlib.sha256((source/'COPYRIGHT').read_bytes()).hexdigest()=='3d6af92ff8a4c2cdf69afb1cf44edea727922f5cd0cf8b5f72b11cdecac8fdfd'
tools={name:shutil.which(name) for name in ('gcc','make','bison','flex','pkg-config','openssl')}
dependencies=['build-essential','bison','flex','pkg-config','libssl-dev','libicu-dev','libreadline-dev','zlib1g-dev']
packages=subprocess.run(['dpkg-query','-W','-f=${Package}\t${Version}\t${Status}\n',*dependencies],capture_output=True,text=True,timeout=10)
states=[]
for line in packages.stdout.splitlines():
    fields=line.split('\t')
    assert len(fields)==3
    states.append(dict(name=fields[0],version=fields[1],installed=fields[2]=='install ok installed'))
owned_bytes=sum(p.stat().st_size for p in owned.rglob('*') if p.is_file())
assert owned_bytes<=5000000000 and shutil.disk_usage('/').free>=50000000000
receipt.update(source_url=SOURCE_URL,source_bytes=length,source_members=len(members),owned_logical_bytes=owned_bytes,
               tools=tools,package_states=states,postgres_started=False,production_services_enabled=False,numerical_certificate=False)
(owned/'source-intake.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
