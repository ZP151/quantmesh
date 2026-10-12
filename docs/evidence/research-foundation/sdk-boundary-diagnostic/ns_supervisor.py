import json
import os
from pathlib import Path
import pty
import select
import signal
import subprocess
import sys
import termios
import time

root = Path(sys.argv[1])
release, receipts = map(int,sys.argv[2:4])
def emit(value):
    os.write(receipts,(json.dumps(value)+'\n').encode())
def safe_exception(kind,value,tb):
    while tb.tb_next is not None: tb=tb.tb_next
    emit({'supervisor_exception_class':kind.__name__,'supervisor_exception_line':tb.tb_lineno,'supervisor_exception_file':Path(tb.tb_frame.f_code.co_filename).name})
sys.excepthook=safe_exception
emit({'gate_waiting':True,'pid':os.getpid(),'namespaces':{n:os.readlink('/proc/self/ns/'+n) for n in ['user','net','mnt','pid']}})
assert os.read(release,1)==b'R'
os.close(release)
subprocess.run(['/bin/mount','--bind',str(root/'home'),'/root'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
subprocess.run(['/usr/sbin/ip','link','set','lo','up'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
interfaces = sorted(line.split(':',1)[0].strip() for line in Path('/proc/net/dev').read_text().splitlines()[2:])
emit({'namespace_proc_interfaces':interfaces,'inherited_sysfs_interfaces':sorted(p.name for p in Path('/sys/class/net').iterdir())})
assert interfaces == ['lo']
emit({'interfaces':interfaces,'home_mode':oct(Path('/root').stat().st_mode & 511),'gate_released':True})
binary = root/'vendor/moomoo_OpenD_10.10.7008_Ubuntu18.04/moomoo_OpenD_10.10.7008_Ubuntu18.04/OpenD'
env = {'HOME':'/root','PATH':'/usr/bin:/bin:/usr/sbin:/sbin','LANG':'C.UTF-8','LD_LIBRARY_PATH':str(binary.parent)}
master,slave = pty.openpty()
flags = termios.tcgetattr(slave)
flags[3] &= ~(termios.ECHO | termios.ECHONL)
termios.tcsetattr(slave,termios.TCSANOW,flags)
vendor = subprocess.Popen([str(binary),'-cfg_file='+str(root/'candidate.xml'),'-api_ip=127.0.0.1','-api_port=11112','-auto_hold_quote_right=0','-no_monitor=1','-simulate_trade=disable','-console=0','-log_level=no'],env=env,cwd=binary.parent,stdin=slave,stdout=slave,stderr=slave)
vfd = os.pidfd_open(vendor.pid)
emit({'vendor_pid':vendor.pid,'vendor_exe':os.readlink(f'/proc/{vendor.pid}/exe'),'vendor_pidfd_acquired':True,'namespaces':{n:os.readlink(f'/proc/{vendor.pid}/ns/'+n) for n in ['user','net','mnt','pid']}})
sdk = None
sfd = None
discarded = 0
listening = False
started = time.monotonic()
try:
    while time.monotonic()-started < 65:
        if select.select([master],[],[],.05)[0]:
            try: discarded += len(os.read(master,8192))
            except OSError: break
            if discarded > 1048576:
                emit({'output_cap_exceeded':True}); break
        if not listening:
            lines = Path('/proc/net/tcp').read_text().splitlines()[1:]
            listening = any(line.split()[1]=='0100007F:2B68' and line.split()[3]=='0A' for line in lines)
            if listening:
                emit({'loopback_listener':True,'vendor_socket_inodes':sorted(os.readlink(str(p)) for p in Path(f'/proc/{vendor.pid}/fd').iterdir() if os.readlink(str(p)).startswith('socket:'))})
                sdk = subprocess.Popen([str(root/'sdk-env/bin/python'),'-I',str(root/'sdk_observe.py'),str(receipts)],env={'HOME':'/root','PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},cwd=root,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,pass_fds=(receipts,))
                sfd = os.pidfd_open(sdk.pid)
                emit({'sdk_pid':sdk.pid,'sdk_pidfd_acquired':True})
        if sdk is not None and sdk.poll() is not None:
            break
        if vendor.poll() is not None:
            break
finally:
    if sdk is not None and sdk.poll() is None:
        signal.pidfd_send_signal(sfd,signal.SIGKILL)
    if sdk is not None:
        sdk.wait(timeout=3)
    if vendor.poll() is None:
        signal.pidfd_send_signal(vfd,signal.SIGTERM)
        try: vendor.wait(timeout=2)
        except subprocess.TimeoutExpired:
            signal.pidfd_send_signal(vfd,signal.SIGKILL)
    vendor.wait(timeout=3)
    emit({'vendor_exit':vendor.returncode,'sdk_exit':None if sdk is None else sdk.returncode,'vendor_output_discarded_bytes':discarded,'input_bytes':0,'inner_owned_cleanup':True,'elapsed_seconds':round(time.monotonic()-started,3),'processes_remaining_in_namespace':sorted(p.name for p in Path('/proc').iterdir() if p.name.isdecimal())})
    os.close(vfd)
    if sfd is not None: os.close(sfd)
    os.close(master); os.close(slave)
