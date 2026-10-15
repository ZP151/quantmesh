from pathlib import Path
import hashlib, json, os, signal, subprocess, sys, threading
root=Path('/mnt/c/Users/15492/.codex-clean/worktrees/0038-research-integration/QuantMesh')
owned=Path('/var/tmp/quantmesh-portfolio-runtime-9r8rsnwz')
checkout=owned/'integration-f3a72af-checkout'
out=root/'output/0038-staging-order-green'
if len(sys.argv)>1 and sys.argv[1]=='child':
    import pytest
    snapshots=[]
    class Snapshot:
        def pytest_runtest_setup(self,item):
            snapshots.append({'node':item.nodeid,'threads':[{'name':t.name,'daemon':t.daemon,'alive':t.is_alive()} for t in threading.enumerate()], 'sigchld':str(signal.getsignal(signal.SIGCHLD))})
        def pytest_sessionfinish(self,session,exitstatus):
            (out/'state.json').write_text(json.dumps({'snapshots':snapshots,'exit':int(exitstatus)},indent=2)+'\n')
    raise SystemExit(pytest.main(['--rootdir',str(root),'-c','/dev/null','-p','pytest_asyncio.plugin','-p','no:cacheprovider','--confcutdir',str(root/'tests'),str(root/'tests/test_live_fence.py'),str(root/'tests/test_live_moomoo.py'),str(root/'tests/test_opend_staging_window.py'),'--basetemp',str(owned/'staging-order-green-tmp'),'--junitxml',str(out/'tests.xml'),'-q'],plugins=[Snapshot()]))
out.mkdir(exist_ok=False)
sources={}
for relative in ('tests/test_live_fence.py','tests/test_live_moomoo.py','tests/test_opend_staging_window.py','deploy/aws/opend/stage_console.py'):
    actual=(root/relative).read_bytes()
    if relative not in ('tests/test_live_moomoo.py','tests/test_live_fence.py'): assert actual==(checkout/relative).read_bytes(),relative
    sources[relative]=hashlib.sha256(actual).hexdigest()
env={'PATH':'/usr/bin:/bin','HOME':str(owned/'home'),'TMPDIR':str(owned),'PYTHONDONTWRITECODE':'1','PYTHONDONTWRITEBYTECODE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','PYTHONPATH':os.pathsep.join(str(checkout/p) for p in ('','src','tests'))}
with (out/'tests.stdout').open('wb') as stdout,(out/'tests.stderr').open('wb') as stderr:
    result=subprocess.run([str(owned/'venv/bin/python'),'-B',str(Path(__file__).resolve()),'child'],cwd=checkout,env=env,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,start_new_session=True,timeout=90)
(out/'tests.exit').write_text(str(result.returncode)+'\n')
receipt={'exit':result.returncode,'candidate_head':'57a66f84d4e101d54410fcfa49ea2ee064f2ba33','native_checkout':'f3a72af','exact_tested_source_sha256':sources,'scope':'SCRIPTED_LIVE_TEST_ORDER_AND_SYNTHETIC_NATIVE_STAGING_ONLY','market_requests':0,'model_calls':0,'production_qualified':False}
(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
raise SystemExit(result.returncode)



