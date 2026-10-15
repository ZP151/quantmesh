"""One owned no-network immutable-base stdlib probe; no Worker/Agent/job."""
import hashlib,json,os,re,shutil,stat,subprocess,time,uuid
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path('/home/ubuntu/quantmesh-numeric-materialization-4e00a5cecd0047fa9d5aa71c020a077a')
PHASE=ROOT/'canonical-probe'
IMAGE='sha256:2ed6491b93cd49272ee6de2b5a38440c3448360322c089fc23e370722d74179d'
ENGINE='cfe71bf3-9059-4059-887d-ac401f2283ec'
nonce=uuid.uuid4().hex;cid=None;created=False;create_requested=False
CODE='''import sys,os,json,hashlib,contextvars,gc
from pathlib import Path
binary=Path(sys.executable).resolve()
paths=sorted({line.split()[-1] for line in Path('/proc/self/maps').read_text().splitlines() if len(line.split())>=6 and 'x' in line.split()[1]})
print(json.dumps(dict(scope='canonical stdlib observation only',python_version=sys.version,
 executable=sys.executable,resolved_executable=str(binary),executable_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
 prefix=sys.prefix,base_prefix=sys.base_prefix,sys_path=sys.path,
 flags=dict(isolated=sys.flags.isolated,no_site=sys.flags.no_site,dont_write_bytecode=sys.flags.dont_write_bytecode,ignore_environment=sys.flags.ignore_environment),
 uid=os.getuid(),gid=os.getgid(),executable_mapping_paths=paths,
 missing_kind=type(contextvars.Token.MISSING).__name__,missing_gc_referents=len(gc.get_referents(contextvars.Token.MISSING)),
 native_admission=False,numerical_certificate=False)))
'''
result=dict(scope='actual canonical stdlib probe only',numerical_certificate=False,native_admission=False,
    production_services_enabled=False,full_option_A_complete=False,nonce=nonce,container_started=False,start_requested=False)
def require(ok,why):
    if not ok:raise ValueError(why)
def owned(p):
    st=p.lstat();return p.resolve()==p and st.st_uid==os.getuid() and stat.S_ISDIR(st.st_mode) and stat.S_IMODE(st.st_mode)==0o700
def read(p,limit):
    require(p.resolve()==p and not any(q.is_symlink() for q in (p,*p.parents)),'input_links')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as f:
        st=os.fstat(f.fileno());require(stat.S_ISREG(st.st_mode) and st.st_uid==os.getuid() and st.st_nlink==1 and 0<st.st_size<=limit,'regular_owned')
        b=f.read(limit+1);after=os.fstat(f.fileno());path=p.lstat()
        shape=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns,s.st_mode,s.st_uid,s.st_nlink)
        require(len(b)==st.st_size and shape(st)==shape(after)==shape(path),'stable_bytes');return b
def command(args,seconds=10):
    return ['sudo','-n','/usr/bin/timeout','-k','3s',str(seconds)+'s','/usr/bin/env','-i',
        'PATH=/usr/sbin:/usr/bin:/sbin:/bin','/usr/bin/docker','--config',str(PHASE/'empty-config'),
        '--host','unix:///var/run/docker.sock',*args]
def run(args,seconds=10):
    r=subprocess.run(command(args,seconds),capture_output=True,timeout=seconds+8)
    require(len(r.stdout)<=32768 and len(r.stderr)<=32768,'bounded_cli_result')
    require(r.returncode==0 and not r.stderr,'cli_result');return r.stdout
def inspect():
    rows=json.loads(run(['container','inspect',cid]));require(len(rows)==1,'one_container')
    d=rows[0];require(d['Id']==cid and d['Image']==IMAGE and d['Config']['Labels']=={'org.quantmesh.canonical-probe':nonce},'owned_exact_cid')
    if d['State']['Running'] or not d['State']['StartedAt'].startswith('0001-01-01'):
        result['container_started']=True
    return d
def stopped_remove():
    d=inspect()
    if d['State']['Running']:
        run(['container','stop','--time','2',cid],8);d=inspect()
    require(not d['State']['Running'] and d['State']['Pid']==0,'actual_stopped_before_remove')
    run(['container','rm',cid]);result['owned_container_removed']=True
try:
    os.umask(0o077);require(os.getuid()!=0 and owned(ROOT),'owned_nonroot_root')
    owner=json.loads(read(ROOT/'ownership.json',16384))
    free=shutil.disk_usage('/').free;require(free>=50000000000 and owner['free_before']-free<500000000,'original_disk_gate')
    require(not PHASE.exists() and not PHASE.is_symlink(),'new_probe_phase')
    PHASE.mkdir(mode=0o700);created=True;(PHASE/'empty-config').mkdir(mode=0o700)
    require(owned(PHASE) and owned(PHASE/'empty-config'),'phase_owner')
    before=json.loads(run(['info','--format','{{json .}}']))
    require(before['ID']==ENGINE and before['ServerVersion']=='29.9.0' and before['Containers']==0 and before['Images']==1,'same_empty_engine')
    image=json.loads(run(['image','inspect',IMAGE]))[0]
    config_raw=read(ROOT/'blobs/4f228bc1cbcfc794e4878312cfc241d368eff55a21c08d1e2bb263116c4ef524',65536)
    require(hashlib.sha256(config_raw).hexdigest()=='4f228bc1cbcfc794e4878312cfc241d368eff55a21c08d1e2bb263116c4ef524','source_config')
    config=json.loads(config_raw)
    require(image['Id']==IMAGE and image['Config']==config['config'] and image['RootFS']['Layers']==config['rootfs']['diff_ids'],'same_image')
    (PHASE/'probe-source.py').write_text(CODE)
    name='qm-canonical-'+nonce
    create_requested=True
    raw=run(['container','create','--name',name,'--label','org.quantmesh.canonical-probe='+nonce,
        '--pull','never','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges=true',
        '--pids-limit','32','--cpus','1','--memory','128m','--memory-swap','128m','--user','10001:10001',
        '--env','PYTHONDONTWRITEBYTECODE=1','--tmpfs','/tmp:rw,noexec,nosuid,nodev,size=1m',
        '--entrypoint','/usr/local/bin/python3',IMAGE,'-B','-I','-S','-c',CODE])
    cid=raw.decode().strip();require(re.fullmatch(r'[0-9a-f]{64}',cid),'full_cid')
    result['container_id']=cid
    d=inspect();h=d['HostConfig'];c=d['Config']
    require(c['Entrypoint']==['/usr/local/bin/python3'] and c['Cmd']==['-B','-I','-S','-c',CODE]
        and c['User']=='10001:10001' and h['ReadonlyRootfs'] and h['NetworkMode']=='none'
        and h['CapDrop']==['ALL'] and h['PidsLimit']==32 and h['Memory']==134217728 and h['MemorySwap']==134217728
        and h['NanoCpus']==1000000000 and h['Tmpfs']=={'/tmp':'rw,noexec,nosuid,nodev,size=1m'}
        and not d['Mounts'] and not d['State']['Running'],'actual_created_boundary')
    require('no-new-privileges' in ' '.join(h['SecurityOpt']),'no_new_privileges')
    result['start_requested']=True
    raw=run(['container','start','--attach',cid],15);observation=json.loads(raw)
    d=inspect();require(not d['State']['Running'] and d['State']['ExitCode']==0 and d['State']['Pid']==0
        and not d['State']['OOMKilled'] and d['State']['StartedAt']!=d['State']['FinishedAt'],'actual_exit')
    require(observation['prefix']==observation['base_prefix']=='/usr/local' and observation['executable']=='/usr/local/bin/python3'
        and observation['python_version'].startswith('3.12.15 ') and observation['uid']==observation['gid']==10001
        and observation['flags']==dict(isolated=1,no_site=1,dont_write_bytecode=1,ignore_environment=1),'canonical_observation')
    result.update(exit=0,observation=observation,actual_process_exit=0,probe_source_sha256=hashlib.sha256(CODE.encode()).hexdigest(),
        observed_engine_id=ENGINE,observed_image_id=IMAGE,readonly_rootfs=True,network_none=True,
        mounts=[],tmpfs_noexec_requested=True,kernel_profile_qualified=False)
except BaseException as e:
    result.update(exit=1,failure_kind=type(e).__name__)
    if type(e)is ValueError:result['reason']=str(e)
finally:
    if cid:
        try:stopped_remove()
        except BaseException as e:result.update(exit=1,owned_container_quiescence='NOT_PROVEN',cleanup_failure_kind=type(e).__name__)
    elif created:
        # A timed-out create can outlive its CLI: inspect only the exact nonce,
        # never retry creation or remove any container by a broad selection.
        if create_requested:result['partial_create_quiescence']='NOT_PROVEN'
        try:
            rows=run(['container','ls','-aq','--no-trunc','--filter','label=org.quantmesh.canonical-probe='+nonce]).decode().splitlines()
            if rows:
                require(len(rows)==1 and re.fullmatch(r'[0-9a-f]{64}',rows[0]),'one_owned_partial_cid');cid=rows[0];stopped_remove()
        except BaseException:result.update(exit=1,partial_create_quiescence='NOT_PROVEN')
    if created:
        require(owned(ROOT) and owned(PHASE),'receipt_owner')
        try:
            after=json.loads(run(['info','--format','{{json .}}']))
            require(after['ID']==ENGINE and after['Containers']==0 and after['Images']==1,'final_same_empty_engine')
            result['final_engine']=dict(ID=ENGINE,Images=1,Containers=0)
        except BaseException:result.update(exit=1,final_engine='NOT_PROVEN')
        free=shutil.disk_usage('/').free
        result.update(host_free_bytes=free,phase1_host_introduced_bytes=owner['free_before']-free,at_utc=datetime.now(timezone.utc).isoformat())
        if free<50000000000 or owner['free_before']-free>500000000:result.update(exit=1,disk_gate='FAILED')
        (PHASE/'probe-receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)
raise SystemExit(result['exit'])
