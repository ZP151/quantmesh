"""Test actual installer failure-observation order, no Engine or install."""
import ast,json,sys
from pathlib import Path
tree=ast.parse(Path(sys.argv[1]).read_text());outer=next(n for n in tree.body if isinstance(n,ast.Try))
end=next(i for i,n in enumerate(outer.body) if isinstance(n,ast.While))
stop=next(i for i,n in enumerate(outer.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='image_commit_requested' for t in n.targets))
block=compile(ast.fix_missing_locations(ast.Module(body=outer.body[end+1:stop],type_ignores=[])),'<actual-failure-output-order>','exec')
captured=[]
def require(ok,why):
 if not ok:raise ValueError(why)
def capture_logs():
 captured.append('before-cleanup');return b'{"exit":1,"failed_step":"base_bootstrap","failure_kind":"AssertionError"}'
env=dict(require=require,capture_logs=capture_logs,json=json,result={'container_started':True},
 d={'State':{'ExitCode':1,'Pid':0,'OOMKilled':False}},run=lambda *a,**k:capture_logs(),PHASE=Path('unused'),cid='owned')
try:exec(block,env)
except ValueError:pass
ok=bool(captured) and env['result'].get('actual_container_exit')==1 and env['result'].get('observation',{}).get('failed_step')=='base_bootstrap'
print(json.dumps(dict(exit=int(not ok),failed=int(not ok),failure_output_preserved_before_rejection=ok,software_control_flow_only=True,Engine_executed=False)))
raise SystemExit(int(not ok))
