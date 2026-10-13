"""Signed build-only dependencies on the approved host; no PostgreSQL daemon."""
import json
import shutil
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

root=Path('/home/ubuntu/quantmesh-pg-tls-qualification-576db8859b72410b8fe8895845b2ae6e')
owner=json.loads((root/'ownership.json').read_text())
assert owner['nonce']=='576db8859b72410b8fe8895845b2ae6e' and root.resolve()==root
assert root.stat().st_uid==owner['uid'] and shutil.disk_usage('/').free>=50000000000
status=json.loads(subprocess.run(['sudo','tailscale','status','--json'],capture_output=True,check=True,timeout=10).stdout)
assert status['BackendState']=='Running' and status['Self']['HostName']=='quantmesh-research-8gb'
with urllib.request.urlopen('https://ftp.postgresql.org/pub/source/v18.6/postgresql-18.6.tar.bz2.sha256',timeout=30) as response:
    checksum=response.read(1025).decode()
assert len(checksum)<=1024 and checksum.split()==[owner['source_sha256'],'postgresql-18.6.tar.bz2']
(root/'published-source.sha256').write_text(checksum)
packages=['build-essential','bison','flex','pkg-config','libssl-dev','libicu-dev','libreadline-dev','zlib1g-dev']
simulation=subprocess.run(['sudo','apt-get','--simulate','install','--no-install-recommends',*packages],capture_output=True,text=True,check=True,timeout=30)
assert not any(line.startswith('Remv ') for line in simulation.stdout.splitlines())
(root/'dependency-simulation.log').write_text(simulation.stdout+simulation.stderr)
with (root/'dependency-install.log').open('w') as log:
    result=subprocess.run(['sudo','apt-get','install','-y','--no-install-recommends',*packages],stdout=log,stderr=subprocess.STDOUT,timeout=240)
(root/'dependency-install.exit').write_text(str(result.returncode)+'\n')
assert result.returncode==0 and (root/'dependency-install.log').stat().st_size<=262144
versions=subprocess.run(['dpkg-query','-W','-f=${Package}\t${Version}\t${Status}\n',*packages],capture_output=True,text=True,check=True,timeout=10).stdout
assert all(line.split('\t')[2]=='install ok installed' for line in versions.splitlines())
assert all(shutil.which(name) for name in ('gcc','make','bison','flex','pkg-config','openssl'))
introduced=owner['free_before']-shutil.disk_usage('/').free
assert introduced<=5000000000 and shutil.disk_usage('/').free>=50000000000
receipt=dict(at_utc=datetime.now(timezone.utc).isoformat(),owned_root=str(root),source_published_sha_verified=True,
             installed_build_packages=[dict(name=p.split('\t')[0],version=p.split('\t')[1]) for p in versions.splitlines()],
             introduced_host_filesystem_bytes=introduced,build_complete=False,postgres_started=False,production_services_enabled=False)
(root/'dependency-intake.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
