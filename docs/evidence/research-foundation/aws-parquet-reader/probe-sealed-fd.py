"""Fixed canonical Parquet schema diagnostic; no production/native admission."""
import hashlib,json,os,re,shutil,stat,subprocess,time,uuid
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path('/home/ubuntu/quantmesh-numeric-materialization-4e00a5cecd0047fa9d5aa71c020a077a')
PHASE=ROOT/'canonical-parquet-sealed-fd'
IMAGE='sha256:093b47341cb1c02ae0d9490ed40fbf0bc325ff224bced40329674942cced991c'
ENGINE='cfe71bf3-9059-4059-887d-ac401f2283ec'
INSTALL='30a62b81e8712534288e3381c0a71f610305b56a6a0092ac8831058666b61e8f'
EXPECTED_CASES={'exact-allowlisted-read','sibling-path-refused','external-setting-locked','path-setting-locked'}
CODE='"""One finite synthetic observation; no job input or production admission."""\nimport ctypes\nimport errno\nimport fcntl\nimport hashlib\nimport json\nimport os\nimport resource\nimport stat\nimport sys\nfrom datetime import datetime, timezone\nfrom pathlib import Path\n\nresult=dict(exit=1,Worker_admission=False,numerical_certificate=False,\n extension_INSTALL_or_LOAD_exercised=False,network_requested=False,\n general_executable_mapping_denial_proven=False)\nstep=\'canonical_startup\'\ntry:\n assert sys.version.startswith(\'3.12.15 \') and sys.prefix==sys.base_prefix==\'/usr/local\'\n assert sys.executable==\'/usr/local/bin/python3\' and os.getuid()==os.getgid()==10001\n assert sys.flags.isolated and sys.flags.no_site and sys.flags.ignore_environment and sys.dont_write_bytecode\n resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_CPU,(10,10))\n resource.setrlimit(resource.RLIMIT_FSIZE,(1048576,1048576))\n step=\'self_dumpability\'\n libc=ctypes.CDLL(None,use_errno=True);prctl=libc.prctl\n prctl.argtypes=[ctypes.c_int,ctypes.c_ulong,ctypes.c_ulong,ctypes.c_ulong,ctypes.c_ulong]\n prctl.restype=ctypes.c_int\n assert prctl(4,0,0,0,0)==0 and prctl(3,0,0,0,0)==0\n sys.path.append(\'/usr/local/lib/python3.12/site-packages\')\n step=\'fixed_native_import\'\n import duckdb,_duckdb,pandas as pd\n assert duckdb.__version__==\'1.5.5\' and pd.__version__==\'2.3.3\'\n os.umask(0o077);root=Path(\'/tmp/qm-parquet-sealed-fd\');root.mkdir(mode=0o700)\n Path(\'/tmp/qm-home\').mkdir(mode=0o700)\n path=root/\'canonical.parquet\';sibling=root/\'sibling.parquet\';alias=None\n controls=dict(threads=\'1\',memory_limit=\'32MB\',temp_directory=\'\',\n  autoload_known_extensions=\'false\',autoinstall_known_extensions=\'false\',\n  allow_unsigned_extensions=\'false\',allow_community_extensions=\'false\',allow_persistent_secrets=\'false\')\n def open_disarmed(profile):\n  c=duckdb.connect(config=controls)\n  try:\n   c.execute("SET temp_directory=\'\'");c.execute(\'SET allowed_directories=[]\')\n   assert profile in (\'fixture\',\'reader\')\n   allowed=[str(path),str(sibling)] if profile==\'fixture\' else [alias]\n   c.execute("SET allowed_paths=["+\',\'.join("\'"+p.replace("\'","\'\'")+"\'" for p in allowed)+"]")\n   c.execute(\'SET enable_external_access=false\');c.execute(\'SET lock_configuration=true\')\n   return c\n  except BaseException:c.close();raise\n step=\'fixed_frame\'\n frame=pd.DataFrame(dict(timestamp=[datetime(2026,1,5,0,tzinfo=timezone.utc),datetime(2026,1,5,1,tzinfo=timezone.utc)],\n  open=[1.,1.5],high=[2.,2.5],low=[.5,1.],close=[1.5,2.],volume=[10.,11.],\n  instrument_type=[\'stock\',\'stock\'],currency=[\'USD\',\'USD\']))\n names=[\'timestamp\',\'open\',\'high\',\'low\',\'close\',\'volume\',\'instrument_type\',\'currency\']\n assert list(frame.columns)==names and len(frame)==2\n step=\'restricted_copy\'\n with open_disarmed(\'fixture\') as c:\n  c.register(\'frame\',frame)\n  try:\n   c.execute(\'COPY (SELECT * FROM frame) TO ? (FORMAT PARQUET)\',[str(path)])\n   replacement_frame=frame.copy()\n   for name,values in dict(open=[10.,11.],high=[12.,13.],low=[9.,10.],close=[11.,12.],volume=[30.,31.]).items():replacement_frame[name]=values\n   c.unregister(\'frame\');c.register(\'frame\',replacement_frame)\n   c.execute(\'COPY (SELECT * FROM frame) TO ? (FORMAT PARQUET)\',[str(sibling)])\n  finally:c.unregister(\'frame\')\n step=\'bounded_source_to_nonexec_sealed_file\'\n required_seals=47\n def fd_shape(n):\n  s=os.fstat(n)\n  assert stat.S_ISREG(s.st_mode) and s.st_nlink==0 and s.st_uid==10001 and 0<s.st_size<=16384\n  return [s.st_dev,s.st_ino,s.st_size,s.st_uid,s.st_nlink,stat.S_IMODE(s.st_mode)]\n def sealed_copy(p,name):\n  source_fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)\n  try:\n   before=os.fstat(source_fd)\n   assert stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_uid==10001 and 0<before.st_size<=16384\n   raw=os.pread(source_fd,before.st_size+1,0)\n   shape=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_size,s.st_uid,s.st_nlink,s.st_mtime_ns,s.st_ctime_ns)\n   assert len(raw)==before.st_size and shape(before)==shape(os.fstat(source_fd))==shape(p.lstat())\n   digest=hashlib.sha256(raw).hexdigest()\n   n=os.memfd_create(name,flags=os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING|0x8)\n   try:\n    offset=0\n    while offset<len(raw):\n     written=os.write(n,raw[offset:]);assert written>0;offset+=written\n    os.fchmod(n,0o400)\n    fcntl.fcntl(n,fcntl.F_ADD_SEALS,required_seals)\n    actual=fcntl.fcntl(n,fcntl.F_GET_SEALS)\n    assert actual&required_seals==required_seals and not actual&~63\n    assert fd_shape(n)[5]==0o400 and hashlib.sha256(os.pread(n,len(raw)+1,0)).hexdigest()==digest\n    assert shape(before)==shape(os.fstat(source_fd))==shape(p.lstat())\n    return n,digest,before.st_ino\n   except BaseException:os.close(n);raise\n  finally:os.close(source_fd)\n fd,source_sha256,source_inode=sealed_copy(path,\'qm-original-data\')\n other,sibling_sha256,_=sealed_copy(sibling,\'qm-sibling-data\')\n assert source_sha256!=sibling_sha256\n before=fd_shape(fd);seals_before=fcntl.fcntl(fd,fcntl.F_GET_SEALS)\n child_pid=os.getpid();alias=\'/proc/\'+str(child_pid)+\'/fd/\'+str(fd);other_alias=\'/proc/\'+str(child_pid)+\'/fd/\'+str(other)\n sealed_sha256_before=hashlib.sha256(os.pread(fd,before[2]+1,0)).hexdigest()\n held=root/\'original-held.parquet\';os.rename(path,held);path.write_bytes(sibling.read_bytes())\n assert held.stat().st_ino==source_inode and path.stat().st_ino!=source_inode\n assert hashlib.sha256(path.read_bytes()).hexdigest()==sibling_sha256\n fixture_bytes=sum(p.stat().st_size for p in (path,sibling,held))+before[2]+fd_shape(other)[2]\n assert fixture_bytes<=16384\n result.update(fd_alias=alias,child_pid=child_pid,fd_before=before,seals_before=seals_before,\n  source_sha256=source_sha256,sealed_sha256_before=sealed_sha256_before,fixture_bytes=fixture_bytes,\n  memfd_flags=0xB,required_seals=required_seals)\n cases=[dict(case=\'path-replacement-keeps-original\',passed=True)]\n step=\'actual_kernel_seal_refusals\'\n for case,operation in (\n  (\'pwrite-refused\',lambda:os.pwrite(fd,b\'X\',0)),\n  (\'shrink-refused\',lambda:os.ftruncate(fd,0)),\n  (\'grow-refused\',lambda:os.ftruncate(fd,before[2]+1)),\n  (\'chmod-execute-refused\',lambda:os.fchmod(fd,0o500))):\n  try:operation()\n  except OSError as e:\n   assert e.errno==errno.EPERM\n   cases.append(dict(case=case,passed=True,actual_errno=e.errno))\n  else:raise AssertionError(\'required seal operation admitted: \'+case)\n step=\'restricted_metadata_reader\'\n with open_disarmed(\'reader\') as c:\n  keys=[*controls,\'allowed_directories\',\'allowed_paths\',\'enable_external_access\',\'lock_configuration\']\n  settings={k:c.execute(\'SELECT current_setting(?)\',[k]).fetchone()[0] for k in keys}\n  result[\'observed_reader_settings\']=settings\n  assert all(settings[k] is False for k in (\'autoload_known_extensions\',\'autoinstall_known_extensions\',\n   \'allow_unsigned_extensions\',\'allow_community_extensions\',\'allow_persistent_secrets\',\'enable_external_access\'))\n  assert settings[\'threads\']==1 and settings[\'temp_directory\']==\'\' and settings[\'lock_configuration\'] is True\n  step=\'reader_exact_sealed_allowlist\'\n  assert settings[\'allowed_paths\']==[alias] and settings[\'allowed_directories\']==[]\n  step=\'reader_logical_metadata_query\'\n  logical=c.execute(\'DESCRIBE SELECT * FROM read_parquet(?)\',[alias]).fetchmany(9)\n  logical=[[row[0],row[1]] for row in logical]\n  step=\'reader_physical_metadata_query\'\n  physical=c.execute(\'SELECT name,type,repetition_type,num_children,converted_type,logical_type FROM parquet_schema(?)\',[alias]).fetchmany(10)\n  step=\'reader_footer_query\'\n  footer=c.execute(\'SELECT num_rows,num_row_groups,format_version FROM parquet_file_metadata(?)\',[alias]).fetchmany(2)\n  step=\'restricted_primitive_read\'\n  rows=c.execute(\'SELECT timestamp,open,high,low,close,volume,instrument_type,currency FROM read_parquet(?)\',[alias]).fetchmany(3)\n  assert len(rows)==2 and len(logical)==8 and len(physical)==9 and footer[0][0]==2\n  encoded=[]\n  for row in rows:\n   assert type(row[0]) is datetime and row[0].utcoffset().total_seconds()==0\n   assert all(type(v) is float for v in row[1:6]) and row[6:]==(\'stock\',\'USD\')\n   encoded.append([row[0].isoformat(),*row[1:]])\n  cases.append(dict(case=\'sealed-fd-pinned-read\',passed=encoded==[\n   [\'2026-01-05T00:00:00+00:00\',1.,2.,.5,1.5,10.,\'stock\',\'USD\'],\n   [\'2026-01-05T01:00:00+00:00\',1.5,2.5,1.,2.,11.,\'stock\',\'USD\']]))\n  step=\'exact_other_object_refusals\'\n  for case,denied in ((\'ordinary-path-refused\',str(path)),(\'sibling-fd-refused\',other_alias)):\n   try:c.execute(\'SELECT timestamp FROM read_parquet(?)\',[denied]).fetchmany(3)\n   except duckdb.PermissionException as e:\n    reason=\'Permission Error: Cannot access file "\'+denied+\'" - file system operations are disabled by configuration\'\n    assert str(e).split(\'\\n\',1)[0]==reason\n    after_settings={k:c.execute(\'SELECT current_setting(?)\',[k]).fetchone()[0] for k in keys}\n    assert after_settings==settings\n    cases.append(dict(case=case,passed=True,policy_reason=reason,settings_unchanged=True))\n   else:raise AssertionError(\'unallowlisted object unexpectedly admitted\')\n step=\'post_connection_held_seal_verification\'\n after=fd_shape(fd);seals_after=fcntl.fcntl(fd,fcntl.F_GET_SEALS)\n sealed_sha256_after=hashlib.sha256(os.pread(fd,after[2]+1,0)).hexdigest()\n assert before==after and seals_before==seals_after and source_sha256==sealed_sha256_before==sealed_sha256_after\n cases.append(dict(case=\'sealed-fd-stable\',passed=True))\n os.close(other);os.close(fd)\n result.update(cases=cases,fd_after=after,seals_after=seals_after,sealed_sha256_after=sealed_sha256_after)\n assert all(x[\'passed\'] is True for x in cases)\n assert prctl(3,0,0,0,0)==0\n module=Path(_duckdb.__file__)\n with module.open(\'rb\') as f:module_digest=hashlib.file_digest(f,\'sha256\').hexdigest()\n result.update(exit=0,names=names,logical_schema=logical,physical_schema=physical,file_metadata=footer,rows=encoded,\n  settings=settings,python_version=sys.version,prefix=sys.prefix,base_prefix=sys.base_prefix,\n  executable=sys.executable,uid=os.getuid(),gid=os.getgid(),duckdb_version=duckdb.__version__,pandas_version=pd.__version__,dumpable=0,\n  native_module_file=str(module),native_module_sha256=module_digest,\n  flags=dict(isolated=sys.flags.isolated,no_site=sys.flags.no_site,dont_write_bytecode=int(sys.dont_write_bytecode),ignore_environment=sys.flags.ignore_environment))\nexcept BaseException as e:result.update(exit=1,failure_kind=type(e).__name__,failed_step=step,fixed_fixture_error=str(e)[:2048])\nprint(json.dumps(result),flush=True)\nraise SystemExit(result[\'exit\'])\n'

def require(ok,why):
 if not ok:raise ValueError(why)

def validate_observation(d,o):
 s=d['State']
 require(not s['Running'] and s['ExitCode']==0 and s['Pid']==0 and not s['OOMKilled'],'actual_child_exit')
 require(not s['StartedAt'].startswith('0001-01-01') and
  datetime.fromisoformat(s['FinishedAt'].replace('Z','+00:00'))>datetime.fromisoformat(s['StartedAt'].replace('Z','+00:00')),'actual_execution_times')
 require(o['exit']==0 and o['python_version'].startswith('3.12.15 ') and
  o['prefix']==o['base_prefix']=='/usr/local' and o['executable']=='/usr/local/bin/python3' and
  o['uid']==o['gid']==10001 and o['duckdb_version']=='1.5.5' and o['pandas_version']=='2.3.3' and o['dumpable']==0 and
  o['flags']==dict(isolated=1,no_site=1,dont_write_bytecode=1,ignore_environment=1),'canonical_observation')
 names=['timestamp','open','high','low','close','volume','instrument_type','currency']
 require(o['names']==names and len(o['logical_schema'])==8 and [r[0] for r in o['logical_schema']]==names,'logical_schema_shape')
 require(len(o['physical_schema'])==9 and o['physical_schema'][0][3]==8 and
  [r[0] for r in o['physical_schema'][1:]]==names and all(r[3] in (None,0) for r in o['physical_schema'][1:]),'flat_physical_schema')
 require(len(o['file_metadata'])==1 and o['file_metadata'][0][0:2]==[2,1] and len(o['rows'])==2 and
  all(len(r)==8 for r in o['rows']),'fixed_actual_rows')
 require(type(o['fixture_bytes']) is int and 0<o['fixture_bytes']<=16384,'fixture_bound')
 require(all(o[k] is False for k in ('extension_INSTALL_or_LOAD_exercised','network_requested','Worker_admission','numerical_certificate')),'no_production_claim')

def validate_sealed_observation(o):
 pid=o['child_pid'];require(type(pid) is int and 0<pid<=32,'actual_child_namespace_PID')
 require(re.fullmatch(r'/proc/'+str(pid)+r'/fd/[0-9]+',o['fd_alias']) is not None,'sealed_fd_alias')
 before=o['fd_before'];after=o['fd_after']
 require(len(before)==6 and all(type(v) is int for v in before) and before==after and
  0<before[2]<=16384 and before[3:]==[10001,0,256],'sealed_fd_identity_mode')
 seals=o['seals_before']
 require(type(seals) is int and seals&47==47 and not seals&~63 and seals==o['seals_after'],'actual_kernel_seals')
 require(o['memfd_flags']==11 and o['required_seals']==47 and
  o['general_executable_mapping_denial_proven'] is False,'nonexec_memfd_without_full_kernel_claim')
 digest=o['source_sha256']
 require(re.fullmatch(r'[0-9a-f]{64}',digest) is not None and
  digest==o['sealed_sha256_before']==o['sealed_sha256_after'],'immutable_copied_bytes')
 settings=o['settings']
 require(settings['allowed_paths']==[o['fd_alias']] and settings['allowed_directories']==[] and
  settings['enable_external_access'] is False and settings['lock_configuration'] is True,'exact_sealed_read_policy')
 names={'path-replacement-keeps-original','sealed-fd-pinned-read','ordinary-path-refused',
  'sibling-fd-refused','pwrite-refused','shrink-refused','grow-refused','chmod-execute-refused','sealed-fd-stable'}
 require(len(o['cases'])==9 and {x['case'] for x in o['cases']}==names and
  all(x['passed'] is True for x in o['cases']),'actual_sealed_cases')
 for case in o['cases']:
  if case['case'] in ('pwrite-refused','shrink-refused','grow-refused','chmod-execute-refused'):
   require(type(case['actual_errno']) is int and case['actual_errno']==1,'actual_kernel_EPERM')
  if case['case'] in ('ordinary-path-refused','sibling-fd-refused'):
   require(case['settings_unchanged'] is True and case['policy_reason'].startswith('Permission Error: Cannot access file "') and
    case['policy_reason'].endswith('" - file system operations are disabled by configuration'),'actual_configuration_permission_refusal')


nonce=uuid.uuid4().hex;cid=None;created=False;create_requested=False;logs_collected=False;owner=None;expected_labels=None
result=dict(scope='fixed synthetic canonical eight-column writer schema only',nonce=nonce,exit=1,
 native_admission=False,numerical_certificate=False,kernel_profile_qualified=False,
 production_services_enabled=False,full_option_A_complete=False,container_started=False)

def owned(p):
 s=p.lstat();return p.resolve()==p and s.st_uid==os.getuid() and stat.S_ISDIR(s.st_mode) and stat.S_IMODE(s.st_mode)==0o700

def read(p,limit):
 require(p.resolve()==p and not any(x.is_symlink() for x in (p,*p.parents)),'input_links')
 fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as f:
  s=os.fstat(f.fileno());require(stat.S_ISREG(s.st_mode) and s.st_uid==os.getuid() and s.st_nlink==1 and 0<s.st_size<=limit,'owned_regular')
  raw=f.read(limit+1);shape=lambda x:(x.st_dev,x.st_ino,x.st_mode,x.st_size,x.st_uid,x.st_nlink,x.st_mtime_ns,x.st_ctime_ns)
  require(len(raw)==s.st_size and shape(s)==shape(os.fstat(f.fileno()))==shape(p.lstat()),'stable_bytes')
 return raw

def disk():
 free=shutil.disk_usage('/').free
 require(free>=50000000000 and owner['free_before']-free<=5000000000,'original_disk_gate')
 return free

def command(args,seconds):
 return ['sudo','-n','/usr/bin/timeout','-k','3s',str(seconds)+'s','/usr/bin/env','-i',
  'PATH=/usr/sbin:/usr/bin:/sbin:/bin','/usr/bin/docker','--config',str(PHASE/'empty-config'),
  '--host','unix:///var/run/docker.sock',*args]

def run(args,seconds=10):
 r=subprocess.run(command(args,seconds),capture_output=True,timeout=seconds+8)
 require(r.returncode==0 and not r.stderr and len(r.stdout)<=65536,'bounded_cli_result');return r.stdout

def inspect():
 rows=json.loads(run(['container','inspect',cid]));require(len(rows)==1,'one_container');d=rows[0]
 require(d['Id']==cid and d['Image']==IMAGE and d['Config']['Labels']==expected_labels,'exact_owned_cid')
 if not d['State']['StartedAt'].startswith('0001-01-01'):result['container_started']=True
 return d

def capture():
 global logs_collected
 r=subprocess.run(command(['container','logs',cid],10),capture_output=True,timeout=18)
 require(len(r.stdout)<=65536 and len(r.stderr)<=65536,'logs_bound')
 (PHASE/'probe-output.json').write_bytes(r.stdout);(PHASE/'probe-stderr.log').write_bytes(r.stderr);logs_collected=True
 require(r.returncode==0,'log_observer_exit');return r.stdout

def remove_owned():
 d=inspect()
 if d['State']['Running']:run(['container','stop','--time','2',cid],8);d=inspect()
 require(not d['State']['Running'] and d['State']['Pid']==0,'stopped_before_remove')
 run(['container','rm',cid]);result['owned_container_removed']=True

try:
 os.umask(0o077);require(os.getuid()==1000 and owned(ROOT),'owned_host_root')
 owner=json.loads(read(ROOT/'ownership.json',16384));disk()
 raw=read(ROOT/'canonical-wheel-install-base-pip-alias/install-receipt.json',16384)
 require(hashlib.sha256(raw).hexdigest()==INSTALL,'actual_install_receipt');installation=json.loads(raw)
 require(installation['exit']==0 and installation['derived_image_id']==IMAGE and installation['owned_container_removed'],'actual_installed_image')
 prior=read(ROOT/'canonical-parquet-schema/probe-receipt.json',16384)
 require(hashlib.sha256(prior).hexdigest()=='e603a5cb4c6c8389957849dba0351cbb6f897abe83d2dd71a5cffe8c1819a9cf','prior_actual_policy_receipt')
 failed=read(ROOT/'canonical-parquet-fd-alias-diagnostic/probe-receipt.json',16384)
 require(hashlib.sha256(failed).hexdigest()=='0d7413602013379fd61e40475d5361fad96348232396fdd8544a25cb1a53a61a','prior_exact_FD_policy_failure')
 require(not PHASE.exists() and not PHASE.is_symlink(),'fresh_diagnostic_phase')
 PHASE.mkdir(mode=0o700);created=True;(PHASE/'empty-config').mkdir(mode=0o700)
 before=json.loads(run(['info','--format','{{json .}}']))
 require(before['ID']==ENGINE and before['ServerVersion']=='29.9.0' and before['Images']==2 and before['Containers']==0,'same_engine')
 image=json.loads(run(['image','inspect',IMAGE]))[0]
 require(image['Id']==IMAGE and image['RootFS']['Layers']==installation['derived_rootfs_layers']
  and image['Config']['Labels']=={'org.quantmesh.dependency-install':installation['nonce']},'installed_image_layers')
 expected_labels=dict(image['Config']['Labels'],**{'org.quantmesh.parquet-sealed-fd':nonce})
 (PHASE/'probe-source.py').write_text(CODE)
 create_requested=True
 args=['container','create','--name','qm-parquet-sealed-fd-'+nonce,'--label','org.quantmesh.parquet-sealed-fd='+nonce,
  '--pull','never','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges=true',
  '--pids-limit','32','--cpus','1','--memory','512m','--memory-swap','512m','--user','10001:10001',
  '--env','PYTHONDONTWRITEBYTECODE=1','--env','OPENBLAS_NUM_THREADS=1','--env','OMP_NUM_THREADS=1',
  '--env','MKL_NUM_THREADS=1','--env','HOME=/tmp/qm-home','--ulimit','core=0:0',
  '--tmpfs','/tmp:rw,noexec,nosuid,nodev,size=16m','--workdir','/tmp',
  '--log-opt','max-size=1m','--log-opt','max-file=1','--entrypoint','/usr/local/bin/python3',IMAGE,'-B','-I','-S','-c',CODE]
 candidate=run(args).decode().strip();require(re.fullmatch(r'[0-9a-f]{64}',candidate),'full_cid');cid=candidate
 result['container_id']=cid;d=inspect();h=d['HostConfig'];c=d['Config']
 require(c['Entrypoint']==['/usr/local/bin/python3'] and c['Cmd']==['-B','-I','-S','-c',CODE]
  and c['User']=='10001:10001' and c['WorkingDir']=='/tmp' and h['ReadonlyRootfs'] and h['NetworkMode']=='none'
  and h['CapDrop']==['ALL'] and not h['Privileged'] and h['PidsLimit']==32
  and h['Memory']==h['MemorySwap']==536870912 and h['NanoCpus']==1000000000
  and h['Tmpfs']=={'/tmp':'rw,noexec,nosuid,nodev,size=16m'} and not d['Mounts']
  and 'no-new-privileges' in ' '.join(h['SecurityOpt']) and not d['State']['Running'],'actual_created_boundary')
 run(['container','start',cid]);deadline=time.monotonic()+30
 while True:
  d=inspect();disk()
  if not d['State']['Running']:break
  require(time.monotonic()<deadline,'diagnostic_deadline');time.sleep(.5)
 result.update(actual_child_exit=d['State']['ExitCode'],actual_oom=d['State']['OOMKilled'],actual_pid=d['State']['Pid'],actual_started_at=d['State']['StartedAt'],actual_finished_at=d['State']['FinishedAt'])
 raw=capture();observation=json.loads(raw);result['observation']=observation
 validate_observation(d,observation);validate_sealed_observation(observation)
 require(observation['logical_schema']==json.loads(prior)['observation']['logical_schema'] and observation['physical_schema']==json.loads(prior)['observation']['physical_schema'] and observation['rows']==json.loads(prior)['observation']['rows'],'same_original_canonical_schema_and_rows')
 result.update(exit=0,observed_image_id=IMAGE,observed_engine_id=ENGINE,readonly_rootfs=True,
  network_none=True,mounts=[],tmpfs_noexec_requested=True,child_source_sha256=hashlib.sha256(CODE.encode()).hexdigest())
except BaseException as e:
 result.update(exit=1,failure_kind=type(e).__name__)
 if type(e) is ValueError:result['reason']=str(e)
finally:
 if cid:
  if not logs_collected:
   try:capture()
   except BaseException:result['raw_output']='NOT_CAPTURED'
  try:remove_owned()
  except BaseException as e:result.update(exit=1,owned_container_quiescence='NOT_PROVEN',cleanup_failure_kind=type(e).__name__)
 elif created and create_requested:
  result['partial_create_quiescence']='NOT_PROVEN'
  try:
   rows=run(['container','ls','-aq','--no-trunc','--filter','label=org.quantmesh.parquet-sealed-fd='+nonce]).decode().splitlines()
   if rows:
    require(len(rows)==1 and re.fullmatch(r'[0-9a-f]{64}',rows[0]),'one_partial_owned_cid');cid=rows[0];remove_owned()
  except BaseException:result['partial_create_quiescence']='NOT_PROVEN'
 if created:
  try:
   after=json.loads(run(['info','--format','{{json .}}']))
   require(after['ID']==ENGINE and after['Images']==2 and after['Containers']==0,'final_engine')
   result['final_engine']=dict(ID=ENGINE,Images=2,Containers=0)
  except BaseException:result.update(exit=1,final_engine='NOT_PROVEN')
  free=shutil.disk_usage('/').free
  result.update(host_free_bytes=free,whole_host_introduced_bytes=owner['free_before']-free,at_utc=datetime.now(timezone.utc).isoformat())
  if free<50000000000 or owner['free_before']-free>5000000000:result.update(exit=1,disk_gate='FAILED')
  require(owned(PHASE),'receipt_owner');(PHASE/'probe-receipt.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result),flush=True)
raise SystemExit(result['exit'])
