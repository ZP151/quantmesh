"""Deterministic owned OCI archive from already verified public blobs only."""
import hashlib,io,json,os,shutil,signal,stat,tarfile,time
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path('/home/ubuntu/quantmesh-numeric-materialization-4e00a5cecd0047fa9d5aa71c020a077a')
MANIFEST='2ed6491b93cd49272ee6de2b5a38440c3448360322c089fc23e370722d74179d'
CONFIG='4f228bc1cbcfc794e4878312cfc241d368eff55a21c08d1e2bb263116c4ef524'
PHASE=ROOT/'oci-capsule';ARCHIVE=PHASE/'python-base.oci.tar'
started=time.monotonic();deadline=started+90
created=False;child=None;pidfd=None;reaped=False;owner=None
result=dict(scope='actual nonroot offline OCI archive only',docker_mutation=False,container_started=False,
            actual_Engine_image_qualified=False,actual_runtime_qualified=False,numerical_certificate=False,
            production_services_enabled=False,full_option_A_complete=False)
def require(ok,reason):
    if not ok:raise ValueError(reason)
def owned(path):
    st=path.lstat()
    return path.resolve()==path and st.st_uid==os.getuid() and stat.S_ISDIR(st.st_mode) and stat.S_IMODE(st.st_mode)==0o700
def signature(st):return (st.st_dev,st.st_ino,st.st_mode,st.st_uid,st.st_nlink,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
def source(path,limit):
    require(path.resolve()==path and not any(p.is_symlink() for p in (path,*path.parents)),'source_links')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK);st=os.fstat(fd)
    require(stat.S_ISREG(st.st_mode) and st.st_uid==os.getuid() and st.st_nlink==1 and 0<st.st_size<=limit,'source_owner_size')
    return os.fdopen(fd,'rb'),st
def small(path,limit):
    f,st=source(path,limit)
    with f:raw=f.read(limit+1);after=os.fstat(f.fileno())
    require(len(raw)==st.st_size and signature(st)==signature(after)==signature(path.lstat()),'small_stable')
    return raw
def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()+b'\n'
def disk():
    free=shutil.disk_usage('/').free
    require(owner['free_before']-free<=500000000 and free>=50000000000,'phase1_disk_bound')
    return free
def build():
    manifest_raw=small(ROOT/'blobs'/MANIFEST,65536);config_raw=small(ROOT/'blobs'/CONFIG,65536)
    require(hashlib.sha256(manifest_raw).hexdigest()==MANIFEST and hashlib.sha256(config_raw).hexdigest()==CONFIG,'source_pin')
    manifest=json.loads(manifest_raw);config=json.loads(config_raw)
    require(manifest['schemaVersion']==2 and manifest['mediaType']=='application/vnd.oci.image.manifest.v1+json'
            and manifest['config']['digest']=='sha256:'+CONFIG and config['architecture']=='amd64'
            and config['os']=='linux' and len(manifest['layers'])==4,'fixed_linux_manifest')
    tag='quantmesh-numeric-base:4e00a5cecd0047fa9d5aa71c020a077a'
    index=encode(dict(schemaVersion=2,mediaType='application/vnd.oci.image.index.v1+json',manifests=[dict(
        mediaType=manifest['mediaType'],digest='sha256:'+MANIFEST,size=len(manifest_raw),
        platform=dict(os='linux',architecture='amd64'),annotations={'org.opencontainers.image.ref.name':tag})]))
    metadata={'oci-layout':encode(dict(imageLayoutVersion='1.0.0')),'index.json':index}
    entries=[]
    with ARCHIVE.open('xb') as raw:
        with tarfile.open(fileobj=raw,mode='w',format=tarfile.USTAR_FORMAT) as archive:
            def header(name,size):
                h=tarfile.TarInfo(name);h.size=size;h.mode=0o644;h.uid=h.gid=h.mtime=0;h.type=tarfile.REGTYPE
                return h
            for name,data in metadata.items():
                archive.addfile(header(name,len(data)),io.BytesIO(data))
                entries.append(dict(path=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
            blobs=[dict(digest='sha256:'+MANIFEST,size=len(manifest_raw)),manifest['config'],*manifest['layers']]
            require(len({b['digest'] for b in blobs})==6,'unique_blobs')
            for b in blobs:
                digest=b['digest'];require(digest.startswith('sha256:') and len(digest)==71 and all(c in '0123456789abcdef' for c in digest[7:]),'blob_name')
                path=ROOT/'blobs'/digest[7:];f,st=source(path,50000000)
                require(type(b['size']) is int and st.st_size==b['size'],'blob_size')
                h=hashlib.sha256()
                class Reader:
                    def read(self,size):
                        data=f.read(size);h.update(data);return data
                with f:
                    archive.addfile(header('blobs/sha256/'+digest[7:],st.st_size),Reader())
                    after=os.fstat(f.fileno())
                require(h.hexdigest()==digest[7:] and signature(st)==signature(after)==signature(path.lstat()),'blob_stable_pin')
                entries.append(dict(path='blobs/sha256/'+digest[7:],bytes=st.st_size,sha256=h.hexdigest()))
                disk()
        raw.flush();os.fsync(raw.fileno())
    require(ARCHIVE.stat().st_size<50000000,'archive_byte_bound')
    actual=[]
    with tarfile.open(ARCHIVE,'r:') as archive:
        for member in archive:
            require(member.isfile() and member.uid==member.gid==member.mtime==0 and member.mode==0o644,'archive_member')
            h=hashlib.sha256()
            with archive.extractfile(member) as f:
                while chunk:=f.read(65536):h.update(chunk)
            actual.append(dict(path=member.name,bytes=member.size,sha256=h.hexdigest()))
    require(actual==entries and len(actual)==8,'independent_archive_readback')
    h=hashlib.sha256()
    with ARCHIVE.open('rb') as f:
        while b:=f.read(65536):h.update(b)
    result.update(exit=0,archive=str(ARCHIVE),archive_bytes=ARCHIVE.stat().st_size,archive_sha256=h.hexdigest(),
                  entries=entries,manifest_sha256=MANIFEST,config_sha256=CONFIG,tag_reference_only=tag,
                  exact_source_bytes_preserved=True)
try:
    os.umask(0o077)
    require(os.getuid()!=0 and signal.getsignal(signal.SIGCHLD)==signal.SIG_DFL and owned(ROOT),'nonroot_owner')
    owner=json.loads(small(ROOT/'ownership.json',16384));require(owner['manifest_sha256']==MANIFEST and owner['config_sha256']==CONFIG,'owner_binding')
    after=json.loads(small(ROOT/'source-after-receipt.json',65536))
    require(after['exit']==0 and after['images']==after['containers']==0 and after['private_tailnet_online'],'previous_actual_after')
    require(not PHASE.exists() and not PHASE.is_symlink(),'new_capsule_phase')
    PHASE.mkdir(mode=0o700);created=True;disk()
    child=os.fork()
    if child==0:
        try:
            try:build()
            except BaseException as e:
                result.update(exit=1,failure_kind=type(e).__name__)
                if type(e) is ValueError:result['reason']=str(e)
            (PHASE/'worker-result.json').write_bytes(encode(result))
        finally:os._exit(0)
    pidfd=os.pidfd_open(child)
    while True:
        ended,status=os.waitpid(child,os.WNOHANG)
        if ended:
            reaped=True;require(os.waitstatus_to_exitcode(status)==0,'worker_exit')
            result=json.loads(small(PHASE/'worker-result.json',16384));break
        require(time.monotonic()<deadline,'capsule_watchdog');disk();time.sleep(0.05)
except BaseException as e:
    result.update(exit=1,failure_kind=type(e).__name__)
    if type(e) is ValueError:result['reason']=str(e)
finally:
    if child and not reaped:
        ended,status=os.waitpid(child,os.WNOHANG)
        if ended:reaped=True
        else:
            if pidfd is not None:signal.pidfd_send_signal(pidfd,signal.SIGKILL)
            else:os.kill(child,signal.SIGKILL)
            stop=time.monotonic()+5
            while time.monotonic()<stop:
                ended,status=os.waitpid(child,os.WNOHANG)
                if ended:reaped=True;break
                time.sleep(0.05)
    if pidfd is not None:os.close(pidfd)
    if child and not reaped:result.update(exit=1,worker_quiescence='NOT_PROVEN')
    if created:
        require(owned(ROOT) and owned(PHASE),'receipt_owner')
        free=shutil.disk_usage('/').free
        result.update(worker_reaped=reaped,elapsed_seconds=round(time.monotonic()-started,3),at_utc=datetime.now(timezone.utc).isoformat(),
                      host_free_bytes=free,phase1_host_introduced_bytes=owner['free_before']-free,
                      retained_archive_bytes=ARCHIVE.stat().st_size if ARCHIVE.exists() else 0)
        (PHASE/'capsule-receipt.json').write_bytes(encode(result))
    print(json.dumps(result),flush=True)
raise SystemExit(result['exit'])
