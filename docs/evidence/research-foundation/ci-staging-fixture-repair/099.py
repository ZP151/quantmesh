from pathlib import Path
import json,os,subprocess
root=Path('/mnt/c/Users/15492/.codex-clean/worktrees/0038-research-integration/QuantMesh')
owned=Path('/var/tmp/quantmesh-portfolio-runtime-9r8rsnwz')
out=root/'output/0038-staging-repair-seal'
out.mkdir(exist_ok=False)
env={'PATH':'/usr/bin:/bin','HOME':str(owned/'home'),'TMPDIR':str(owned),'PYTHONDONTWRITEBYTECODE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1'}
codes={}
for name,args in [('ruff',[str(owned/'venv/bin/python'),'-B','-m','ruff','check',str(root/'tests/test_live_fence.py'),str(root/'tests/test_live_moomoo.py')]),('dependency-after',[str(owned/'venv/bin/python'),'-B',str(owned/'admit.py'),str(owned/'integration-f3a72af-checkout')])]:
    with (out/(name+'.stdout')).open('wb') as stdout,(out/(name+'.stderr')).open('wb') as stderr:
        result=subprocess.run(args,cwd=owned,env=env,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,start_new_session=True,timeout=45)
    (out/(name+'.exit')).write_text(str(result.returncode)+'\n')
    codes[name]=result.returncode
(out/'checked.json').write_text(json.dumps({'codes':codes,'bytecode_after':len(list((owned/'venv').rglob('*.pyc'))),'scope':'DEPENDENCY_ADMISSION_AND_TWO_TEST_FILE_LINT_ONLY'},indent=2)+'\n')
print(json.dumps(codes))
raise SystemExit(any(codes.values()))
