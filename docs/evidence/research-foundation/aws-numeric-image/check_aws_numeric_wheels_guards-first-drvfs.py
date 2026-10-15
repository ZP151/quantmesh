"""Two actual native pre-network failures; owned tiny fixtures, no downloads."""
import ast,base64,json,os,shutil,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
native=root.parent.parent/'a718/QuantMesh'
fixture=root/'output/0038-aws-numeric-wheel-guards'
fixture.mkdir(mode=0o700,exist_ok=False)
meta=(native/'output/172-task2-proposal-20261013/linux-wheels.json').read_bytes()
lock=(root/'services/research_agent/requirements.linux-cp312.lock').read_bytes()
prefix='METADATA_B64='+repr(base64.b64encode(meta).decode())+'\nLOCK_B64='+repr(base64.b64encode(lock).decode())+'\n'
source=(root/'output/fetch_aws_numeric_wheels.py').read_text()
results=[]
for name in ('owner-fifo','wheelhouse-mkdir-failure'):
    owned=fixture/name;owned.mkdir(mode=0o700)
    if name=='owner-fifo':os.mkfifo(owned/'ownership.json',0o600)
    else:
        (owned/'ownership.json').write_text(json.dumps(dict(free_before=shutil.disk_usage('/').free,
            manifest_sha256='2ed6491b93cd49272ee6de2b5a38440c3448360322c089fc23e370722d74179d')))
    tree=ast.parse(source)
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='ROOT' for t in node.targets):
            node.value=ast.Call(func=ast.Name(id='Path',ctx=ast.Load()),args=[ast.Constant(str(owned))],keywords=[])
    code=prefix
    if name=='wheelhouse-mkdir-failure':
        code+='from pathlib import Path\n_real_mkdir=Path.mkdir\ndef _fault_mkdir(self,*a,**kw):\n if self.name=="wheelhouse":raise OSError("fixture injected")\n return _real_mkdir(self,*a,**kw)\nPath.mkdir=_fault_mkdir\n'
    code+=ast.unparse(ast.fix_missing_locations(tree))
    r=subprocess.run([sys.executable,'-B','-I','-S','-'],input=code.encode(),capture_output=True,timeout=5)
    assert r.returncode==1 and not r.stderr
    d=json.loads(r.stdout)
    assert d['exit']==1 and not d['docker_mutation'] and not d['container_started'] and not d['wheels_installed']
    if name=='owner-fifo':
        assert d['reason']=='input_owned_regular' and not (owned/'wheel-intake').exists()
    else:
        assert d['failure_kind']=='OSError' and not d['wheelhouse_created'] and d['retained_wheel_bytes']==0
        saved=json.loads((owned/'wheel-intake/intake-receipt.json').read_bytes())
        assert saved==d
    results.append(dict(case=name,actual_exit=r.returncode,receipt=d,network_started=False,download_child_started=False))
print(json.dumps(dict(exit=0,cases=results,scope='native tiny pre-network operator failures only')))
