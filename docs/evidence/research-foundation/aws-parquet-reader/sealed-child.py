"""One finite synthetic observation; no job input or production admission."""
import ctypes
import errno
import fcntl
import hashlib
import json
import os
import resource
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

result=dict(exit=1,Worker_admission=False,numerical_certificate=False,
 extension_INSTALL_or_LOAD_exercised=False,network_requested=False,
 general_executable_mapping_denial_proven=False)
step='canonical_startup'
try:
 assert sys.version.startswith('3.12.15 ') and sys.prefix==sys.base_prefix=='/usr/local'
 assert sys.executable=='/usr/local/bin/python3' and os.getuid()==os.getgid()==10001
 assert sys.flags.isolated and sys.flags.no_site and sys.flags.ignore_environment and sys.dont_write_bytecode
 resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_CPU,(10,10))
 resource.setrlimit(resource.RLIMIT_FSIZE,(1048576,1048576))
 step='self_dumpability'
 libc=ctypes.CDLL(None,use_errno=True);prctl=libc.prctl
 prctl.argtypes=[ctypes.c_int,ctypes.c_ulong,ctypes.c_ulong,ctypes.c_ulong,ctypes.c_ulong]
 prctl.restype=ctypes.c_int
 assert prctl(4,0,0,0,0)==0 and prctl(3,0,0,0,0)==0
 sys.path.append('/usr/local/lib/python3.12/site-packages')
 step='fixed_native_import'
 import duckdb,_duckdb,pandas as pd
 assert duckdb.__version__=='1.5.5' and pd.__version__=='2.3.3'
 os.umask(0o077);root=Path('/tmp/qm-parquet-sealed-fd');root.mkdir(mode=0o700)
 Path('/tmp/qm-home').mkdir(mode=0o700)
 path=root/'canonical.parquet';sibling=root/'sibling.parquet';alias=None
 controls=dict(threads='1',memory_limit='32MB',temp_directory='',
  autoload_known_extensions='false',autoinstall_known_extensions='false',
  allow_unsigned_extensions='false',allow_community_extensions='false',allow_persistent_secrets='false')
 def open_disarmed(profile):
  c=duckdb.connect(config=controls)
  try:
   c.execute("SET temp_directory=''");c.execute('SET allowed_directories=[]')
   assert profile in ('fixture','reader')
   allowed=[str(path),str(sibling)] if profile=='fixture' else [alias]
   c.execute("SET allowed_paths=["+','.join("'"+p.replace("'","''")+"'" for p in allowed)+"]")
   c.execute('SET enable_external_access=false');c.execute('SET lock_configuration=true')
   return c
  except BaseException:c.close();raise
 step='fixed_frame'
 frame=pd.DataFrame(dict(timestamp=[datetime(2026,1,5,0,tzinfo=timezone.utc),datetime(2026,1,5,1,tzinfo=timezone.utc)],
  open=[1.,1.5],high=[2.,2.5],low=[.5,1.],close=[1.5,2.],volume=[10.,11.],
  instrument_type=['stock','stock'],currency=['USD','USD']))
 names=['timestamp','open','high','low','close','volume','instrument_type','currency']
 assert list(frame.columns)==names and len(frame)==2
 step='restricted_copy'
 with open_disarmed('fixture') as c:
  c.register('frame',frame)
  try:
   c.execute('COPY (SELECT * FROM frame) TO ? (FORMAT PARQUET)',[str(path)])
   replacement_frame=frame.copy()
   for name,values in dict(open=[10.,11.],high=[12.,13.],low=[9.,10.],close=[11.,12.],volume=[30.,31.]).items():replacement_frame[name]=values
   c.unregister('frame');c.register('frame',replacement_frame)
   c.execute('COPY (SELECT * FROM frame) TO ? (FORMAT PARQUET)',[str(sibling)])
  finally:c.unregister('frame')
 step='bounded_source_to_nonexec_sealed_file'
 required_seals=47
 def fd_shape(n):
  s=os.fstat(n)
  assert stat.S_ISREG(s.st_mode) and s.st_nlink==0 and s.st_uid==10001 and 0<s.st_size<=16384
  return [s.st_dev,s.st_ino,s.st_size,s.st_uid,s.st_nlink,stat.S_IMODE(s.st_mode)]
 def sealed_copy(p,name):
  source_fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
  try:
   before=os.fstat(source_fd)
   assert stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_uid==10001 and 0<before.st_size<=16384
   raw=os.pread(source_fd,before.st_size+1,0)
   shape=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_size,s.st_uid,s.st_nlink,s.st_mtime_ns,s.st_ctime_ns)
   assert len(raw)==before.st_size and shape(before)==shape(os.fstat(source_fd))==shape(p.lstat())
   digest=hashlib.sha256(raw).hexdigest()
   n=os.memfd_create(name,flags=os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING|0x8)
   try:
    offset=0
    while offset<len(raw):
     written=os.write(n,raw[offset:]);assert written>0;offset+=written
    os.fchmod(n,0o400)
    fcntl.fcntl(n,fcntl.F_ADD_SEALS,required_seals)
    actual=fcntl.fcntl(n,fcntl.F_GET_SEALS)
    assert actual&required_seals==required_seals and not actual&~63
    assert fd_shape(n)[5]==0o400 and hashlib.sha256(os.pread(n,len(raw)+1,0)).hexdigest()==digest
    assert shape(before)==shape(os.fstat(source_fd))==shape(p.lstat())
    return n,digest,before.st_ino
   except BaseException:os.close(n);raise
  finally:os.close(source_fd)
 fd,source_sha256,source_inode=sealed_copy(path,'qm-original-data')
 other,sibling_sha256,_=sealed_copy(sibling,'qm-sibling-data')
 assert source_sha256!=sibling_sha256
 before=fd_shape(fd);seals_before=fcntl.fcntl(fd,fcntl.F_GET_SEALS)
 child_pid=os.getpid();alias='/proc/'+str(child_pid)+'/fd/'+str(fd);other_alias='/proc/'+str(child_pid)+'/fd/'+str(other)
 sealed_sha256_before=hashlib.sha256(os.pread(fd,before[2]+1,0)).hexdigest()
 held=root/'original-held.parquet';os.rename(path,held);path.write_bytes(sibling.read_bytes())
 assert held.stat().st_ino==source_inode and path.stat().st_ino!=source_inode
 assert hashlib.sha256(path.read_bytes()).hexdigest()==sibling_sha256
 fixture_bytes=sum(p.stat().st_size for p in (path,sibling,held))+before[2]+fd_shape(other)[2]
 assert fixture_bytes<=16384
 result.update(fd_alias=alias,child_pid=child_pid,fd_before=before,seals_before=seals_before,
  source_sha256=source_sha256,sealed_sha256_before=sealed_sha256_before,fixture_bytes=fixture_bytes,
  memfd_flags=0xB,required_seals=required_seals)
 cases=[dict(case='path-replacement-keeps-original',passed=True)]
 step='actual_kernel_seal_refusals'
 for case,operation in (
  ('pwrite-refused',lambda:os.pwrite(fd,b'X',0)),
  ('shrink-refused',lambda:os.ftruncate(fd,0)),
  ('grow-refused',lambda:os.ftruncate(fd,before[2]+1)),
  ('chmod-execute-refused',lambda:os.fchmod(fd,0o500))):
  try:operation()
  except OSError as e:
   assert e.errno==errno.EPERM
   cases.append(dict(case=case,passed=True,actual_errno=e.errno))
  else:raise AssertionError('required seal operation admitted: '+case)
 step='restricted_metadata_reader'
 with open_disarmed('reader') as c:
  keys=[*controls,'allowed_directories','allowed_paths','enable_external_access','lock_configuration']
  settings={k:c.execute('SELECT current_setting(?)',[k]).fetchone()[0] for k in keys}
  result['observed_reader_settings']=settings
  assert all(settings[k] is False for k in ('autoload_known_extensions','autoinstall_known_extensions',
   'allow_unsigned_extensions','allow_community_extensions','allow_persistent_secrets','enable_external_access'))
  assert settings['threads']==1 and settings['temp_directory']=='' and settings['lock_configuration'] is True
  step='reader_exact_sealed_allowlist'
  assert settings['allowed_paths']==[alias] and settings['allowed_directories']==[]
  step='reader_logical_metadata_query'
  logical=c.execute('DESCRIBE SELECT * FROM read_parquet(?)',[alias]).fetchmany(9)
  logical=[[row[0],row[1]] for row in logical]
  step='reader_physical_metadata_query'
  physical=c.execute('SELECT name,type,repetition_type,num_children,converted_type,logical_type FROM parquet_schema(?)',[alias]).fetchmany(10)
  step='reader_footer_query'
  footer=c.execute('SELECT num_rows,num_row_groups,format_version FROM parquet_file_metadata(?)',[alias]).fetchmany(2)
  step='restricted_primitive_read'
  rows=c.execute('SELECT timestamp,open,high,low,close,volume,instrument_type,currency FROM read_parquet(?)',[alias]).fetchmany(3)
  assert len(rows)==2 and len(logical)==8 and len(physical)==9 and footer[0][0]==2
  encoded=[]
  for row in rows:
   assert type(row[0]) is datetime and row[0].utcoffset().total_seconds()==0
   assert all(type(v) is float for v in row[1:6]) and row[6:]==('stock','USD')
   encoded.append([row[0].isoformat(),*row[1:]])
  cases.append(dict(case='sealed-fd-pinned-read',passed=encoded==[
   ['2026-01-05T00:00:00+00:00',1.,2.,.5,1.5,10.,'stock','USD'],
   ['2026-01-05T01:00:00+00:00',1.5,2.5,1.,2.,11.,'stock','USD']]))
  step='exact_other_object_refusals'
  for case,denied in (('ordinary-path-refused',str(path)),('sibling-fd-refused',other_alias)):
   try:c.execute('SELECT timestamp FROM read_parquet(?)',[denied]).fetchmany(3)
   except duckdb.PermissionException as e:
    reason='Permission Error: Cannot access file "'+denied+'" - file system operations are disabled by configuration'
    assert str(e).split('\n',1)[0]==reason
    after_settings={k:c.execute('SELECT current_setting(?)',[k]).fetchone()[0] for k in keys}
    assert after_settings==settings
    cases.append(dict(case=case,passed=True,policy_reason=reason,settings_unchanged=True))
   else:raise AssertionError('unallowlisted object unexpectedly admitted')
 step='post_connection_held_seal_verification'
 after=fd_shape(fd);seals_after=fcntl.fcntl(fd,fcntl.F_GET_SEALS)
 sealed_sha256_after=hashlib.sha256(os.pread(fd,after[2]+1,0)).hexdigest()
 assert before==after and seals_before==seals_after and source_sha256==sealed_sha256_before==sealed_sha256_after
 cases.append(dict(case='sealed-fd-stable',passed=True))
 os.close(other);os.close(fd)
 result.update(cases=cases,fd_after=after,seals_after=seals_after,sealed_sha256_after=sealed_sha256_after)
 assert all(x['passed'] is True for x in cases)
 assert prctl(3,0,0,0,0)==0
 module=Path(_duckdb.__file__)
 with module.open('rb') as f:module_digest=hashlib.file_digest(f,'sha256').hexdigest()
 result.update(exit=0,names=names,logical_schema=logical,physical_schema=physical,file_metadata=footer,rows=encoded,
  settings=settings,python_version=sys.version,prefix=sys.prefix,base_prefix=sys.base_prefix,
  executable=sys.executable,uid=os.getuid(),gid=os.getgid(),duckdb_version=duckdb.__version__,pandas_version=pd.__version__,dumpable=0,
  native_module_file=str(module),native_module_sha256=module_digest,
  flags=dict(isolated=sys.flags.isolated,no_site=sys.flags.no_site,dont_write_bytecode=int(sys.dont_write_bytecode),ignore_environment=sys.flags.ignore_environment))
except BaseException as e:result.update(exit=1,failure_kind=type(e).__name__,failed_step=step,fixed_fixture_error=str(e)[:2048])
print(json.dumps(result),flush=True)
raise SystemExit(result['exit'])
