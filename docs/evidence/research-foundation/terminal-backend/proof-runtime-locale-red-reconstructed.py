import ctypes,fcntl,json,os,pathlib,select,signal,socket,stat,struct,sys,time

O=pathlib.Path(__file__).resolve().parent
R=pathlib.Path((O/'native-root.txt').read_text().strip())
F=R/'fixture-root'
PRE='--preflight' in sys.argv
START=time.monotonic()
C=ctypes.CDLL(None,use_errno=True)
NAMES=('user','net','mnt','pid')
COMMANDS=[]
def check(ok,code):
    if not ok: raise RuntimeError(code)
def call(name,*args):
    check(getattr(C,name)(*args)==0,name+'-errno-'+str(ctypes.get_errno()))
def b(p): return os.fsencode(p) if p is not None else None
def mount(src,dst,kind,flags=0,data=None): call('mount',b(src),b(dst),b(kind),ctypes.c_ulong(flags),b(data))
def alive(fd): return not select.select([fd],[],[],0)[0]
def ticks(pid): return pathlib.Path('/proc',str(pid),'stat').read_text().rsplit(')',1)[1].split()[19]
def namespaces(pid): return {n:os.stat('/proc/'+str(pid)+'/ns/'+n).st_ino for n in NAMES}
def send(sock,row): sock.send(json.dumps(row).encode())
def recv(sock,timeout=5):
    check(select.select([sock],[],[],timeout)[0],'ipc-timeout')
    data=sock.recv(8192); check(bool(data),'ipc-closed'); return json.loads(data)
def held_fork(action):
    rd,wr=os.pipe(); pid=os.fork()
    if pid==0:
        os.close(wr)
        signal.signal(signal.SIGALRM,lambda *_:os._exit(45)); signal.alarm(75)
        try:
            check(select.select([rd],[],[],3)[0] and os.read(rd,1)==b'R','gate-not-released')
            os.close(rd); action(); os._exit(0)
        except BaseException: os._exit(46)
    os.close(rd)
    fd=os.pidfd_open(pid); ns={n:os.open('/proc/'+str(pid)+'/ns/'+n,os.O_RDONLY) for n in NAMES}
    h={'pid':pid,'fd':fd,'nsfds':ns,'ticks':ticks(pid),'identities':{n:os.fstat(f).st_ino for n,f in ns.items()},'gate':wr}
    return h
def valid(h,expected=None):
    if h.get('fd') is None or not alive(h['fd']): return False
    try:
        return h['ticks']==ticks(h['pid']) and namespaces(h['pid'])==(expected or h['identities'])
    except OSError: return False
def release(h):
    check(valid(h),'ownership-denied-before-release'); os.write(h['gate'],b'R'); os.close(h['gate']); h['gate']=-1
def stop(h):
    if alive(h['fd']):
        check(valid(h),'unknown-identity-cleanup-pending')
        signal.pidfd_send_signal(h['fd'],signal.SIGKILL)
    check(select.select([h['fd']],[],[],3)[0],'cleanup-pending')
    _,status=os.waitpid(h['pid'],0)
    for fd in h['nsfds'].values(): os.close(fd)
    os.close(h['fd']); return os.waitstatus_to_exitcode(status)

PANE=r'''
import fcntl,json,os,pathlib,signal,sys,termios,time,types
signal.signal(signal.SIGALRM,lambda *_:sys.exit(48)); signal.alarm(60)
module=types.ModuleType('qm_admission');sys.modules[module.__name__]=module
source=pathlib.Path('/proof/admission.py').read_bytes()
exec(compile(source,'/proof/admission.py','exec'),module.__dict__)
os.fchmod(0,0o600)
a=termios.tcgetattr(0);a[3]&=~(termios.ECHO|termios.ECHONL);termios.tcsetattr(0,termios.TCSANOW,a)
base=module.inspect_private_terminal(0,1,2,expected_uid=os.getuid())
negative={}
def deny(name,fn):
    try: fn()
    except module.TerminalQualificationError as e: negative[name]=e.code
    else: raise RuntimeError('negative-not-denied')
deny('wrong-owner',lambda:module.inspect_private_terminal(0,1,2,expected_uid=1))
os.fchmod(0,0o620)
deny('nonprivate-mode',lambda:module.inspect_private_terminal(0,1,2,expected_uid=0))
os.fchmod(0,0o600)
on=termios.tcgetattr(0);on[3]|=termios.ECHO;termios.tcsetattr(0,termios.TCSANOW,on)
deny('echo-enabled',lambda:module.inspect_private_terminal(0,1,2,expected_uid=0))
termios.tcsetattr(0,termios.TCSANOW,a)
null=os.open('/dev/null',os.O_RDWR)
deny('not-tty',lambda:module.inspect_private_terminal(null,1,2,expected_uid=0));os.close(null)
ro=os.open(os.ttyname(0),os.O_RDONLY)
deny('wrong-output-direction',lambda:module.inspect_private_terminal(0,ro,2,expected_uid=0));os.close(ro)
master,slave=os.openpty();os.fchmod(slave,0o600);off=termios.tcgetattr(slave);off[3]&=~(termios.ECHO|termios.ECHONL);termios.tcsetattr(slave,termios.TCSANOW,off)
deny('mismatched-tty',lambda:module.inspect_private_terminal(0,slave,2,expected_uid=0));os.close(master);os.close(slave)
base=module.inspect_private_terminal(0,1,2,expected_uid=0)
info={'pid':os.getpid(),'ppid':os.getppid(),'tty':os.ttyname(0),'terminal':base,'negatives':negative,'namespace':{n:os.stat('/proc/self/ns/'+n).st_ino for n in ('user','net','mnt','pid')},'no_new_privs':next(s for s in pathlib.Path('/proc/self/status').read_text().splitlines() if s.startswith('NoNewPrivs:')),'stdout_bytes':0,'stdin_bytes':0}
p=pathlib.Path('/proof/pane.json');p.write_text(json.dumps(info));p.chmod(0o600)
while not pathlib.Path('/proof/pane-release').exists():time.sleep(.02)
pathlib.Path('/proof/pane-released').touch(mode=0o600)
while True:time.sleep(.1)
'''

def manager(channel):
    owned=[];report={'checks':{},'commands':COMMANDS,'false_flags':{n:False for n in ['production_release_qualified','actual_systemd_cgroup','source_host_private_input_verified','private_input_verified','operator_authenticated','sdk_wire_verified','market_verified','installation_approved','pc_independence_verified']}}
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(RuntimeError('native-deadline')));signal.alarm(65)
    try:
        mount('proc',F/'proc','proc',14)
        mount('devpts',F/'dev/pts','devpts',10,'newinstance,uid=0,gid=0,mode=0600,ptmxmode=0666')
        for node in ['null','zero','urandom']: mount('/dev/'+node,F/'dev'/node,None,4096)
        os.chroot(F);os.chdir('/home/fixture');os.umask(0o077)
        call('prctl',38,1,0,0,0) # PR_SET_NO_NEW_PRIVS
        for fd in range(3,1024):
            if fd!=channel.fileno():
                try: os.close(fd)
                except OSError: pass
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as net:
            flags=fcntl.ioctl(net.fileno(),0x8913,struct.pack('16sH14s',b'lo',0,b''))
            previous=struct.unpack('16sH14s',flags)[1]
            fcntl.ioctl(net.fileno(),0x8914,struct.pack('16sH14s',b'lo',previous|1,b''))
        interfaces=[line.split(':')[0].strip() for line in pathlib.Path('/proc/net/dev').read_text().splitlines()[2:]]
        check(interfaces==['lo'],'unexpected-network-interface')
        check(len(pathlib.Path('/proc/net/route').read_text().splitlines())==1,'unexpected-network-route')
        check(os.getpid()==1 and os.getuid()==0,'namespace-init-identity')
        check(not pathlib.Path('/run/systemd').exists() and not pathlib.Path('/run/user').exists(),'unexpected-system-bus')
        report['isolation']={'pid':1,'uid':0,'uid_map':pathlib.Path('/proc/self/uid_map').read_text().strip(),'namespaces':namespaces(1),'interfaces':interfaces,'no_route':True,'chroot':True,'private_devpts':True,'private_utmp':True,'bare_home':not any(pathlib.Path('/home/fixture').iterdir()),'no_new_privs':next(s for s in pathlib.Path('/proc/self/status').read_text().splitlines() if s.startswith('NoNewPrivs:'))}
        send(channel,{'kind':'isolated','isolation':report['isolation']})
        check(recv(channel)['release'] is True,'outer-release-missing')
        if PRE:
            report['checks']['no_candidate_executed']=True
        else:
            ENV={'HOME':'/home/fixture','PATH':'/usr/bin','TERM':'dumb','LANG':'C','PYTHONDONTWRITEBYTECODE':'1'}
            tmux=['/usr/bin/tmux','-S','/run/fixture.sock','-f','/proof/tmux.conf']
            def execute(args):
                null=os.open('/dev/null',os.O_RDWR)
                for fd in (0,1,2):os.dup2(null,fd)
                os.close(null);os.execve(args[0],args,ENV)
            sibling=held_fork(lambda:time.sleep(55));owned.append(sibling);release(sibling)
            server=held_fork(lambda:execute(tmux+['-D']));owned.append(server)
            report['server_before_release']={'pid':server['pid'],'ticks':server['ticks'],'ns':server['identities'],'pidfd_owned':True,'held_before_exec':True}
            report['checks']['missing_handle_refused']=not valid({**server,'fd':None})
            changed={**server['identities'],'pid':server['identities']['pid']+1}
            report['checks']['replaced_identity_refused']=not valid(server,changed)
            release(server)
            until=time.monotonic()+4
            while not pathlib.Path('/run/fixture.sock').exists() and time.monotonic()<until:
                check(alive(server['fd']),'foreground-server-exited');time.sleep(.02)
            sock=pathlib.Path('/run/fixture.sock');si=sock.stat()
            check(stat.S_ISSOCK(si.st_mode) and stat.S_IMODE(si.st_mode)==0o600 and si.st_uid==0,'socket-not-private')
            sig=(si.st_dev,si.st_ino,si.st_uid,si.st_mode)
            report['socket']={'mode':stat.S_IMODE(si.st_mode),'uid':si.st_uid,'inode':si.st_ino,'dev':si.st_dev}
            def client(args):
                check(valid(server),'server-ownership-changed')
                q=sock.stat();check((q.st_dev,q.st_ino,q.st_uid,q.st_mode)==sig,'socket-replaced')
                rd,wr=os.pipe()
                def invoke():
                    os.close(rd);null=os.open('/dev/null',os.O_RDWR);os.dup2(null,0);os.dup2(wr,1);os.dup2(null,2);os.close(wr);os.close(null);os.execve(tmux[0],tmux+['-N']+args,ENV)
                h=held_fork(invoke);owned.append(h);os.close(wr);release(h)
                buf=b'';deadline=time.monotonic()+4
                while time.monotonic()<deadline:
                    if select.select([rd],[],[],.03)[0]:
                        chunk=os.read(rd,1024)
                        if not chunk:break
                        buf+=chunk;check(len(buf)<=4096,'metadata-output-limit')
                os.close(rd)
                check(select.select([h['fd']],[],[],1)[0],'client-did-not-exit')
                _,status=os.waitpid(h['pid'],0);rc=os.waitstatus_to_exitcode(status)
                for fd in h['nsfds'].values():os.close(fd)
                os.close(h['fd']);owned.remove(h)
                text=buf.decode();COMMANDS.append({'argv':tmux+['-N']+args,'exit':rc,'stdout':text,'stderr':'discarded; no terminal stream retained'})
                check(rc==0,'metadata-client-failed');return text
            client(['new-session','-d','-s','fixture','-x','80','-y','24','/usr/bin/python3.12','-I','-S','/proof/pane.py'])
            until=time.monotonic()+4
            while not pathlib.Path('/proof/pane.json').exists() and time.monotonic()<until:time.sleep(.02)
            pane=json.loads(pathlib.Path('/proof/pane.json').read_text());report['pane']=pane
            pid=pane['pid'];fd=os.pidfd_open(pid);nsfds={n:os.open('/proc/'+str(pid)+'/ns/'+n,os.O_RDONLY) for n in NAMES}
            paneheld={'pid':pid,'fd':fd,'nsfds':nsfds,'ticks':ticks(pid),'identities':{n:os.fstat(f).st_ino for n,f in nsfds.items()},'gate':-1}
            # Identity is from this admitted server's own metadata and fixed child, never a borrowed process.
            check(pane['ppid']==server['pid'] and pane['namespace']==server['identities'],'pane-not-owned-server-child')
            pathlib.Path('/proof/pane-release').touch(mode=0o600)
            fmt='#{pid}:#{pane_pid}:#{pane_id}:#{pane_tty}:#{session_attached}:#{pane_dead}'
            first=client(['display-message','-p','-t','fixture',fmt]).strip()
            fields=first.split(':');check(fields[0]==str(server['pid']) and fields[1]==str(pid) and fields[3]==pane['tty'] and fields[-2:]==['0','0'],'server-pane-identity-mismatch')
            check(client(['list-clients','-F','#{client_pid}'])=='','unexpected-attached-client')
            report['checks']['originating_client_exited']=True
            time.sleep(.4)
            check(valid(server) and valid(paneheld),'detached-lifetime-not-preserved')
            second=client(['display-message','-p','-t','fixture',fmt]).strip()
            report['checks']['new_client_observed_same_identity']=first==second
            report['checks']['pane_alive_after_clients_exit']=valid(paneheld)
            check(pathlib.Path('/proof/pane-released').exists(),'pane-release-not-observed')
            report['metadata_before']=first;report['metadata_after']=second
            report['maps']={}
            for role,p in [('server',server['pid']),('pane',pid)]:
                paths=sorted({line.split()[-1] for line in pathlib.Path('/proc',str(p),'maps').read_text().splitlines() if line.split()[-1].startswith('/')})
                report['maps'][role]=paths
            report['checks']['history_disabled']=client(['show-options','-g','-v','history-limit']).strip()=='0'
            client(['kill-server'])
            check(select.select([server['fd']],[],[],3)[0],'server-stop-pending')
            check(select.select([fd],[],[],3)[0],'pane-cleanup-pending')
            report['checks']['server_terminal_after_stop']=True
            report['checks']['pane_terminal_after_stop']=True
            report['checks']['known_sibling_survived_server_stop']=valid(sibling)
            for f in nsfds.values():os.close(f)
            os.close(fd)
            # PID1 reaps this server's exited synthetic pane, including reparented children.
            try:
                w,status=os.waitpid(pid,0);report['pane_exit']=os.waitstatus_to_exitcode(status)
            except ChildProcessError: report['pane_exit']='already reaped by owned server'
            report['server_exit']=stop(server);owned.remove(server)
            report['sibling_exit']=stop(sibling);owned.remove(sibling)
            report['checks']['socket_unlinked']=not sock.exists()
            for name in ['run/utmp','var/log/wtmp']:
                s=pathlib.Path('/'+name).stat();report.setdefault('private_utmp_metadata',{})[name]={'bytes':s.st_size,'inode':s.st_ino,'uid':s.st_uid}
        check(all(report['checks'].values()),'required-check-failed')
        report['status']='passed';rc=0
    except BaseException as e:
        report['status']='pending';report['diagnostic']=type(e).__name__+':'+str(e)[:150];rc=1
    finally:
        for h in list(reversed(owned)):
            try:stop(h);owned.remove(h)
            except BaseException:report['status']='pending';report['cleanup_unverified']=True;rc=1
        report['elapsed_inner_seconds']=time.monotonic()-START
        pathlib.Path('/proof/receipt-'+('preflight' if PRE else 'native')+'.json').write_text(json.dumps(report,indent=2))
        send(channel,{'kind':'result','status':report['status'],'exit':rc})
    os._exit(rc)

def setup(channel):
    try:
        uid,gid=os.getuid(),os.getgid()
        call('unshare',0x10000000)
        pathlib.Path('/proc/self/setgroups').write_text('deny')
        pathlib.Path('/proc/self/uid_map').write_text('0 '+str(uid)+' 1')
        pathlib.Path('/proc/self/gid_map').write_text('0 '+str(gid)+' 1')
        call('unshare',0x40000000|0x00020000|0x20000000)
        mount(None,'/',None,16384|262144)
        managerpid=os.fork()
        if managerpid==0:manager(channel)
        fd=os.pidfd_open(managerpid)
        _,status=os.waitpid(managerpid,0)
        check(select.select([fd],[],[],0)[0],'namespace-init-not-terminal');os.close(fd)
        os._exit(os.waitstatus_to_exitcode(status))
    except BaseException as e:
        send(channel,{'kind':'setup-failure','diagnostic':type(e).__name__+':'+str(e)[:150]});os._exit(1)

if __name__=='__main__':
    check((O/'license-admission.json').exists(),'license-prerequisite-missing')
    (F/'proof/pane.py').write_text(PANE)
    # Every run has a fresh root home; no previous runtime socket or gates may be reused.
    check(not (F/'run/fixture.sock').exists(),'existing-socket-refused')
    for n in ['pane.json','pane-release','pane-released']:check(not (F/'proof'/n).exists(),'previous-fixture-refused')
    original=namespaces(os.getpid());left,right=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
    outside=held_fork(lambda:time.sleep(80));release(outside)
    rd,wr=os.pipe();pid=os.fork()
    if pid==0:
        os.close(wr);left.close();os.read(rd,1);os.close(rd);setup(right)
    os.close(rd);right.close()
    fd=os.pidfd_open(pid)
    # This direct fork is owned before its namespace setup or any candidate execution.
    os.write(wr,b'R');os.close(wr)
    result={'preflight':PRE,'owned_setup_pid':pid,'setup_pidfd_before_release':True}
    try:
        message=recv(left,8);result['first']=message
        check(message.get('kind')=='isolated','isolation-not-established')
        ns=message['isolation']['namespaces'];check(all(ns[n]!=original[n] for n in NAMES),'namespace-not-fresh')
        result['all_namespaces_differ_from_controller']=True
        send(left,{'release':True})
        result['result']=recv(left,60)
    except BaseException as e:result['diagnostic']=type(e).__name__+':'+str(e)[:150]
    finally:
        if not select.select([fd],[],[],3)[0]:signal.pidfd_send_signal(fd,signal.SIGKILL)
        check(select.select([fd],[],[],3)[0],'outer-cleanup-pending')
        _,status=os.waitpid(pid,0);os.close(fd);result['raw_exit']=os.waitstatus_to_exitcode(status)
        result['outside_sibling_survives']=valid(outside);result['outside_sibling_exit']=stop(outside)
        result['elapsed_seconds_including_cleanup']=time.monotonic()-START
        result['within_90_seconds']=result['elapsed_seconds_including_cleanup']<=90
        left.close()
        (O/('preflight-controller.json' if PRE else 'native-controller.json')).write_text(json.dumps(result,indent=2))
        receipt=F/'proof'/('receipt-preflight.json' if PRE else 'receipt-native.json')
        if receipt.exists():(O/receipt.name).write_bytes(receipt.read_bytes())
    print(json.dumps(result))
    sys.exit(0 if result['raw_exit']==0 and result['within_90_seconds'] and result['outside_sibling_survives'] else 1)
