"""Actual recipe AST control-flow counterexample; no Docker/SSH/installation."""
import ast,json,sys,hashlib
from pathlib import Path
source=Path(sys.argv[1]);tree=ast.parse(source.read_text())
outer=next(n for n in tree.body if isinstance(n,ast.Try))
start=next(i for i,n in enumerate(outer.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='image_commit_requested' for t in n.targets))
block=ast.Module(body=outer.body[start:],type_ignores=[])
final=next(n for n in outer.finalbody if isinstance(n,ast.If) and 'image_commit_requested' in ast.unparse(n.test))
code=compile(ast.fix_missing_locations(block),'<actual-commit-block>','exec');finish=compile(ast.fix_missing_locations(ast.Module(body=[final],type_ignores=[])),'<actual-final-marker>','exec')
cases=[]
for name,answer,inspect_bad,expected in (
 ('nonempty-invalid-id',b'Unexpected commit status\n',False,'NOT_PROVEN'),
 ('full-id-observer-failed',('sha256:'+'a'*64+'\n').encode(),True,'NOT_PROVEN'),
 ('full-id-observed',('sha256:'+'a'*64+'\n').encode(),False,None)):
 import re
 def require(ok,why):
  if not ok:raise ValueError(why)
 def run(args,*unused):
  if args[:2]==['container','commit']:return answer
  if inspect_bad:raise ValueError('observer_result')
  if args[-1]=='base':return json.dumps([{'RootFS':{'Layers':['base']}}]).encode()
  return json.dumps([{'Id':'sha256:'+'a'*64,'RootFS':{'Layers':['base','new']},'Config':{'Labels':{'org.quantmesh.dependency-install':'nonce'}}}]).encode()
 env=dict(run=run,require=require,re=re,json=json,hashlib=hashlib,cid='own',IMAGE='base',nonce='nonce',derived=None,
  image_commit_requested=False,commit_observed=False,result={},observation={},CODE='fixture',mounts=[])
 try:exec(code,env)
 except ValueError:pass
 exec(finish,env);actual=env['result'].get('image_commit_completion')
 cases.append(dict(case=name,expected=expected,actual=actual,matched=actual==expected))
failed=sum(not c['matched'] for c in cases);print(json.dumps(dict(exit=int(bool(failed)),failed=failed,cases=cases,software_control_flow_only=True,install_executed=False)))
raise SystemExit(int(bool(failed)))
