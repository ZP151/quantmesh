import hashlib
import json
import os
from pathlib import Path
import select
import shutil
import signal
import subprocess
import tarfile
import time

OUT = Path('/mnt/c/Users/15492/.codex-clean/worktrees/6e1e/QuantMesh/output/169-sdk-boundary-diagnostic')
ROOT = Path((OUT/'native-root.txt').read_text())
BASE_ROOT = ROOT
ROOT = ROOT/'attempt6'
ROOT.mkdir(mode=0o700)
assert os.getuid()==1000 and ROOT.stat().st_uid==1000 and ROOT.stat().st_mode&511==448
started = time.monotonic()
deadline = started+90
archive = Path('/mnt/c/Users/15492/.codex-clean/worktrees/acf3/QuantMesh/output/task2-opend-qualification/moomoo_OpenD_10.10.7008_Ubuntu18.04.tar.gz')
assert archive.stat().st_size==466932458
with archive.open('rb') as f: archive_sha = hashlib.file_digest(f,'sha256').hexdigest()
assert archive_sha=='72eaa6e47b5cb8905306427b5e3679d591408243492e3e7acbc3a7d46f09a0aa'
vendor_root = ROOT/'vendor'
vendor_root.mkdir(mode=0o700)
prefix = 'moomoo_OpenD_10.10.7008_Ubuntu18.04/moomoo_OpenD_10.10.7008_Ubuntu18.04/'
with tarfile.open(archive) as t:
    members = [m for m in t.getmembers() if m.name.startswith(prefix)]
    assert members and all((m.isfile() or m.isdir()) and (vendor_root/m.name).resolve().is_relative_to(vendor_root) for m in members)
    t.extractall(vendor_root,members=members,filter='data')
binary = vendor_root/prefix/'OpenD'
with binary.open('rb') as f: binary_sha = hashlib.file_digest(f,'sha256').hexdigest()
assert binary_sha=='e05b901dbe9107061b954a7fe3c059916c4a1e580d8f0a57277d402438898601'
(ROOT/'home').mkdir(mode=0o700)
config = b'''<?xml version="1.0" encoding="UTF-8"?>
<moomoo_opend>
  <ip>127.0.0.1</ip>
  <api_port>11112</api_port>
  <lang>en</lang>
  <log_level>no</log_level>
  <push_proto_type>0</push_proto_type>
  <auto_hold_quote_right>0</auto_hold_quote_right>
</moomoo_opend>
'''
assert hashlib.sha256(config).hexdigest()=='d6c9c112004bd0866dacc5d0e4fae4d715fcd6db250cd68cae859f787583bffb'
(ROOT/'candidate.xml').write_bytes(config)
for n in ['sdk_observe.py','ns_supervisor.py']: shutil.copyfile(OUT/n,ROOT/n)
os.symlink(BASE_ROOT/'sdk-env',ROOT/'sdk-env')
read_release,write_release = os.pipe()
read_receipt,write_receipt = os.pipe()
env = {'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','HOME':str(ROOT),'LANG':'C.UTF-8'}
sibling = subprocess.Popen(['/bin/sleep','100'],env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
sibling_fd = os.pidfd_open(sibling.pid)
command = ['unshare','-Urnmpf','--mount-proc','--kill-child=KILL','--propagation','private','/usr/bin/python3.12','-I',str(ROOT/'ns_supervisor.py'),str(ROOT),str(read_release),str(write_receipt)]
p = subprocess.Popen(command,env=env,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,pass_fds=(read_release,write_receipt))
parent_fd = os.pidfd_open(p.pid)
os.close(read_release); os.close(write_receipt)
events = []
raw = b''
pid1_fd = None
nsfds = []
receipt = {'baseline':'9b72aa4bf324021b81ec76e071c07b3125e6ee47','native_uid':os.getuid(),'owned_root':str(ROOT),'archive_sha256':archive_sha,'archive_bytes':archive.stat().st_size,'executable_sha256':binary_sha,'configuration_sha256':hashlib.sha256(config).hexdigest(),'protocol_handshake':False,'deadline_seconds':90,'controller_pid':p.pid,'controller_pidfd_before_release':True,'sdk_vendor_raw_output_archived':False}
try:
    gate_deadline = min(deadline-10,time.monotonic()+5)
    while time.monotonic()<gate_deadline and p.poll() is None:
        if select.select([read_receipt],[],[],.05)[0]:
            raw += os.read(read_receipt,8192)
            if b'\n' in raw: break
    assert b'\n' in raw, 'namespace gate unavailable'
    first,raw = raw.split(b'\n',1)
    gate = json.loads(first)
    assert gate['gate_waiting'] is True and gate['pid']==1
    events.append(gate)
    children = Path(f'/proc/{p.pid}/task/{p.pid}/children').read_text().split()
    assert len(children)==1
    child = int(children[0])
    pid1_fd = os.pidfd_open(child)
    identity = Path(f'/proc/{child}/stat').read_text()
    receipt['namespace_pid1_host_pid'] = child
    receipt['namespace_pid1_start_ticks'] = identity[identity.rfind(')')+2:].split()[19]
    receipt['namespace_pid1_pidfd_before_release'] = True
    actual = {n:os.readlink(f'/proc/{child}/ns/{n}') for n in ['user','net','mnt','pid']}
    assert actual==gate['namespaces']
    assert all(actual[n]!=os.readlink('/proc/self/ns/'+n) for n in actual)
    for n in actual: nsfds.append(os.open(f'/proc/{child}/ns/{n}',os.O_RDONLY))
    receipt['namespace_handles_before_release'] = True
    receipt['namespace_identity'] = actual
    os.write(write_release,b'R'); os.close(write_release); write_release=None
    while time.monotonic()<deadline-6 and p.poll() is None:
        if select.select([read_receipt],[],[],.1)[0]:
            chunk = os.read(read_receipt,8192)
            if not chunk: break
            raw += chunk
            assert len(raw)<65536
            while b'\n' in raw:
                line,raw = raw.split(b'\n',1)
                events.append(json.loads(line))
    p.wait(timeout=max(.1,min(2,deadline-time.monotonic()-4)))
except BaseException as e:
    receipt['controller_exception_class'] = type(e).__name__
finally:
    if pid1_fd is not None and not select.select([pid1_fd],[],[],0)[0]:
        signal.pidfd_send_signal(pid1_fd,signal.SIGKILL)
    if p.poll() is None:
        signal.pidfd_send_signal(parent_fd,signal.SIGKILL)
    p.wait(timeout=3)
    if select.select([read_receipt],[],[],0)[0]:
        raw += os.read(read_receipt,65536)
    for line in raw.splitlines():
        try: events.append(json.loads(line))
        except json.JSONDecodeError: receipt['receipt_incomplete']=True
    receipt['controller_exit'] = p.returncode
    receipt['namespace_pid1_terminal'] = pid1_fd is not None and bool(select.select([pid1_fd],[],[],1)[0])
    receipt['known_sibling_survived'] = sibling.poll() is None and not select.select([sibling_fd],[],[],0)[0]
    signal.pidfd_send_signal(sibling_fd,signal.SIGTERM)
    sibling.wait(timeout=3)
    receipt['owned_sibling_cleanup_exit'] = sibling.returncode
    for fd in [parent_fd,sibling_fd,read_receipt,*nsfds]: os.close(fd)
    if pid1_fd is not None: os.close(pid1_fd)
    if write_release is not None: os.close(write_release)
receipt['events'] = events
receipt['elapsed_seconds'] = round(time.monotonic()-started,3)
receipt['within_deadline'] = receipt['elapsed_seconds']<90
receipt['protocol_handshake'] = any(e.get('protocol_handshake') is True for e in events)
receipt['shared_profile_changed'] = False
receipt['actual_host_auth_source_qualified'] = False
(OUT/'native-witness.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt,indent=2))
raise SystemExit(0 if receipt['protocol_handshake'] and receipt['namespace_pid1_terminal'] and receipt['known_sibling_survived'] and receipt['within_deadline'] and any(e.get('sdk_closed') is True for e in events) else 2)
