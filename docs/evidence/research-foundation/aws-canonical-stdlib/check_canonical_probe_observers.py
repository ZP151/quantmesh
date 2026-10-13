"""Software counterexamples: refused start and uncertain create, no Docker."""
import ast,json,os,shutil,subprocess,sys,uuid
from pathlib import Path
root=Path(__file__).resolve().parents[1];native=root.parent.parent/'a718/QuantMesh'
base=Path('/var/tmp/quantmesh-linux-native-90afdbee6add43169483520e384539ae/task2-tests')
assert base.resolve()==base and base.stat().st_uid==os.getuid()
fixture=base/('canonical-observers-'+uuid.uuid4().hex);fixture.mkdir(mode=0o700)
source=(root/'output/probe_aws_canonical_python.py').read_text()
fake='''def run(args,seconds=10):
 if args[0]=='info':return json.dumps(dict(ID=ENGINE,ServerVersion='29.9.0',Containers=0,Images=1)).encode()
 if args[:2]==['image','inspect']:
  c=json.loads(config_raw)
  return json.dumps([dict(Id=IMAGE,Config=c['config'],RootFS=dict(Layers=c['rootfs']['diff_ids']))]).encode()
 if args[:2]==['container','create']:
  if TEST_CASE=='uncertain-create':raise ValueError('simulated_create_unknown')
  return ('f'*64+'\\n').encode()
 if args[:2]==['container','inspect']:
  return json.dumps([dict(Id='f'*64,Image=IMAGE,Config=dict(Labels={'org.quantmesh.canonical-probe':nonce},
   Entrypoint=['/usr/local/bin/python3'],Cmd=['-B','-I','-S','-c',CODE],User='10001:10001'),
   HostConfig=dict(ReadonlyRootfs=True,NetworkMode='none',CapDrop=['ALL'],PidsLimit=32,Memory=134217728,MemorySwap=134217728,
    NanoCpus=1000000000,Tmpfs={'/tmp':'rw,noexec,nosuid,nodev,size=1m'},SecurityOpt=['no-new-privileges']),Mounts=[],
   State=dict(Running=False,Pid=0,StartedAt='0001-01-01T00:00:00Z'))]).encode()
 if args[:2]==['container','start']:raise ValueError('simulated_start_refused')
 if args[:2] in (['container','ls'],['container','rm']):return b''
 raise AssertionError('unexpected controller action')
'''
results=[];failed=0
for name in ['refused-start','uncertain-create']:
    owned=fixture/name;owned.mkdir(mode=0o700);(owned/'blobs').mkdir(mode=0o700)
    config=(native/'output/172-task2-proposal-20261013/amd64-config.json').read_bytes()
    (owned/'blobs/4f228bc1cbcfc794e4878312cfc241d368eff55a21c08d1e2bb263116c4ef524').write_bytes(config)
    (owned/'ownership.json').write_text(json.dumps(dict(free_before=shutil.disk_usage('/').free)))
    tree=ast.parse(source)
    for n in tree.body:
        if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='ROOT' for t in n.targets):
            n.value=ast.Call(func=ast.Name(id='Path',ctx=ast.Load()),args=[ast.Constant(str(owned))],keywords=[])
    first_try=next(i for i,n in enumerate(tree.body) if isinstance(n,ast.Try))
    tree.body[first_try:first_try]=ast.parse(fake).body
    code='TEST_CASE='+repr(name)+'\nconfig_raw='+repr(config)+'\n'+ast.unparse(ast.fix_missing_locations(tree))
    r=subprocess.run([sys.executable,'-B','-I','-S','-'],input=code.encode(),capture_output=True,timeout=5)
    assert r.returncode==1 and not r.stderr
    d=json.loads(r.stdout)
    ok=not d['container_started'] if name=='refused-start' else d.get('partial_create_quiescence')=='NOT_PROVEN'
    if not ok:failed+=1
    results.append(dict(case=name,expected_refusal_reported_truthfully=ok,recipe_exit=r.returncode,receipt=d))
print(json.dumps(dict(exit=1 if failed else 0,failed=failed,cases=results,actual_Docker=False,native_certificate=False)))
raise SystemExit(1 if failed else 0)
