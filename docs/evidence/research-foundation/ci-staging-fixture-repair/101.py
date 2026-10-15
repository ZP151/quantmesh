from pathlib import Path
import json,os,subprocess
root=Path('/mnt/c/Users/15492/.codex-clean/worktrees/0038-research-integration/QuantMesh')
owned=Path('/var/tmp/quantmesh-portfolio-runtime-9r8rsnwz')
checkout=owned/'integration-f3a72af-checkout'
out=root/'output/0038-staging-repair-admission-r3'
out.mkdir(exist_ok=False)
env={'PATH':'/usr/bin:/bin','HOME':str(owned/'home'),'TMPDIR':str(owned),'PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':os.pathsep.join(str(checkout/p) for p in ('','src','services/research_agent/src'))}
with (out/'dependency-after.stdout').open('wb') as stdout,(out/'dependency-after.stderr').open('wb') as stderr:
    result=subprocess.run([str(owned/'venv/bin/python'),'-B',str(owned/'admit.py'),str(checkout)],cwd=owned,env=env,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,start_new_session=True,timeout=45)
(out/'dependency-after.exit').write_text(str(result.returncode)+'\n')
receipt={'exit':result.returncode,'bytecode_after':len(list((owned/'venv').rglob('*.pyc'))),'scope':'DEPENDENCY_ADMISSION_ONLY_AFTER_NATIVE_FIXTURE_TESTS','earlier_missing_import_receipt_retained':True}
(out/'checked.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
raise SystemExit(result.returncode)

