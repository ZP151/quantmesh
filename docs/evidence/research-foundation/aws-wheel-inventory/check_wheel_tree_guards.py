"""Actual ZIP interpretation counterexamples on tiny owned Linux fixtures."""
import ast,base64,csv,hashlib,io,json,os,shutil,stat,struct,time,uuid,zlib
from pathlib import Path
root=Path(__file__).resolve().parents[1]
parent=Path('/var/tmp/quantmesh-linux-native-90afdbee6add43169483520e384539ae/task2-tests')
assert parent.resolve()==parent and parent.stat().st_uid==os.getuid()
fixture=parent/('wheel-tree-guards-'+uuid.uuid4().hex);fixture.mkdir(mode=0o700)
source=ast.parse((root/'output/inspect_aws_numeric_wheels.py').read_text())
defs=[n for n in source.body if isinstance(n,(ast.Import,ast.ImportFrom,ast.FunctionDef))]
module=compile(ast.Module(body=defs,type_ignores=[]),'operator-fixture','exec')
def raw_zip(entries):
    raw=bytearray();central=bytearray()
    for name,data in entries:
        nb=name.encode();offset=len(raw);crc=zlib.crc32(data);size=len(data)
        raw.extend(struct.pack('<IHHHHHIIIHH',0x04034b50,20,0,0,0,0,crc,size,size,len(nb),0)+nb+data)
        external=((stat.S_IFDIR|0o755) if name.endswith('/') else (stat.S_IFREG|0o644))<<16
        central.extend(struct.pack('<IHHHHHHIIIHHHHHII',0x02014b50,3<<8|20,20,0,0,0,0,crc,size,size,len(nb),0,0,0,0,external,offset)+nb)
    offset=len(raw);raw.extend(central);raw.extend(struct.pack('<IHHHHIIH',0x06054b50,0,0,len(entries),len(entries),len(central),offset,0))
    return bytes(raw)
cases={'NUL-name':[('LICENSE\x00suffix',b'notice')],
       'file-directory-alias':[('a',b'x'),('a/',b''),('LICENSE',b'notice')],
       'non-directory-ancestor':[('a',b'x'),('a/b',b'y'),('LICENSE',b'notice')],
       'normal':[('a/b',b'normal'),('LICENSE',b'notice')]}
results=[];failures=0
for case,entries in cases.items():
    owned=fixture/case;owned.mkdir(mode=0o700)
    intake=owned/'intake';intake.mkdir(mode=0o700);(intake/'wheelhouse').mkdir(mode=0o700)
    phase=owned/'inventory';phase.mkdir(mode=0o700);(phase/'notices').mkdir(mode=0o700)
    record_name='fixture-0.dist-info/RECORD';record=io.StringIO();writer=csv.writer(record,lineterminator='\n')
    for name,data in entries:
        if name.endswith('/'):continue
        interpreted=name.split('\x00',1)[0]
        writer.writerow([interpreted,'sha256='+base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('='),str(len(data))])
    writer.writerow([record_name,'','']);entries=entries+[(record_name,record.getvalue().encode())]
    payload=raw_zip(entries);(intake/'wheelhouse/fixture.whl').write_bytes(payload)
    env={};exec(module,env)
    env.update(ROOT=owned,PHASE=phase,INTAKE=intake,META='fixture',LOCK='fixture',started=time.monotonic(),
        owner=dict(free_before=shutil.disk_usage('/').free),result=dict(scope='synthetic ZIP interpreter only'),
        metadata=[dict(name='fixture',version='0',filename='fixture.whl',previous_cached_compressed_bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest())])
    env['work']();d=json.loads((phase/'worker-result.json').read_bytes())
    expected=0 if case=='normal' else 1;ok=d['exit']==expected
    failures+=int(not ok);results.append(dict(case=case,expected_exit=expected,matched=ok,receipt=d))
print(json.dumps(dict(exit=1 if failures else 0,failed=failures,cases=results,
    native_container_certificate=False,production_pins_bypassed_for_test_only=True)))
raise SystemExit(1 if failures else 0)
