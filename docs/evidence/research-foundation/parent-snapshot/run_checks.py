"""New bounded178 checks;177 artifacts remain read-only and charged."""
import hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
ROOT=Path('/mnt/c/Users/15492/.codex-clean/worktrees/0038-research-integration/QuantMesh')
OUT=ROOT/'output/178-worker-directory-association-20261014'
OLD=ROOT/'output/177-worker-parent-snapshot-20261014'
OWN=Path('/var/tmp/quantmesh-linux-native-90afdbee6add43169483520e384539ae')
assert json.loads((OWN/'ownership.json').read_text())['nonce']=='90afdbee6add43169483520e384539ae'
FILES=['src/quantmesh/research/fixture_snapshot.py','src/quantmesh/research/_fixture_handles.py','src/quantmesh/research/job_runner.py','tests/test_fixture_snapshot.py','tests/test_research_job_runner.py']
def size(p):return sum(f.stat().st_size for f in p.rglob('*') if f.is_file() and not f.is_symlink()) if p.exists() else 0
def measure():
 p=ROOT/'output/measure_lineage_frontier.py';raw=p.read_text();ns={'__file__':str(p)}
 exec(compile(raw[:raw.index("(root / 'output/0038-linux-native-admission/lineage-frontier-resources.json').write_text")],str(p),'exec'),ns)
 source=sum((ROOT/n).stat().st_size for n in FILES if (ROOT/n).exists())
 windows=size(ROOT/'output/177-root-windows-boundary-tmp')+size(OUT/'windows-tmp')+size(OUT/'windows-final-tmp')+1000
 tests=size(OWN/'task177-tests')+size(OWN/'task178-tests')+windows
 value=dict(frontier=ns['result'],source_copies_bytes=2*source,raw_copies_bytes=2*(size(OLD)+size(OUT)),git_reserve=35000,owned_test_bytes=tests,root_windows_fixtures_and_short_case_reserve=windows,scope_upper=2*source+2*(size(OLD)+size(OUT))+35000,full_upper=ns['result']['conservative_upper_with_future']+600000,free_c_bytes=shutil.disk_usage('/mnt/c').free)
 assert value['scope_upper']<=600000 and tests<=2000000 and value['full_upper']<=24000000 and value['free_c_bytes']>=50000000000
 return value
if __name__=='__main__':
 name=sys.argv[1];assert name in {'intake','red','green','final','affected','receipt-fix','planner-cover','checkpoint'}
 before=measure()
 if name in {'intake','checkpoint'}:
  if name=='intake':(OUT/'intake.json').write_text(json.dumps(before,indent=2)+'\n')
  print(json.dumps(before));sys.exit(0)
 tmp=OWN/'task178-tests'/name;assert not tmp.exists();tmp.parent.mkdir(exist_ok=True)
 selection=['tests/test_fixture_snapshot.py::test_transient_ancestor_swap_keeps_intended_parent_handle']
 forecast=10000
 if name in {'green','final'}:selection=['tests/test_fixture_snapshot.py','tests/test_research_job_runner.py::test_runtime_rejection_precedes_job_and_content_decoding','tests/test_research_job_runner.py::test_child_metadata_bounds_and_file_types_precede_job_decoder'];forecast=100000
 if name=='affected':selection+=['tests/test_research_job_runner.py','tests/test_worker_execution.py'];forecast=500000
 if name=='receipt-fix':selection=['tests/test_research_job_runner.py::test_child_receipt_rejects_wrong_identity_or_file[symlink]','tests/test_fixture_snapshot.py::test_unsupported_snapshot_profile_precedes_fixture_io','tests/test_fixture_snapshot.py::test_all_opens_are_handle_relative_and_finally_closed','tests/test_fixture_snapshot.py::test_descriptor_bound_refuses_and_closes_all_acquired_handles'];forecast=60000
 if name=='planner-cover':selection=['tests/test_fixture_snapshot.py','tests/test_research_job_runner.py::test_runtime_rejection_precedes_job_and_content_decoding','tests/test_research_job_runner.py::test_child_metadata_bounds_and_file_types_precede_job_decoder'];forecast=30000
 assert before['owned_test_bytes']+forecast<=2000000
 argv=[sys.executable,'-B','-m','pytest',*selection,'-q','--tb=short','-p','no:cacheprovider','--basetemp',str(tmp)]
 if name=='planner-cover':argv+=['--deselect=tests/test_fixture_snapshot.py::test_real_fixture_child_validates_twice_and_preserves_canonical_numerics']
 env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(ROOT/'src')}
 if name in {'affected','receipt-fix'}:
  argv+=['-p','bounded_fixtures'];env['PYTHONPATH']=str(OLD)+os.pathsep+env['PYTHONPATH'];env['PATH']=str(OLD/'bin')+os.pathsep+env['PATH']
 with (OUT/(name+'.log')).open('xb') as out:
  result=subprocess.run(argv,cwd=ROOT,env=env,stdout=out,stderr=subprocess.STDOUT,timeout=120)
 (OUT/(name+'.exit')).write_text(str(result.returncode)+'\n')
 after=measure();(OUT/(name+'-resources.json')).write_text(json.dumps(dict(before=before,after=after,argv=argv,source_hashes={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in FILES if (ROOT/n).exists()}),indent=2)+'\n')
 print(json.dumps(dict(exit=result.returncode,after=after)))
