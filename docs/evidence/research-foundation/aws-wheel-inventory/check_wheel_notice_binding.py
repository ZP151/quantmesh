"""Small source-notice association tests; synthetic pins, no live acceptance."""
import ast,hashlib,json,os,time,uuid
from pathlib import Path
root=Path(__file__).resolve().parents[1]
parent=Path('/var/tmp/quantmesh-linux-native-90afdbee6add43169483520e384539ae/task2-tests')
assert parent.resolve()==parent and parent.stat().st_uid==os.getuid()
fixture=parent/('wheel-notice-binding-'+uuid.uuid4().hex);fixture.mkdir(mode=0o700)
tree=ast.parse((root/'output/inspect_aws_numeric_wheels.py').read_text())
module=compile(ast.Module(body=[n for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom,ast.FunctionDef))],type_ignores=[]),'notice-fixture','exec')
body=b'actual fixture notice bytes';digest=hashlib.sha256(body).hexdigest();wheel='f'*64
cases=['normal','wrong-wheel','wrong-version','wrong-source','body-tamper','body-link','unlisted-package']
results=[]
for case in cases:
    owned=fixture/case;owned.mkdir(mode=0o700);folder=owned/'wheel-notice-supplements';folder.mkdir(mode=0o700)
    n=dict(name='fixture',version='0',wheel_sha256=wheel,notice_file='fixture-LICENSE',notice_sha256=digest,
        notice_bytes=len(body),source_commit='fixed-source')
    if case=='wrong-source':n['source_commit']='different-source'
    receipt=dict(exit=0,worker_reaped=True,source_to_wheel_equivalence_claimed=False,notices=[n])
    (folder/'notice-receipt.json').write_text(json.dumps(receipt))
    path=folder/'fixture-LICENSE'
    if case=='body-link':
        (owned/'other').write_bytes(body);path.symlink_to(owned/'other')
    else:path.write_bytes(b'changed bytes' if case=='body-tamper' else body)
    request=dict(name='unknown' if case=='unlisted-package' else 'fixture',version='1' if case=='wrong-version' else '0',
        sha256='a'*64 if case=='wrong-wheel' else wheel)
    env={};exec(module,env)
    env.update(ROOT=owned,SUPPLEMENTS={'fixture':('0',wheel,'fixture-LICENSE',digest,len(body),'source_commit','fixed-source')})
    try:
        got,provenance=env['supplement'](request);accepted=True;assert got==body
    except ValueError:accepted=False
    assert accepted==(case=='normal')
    results.append(dict(case=case,accepted=accepted))
print(json.dumps(dict(exit=0,cases=results,production_pins_replaced_for_test_only=True,native_certificate=False)))
