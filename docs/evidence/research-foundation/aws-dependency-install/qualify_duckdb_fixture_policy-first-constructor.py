"""New bounded DuckDB1.5.5 configuration diagnostic in the existing Linux env.

No extension INSTALL/LOAD, network, research source import or native Worker claim.
"""
import json,os,resource,sys,time,uuid
from pathlib import Path
started=time.monotonic()
resource.setrlimit(resource.RLIMIT_AS,(1073741824,1073741824))
resource.setrlimit(resource.RLIMIT_CPU,(10,10))
resource.setrlimit(resource.RLIMIT_FSIZE,(1048576,1048576))
assert sys.version_info[:2]==(3,12) and sys.dont_write_bytecode and sys.flags.no_site
sys.path.append('/var/tmp/quantmesh-portfolio-runtime-9r8rsnwz/venv/lib/python3.12/site-packages')
import duckdb
assert duckdb.__version__=='1.5.5'
root=Path('/var/tmp/quantmesh-linux-native-90afdbee6add43169483520e384539ae/task2-tests')/('duckdb-policy-'+uuid.uuid4().hex)
os.umask(0o077);root.mkdir();one=root/'allowed.parquet';two=root/'denied.parquet'
with duckdb.connect(config={'threads':'1','memory_limit':'32MB','temp_directory':''}) as c:
 for p in (one,two):c.execute('COPY (SELECT 1::BIGINT AS n) TO ? (FORMAT PARQUET)',[str(p)])
assert sum(p.stat().st_size for p in root.iterdir())<65536
config=dict(threads='1',memory_limit='32MB',temp_directory='',
 autoload_known_extensions='false',autoinstall_known_extensions='false',allow_unsigned_extensions='false',
 allow_community_extensions='false',allow_persistent_secrets='false',enable_external_access='false',
 allowed_paths=[str(one)],allowed_directories=[],lock_configuration='true')
cases=[]
with duckdb.connect(config=config) as c:
 settings={k:c.execute('SELECT current_setting(?)',[k]).fetchone()[0] for k in config}
 assert all(settings[k] is False for k in ('autoload_known_extensions','autoinstall_known_extensions','allow_unsigned_extensions','allow_community_extensions','allow_persistent_secrets','enable_external_access'))
 assert settings['allowed_paths']==[str(one)] and settings['allowed_directories']==[] and settings['lock_configuration'] is True
 rows=c.execute('SELECT n FROM read_parquet(?)',[str(one)]).fetchmany(2);assert rows==[(1,)]
 cases.append(dict(case='exact-allowlisted-Parquet-read',passed=True))
 try:c.execute('SELECT n FROM read_parquet(?)',[str(two)]).fetchone()
 except duckdb.PermissionException:cases.append(dict(case='owned-sibling-path-refused',passed=True))
 else:cases.append(dict(case='owned-sibling-path-refused',passed=False))
 try:c.execute("SET enable_external_access=true")
 except duckdb.InvalidInputException:cases.append(dict(case='locked-config-refused',passed=True))
 else:cases.append(dict(case='locked-config-refused',passed=False))
result=dict(exit=int(not all(x['passed'] for x in cases)),duckdb_version=duckdb.__version__,python_version=sys.version,
 cases=cases,settings=settings,fixture_bytes=sum(p.stat().st_size for p in root.iterdir()),fixture_root=str(root),
 extension_INSTALL_or_LOAD_exercised=False,network_requested=False,Worker_admission=False,
 canonical_AWS_3_12_15_certificate=False,elapsed_seconds=round(time.monotonic()-started,3))
(root/'receipt.json').write_text(json.dumps(result)+'\n');print(json.dumps(result))
raise SystemExit(result['exit'])
