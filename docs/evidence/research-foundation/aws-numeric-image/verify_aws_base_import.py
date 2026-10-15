"""Read-only reconciliation by pinned OCI content ID; retain failed tag lookup."""
import hashlib,json,os,shutil,stat,subprocess
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path('/home/ubuntu/quantmesh-numeric-materialization-4e00a5cecd0047fa9d5aa71c020a077a')
PHASE=ROOT/'engine-import'
MANIFEST='2ed6491b93cd49272ee6de2b5a38440c3448360322c089fc23e370722d74179d'
CONFIG='4f228bc1cbcfc794e4878312cfc241d368eff55a21c08d1e2bb263116c4ef524'
ENGINE='cfe71bf3-9059-4059-887d-ac401f2283ec'
TAG='quantmesh-numeric-base:4e00a5cecd0047fa9d5aa71c020a077a'
result=dict(read_only=True,actual_runtime_qualified=False,numerical_certificate=False,
    production_research_services_enabled=False,full_option_A_complete=False)
def require(ok,reason):
    if not ok: raise ValueError(reason)
def read(p,limit):
    require(p.resolve()==p and not any(q.is_symlink() for q in (p,*p.parents)),'links')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as f:
        st=os.fstat(f.fileno())
        require(stat.S_ISREG(st.st_mode) and st.st_uid==os.getuid() and st.st_nlink==1 and 0<st.st_size<=limit,'owned_regular')
        b=f.read(limit+1);after=os.fstat(f.fileno());path=p.lstat()
        shape=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns,s.st_mode,s.st_uid,s.st_nlink)
        require(len(b)==st.st_size and shape(st)==shape(after)==shape(path),'stable')
        return b
def observe(args):
    r=subprocess.run(['sudo','-n','/usr/bin/timeout','-k','2s','10s','/usr/bin/env','-i',
        'PATH=/usr/sbin:/usr/bin:/sbin:/bin','/usr/bin/docker','--config',str(PHASE/'empty-config'),
        '--host','unix:///var/run/docker.sock',*args],capture_output=True,timeout=15)
    require(r.returncode==0 and len(r.stdout)<=65536 and not r.stderr,'observer')
    return json.loads(r.stdout)
try:
    require(os.getuid()!=0 and ROOT.resolve()==ROOT and ROOT.stat().st_uid==os.getuid(),'owned_root')
    old=json.loads(read(PHASE/'import-receipt.json',16384))
    require(old['exit']==1 and old['reason']=='observer_result' and old['load_cli_exit']==0
        and old['before_engine']['ID']==ENGINE and old['before_engine']['Images']==0
        and old['before_engine']['Containers']==0,'original_actual_import')
    require(read(PHASE/'load.log',65536).decode().strip()=='Loaded image: '+TAG,'sole_load_success')
    raw_manifest=read(ROOT/'blobs'/MANIFEST,65536);raw_config=read(ROOT/'blobs'/CONFIG,65536)
    require(hashlib.sha256(raw_manifest).hexdigest()==MANIFEST and hashlib.sha256(raw_config).hexdigest()==CONFIG,'source_pins')
    manifest=json.loads(raw_manifest);config=json.loads(raw_config)
    require(manifest['config']['digest']=='sha256:'+CONFIG and manifest['config']['size']==len(raw_config),'manifest_config_chain')
    images=observe(['image','inspect','sha256:'+MANIFEST]);require(type(images)is list and len(images)==1,'single_image')
    image=images[0]
    require(image['Id']=='sha256:'+MANIFEST and image['Os']=='linux' and image['Architecture']=='amd64'
        and image['Config']==config['config'] and image['RootFS']['Layers']==config['rootfs']['diff_ids']
        and image['Descriptor']['digest']=='sha256:'+MANIFEST and image['Descriptor']['size']==len(raw_manifest),'exact_content_identity')
    engine=observe(['info','--format','{{json .}}']);version=observe(['version','--format','{{json .}}'])
    require(engine['ID']==ENGINE and engine['Images']==1 and engine['Containers']==0 and engine['ServerVersion']=='29.9.0'
        and version['Server']['GitCommit']=='a5b58c9' and version['Client']['GitCommit']=='f415da8','same_engine_build')
    owner=json.loads(read(ROOT/'ownership.json',16384));free=shutil.disk_usage('/').free;introduced=owner['free_before']-free
    require(free>=50000000000 and introduced<=500000000,'original_disk_gate')
    result.update(exit=0,physical_base_imported=True,physical_image_id=image['Id'],
        physical_config=image['Config'],exact_rootfs_diff_ids=image['RootFS']['Layers'],
        source_manifest_sha256=MANIFEST,source_config_sha256=CONFIG,
        actual_engine_id=ENGINE,images=1,containers=0,host_free_bytes=free,phase1_host_introduced_bytes=introduced,
        original_import_exit=1,original_failure='human_reference_tag_lookup',original_failure_retained=True,
        verified_by='immutable OCI image ID, exact descriptor/config/source hashes and ordered diff IDs',
        daemon_import_completion='normal_load_request_returned_and_exact_image_observed',
        actual_Engine_image_qualified=False,image_runtime_not_yet_executed=True)
except BaseException as e:
    result.update(exit=1,physical_base_imported=False,failure_kind=type(e).__name__)
    if type(e)is ValueError:result['reason']=str(e)
result['at_utc']=datetime.now(timezone.utc).isoformat()
print(json.dumps(result))
raise SystemExit(result['exit'])
