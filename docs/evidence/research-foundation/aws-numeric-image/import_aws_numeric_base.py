"""Finite offline archive import only. No container or numerical activation."""
import hashlib,json,os,re,shutil,stat,subprocess,time
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path('/home/ubuntu/quantmesh-numeric-materialization-4e00a5cecd0047fa9d5aa71c020a077a')
PHASE=ROOT/'engine-import';CAPSULE=ROOT/'oci-capsule/python-base.oci.tar'
ARCHIVE_SHA='43462a2b05ffb930b745fc72b889716af8ffc9945a586273d54dea3b029931b0'
MANIFEST='2ed6491b93cd49272ee6de2b5a38440c3448360322c089fc23e370722d74179d'
CONFIG='4f228bc1cbcfc794e4878312cfc241d368eff55a21c08d1e2bb263116c4ef524'
ENGINE='cfe71bf3-9059-4059-887d-ac401f2283ec'
TAG='quantmesh-numeric-base:4e00a5cecd0047fa9d5aa71c020a077a'
started=time.monotonic();created=False;owner=None;process=None;archive=None
result=dict(scope='actual finite offline OCI import only',container_started=False,
            actual_runtime_qualified=False,numerical_certificate=False,
            production_research_services_enabled=False,full_option_A_complete=False,
            import_started=False,daemon_import_completion='NOT_PROVEN')
def require(ok,reason):
    if not ok:raise ValueError(reason)
def owned(p):
    st=p.lstat();return p.resolve()==p and st.st_uid==os.getuid() and stat.S_ISDIR(st.st_mode) and stat.S_IMODE(st.st_mode)==0o700
def stable(st):return (st.st_dev,st.st_ino,st.st_size,st.st_mode,st.st_uid,st.st_nlink,st.st_mtime_ns,st.st_ctime_ns)
def open_owned(p,limit):
    require(p.resolve()==p and not any(q.is_symlink() for q in (p,*p.parents)),'input_links')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK);st=os.fstat(fd)
    require(stat.S_ISREG(st.st_mode) and st.st_uid==os.getuid() and st.st_nlink==1 and 0<st.st_size<=limit,'input_owner_size')
    return os.fdopen(fd,'rb'),st
def small(p,limit):
    f,st=open_owned(p,limit)
    with f:raw=f.read(limit+1);after=os.fstat(f.fileno())
    require(len(raw)==st.st_size and stable(st)==stable(after)==stable(p.lstat()),'input_stable')
    return raw
def command(args,seconds=10):
    # GNU timeout runs AS ROOT and owns its new command process group. A CLI
    # exit proves that CLI outcome only; never infer daemon cancellation from it.
    return ['sudo','-n','/usr/bin/timeout','-k','5s',str(seconds)+'s','/usr/bin/env','-i',
            'PATH=/usr/sbin:/usr/bin:/sbin:/bin','/usr/bin/docker','--config',str(PHASE/'empty-config'),
            '--host','unix:///var/run/docker.sock',*args]
def observe(args):
    r=subprocess.run(command(args),capture_output=True,timeout=18)
    require(r.returncode==0 and len(r.stdout)<=65536 and len(r.stderr)<=65536,'observer_result')
    return json.loads(r.stdout)
def info():
    d=observe(['info','--format','{{json .}}'])
    require(d['ID']==ENGINE and d['ServerVersion']=='29.9.0' and d['Containers']==0,'same_engine_no_containers')
    return {k:d[k] for k in ('ID','ServerVersion','Containers','Images','DockerRootDir','Driver')}
def measure():
    free=shutil.disk_usage('/').free
    return dict(host_free_bytes=free,phase1_host_introduced_bytes=owner['free_before']-free)
def disk_gate():
    d=measure();require(d['host_free_bytes']>=50000000000 and d['phase1_host_introduced_bytes']<=500000000,'phase1_disk_bound');return d
try:
    os.umask(0o077);require(os.getuid()!=0 and owned(ROOT),'nonroot_owned_root')
    owner=json.loads(small(ROOT/'ownership.json',16384))
    require(owner['manifest_sha256']==MANIFEST and owner['config_sha256']==CONFIG,'owner_binding')
    capsule=json.loads(small(ROOT/'oci-capsule/capsule-receipt.json',16384))
    require(capsule['exit']==0 and capsule['worker_reaped'] and capsule['archive_sha256']==ARCHIVE_SHA
            and capsule['archive_bytes']==47575040,'actual_capsule_binding')
    require(not PHASE.exists() and not PHASE.is_symlink(),'new_import_phase')
    PHASE.mkdir(mode=0o700);created=True;(PHASE/'empty-config').mkdir(mode=0o700)
    require(owned(PHASE) and owned(PHASE/'empty-config'),'owned_phase')
    result['before_engine']=info();require(result['before_engine']['Images']==0,'fresh_empty_engine')
    result['before_disk']=disk_gate()
    version=observe(['version','--format','{{json .}}'])
    require(version['Server']['GitCommit']=='a5b58c9' and version['Client']['GitCommit']=='f415da8','engine_build_binding')
    result['engine_build']=dict(server='a5b58c9',client='f415da8',api=version['Server']['ApiVersion'])
    manifest=json.loads(small(ROOT/'blobs'/MANIFEST,65536));config_raw=small(ROOT/'blobs'/CONFIG,65536)
    require(hashlib.sha256(config_raw).hexdigest()==CONFIG,'config_source_pin');config=json.loads(config_raw)
    archive,st=open_owned(CAPSULE,50000000);h=hashlib.sha256()
    while b:=archive.read(65536):h.update(b)
    require(h.hexdigest()==ARCHIVE_SHA and stable(st)==stable(os.fstat(archive.fileno()))==stable(CAPSULE.lstat()),'archive_pin_stable')
    archive.seek(0)
    log=PHASE/'load.log'
    with log.open('xb') as output:
        process=subprocess.Popen(command(['image','load','--quiet','--platform','linux/amd64'],150),
                                 stdin=archive,stdout=output,stderr=subprocess.STDOUT)
        result['import_started']=True
        while process.poll() is None:
            # On a guard failure, wait for the already armed ROOT watchdog;
            # do not attempt nonroot kill of sudo or claim daemon quiescence.
            if log.stat().st_size>65536 or measure()['phase1_host_introduced_bytes']>500000000:
                result['guard_failed']=True
            require(time.monotonic()-started<185,'root_watchdog_observation_failed')
            time.sleep(0.1)
    result['load_cli_exit']=process.returncode;require(process.returncode==0,'load_cli_refused')
    require(not result.get('guard_failed') and log.stat().st_size<=65536,'load_guard')
    text=small(log,65536).decode('utf-8')
    # This Engine can return0 despite unpack errors. No other line is accepted.
    lines=text.strip().splitlines()
    require(lines in (['Loaded image: '+TAG],['Loaded image ID: sha256:'+MANIFEST]),'load_exact_success_stream')
    require(stable(st)==stable(os.fstat(archive.fileno()))==stable(CAPSULE.lstat()),'archive_after_stable')
    image=observe(['image','inspect',TAG]);require(type(image)is list and len(image)==1,'single_image')
    image=image[0]
    require(image['Id']=='sha256:'+MANIFEST and image['Os']=='linux' and image['Architecture']=='amd64'
            and image['RootFS']['Layers']==config['rootfs']['diff_ids'] and image['Config']==config['config'],'image_identity_config')
    result['after_engine']=info();require(result['after_engine']['Images']==1,'one_new_image')
    result['after_disk']=disk_gate()
    result.update(exit=0,daemon_import_completion='normal_load_request_returned_and_exact_image_observed',
                  physical_image_id=image['Id'],source_manifest_sha256=MANIFEST,source_config_sha256=CONFIG,
                  exact_rootfs_diff_ids=image['RootFS']['Layers'],archive_sha256=ARCHIVE_SHA,
                  physical_base_imported=True,actual_Engine_image_qualified=False,
                  image_runtime_not_yet_executed=True)
except BaseException as e:
    result.update(exit=1,failure_kind=type(e).__name__,physical_base_imported=False)
    if type(e)is ValueError:result['reason']=str(e)
finally:
    if process is not None and process.poll() is None:
        # ROOT timeout150s+kill5s is already armed. Only observe its outcome.
        try:process.wait(timeout=165)
        except subprocess.TimeoutExpired:result['root_watchdog_completion']='NOT_PROVEN'
    if process is not None:result['load_cli_exit']=process.poll()
    if archive is not None:archive.close()
    if created:
        require(owned(ROOT) and owned(PHASE),'receipt_owner')
        result.update(final_disk=measure(),elapsed_seconds=round(time.monotonic()-started,3),
                      at_utc=datetime.now(timezone.utc).isoformat(),root=str(ROOT),phase_root=str(PHASE),
                      retained_files=[dict(name=p.name,bytes=p.stat().st_size) for p in PHASE.iterdir() if p.is_file()])
        try:result['final_engine']=info()
        except BaseException:result['final_engine']='NOT_PROVEN'
        (PHASE/'import-receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)
raise SystemExit(result['exit'])
