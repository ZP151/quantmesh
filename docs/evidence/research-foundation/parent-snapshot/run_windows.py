"""Actual Windows unsupported-profile checks; no privilege/policy/Job Object change."""
import hashlib,json,os,subprocess,sys
from pathlib import Path

root=Path(__file__).resolve().parents[2]
out=Path(__file__).resolve().parent
assert os.name=='nt'
phase='windows-final' if len(sys.argv)>1 and sys.argv[1]=='final' else 'windows'
argv=[sys.executable,'-B','-m','pytest','tests/test_fixture_snapshot.py',
      'tests/test_research_job_runner.py::test_runtime_rejection_precedes_job_and_content_decoding',
      'tests/test_research_job_runner.py::test_child_metadata_bounds_and_file_types_precede_job_decoder',
      '-q','-rs','--tb=short','-p','no:cacheprovider','--basetemp',str(out/(phase+'-tmp'))]
assert not (out/(phase+'-tmp')).exists()
if phase=='windows-final':
    argv=[sys.executable,'-B','-m','pytest',
          'tests/test_fixture_snapshot.py::test_unsupported_snapshot_profile_precedes_fixture_io',
          'tests/test_research_job_runner.py::test_runtime_rejection_precedes_job_and_content_decoding[fingerprint]',
          '-q','--tb=short','-p','no:cacheprovider','--basetemp',str(out/(phase+'-tmp'))]
env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
with (out/(phase+'.log')).open('xb') as log:
    result=subprocess.run(argv,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=60)
(out/(phase+'.exit')).write_text(str(result.returncode)+'\n')
files=['src/quantmesh/research/_fixture_handles.py','src/quantmesh/research/fixture_snapshot.py',
       'src/quantmesh/research/job_runner.py','tests/test_fixture_snapshot.py','tests/test_research_job_runner.py']
receipt=dict(argv=argv,exit=result.returncode,python=sys.version,platform=sys.platform,
             actual_supports_dir_fd=sorted(f.__name__ for f in os.supports_dir_fd),
             source_hashes={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in files},
             fixture_bytes=sum(p.stat().st_size for p in (out/(phase+'-tmp')).rglob('*') if p.is_file()),
             claim='unsupported profile only; no Windows snapshot/admission/Job Object witness')
(out/(phase+'-receipt.json')).write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(dict(exit=result.returncode,fixture_bytes=receipt['fixture_bytes'])))
