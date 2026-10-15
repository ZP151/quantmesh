"""Actual recipe removal block against small real Linux alias fixtures."""
import ast,hashlib,json,shutil,sys,uuid
from pathlib import Path
raw=Path(sys.argv[1]).read_text();outer=ast.parse(raw)
code=next(n.value.value for n in outer.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='CODE' for t in n.targets))
tree=ast.parse(code);body=next(n for n in tree.body if isinstance(n,ast.Try)).body
start=next(i for i,n in enumerate(body) if isinstance(n,ast.Assign) and ast.unparse(n)=='step = \'remove_pip\'')
end=next(i for i,n in enumerate(body) if isinstance(n,ast.Assign) and ast.unparse(n).startswith("step = 'package_inventory'"))
block=ast.Module(body=body[start:end],type_ignores=[])
fixture=b'fixed public bootstrap test script\n';digest=hashlib.sha256(fixture).hexdigest()
class PinSubstitution(ast.NodeTransformer):
 def visit_Constant(self,node):
  if node.value=='6d2cd44b1e30b4969035606e18bcbc4304d45aca49c693b8f2ae2fbca4fa5d87':return ast.copy_location(ast.Constant(digest),node)
  return node
compiled=compile(ast.fix_missing_locations(PinSubstitution().visit(block)),'<actual-bootstrap-removal>','exec')
base=Path('/var/tmp/quantmesh-linux-native-90afdbee6add43169483520e384539ae/task2-tests')/('pip-alias-'+uuid.uuid4().hex)
base.mkdir();cases=[]
for name,kind,expected in [('normal-alias','symlink',True),('wrong-target','wrong',False),('regular-alias','regular',False)]:
 root=base/name;site=root/'usr/local/lib/python3.12/site-packages';site.mkdir(parents=True)
 for folder in ('pip','pip-25.0.1.dist-info'):(site/folder).mkdir()
 scripts=root/'usr/local/bin';scripts.mkdir(parents=True)
 for script in ('pip3','pip3.12'):(scripts/script).write_bytes(fixture)
 if kind=='regular':(scripts/'pip').write_bytes(fixture)
 else:(scripts/'pip').symlink_to('pip3' if kind=='symlink' else '../wrong')
 def mapped(value):return root/str(value).lstrip('/')
 accepted=True
 try:exec(compiled,dict(Path=mapped,site=site,shutil=shutil,hashlib=hashlib))
 except AssertionError:accepted=False
 cases.append(dict(case=name,accepted=accepted,expected=expected,matched=accepted==expected))
failed=sum(not c['matched'] for c in cases)
print(json.dumps(dict(exit=int(bool(failed)),failed=failed,cases=cases,production_script_hash_replaced_for_test_only=True,
 Engine_or_install_executed=False,fixture_root=str(base))))
raise SystemExit(int(bool(failed)))
