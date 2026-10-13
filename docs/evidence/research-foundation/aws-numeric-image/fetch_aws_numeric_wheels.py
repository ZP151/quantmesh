"""Injected pinned metadata/lock bytes; data-only exact wheel intake on AWS."""
import base64,hashlib,json,os,re,shutil,signal,ssl,stat,sys,time,urllib.request,urllib.parse
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path('/home/ubuntu/quantmesh-numeric-materialization-4e00a5cecd0047fa9d5aa71c020a077a')
PHASE=ROOT/'wheel-intake'
META_SHA='900a8ab850e85a84aafc2b4061758767902d377704c4cad22fb0041b30d5d5cf'
LOCK_SHA='07f4e7ec64805a375e0bdc707d0158fbdb08bd07d02aa569e2d119496b32592a'
started=time.monotonic();child=None;pidfd=None;reaped=False;created=False;wheelhouse_ready=False;owner=None
result=dict(scope='actual exact public wheel bytes only',docker_mutation=False,
    container_started=False,wheels_installed=False,actual_runtime_qualified=False,
    numerical_certificate=False,production_services_enabled=False,full_option_A_complete=False)
def require(ok,why):
    if not ok:raise ValueError(why)
def owned(p):
    st=p.lstat();return p.resolve()==p and st.st_uid==os.getuid() and stat.S_ISDIR(st.st_mode) and stat.S_IMODE(st.st_mode)==0o700
def read_owned(p,limit):
    require(p.resolve()==p and not any(q.is_symlink() for q in (p,*p.parents)),'input_links')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as f:
        st=os.fstat(f.fileno())
        require(stat.S_ISREG(st.st_mode) and st.st_uid==os.getuid() and st.st_nlink==1 and 0<st.st_size<=limit,'input_owned_regular')
        b=f.read(limit+1);after=os.fstat(f.fileno());path=p.lstat()
        shape=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns,s.st_mode,s.st_uid,s.st_nlink)
        require(len(b)==st.st_size and shape(st)==shape(after)==shape(path),'input_stable_bound')
        return b
def disk():
    free=shutil.disk_usage('/').free
    require(free>=50000000000 and owner['free_before']-free<=500000000,'original_phase1_disk_bound')
    return dict(host_free_bytes=free,phase1_host_introduced_bytes=owner['free_before']-free)
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None
def download():
    local=dict(result,artifacts=[])
    try:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),
            urllib.request.HTTPSHandler(context=ssl.create_default_context()),NoRedirect())
        for row in metadata:
            require(time.monotonic()-started<240,'download_deadline')
            req=urllib.request.Request(row['url'],headers={'Accept-Encoding':'identity'})
            h=hashlib.sha256();count=0;dest=PHASE/'wheelhouse'/row['filename']
            with dest.open('xb') as f,opener.open(req,timeout=10) as response:
                require(response.status==200,'HTTP_status')
                size=row['previous_cached_compressed_bytes']
                if response.headers.get('Content-Length') is not None:
                    require(response.headers['Content-Length']==str(size),'HTTP_size')
                while True:
                    require(time.monotonic()-started<240,'download_deadline')
                    b=response.read(min(65536,size-count+1))
                    if not b:break
                    count+=len(b);require(count<=size,'wheel_size_bound')
                    f.write(b);h.update(b);disk()
            require(count==size and h.hexdigest()==row['sha256'],'wheel_exact_bytes')
            local['artifacts'].append(dict(name=row['name'],version=row['version'],
                filename=row['filename'],bytes=count,sha256=h.hexdigest()))
        local.update(exit=0,wheels=len(local['artifacts']),compressed_wheel_bytes=sum(x['bytes'] for x in local['artifacts']),
            metadata_sha256=META_SHA,lock_sha256=LOCK_SHA)
    except BaseException as e:
        local.update(exit=1,failure_kind=type(e).__name__,partial_bytes_retained=True)
        if type(e)is ValueError:local['reason']=str(e)
    (PHASE/'worker-receipt.json').write_text(json.dumps(local)+'\n')
try:
    os.umask(0o077)
    require(os.getuid()!=0 and owned(ROOT) and signal.getsignal(signal.SIGCHLD)==signal.SIG_DFL,'nonroot_owned_root')
    owner=json.loads(read_owned(ROOT/'ownership.json',16384));disk()
    require(owner['manifest_sha256']=='2ed6491b93cd49272ee6de2b5a38440c3448360322c089fc23e370722d74179d','source_owner')
    meta_raw=base64.b64decode(METADATA_B64,validate=True);lock_raw=base64.b64decode(LOCK_B64,validate=True)
    require(len(meta_raw)==156544 and len(lock_raw)<16384 and hashlib.sha256(meta_raw).hexdigest()==META_SHA
        and hashlib.sha256(lock_raw).hexdigest()==LOCK_SHA,'exact_input_bytes')
    metadata=json.loads(meta_raw);require(type(metadata)is list and len(metadata)==81,'fixed_81')
    norm=lambda s:re.sub(r'[-_.]+','-',s).lower()
    pins={}
    for line in lock_raw.decode().splitlines():
        if not line or line.startswith('#'):continue
        m=re.fullmatch(r'([a-zA-Z0-9_.-]+)==([^\s]+) --hash=sha256:([0-9a-f]{64})',line)
        require(m is not None and norm(m[1]) not in pins,'fixed_lock_syntax')
        pins[norm(m[1])]=(m[2],m[3])
    require(len(pins)==81,'fixed_lock_count')
    names=set();files=set()
    for row in metadata:
        u=urllib.parse.urlsplit(row['url']);name=norm(row['name']);filename=row['filename']
        require(name not in names and filename not in files and re.fullmatch(r'[A-Za-z0-9_.+-]{1,200}\.whl',filename),'unique_wheel_path')
        require(u.scheme=='https' and u.hostname=='files.pythonhosted.org' and u.port in (None,443)
            and not u.username and not u.password and not u.query and not u.fragment
            and u.path.startswith('/packages/') and u.path.endswith('/'+filename),'official_fixed_url')
        require(pins.get(name)==(row['version'],row['sha256']) and type(row['previous_cached_compressed_bytes'])is int
            and 0<row['previous_cached_compressed_bytes']<22000000,'lock_metadata_match')
        names.add(name);files.add(filename)
    require(sum(x['previous_cached_compressed_bytes'] for x in metadata)==88992477,'fixed_total_bytes')
    require(not PHASE.exists() and not PHASE.is_symlink(),'new_owned_phase')
    PHASE.mkdir(mode=0o700);created=True;(PHASE/'wheelhouse').mkdir(mode=0o700)
    require(owned(PHASE) and owned(PHASE/'wheelhouse'),'owned_phase')
    wheelhouse_ready=True
    (PHASE/'linux-wheels.json').write_bytes(meta_raw);(PHASE/'requirements.linux-cp312.lock').write_bytes(lock_raw)
    result['before_disk']=disk()
    child=os.fork()
    if child==0:
        try:download()
        finally:os._exit(0)
    pidfd=os.pidfd_open(child)
    while True:
        ended,status=os.waitpid(child,os.WNOHANG)
        if ended:
            reaped=True;require(os.waitstatus_to_exitcode(status)==0,'worker_exit')
            result=json.loads(read_owned(PHASE/'worker-receipt.json',32768));break
        require(time.monotonic()-started<240,'parent_watchdog');disk();time.sleep(.05)
except BaseException as e:
    result.update(exit=1,failure_kind=type(e).__name__,partial_bytes_retained=True)
    if type(e)is ValueError:result['reason']=str(e)
finally:
    if child and not reaped:
        ended,status=os.waitpid(child,os.WNOHANG)
        if ended:reaped=True
        else:
            if pidfd is not None:signal.pidfd_send_signal(pidfd,signal.SIGKILL)
            else:os.kill(child,signal.SIGKILL)
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                ended,status=os.waitpid(child,os.WNOHANG)
                if ended:reaped=True;break
                time.sleep(.05)
    if pidfd is not None:os.close(pidfd)
    result.update(worker_reaped=reaped,watchdog_seconds=240,reap_budget_seconds=5,at_utc=datetime.now(timezone.utc).isoformat(),
        elapsed_seconds=round(time.monotonic()-started,3))
    if child and not reaped:result.update(exit=1,worker_quiescence='NOT_PROVEN')
    if created:
        require(owned(ROOT) and owned(PHASE),'receipt_owner')
        free=shutil.disk_usage('/').free
        retained=0
        if wheelhouse_ready and owned(PHASE/'wheelhouse'):
            retained=sum(p.stat().st_size for p in (PHASE/'wheelhouse').iterdir())
        elif wheelhouse_ready:
            result.update(exit=1,retained_wheel_bytes_status='NOT_PROVEN')
        result.update(host_free_bytes=free,phase1_host_introduced_bytes=owner['free_before']-free,phase_root=str(PHASE),
            retained_wheel_bytes=retained,wheelhouse_created=wheelhouse_ready)
        (PHASE/'intake-receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)
raise SystemExit(result['exit'])
