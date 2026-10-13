import json,os,subprocess,sys
from pathlib import Path
assert sys.dont_write_bytecode and os.environ.get('PYTHONDONTWRITEBYTECODE')=='1'
repo=Path('/mnt/c/Users/15492/.codex-clean/worktrees/a718/QuantMesh')
root=Path('/var/tmp/quantmesh-linux-native-90afdbee6add43169483520e384539ae')
phase=repo/'output/172-task2-software-checkpoint1-20261013'
assert json.loads((root/'ownership.json').read_text())['nonce']=='90afdbee6add43169483520e384539ae'
current=(repo/'src/quantmesh/research/worker_build.py').read_text()
original=current.replace('''        try:
            resolved = item.resolve(strict=True)
        except RuntimeError:
            # Python3.12 reports symlink loops as path-bearing RuntimeError.
            raise ValueError from None
''','''        resolved = item.resolve(strict=True)
''')
start=original.index('        admitted_source = ');end=original.index('        dependencies, actual = ',start)
original=original[:start]+original[end:]
start=original.index('            metadata_root = ');end=original.index('            name = dist.metadata["Name"]',start)
original=original[:start]+original[end:]
assert original!=current
(phase/'pre-review-helper-reproduction.py').write_text(original)
target=root/'source/src/quantmesh/research/worker_build.py'
(root/'source/tests/test_worker_build.py').write_bytes((repo/'tests/test_worker_build.py').read_bytes())
target.write_text(original)
args=[sys.executable,'-B','-m','pytest','tests/test_worker_build.py','-q','-k','dependency_origin or loaded_source or symlink_loop','-p','no:cacheprovider','--basetemp',str(root/'task2-tests/review-real-red1')]
try:
 with (phase/'review-real-red1.log').open('wb') as stream:
  r=subprocess.run(args,cwd=root/'source',env={'PATH':'/usr/bin:/bin','PYTHONPATH':str(root/'source/src'),'PYTHONDONTWRITEBYTECODE':'1'},stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,timeout=45)
 (phase/'review-real-red1.exit').write_text(str(r.returncode)+'\n')
 assert r.returncode==1
finally:
 target.write_text(current)
print(json.dumps(dict(exit=r.returncode,purpose='corrected distribution test routes mutated objects; pre-review helper with only two reviewed fixes reverted, restored in finally',new_image_or_environment=False)))
