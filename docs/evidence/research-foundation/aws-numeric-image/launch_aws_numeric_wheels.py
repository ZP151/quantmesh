"""Send existing public metadata from memory; no local wheel/cache copies."""
import base64,hashlib,json,subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[1]
native=root.parent.parent/'a718/QuantMesh'
metadata=(native/'output/172-task2-proposal-20261013/linux-wheels.json').read_bytes()
lock=(root/'services/research_agent/requirements.linux-cp312.lock').read_bytes()
assert hashlib.sha256(metadata).hexdigest()=='900a8ab850e85a84aafc2b4061758767902d377704c4cad22fb0041b30d5d5cf'
assert hashlib.sha256(lock).hexdigest()=='07f4e7ec64805a375e0bdc707d0158fbdb08bd07d02aa569e2d119496b32592a'
code=(root/'output/fetch_aws_numeric_wheels.py').read_bytes()
prefix=('METADATA_B64='+repr(base64.b64encode(metadata).decode())+'\nLOCK_B64='+repr(base64.b64encode(lock).decode())+'\n').encode()
r=subprocess.run(['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10',
    '-o','ServerAliveInterval=5','-o','ServerAliveCountMax=2','ubuntu@quantmesh-research-8gb.tail99d23c.ts.net',
    'python3','-B','-'],input=prefix+code,capture_output=True,timeout=270)
(root/'output/0038-aws-numeric-wheel-intake.json').write_bytes(r.stdout)
(root/'output/0038-aws-numeric-wheel-intake.stderr').write_bytes(r.stderr)
(root/'output/0038-aws-numeric-wheel-intake.exit').write_text(str(r.returncode)+'\n')
if r.stdout:
    receipt=json.loads(r.stdout)
    print(json.dumps({k:v for k,v in receipt.items() if k!='artifacts'}))
else:print('SSH returned no receipt; inspect owned phase before any retry.')
raise SystemExit(r.returncode)
