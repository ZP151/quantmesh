"""Exact upstream notice supplements only; frozen wheels unchanged/uninstalled."""
import hashlib,json,os,shutil,signal,ssl,stat,tarfile,time,urllib.request,urllib.parse
from datetime import datetime,timezone
from pathlib import Path,PurePosixPath
ROOT=Path('/home/ubuntu/quantmesh-numeric-materialization-4e00a5cecd0047fa9d5aa71c020a077a')
PHASE=ROOT/'wheel-notice-supplements'
COMMIT='15468f97c18467d67ececb90b17107b0875e7a65'
LANG_WHEEL='748538d163cd073879106837d7f0892f34849655ba43cbb5aa5e21509e24423d'
PYL_WHEEL='4497b731aef59508b079dbf5f00bc5bf4329ac45090a6cd37b5a83756f0e69ab'
PYL_SOURCE='ec6e30669d1df50c9ca160486da44a8195bb4c7a5d3d533990d0c5b03accd281'
started=time.monotonic();owner=None;child=None;pidfd=None;reaped=False;created=False
result=dict(scope='upstream full notice bytes only',wheel_pins_changed=False,installed=False,
    source_code_executed=False,numerical_certificate=False,legal_expression_qualified=False,full_option_A_complete=False)
def require(ok,why):
    if not ok:raise ValueError(why)
def owned(p):
    st=p.lstat();return p.resolve()==p and st.st_uid==os.getuid() and stat.S_ISDIR(st.st_mode) and stat.S_IMODE(st.st_mode)==0o700
def small(p,limit):
    require(p.resolve()==p and not any(q.is_symlink() for q in (p,*p.parents)),'input_links')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as f:
        st=os.fstat(f.fileno());require(stat.S_ISREG(st.st_mode) and st.st_uid==os.getuid() and st.st_nlink==1 and 0<st.st_size<=limit,'owned_regular')
        b=f.read(limit+1);after=os.fstat(f.fileno());path=p.lstat()
        shape=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mode,s.st_uid,s.st_nlink,s.st_mtime_ns,s.st_ctime_ns)
        require(len(b)==st.st_size and shape(st)==shape(after)==shape(path),'stable_read');return b
def disk():
    free=shutil.disk_usage('/').free;require(free>=50000000000 and owner['free_before']-free<=500000000,'original_disk_bound');return free
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*a,**k):return None
def fetch(url,limit):
    u=urllib.parse.urlsplit(url)
    require(u.scheme=='https' and u.hostname in ('pypi.org','files.pythonhosted.org','raw.githubusercontent.com')
        and u.port in (None,443) and not u.username and not u.password and not u.query and not u.fragment,'public_source_url')
    require(time.monotonic()-started<90,'deadline')
    op=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=ssl.create_default_context()),NoRedirect())
    with op.open(urllib.request.Request(url,headers={'Accept-Encoding':'identity'}),timeout=10) as r:
        require(r.status==200,'HTTP_status');b=r.read(limit+1);require(len(b)<=limit,'download_bound')
    disk();return b
def notice(body):
    # An actual preserved text check, not a legal-expression interpretation.
    require(500<=len(body)<=16384 and b'Copyright' in body and b'Permission is hereby granted' in body
        and b'THE SOFTWARE IS PROVIDED' in body,'full_notice_body')
def work():
    d=dict(result)
    try:
        url='https://raw.githubusercontent.com/langchain-ai/langsmith-sdk/'+COMMIT+'/LICENSE'
        lang=fetch(url,16384);notice(lang);(PHASE/'langsmith-LICENSE').write_bytes(lang)
        metadata=fetch('https://pypi.org/pypi/pyluach/2.3.0/json',131072)
        (PHASE/'pyluach-release.json').write_bytes(metadata);release=json.loads(metadata)
        require(release['info']['name']=='pyluach' and release['info']['version']=='2.3.0','release_identity')
        rows=[x for x in release['urls'] if x['filename']=='pyluach-2.3.0.tar.gz' and x['packagetype']=='sdist']
        require(len(rows)==1 and rows[0]['digests']['sha256']==PYL_SOURCE and type(rows[0]['size'])is int and rows[0]['size']<=65536,'source_descriptor')
        sdist=fetch(rows[0]['url'],65536)
        require(len(sdist)==rows[0]['size'] and hashlib.sha256(sdist).hexdigest()==PYL_SOURCE,'source_bytes')
        source=PHASE/'pyluach-2.3.0.tar.gz';source.write_bytes(sdist)
        with tarfile.open(source,'r:gz') as tf:
            members=tf.getmembers();require(len(members)<=256,'source_member_bound')
            selected=[m for m in members if m.name=='pyluach-2.3.0/license.txt']
            require(len(selected)==1 and selected[0].isreg() and not selected[0].linkname and selected[0].size<=16384,'regular_source_notice')
            f=tf.extractfile(selected[0]);require(f is not None,'notice_stream')
            with f:pyl=f.read(16385)
            require(len(pyl)==selected[0].size,'notice_size');notice(pyl)
        (PHASE/'pyluach-license.txt').write_bytes(pyl)
        d.update(exit=0,notices=[dict(name='langsmith',version='0.14.7',wheel_sha256=LANG_WHEEL,
            notice_file='langsmith-LICENSE',notice_sha256=hashlib.sha256(lang).hexdigest(),notice_bytes=len(lang),
            source_kind='publisher-commit LICENSE; PyPI wheel attestation commit supplied by primary intake',source_commit=COMMIT,source_url=url),
            dict(name='pyluach',version='2.3.0',wheel_sha256=PYL_WHEEL,notice_file='pyluach-license.txt',
            notice_sha256=hashlib.sha256(pyl).hexdigest(),notice_bytes=len(pyl),source_kind='exact PyPI same-version sdist',
            source_sha256=PYL_SOURCE,source_url=rows[0]['url'],source_bytes=len(sdist))],
            source_to_wheel_equivalence_claimed=False)
    except BaseException as e:
        d.update(exit=1,failure_kind=type(e).__name__,partials_retained=True)
        if type(e)is ValueError:d['reason']=str(e)
    (PHASE/'worker-result.json').write_text(json.dumps(d)+'\n')
try:
    os.umask(0o077);require(os.getuid()!=0 and owned(ROOT) and signal.getsignal(signal.SIGCHLD)==signal.SIG_DFL,'nonroot_owned_root')
    owner=json.loads(small(ROOT/'ownership.json',16384));disk()
    raw=small(ROOT/'wheel-intake/linux-wheels.json',262144)
    require(hashlib.sha256(raw).hexdigest()=='900a8ab850e85a84aafc2b4061758767902d377704c4cad22fb0041b30d5d5cf','metadata_pin')
    rows={r['name']:r for r in json.loads(raw)}
    require(rows['langsmith']['version']=='0.14.7' and rows['langsmith']['sha256']==LANG_WHEEL
        and rows['pyluach']['version']=='2.3.0' and rows['pyluach']['sha256']==PYL_WHEEL,'frozen_wheel_binding')
    require(not PHASE.exists() and not PHASE.is_symlink(),'fresh_phase');PHASE.mkdir(mode=0o700);created=True
    require(owned(PHASE),'phase_owner');child=os.fork()
    if child==0:
        try:work()
        finally:os._exit(0)
    pidfd=os.pidfd_open(child)
    while True:
        ended,status=os.waitpid(child,os.WNOHANG)
        if ended:
            reaped=True;require(os.waitstatus_to_exitcode(status)==0,'worker_exit')
            result=json.loads(small(PHASE/'worker-result.json',16384));break
        require(time.monotonic()-started<90,'parent_watchdog');disk();time.sleep(.05)
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
        require(owned(ROOT) and owned(PHASE),'receipt_owner');free=shutil.disk_usage('/').free
        result.update(phase_root=str(PHASE),host_free_bytes=free,phase1_host_introduced_bytes=owner['free_before']-free)
        if free<50000000000 or owner['free_before']-free>500000000:result.update(exit=1,disk_gate='FAILED')
        (PHASE/'notice-receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)
raise SystemExit(result['exit'])
