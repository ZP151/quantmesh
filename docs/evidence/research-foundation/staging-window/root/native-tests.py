import os,sys,runpy,tempfile
from pathlib import Path
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
sys.path.insert(0,'/mnt/c/Users/15492/AppData/Local/Programs/Python/Python313/Lib/site-packages')
root=Path('/mnt/c/Users/15492/.codex-clean/worktrees/0038-research-integration/QuantMesh')
os.chdir(root)
base=tempfile.mkdtemp(prefix='quantmesh-root-stage-test-',dir='/var/tmp')
os.chmod(base,0o700)
sys.argv=['pytest','-q','tests/test_opend_staging_window.py','--basetemp',str(Path(base)/'pytest'),'--junitxml',str(root/'output/169-root-staging-integrated/native-tests.xml')]
runpy.run_module('pytest',run_name='__main__')
