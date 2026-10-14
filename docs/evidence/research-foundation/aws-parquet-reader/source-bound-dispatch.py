"""Execute one reviewed fixed probe in one fresh owned server phase."""
import base64,hashlib,shlex,subprocess,zlib
from pathlib import Path

out=Path(__file__).resolve().parent
source=(out/'probe_sealed_fd.py').read_bytes()
digest=hashlib.sha256(source).hexdigest()
assert len(source)==23739 and digest=='93da1b0e24bc9a8060ffe5679de7374646d75e36eb9702ae0f08b859f0de1770'
payload=base64.b64encode(zlib.compress(source)).decode()
remote=f'''import os,stat,pathlib,hashlib,base64,zlib,runpy
r=pathlib.Path('/home/ubuntu/quantmesh-numeric-materialization-4e00a5cecd0047fa9d5aa71c020a077a');s=r.lstat()
assert os.getuid()==1000 and r.resolve()==r and stat.S_ISDIR(s.st_mode) and s.st_uid==1000 and stat.S_IMODE(s.st_mode)==448 and not any(x.is_symlink() for x in (r,*r.parents))
phase=r/'canonical-parquet-sealed-fd';assert not phase.exists() and not phase.is_symlink()
b=zlib.decompress(base64.b64decode('{payload}'));assert len(b)=={len(source)} and hashlib.sha256(b).hexdigest()=='{digest}'
p=r/'operator-sealed-fd-{digest[:8]}.py';fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,384)
with os.fdopen(fd,'wb') as f:assert f.write(b)==len(b)
assert p.read_bytes()==b and p.stat().st_uid==1000 and stat.S_IMODE(p.stat().st_mode)==384 and p.stat().st_nlink==1 and not p.is_symlink() and r.lstat().st_ino==s.st_ino
runpy.run_path(str(p),run_name='__main__')
'''
with (out/'sealed-ssh.stdout.json').open('xb') as stdout,(out/'sealed-ssh.stderr.log').open('xb') as stderr:
 p=subprocess.Popen([r'C:\Program Files\Tailscale\tailscale.exe','ssh',
  'ubuntu@quantmesh-research-8gb.tail99d23c.ts.net','python3 -B -c '+shlex.quote(remote)],
  stdout=stdout,stderr=stderr)
 print('owned_fd_probe_started',p.pid,'source',digest,'bytes',len(source),flush=True)
 code=p.wait()
(out/'sealed-ssh.exit').write_text(str(code)+'\n',encoding='utf-8')
print('owned_fd_probe_exit',code,flush=True)
raise SystemExit(code)
