from pathlib import Path
import os,json,subprocess,tempfile
command='echo "QUANTMESH_GATE_LOGS=$RUNNER_TEMP/quantmesh-gate-logs" >> "$GITHUB_ENV"'
receipts=[]
with tempfile.TemporaryDirectory(prefix='quantmesh-ci-env-',dir='/var/tmp') as tmp:
    os.chmod(tmp,0o700)
    for name in ['classify', 'fast', 'domain', 'browser', 'release']:
        directory=Path(tmp)/name
        directory.mkdir(mode=0o700)
        export=directory/'environment'
        result=subprocess.run(['/bin/bash','--noprofile','--norc','-e','-c',command],
            env={'PATH':'/usr/bin:/bin','RUNNER_TEMP':str(directory),'GITHUB_ENV':str(export)},
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5)
        assert result.returncode==0 and not result.stdout and not result.stderr
        assert export.read_text()=='QUANTMESH_GATE_LOGS='+str(directory)+'/quantmesh-gate-logs\n'
        receipts.append({'job':name,'exit':result.returncode,'runtime_temp_export_exact':True})
print(json.dumps({'status':'passed','jobs':receipts,'scope':'OWNED_LOCAL_SHELL_FIXTURE','github_workflow_validation':False}))
