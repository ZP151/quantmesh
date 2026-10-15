"""Read exact wheel ZIP/RECORD/notices without extraction, imports or install."""
import base64,csv,hashlib,io,json,os,re,shutil,signal,ssl,stat,time,zipfile
from datetime import datetime,timezone
from pathlib import Path,PurePosixPath
ROOT=Path('/home/ubuntu/quantmesh-numeric-materialization-4e00a5cecd0047fa9d5aa71c020a077a')
PHASE=ROOT/'wheel-inventory';INTAKE=ROOT/'wheel-intake'
META='900a8ab850e85a84aafc2b4061758767902d377704c4cad22fb0041b30d5d5cf'
LOCK='07f4e7ec64805a375e0bdc707d0158fbdb08bd07d02aa569e2d119496b32592a'
started=time.monotonic();owner=None;created=False;child=None;pidfd=None;reaped=False
result=dict(scope='actual wheel byte/ZIP/RECORD/notices only',wheels_installed=False,
    Docker_mutation=False,native_code_loaded=False,numerical_certificate=False,
    complete_ELF_closure=False,legal_expression_qualified=False,full_option_A_complete=False)
def require(ok,why):
    if not ok:raise ValueError(why)
def owned(p):
    st=p.lstat();return p.resolve()==p and st.st_uid==os.getuid() and stat.S_ISDIR(st.st_mode) and stat.S_IMODE(st.st_mode)==0o700
def signature(s):return (s.st_dev,s.st_ino,s.st_size,s.st_mode,s.st_uid,s.st_nlink,s.st_mtime_ns,s.st_ctime_ns)
def opened(p,limit):
    require(p.resolve()==p and not any(q.is_symlink() for q in (p,*p.parents)),'input_links')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    f=os.fdopen(fd,'rb');st=os.fstat(fd)
    try:require(stat.S_ISREG(st.st_mode) and st.st_uid==os.getuid() and st.st_nlink==1 and 0<st.st_size<=limit,'owned_regular')
    except BaseException:f.close();raise
    return f,st
def read(p,limit):
    f,st=opened(p,limit)
    with f:b=f.read(limit+1);after=os.fstat(f.fileno())
    require(len(b)==st.st_size and signature(st)==signature(after)==signature(p.lstat()),'stable_bounded_read')
    return b
def disk():
    free=shutil.disk_usage('/').free
    require(free>=50000000000 and owner['free_before']-free<=500000000,'original_disk_gate')
    return free
def safe(name):
    require(type(name)is str and 0<len(name)<=512 and '\\' not in name and ':' not in name
        and not name.startswith('/') and all(c not in name for c in ('\x00','\r','\n')),'zip_path')
    p=PurePosixPath(name)
    require('..' not in p.parts and '.' not in p.parts and str(p)==name.rstrip('/'),'zip_canonical_path')
    return p
def work():
    d=dict(result);rows=[];packages=[];total=0;notice_total=0;record_count=0;elf_count=0
    try:
        for wheel in metadata:
            require(time.monotonic()-started<180,'inventory_deadline')
            path=INTAKE/'wheelhouse'/wheel['filename'];f,before=opened(path,22000000)
            with f:
                h=hashlib.sha256()
                while b:=f.read(65536):h.update(b)
                require(before.st_size==wheel['previous_cached_compressed_bytes'] and h.hexdigest()==wheel['sha256'],'wheel_pin')
                f.seek(0)
                with zipfile.ZipFile(f) as z:
                    infos=z.infolist();require(len(infos)<=16384,'zip_members')
                    names=set();regular={}
                    for info in infos:
                        name=info.filename;p=safe(name);require(name not in names,'zip_duplicate');names.add(name)
                        require(not info.flag_bits&1 and not stat.S_ISLNK(info.external_attr>>16),'zip_no_encryption_links')
                        if info.is_dir():continue
                        require(not any(part=='__pycache__' for part in p.parts) and p.suffix not in ('.pyc','.pth'),'zip_no_automatic_code')
                        require(0<=info.file_size<=268435456,'member_uncompressed_bound');regular[name]=info
                    records=[n for n in regular if n.endswith('.dist-info/RECORD')]
                    require(len(records)==1,'one_record')
                    with z.open(records[0]) as rf:record_raw=rf.read(2097153)
                    require(len(record_raw)<=2097152,'record_bound')
                    declared={}
                    for row in csv.reader(io.StringIO(record_raw.decode('utf-8'),newline='')):
                        require(len(row)==3 and row[0] not in declared,'record_unique');safe(row[0]);declared[row[0]]=row[1:]
                    require(set(declared)==set(regular),'record_exact_members')
                    notice_paths=[]
                    for name,info in regular.items():
                        require(time.monotonic()-started<180 and len(rows)<16384,'stream_bounds')
                        is_notice=bool(re.match(r'(?i)^(license|licence|copying|copyright|notice)([._-].*|$)',PurePosixPath(name).name))
                        payload=bytearray() if is_notice else None;h=hashlib.sha256();count=0;prefix=b''
                        with z.open(info) as rf:
                            while b:=rf.read(65536):
                                count+=len(b);total+=len(b)
                                require(count<=info.file_size and total<=1000000000,'stream_uncompressed_bound')
                                if not prefix:prefix=b[:4]
                                h.update(b)
                                if payload is not None:
                                    require(len(payload)+len(b)<=1048576 and notice_total+len(b)<=8388608,'notice_bound')
                                    payload.extend(b);notice_total+=len(b)
                                require(time.monotonic()-started<180,'stream_deadline')
                        require(count==info.file_size,'member_size')
                        encoded=base64.urlsafe_b64encode(h.digest()).decode().rstrip('=')
                        expected=declared[name]
                        if name==records[0]:require(expected==['',''],'record_self')
                        else:
                            require(expected==['sha256='+encoded,str(count)],'record_member_hash_size');record_count+=1
                        elf=prefix==b'\x7fELF';elf_count+=int(elf)
                        row=dict(wheel=wheel['name'],version=wheel['version'],path=name,bytes=count,sha256=h.hexdigest(),ELF_magic=elf)
                        if payload is not None:
                            dest=PHASE/'notices'/str(len(rows));dest.write_bytes(payload);notice_paths.append(dict(path=name,sha256=h.hexdigest(),bytes=count,body_file=dest.name))
                            row['notice_body_file']=dest.name;disk()
                        rows.append(row)
                    require(notice_paths,'bundled_notice_missing')
                    packages.append(dict(name=wheel['name'],version=wheel['version'],wheel_sha256=wheel['sha256'],members=len(regular),notices=notice_paths))
                require(signature(before)==signature(os.fstat(f.fileno()))==signature(path.lstat()),'wheel_after_stable')
        raw=json.dumps(dict(files=rows,packages=packages),sort_keys=True,separators=(',',':')).encode()+b'\n'
        require(len(raw)<=8388608,'catalog_bound');(PHASE/'inventory.json').write_bytes(raw);disk()
        d.update(exit=0,wheels=len(packages),file_members=len(rows),per_file_RECORD_verified=record_count,
            uncompressed_stream_bytes=total,ELF_magic_files=elf_count,packages_with_bundled_notices=len(packages),
            preserved_notice_files=sum(len(p['notices']) for p in packages),notice_bytes=notice_total,
            inventory_bytes=len(raw),inventory_sha256=hashlib.sha256(raw).hexdigest(),metadata_sha256=META,lock_sha256=LOCK)
    except BaseException as e:
        d.update(exit=1,failure_kind=type(e).__name__,partial_notices_retained=True)
        if type(e)is ValueError:d['reason']=str(e)
    (PHASE/'worker-result.json').write_text(json.dumps(d)+'\n')
try:
    os.umask(0o077);require(os.getuid()!=0 and owned(ROOT) and owned(INTAKE),'nonroot_owned_roots')
    require(signal.getsignal(signal.SIGCHLD)==signal.SIG_DFL,'sole_reaper')
    owner=json.loads(read(ROOT/'ownership.json',16384));disk()
    raw=read(INTAKE/'linux-wheels.json',262144);lock=read(INTAKE/'requirements.linux-cp312.lock',16384)
    require(hashlib.sha256(raw).hexdigest()==META and hashlib.sha256(lock).hexdigest()==LOCK,'input_pins')
    metadata=json.loads(raw);require(type(metadata)is list and len(metadata)==81,'fixed_81')
    intake=json.loads(read(INTAKE/'intake-receipt.json',32768))
    require(intake['exit']==0 and intake['worker_reaped'] and intake['compressed_wheel_bytes']==88992477,'actual_intake')
    require(not PHASE.exists() and not PHASE.is_symlink(),'fresh_phase')
    PHASE.mkdir(mode=0o700);created=True;(PHASE/'notices').mkdir(mode=0o700)
    require(owned(PHASE) and owned(PHASE/'notices'),'owned_phase')
    child=os.fork()
    if child==0:
        try:work()
        finally:os._exit(0)
    pidfd=os.pidfd_open(child)
    while True:
        ended,status=os.waitpid(child,os.WNOHANG)
        if ended:
            reaped=True;require(os.waitstatus_to_exitcode(status)==0,'worker_exit')
            result=json.loads(read(PHASE/'worker-result.json',32768));break
        require(time.monotonic()-started<180,'parent_watchdog');disk();time.sleep(.05)
except BaseException as e:
    result.update(exit=1,failure_kind=type(e).__name__)
    if type(e)is ValueError:result['reason']=str(e)
finally:
    if child and not reaped:
        ended,status=os.waitpid(child,os.WNOHANG)
        if ended:reaped=True
        else:
            if pidfd is not None:signal.pidfd_send_signal(pidfd,signal.SIGKILL)
            else:os.kill(child,signal.SIGKILL)
            end=time.monotonic()+5
            while time.monotonic()<end:
                ended,status=os.waitpid(child,os.WNOHANG)
                if ended:reaped=True;break
                time.sleep(.05)
    if pidfd is not None:os.close(pidfd)
    result.update(worker_reaped=reaped,at_utc=datetime.now(timezone.utc).isoformat(),elapsed_seconds=round(time.monotonic()-started,3))
    if child and not reaped:result.update(exit=1,worker_quiescence='NOT_PROVEN')
    if created:
        require(owned(ROOT) and owned(PHASE),'receipt_owner')
        free=shutil.disk_usage('/').free;result.update(host_free_bytes=free,phase1_host_introduced_bytes=owner['free_before']-free,phase_root=str(PHASE))
        if free<50000000000 or owner['free_before']-free>500000000:result.update(exit=1,disk_gate='FAILED')
        (PHASE/'inventory-receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)
raise SystemExit(result['exit'])
