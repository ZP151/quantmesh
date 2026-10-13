"""Tiny synthetic OCI semantic counterexamples, no image/runtime qualification."""
import ast,hashlib,json
from pathlib import Path
source=Path(__file__).with_name('inspect_aws_numeric_layers.py')
tree=ast.parse(source.read_text());inspect=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='inspect')
merge=[n for n in ast.walk(inspect) if isinstance(n,ast.For) and n.col_offset==8 and ast.unparse(n.target) in ('(target, opaque)','(path, node)')]
assert len(merge)==2
merge.sort(key=lambda n:n.lineno)
resolver=next(n for n in ast.walk(inspect) if isinstance(n,ast.FunctionDef) and n.name=='resolve')
normalized=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='normalized')
def require(ok,tag):
    if not ok:raise ValueError(tag)
ctx={'require':require};exec(compile(ast.Module(body=[normalized],type_ignores=[]),'<actual-normalizer>','exec'),ctx)
def apply(nodes,staged,whiteouts=(),index=1):
    env=dict(ctx,nodes=nodes,staged=staged,whiteouts=whiteouts,index=index)
    exec(compile(ast.Module(body=merge,type_ignores=[]),'<actual-layer-merger>','exec'),env)
    return nodes
def file(payload):return dict(kind='regular',layer=0,mode=420,size=1,payload_layer=0,payload_ordinal=payload,payload_name=str(payload),sha256=str(payload))
def directory():return dict(kind='directory',layer=0,mode=493,size=0)
checks=[]
n=apply({'d':directory(),'d/copyright':file(1)},[('d/copyright',file(2))],[('d',True)])
assert n['d/copyright']['payload_ordinal']==2;checks.append('same_layer_new_notice_survives_opaque_whiteout')
n=apply({'d':directory(),'d/copyright':file(1)},[('d',file(3))])
assert 'd/copyright' not in n;checks.append('non_directory_replacement_removes_old_descendants')
n=apply({'d':directory(),'d/copyright':file(1)},[('linked',dict(kind='hardlink',target='d/copyright')),('d/copyright',file(2))])
assert n['linked']['payload_ordinal']==1 and n['d/copyright']['payload_ordinal']==2
checks.append('hardlink_snapshots_prior_inode_before_source_replacement')
n=apply(n,[],[('d/copyright',False)],2)
assert 'd/copyright' not in n and n['linked']['payload_ordinal']==1;checks.append('later_source_whiteout_preserves_linked_inode')
for label,nodes,staged in (
    ('regular_ancestor_refused',{'d':file(1)},[('d/copyright',file(2))]),
    ('symlink_member_ancestor_refused',{'d':dict(kind='symlink',target='elsewhere')},[('d/copyright',file(2))]),
    ('forward_hardlink_refused',{},[('linked',dict(kind='hardlink',target='not-yet-present'))]),
):
    try:apply(nodes,staged)
    except ValueError:checks.append(label)
    else:raise AssertionError(label)
env=dict(ctx,nodes={'d':file(1),'d/copyright':file(2)})
exec(compile(ast.Module(body=[resolver],type_ignores=[]),'<actual-resolver>','exec'),env)
try:env['resolve']('d/copyright')
except ValueError:checks.append('regular_ancestor_virtual_resolution_refused')
else:raise AssertionError('regular ancestor accepted')
env['nodes']={'a':dict(kind='symlink',target='b'),'b':dict(kind='symlink',target='a')}
try:env['resolve']('a')
except ValueError:checks.append('virtual_link_cycle_refused')
else:raise AssertionError('cycle accepted')
try:ctx['normalized']('../outside')
except ValueError:checks.append('virtual_root_escape_refused')
else:raise AssertionError('escape accepted')
receipt=dict(exit=0,checks=checks,count=len(checks),reader_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
             scope='synthetic data-overlay counterexamples only/actual merger and resolver AST',
             remote_executed=False,image_or_runtime_qualified=False)
Path(__file__).with_name('0038-aws-numeric-virtual-counterexamples.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
