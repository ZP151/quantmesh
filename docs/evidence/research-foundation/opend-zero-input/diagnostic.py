"""Owned local credential-free offline observation; never a startup qualification."""
import hashlib
import json
import os
import pty
import select
import signal
import subprocess
import tarfile
import tempfile
import termios
import time
from datetime import UTC, datetime
from pathlib import Path

out = Path('/mnt/c/Users/15492/.codex-clean/worktrees/6e1e/QuantMesh/output/0038-opend-zero-input')
out.mkdir(exist_ok=True)
archive = Path('/mnt/c/Users/15492/.codex-clean/worktrees/acf3/QuantMesh/output/task2-opend-qualification/moomoo_OpenD_10.10.7008_Ubuntu18.04.tar.gz')
assert os.getuid() == 1000
with archive.open('rb') as file:
    assert hashlib.file_digest(file, 'sha256').hexdigest() == '72eaa6e47b5cb8905306427b5e3679d591408243492e3e7acbc3a7d46f09a0aa'
owned = Path(tempfile.mkdtemp(prefix='quantmesh-opend-zero-input-', dir='/var/tmp'))
prefix = 'moomoo_OpenD_10.10.7008_Ubuntu18.04/moomoo_OpenD_10.10.7008_Ubuntu18.04/'
with tarfile.open(archive) as package:
    members = [item for item in package.getmembers() if item.name.startswith(prefix)]
    if any(not (item.isdir() or item.isfile()) or not (owned/item.name).resolve().is_relative_to(owned) for item in members):
        raise ValueError('unsafe pristine archive')
    package.extractall(owned, members=members, filter='data')
binary = owned/prefix/'OpenD'
with binary.open('rb') as file:
    binary_sha = hashlib.file_digest(file,'sha256').hexdigest()
assert binary_sha == 'e05b901dbe9107061b954a7fe3c059916c4a1e580d8f0a57277d402438898601'
home = owned/'empty-home'
home.mkdir(mode=0o700)
# Exact separately-owned noncredential bytes; no vendor configuration/state read.
config = owned/'candidate.xml'
config.write_bytes(b'''<?xml version="1.0" encoding="UTF-8"?>
<moomoo_opend>
  <ip>127.0.0.1</ip>
  <api_port>11112</api_port>
  <lang>en</lang>
  <log_level>no</log_level>
  <push_proto_type>0</push_proto_type>
  <auto_hold_quote_right>0</auto_hold_quote_right>
</moomoo_opend>
''')
assert hashlib.sha256(config.read_bytes()).hexdigest() == 'd6c9c112004bd0866dacc5d0e4fae4d715fcd6db250cd68cae859f787583bffb'
master, slave = pty.openpty()
flags = termios.tcgetattr(slave)
flags[3] &= ~(termios.ECHO | termios.ECHONL)
termios.tcsetattr(slave, termios.TCSANOW, flags)
shell = 'mount --bind "$1" /root && ip link set lo up && exec "$2" -cfg_file="$3" -api_ip=127.0.0.1 -api_port=11112 -auto_hold_quote_right=0 -no_monitor=1 -simulate_trade=disable -console=1 -log_level=no'
command = ['unshare','-Urnmpf','--mount-proc','--kill-child=KILL','--propagation','private',
           '/bin/sh','-c',shell,'qualification',str(home),str(binary),str(config)]
env = {'HOME':'/root','PATH':'/usr/bin:/bin:/usr/sbin:/sbin','LD_LIBRARY_PATH':str(binary.parent),'LANG':'C.UTF-8'}
process = subprocess.Popen(command,cwd=binary.parent,env=env,stdin=slave,stdout=slave,stderr=slave,start_new_session=True)
def start_ticks():
    raw = Path(f'/proc/{process.pid}/stat').read_text()
    return raw[raw.rfind(')')+2:].split()[19]
identity = start_ticks()
started = time.monotonic()
raw = b''
listened = False
try:
    while time.monotonic()-started < 30 and process.poll() is None:
        if select.select([master],[],[],0.2)[0]:
            try:
                raw = (raw + os.read(master,8192))[-65536:]
            except OSError:
                break
        try:
            lines = Path(f'/proc/{process.pid}/net/tcp').read_text().splitlines()[1:]
            listened |= any(line.split()[1]=='0100007F:2B68' and line.split()[3]=='0A' for line in lines)
        except (OSError, IndexError):
            pass
finally:
    # The unshare parent is this new owned process; killing it kills its new PID1
    # and the private namespace. Never enumerate or stop unrelated vendor processes.
    if process.poll() is None:
        assert start_ticks()==identity and os.getpgid(process.pid)==process.pid
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            assert start_ticks()==identity
            process.kill()
            process.wait(timeout=3)
    echo = bool(termios.tcgetattr(slave)[3] & termios.ECHO)
    os.close(master)
    os.close(slave)
text = raw.decode(errors='replace').lower()
receipt = {'observed_at':datetime.now(UTC).isoformat(), 'namespace':'user+network+mount+pid',
    'location':'local-owned-WSL-only','uid':os.getuid(),'owned_root':str(owned),
    'executable_sha256':binary_sha,'loopback_only_namespace':True,'input_bytes_sent':0,
    'sample_seconds':round(time.monotonic()-started,3),'exit':process.returncode,
    'prompt_keywords_observed':('account' in text or 'login' in text),'permission_error_observed':'permission denied' in text,
    'listener_11112_observed':listened,'tty_echo_after_sample':echo,'owned_parent_terminal':process.poll() is not None,
    'auth_attempted':False,'sdk_wire_verified':False,'private_input_verified':False,
    'raw_vendor_output_archived':False,'qualified_profile_changed':False}
(out/'witness.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
print(json.dumps(receipt,indent=2))
