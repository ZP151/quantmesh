import hashlib,json,os,shutil,subprocess,stat
from pathlib import Path
from datetime import datetime,timezone
root=Path('/home/ubuntu/quantmesh-numeric-materialization-4e00a5cecd0047fa9d5aa71c020a077a')
assert os.getuid()!=0 and root.resolve()==root and root.stat().st_uid==os.getuid() and stat.S_IMODE(root.stat().st_mode)==0o700
owner=json.loads((root/'ownership.json').read_bytes())
def command(args):
    r=subprocess.run(args,capture_output=True,timeout=15)
    assert r.returncode==0 and len(r.stdout)<=65536
    return json.loads(r.stdout)
engine=command(['sudo','-n','/usr/bin/timeout','-k','2s','10s','/usr/bin/env','-i','PATH=/usr/sbin:/usr/bin:/sbin:/bin',
                '/usr/bin/docker','--config',str(root/'unused-empty-docker-config'),'--host','unix:///var/run/docker.sock',
                'info','--format','{{json .}}'])
assert engine['ServerVersion']=='29.9.0' and engine['Containers']==0 and engine['Images']==0
ts=command(['/usr/bin/tailscale','status','--json'])
assert ts['BackendState']=='Running' and ts['Self']['Online'] and ts['Self']['HostName']=='quantmesh-research-8gb'
phases={}
for name in ['virtual-notice-intake','virtual-notice-intake-with-common-licenses']:
    phase=root/name;receipt=json.loads((phase/'notice-intake-receipt.json').read_bytes())
    assert receipt['exit']==0 and receipt['worker_reaped'] and not receipt['container_started']
    inv=next(f for f in receipt['files'] if f['path']=='virtual-file-inventory.json')
    actual=hashlib.sha256((phase/'virtual-file-inventory.json').read_bytes()).hexdigest()
    assert inv['sha256']==actual
    nodes=json.loads((phase/'virtual-file-inventory.json').read_bytes())
    common=[dict(path=p,sha256=n['sha256'],bytes=n['size']) for p,n in nodes.items()
            if p.startswith('usr/share/common-licenses/') and n['kind']=='regular']
    if name.endswith('with-common-licenses'):
        assert len(common)==14
        for file in common:
            preserved=phase/'notice-by-sha256'/file['sha256']
            assert preserved.is_file() and preserved.stat().st_size==file['bytes']
            assert hashlib.sha256(preserved.read_bytes()).hexdigest()==file['sha256']
    phases[name]=dict(receipt_sha256=hashlib.sha256((phase/'notice-intake-receipt.json').read_bytes()).hexdigest(),
                     virtual_inventory_sha256=actual,common_license_bodies=common,
                     actual_notice_files=receipt['preserved_unique_notice_files'])
free=shutil.disk_usage('/').free
assert owner['free_before']-free<=500000000 and free>=50000000000
receipt=dict(exit=0,at_utc=datetime.now(timezone.utc).isoformat(),root=str(root),
             engine_id=engine['ID'],engine_version=engine['ServerVersion'],images=0,containers=0,
             private_tailnet_online=True,host_free_bytes=free,phase1_host_introduced_bytes=owner['free_before']-free,
             owned_logical_bytes=sum(p.stat().st_size for p in root.rglob('*') if p.is_file()),phases=phases,
             image_materialized=False,actual_runtime_qualified=False,numerical_certificate=False,
             production_research_services_enabled=False,full_option_A_complete=False)
(root/'source-after-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
