"""Own non-root, bounded feature build; no database or application listener."""
import hashlib
import json
import os
import resource
import shutil
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

root=Path('/home/ubuntu/quantmesh-pg-tls-qualification-576db8859b72410b8fe8895845b2ae6e')
owner=json.loads((root/'ownership.json').read_text())
assert owner['nonce']=='576db8859b72410b8fe8895845b2ae6e' and root.resolve()==root
assert os.getuid()==owner['uid']!=0 and root.stat().st_uid==os.getuid()
assert shutil.disk_usage('/').free>=50000000000
source=root/'postgresql-18.6'
assert hashlib.sha256((root/'postgresql-18.6.tar.bz2').read_bytes()).hexdigest()==owner['source_sha256']
assert (root/'dependency-install.exit').read_text().strip()=='0'
prefix=root/'prefix'
assert not prefix.exists()
build=root/'build'
build.mkdir(mode=0o700)

def limits():
    resource.setrlimit(resource.RLIMIT_AS,(2147483648,2147483648))
    resource.setrlimit(resource.RLIMIT_CPU,(900,900))
    resource.setrlimit(resource.RLIMIT_NPROC,(128,128))
    os.sched_setaffinity(0,{0,1})

def phase(name,argv,timeout):
    path=root/(name+'.log')
    start=time.monotonic()
    with path.open('xb') as log:
        process=subprocess.Popen(argv,cwd=build,stdout=log,stderr=subprocess.STDOUT,
                                 start_new_session=True,preexec_fn=limits)
        try:
            while process.poll() is None:
                if time.monotonic()-start>timeout or path.stat().st_size>4194304:
                    raise TimeoutError('owned build bound')
                if owner['free_before']-shutil.disk_usage('/').free>5000000000:
                    raise ValueError('owned filesystem bound')
                time.sleep(1)
        finally:
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL)
                    process.wait(timeout=5)
        (root/(name+'.exit')).write_text(str(process.returncode)+'\n')
        assert process.returncode==0
    return round(time.monotonic()-start,3)

durations={}
durations['configure']=phase('configure',[str(source/'configure'),'--prefix='+str(prefix),
                                        '--with-ssl=openssl','--with-icu','--with-readline','--with-zlib'],120)
config=(build/'src/include/pg_config.h').read_text()
for flag in ('USE_OPENSSL','USE_ICU','HAVE_LIBREADLINE','HAVE_LIBZ'):
    assert '#define '+flag+' 1' in config
durations['make']=phase('make',['make','-j2'],900)
durations['install']=phase('install',['make','install'],180)
version=subprocess.run([str(prefix/'bin/postgres'),'--version'],capture_output=True,text=True,check=True,timeout=10).stdout.strip()
assert version=='postgres (PostgreSQL) 18.6'
binaries={name:hashlib.sha256((prefix/'bin'/name).read_bytes()).hexdigest()
          for name in ('postgres','initdb','pg_ctl','pg_controldata','pg_dump','pg_restore','psql','pg_config')}
introduced=owner['free_before']-shutil.disk_usage('/').free
assert introduced<=5000000000 and shutil.disk_usage('/').free>=50000000000
receipt=dict(at_utc=datetime.now(timezone.utc).isoformat(),nonce=owner['nonce'],root=str(root),prefix=str(prefix),
             source_sha256=owner['source_sha256'],version=version,features=['OpenSSL','ICU','readline','zlib'],
             binaries=binaries,durations_seconds=durations,introduced_host_filesystem_bytes=introduced,
             postgres_started=False,TLS_protocol_qualified=False,production_services_enabled=False,numerical_certificate=False)
(root/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
