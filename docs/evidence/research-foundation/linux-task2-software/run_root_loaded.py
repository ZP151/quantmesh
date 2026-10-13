import datetime,json,os,shutil,subprocess,sys
from pathlib import Path
assert sys.dont_write_bytecode and os.environ.get('PYTHONDONTWRITEBYTECODE')=='1'
REPO=Path('/mnt/c/Users/15492/.codex-clean/worktrees/a718/QuantMesh')
PHASE=REPO/'output/172-task2-software-checkpoint1-20261013'
ROOT=Path('/var/tmp/quantmesh-linux-native-90afdbee6add43169483520e384539ae')
assert json.loads((ROOT/'ownership.json').read_text())['nonce']=='90afdbee6add43169483520e384539ae'
NAME=sys.argv[1]; assert NAME in {'runtime-red1','runtime-red2','runtime-green1','runtime-red3','runtime-green2','runner-red1','runner-green1','final-focused1','final-focused2','review-fix-red1','review-fix-green1','review-fix-green2','root-loaded-red','root-loaded-green','final-focused-root','root-loaded-entry-red','root-loaded-entry-green','root-loaded-stdlib-red','root-loaded-stdlib-green','root-loaded-stdlib-green2'}
explicit=['src/quantmesh/research/worker_build.py','src/quantmesh/research/job_runner.py','tests/test_worker_build.py','tests/test_research_job_runner.py']
mirrored=[]
for name in explicit:
 source=REPO/name
 if source.exists():
  target=ROOT/'source'/name;target.parent.mkdir(parents=True,exist_ok=True)
  target.write_bytes(source.read_bytes());mirrored.append(name)
def size(p):return sum(f.stat().st_size for f in p.rglob('*') if f.is_file() and not f.is_symlink()) if p.exists() else 0
def observation():
 own=ROOT/'task2-tests';source_bytes=sum((REPO/n).stat().st_size for n in explicit if (REPO/n).exists())
 value=dict(utc=datetime.datetime.now(datetime.UTC).isoformat(),free_c_bytes=shutil.disk_usage('/mnt/c').free,test_fixture_bytes=size(own),evidence_bytes=size(PHASE),explicit_source_bytes=source_bytes,introduced_logical_upper_bound=2*source_bytes+size(own)+size(PHASE)+50000)
 assert value['free_c_bytes']>=50000000000 and value['introduced_logical_upper_bound']<=10000000,'software_resource_stop'
 return value
before=observation();outdir=ROOT/'task2-tests'/NAME
outdir.parent.mkdir(exist_ok=True)
assert not outdir.exists(),'never overwrite test basetemp'
if NAME.startswith('runtime') or NAME.startswith('review-fix') or NAME.startswith('root-loaded'):
 selection=['tests/test_worker_build.py']
elif NAME.startswith('final-focused'):
 selection=['tests/test_worker_build.py','tests/test_research_job_runner.py','-k','worker_build or worker_manifest or child_receipt or child_command or owned_child_poll or windows_launcher or failed_windows_setup or linux_without_crash_safe_limits or boot_eof or runtime_digest_binds_python_build']
else:
 selection=['tests/test_research_job_runner.py','-k','worker_manifest or child_receipt or child_command or owned_child_poll']
args=[sys.executable,'-B','-m','pytest',*selection,'-q','-p','no:cacheprovider','--basetemp',str(outdir)]
env={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(ROOT/'source/src')}
with (PHASE/(NAME+'.log')).open('wb') as stream:
 r=subprocess.run(args,cwd=ROOT/'source',env=env,stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,timeout=90)
(PHASE/(NAME+'.exit')).write_text(str(r.returncode)+'\n')
after=observation()
(PHASE/(NAME+'-observation.json')).write_text(json.dumps(dict(before=before,after=after,argv=args,mirrored=mirrored,borrowed_environment_read_only=True,environment_bytecode_policy='-B and PYTHONDONTWRITEBYTECODE=1',source_semantics='explicit targeted overlay on prior owned c545 clone; not whole042 clean checkout',resource_gate='software logical<=10MB and free C>=50GB; prior whole-C5GB admission remains PENDING'),indent=2)+'\n')
print(json.dumps(dict(exit=r.returncode,before=before,after=after)))








