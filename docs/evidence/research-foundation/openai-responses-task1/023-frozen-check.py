import hashlib,json,pathlib,subprocess
from quantmesh.research.jobs import schema_digest
from quantmesh.research.job_store import protocol_digest
from tools.research_service_gate import SCHEMA,PROTOCOL
root=pathlib.Path.cwd()
assert schema_digest()==SCHEMA
assert protocol_digest()==PROTOCOL
paths=['services/research_agent/requirements.lock','services/research_agent/requirements.linux-cp312.lock','requirements-audit.txt','frontend/package-lock.json']
rows={}
for name in paths:
    actual=(root/name).read_bytes()
    original=subprocess.check_output(['git','show','c545c02093b5f7e3d8dedb5ccc79b128c9dc014f:'+name])
    assert actual==original,name
    rows[name]=hashlib.sha256(actual).hexdigest()
print(json.dumps({'schema':schema_digest(),'protocol':protocol_digest(),'baseline':'c545c02093b5f7e3d8dedb5ccc79b128c9dc014f','unchanged_locks':rows,'bytecode_files':len(list(root.rglob('*.pyc'))),'model_call':False},sort_keys=True))
