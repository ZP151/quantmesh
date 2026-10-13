"""Finite offline dependency image materialization; no Worker or numerical admission."""
import hashlib,json,os,re,shutil,stat,subprocess,time,uuid
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path('/home/ubuntu/quantmesh-numeric-materialization-4e00a5cecd0047fa9d5aa71c020a077a')
PHASE=ROOT/'canonical-wheel-install'
IMAGE='sha256:2ed6491b93cd49272ee6de2b5a38440c3448360322c089fc23e370722d74179d'
ENGINE='cfe71bf3-9059-4059-887d-ac401f2283ec'
META='900a8ab850e85a84aafc2b4061758767902d377704c4cad22fb0041b30d5d5cf'
LOCK='07f4e7ec64805a375e0bdc707d0158fbdb08bd07d02aa569e2d119496b32592a'
CATALOG='cc136f358515c5efa4092f450d5997b2cd48875c4e881de5833d358e1dd4df8a'
nonce=uuid.uuid4().hex;cid=None;created=False;create_requested=False;image_commit_requested=False;derived=None
started=time.monotonic();owner=None
CODE=r'''import sys,os,json,hashlib,runpy,shutil,importlib.metadata,re
from pathlib import Path
result=dict(scope='actual canonical offline install only',numerical_certificate=False,native_admission=False)
try:
 assert sys.version.startswith('3.12.15 ') and sys.prefix==sys.base_prefix=='/usr/local'
 assert sys.executable=='/usr/local/bin/python3' and sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
 assert os.getuid()==os.getgid()==0
 metadata=Path('/inputs/linux-wheels.json').read_bytes();lock=Path('/inputs/requirements.linux-cp312.lock').read_bytes()
 assert hashlib.sha256(metadata).hexdigest()=='900a8ab850e85a84aafc2b4061758767902d377704c4cad22fb0041b30d5d5cf'
 assert hashlib.sha256(lock).hexdigest()=='07f4e7ec64805a375e0bdc707d0158fbdb08bd07d02aa569e2d119496b32592a'
 rows=json.loads(metadata);assert len(rows)==81
 for row in rows:
  p=Path('/wheels')/row['filename'];assert p.is_file() and not p.is_symlink()
  assert p.stat().st_size==row['previous_cached_compressed_bytes'] and hashlib.file_digest(p.open('rb'),'sha256').hexdigest()==row['sha256']
 site=Path('/usr/local/lib/python3.12/site-packages');sys.path.append(str(site))
 before=list(importlib.metadata.distributions(path=[str(site)]));assert len(before)==1 and before[0].metadata['Name']=='pip' and before[0].version=='25.0.1'
 sys.argv=['pip','--isolated','--disable-pip-version-check','install','--no-index','--find-links','/wheels','--require-hashes','--only-binary',':all:','--no-deps','--no-compile','--no-cache-dir','--root-user-action','ignore','--quiet','-r','/inputs/requirements.linux-cp312.lock']
 try:runpy.run_module('pip',run_name='__main__')
 except SystemExit as e:assert e.code in (None,0)
 # Remove only the base bootstrap pip within this disposable container layer.
 for name in ('pip','pip-25.0.1.dist-info'):
  p=site/name;assert p.is_dir() and not p.is_symlink();shutil.rmtree(p)
 for name in ('pip','pip3','pip3.12'):
  p=Path('/usr/local/bin')/name;assert p.is_file() and not p.is_symlink();p.unlink()
 actual={}
 for d in importlib.metadata.distributions(path=[str(site)]):
  n=re.sub(r'[-_.]+','-',d.metadata['Name']).lower();assert n not in actual;actual[n]=d.version
 assert actual=={r['name']:r['version'] for r in rows}
 assert not any(site.rglob('*.pyc')) and not any(site.rglob('*.pth'))
 notices=Path('/usr/local/share/quantmesh-dependency-notices');notices.mkdir()
 for p in Path('/notices').iterdir():
  assert p.is_file() and not p.is_symlink();shutil.copyfile(p,notices/p.name)
 result.update(exit=0,python_version=sys.version,prefix=sys.prefix,base_prefix=sys.base_prefix,
  installed_distributions=actual,installed_package_count=len(actual),base_bootstrap_pip_removed=True,bytecode_files=0,pth_files=0)
except BaseException as e:result.update(exit=1,failure_kind=type(e).__name__)
print(json.dumps(result),flush=True)
raise SystemExit(result['exit'])
'''
result=dict(scope='actual finite dependency materialization only',nonce=nonce,numerical_certificate=False,
 native_admission=False,production_services_enabled=False,full_option_A_complete=False,
 container_started=False,start_requested=False,derived_image_qualified=False)
def require(ok,why):
 if not ok:raise ValueError(why)
def owned(p):
 s=p.lstat();return p.resolve()==p and s.st_uid==os.getuid() and stat.S_ISDIR(s.st_mode) and stat.S_IMODE(s.st_mode)==0o700
def signature(s):return(s.st_dev,s.st_ino,s.st_size,s.st_mode,s.st_uid,s.st_nlink,s.st_mtime_ns,s.st_ctime_ns)
def read(p,limit):
 require(p.resolve()==p and not any(q.is_symlink() for q in (p,*p.parents)),'no_links')
 fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as f:
  s=os.fstat(f.fileno());require(stat.S_ISREG(s.st_mode) and s.st_uid==os.getuid() and s.st_nlink==1 and 0<s.st_size<=limit,'owned_regular')
  b=f.read(limit+1);require(len(b)==s.st_size and signature(s)==signature(os.fstat(f.fileno()))==signature(p.lstat()),'stable_read')
 return b
def disk():
 free=shutil.disk_usage('/').free;require(free>=50000000000 and owner['free_before']-free<=5000000000,'original_materialization_gate');return free
def command(args,seconds):
 return ['sudo','-n','/usr/bin/timeout','-k','3s',str(seconds)+'s','/usr/bin/env','-i','PATH=/usr/sbin:/usr/bin:/sbin:/bin',
  '/usr/bin/docker','--config',str(PHASE/'empty-config'),'--host','unix:///var/run/docker.sock',*args]
def run(args,seconds=10,limit=65536):
 r=subprocess.run(command(args,seconds),capture_output=True,timeout=seconds+8)
 require(len(r.stdout)<=limit and len(r.stderr)<=limit and r.returncode==0 and not r.stderr,'cli_result');return r.stdout
def inspect():
 rows=json.loads(run(['container','inspect',cid]));require(len(rows)==1,'one_container');d=rows[0]
 require(d['Id']==cid and d['Image']==IMAGE and d['Config']['Labels']=={'org.quantmesh.dependency-install':nonce},'owned_exact_cid')
 if not d['State']['StartedAt'].startswith('0001-01-01'):result['container_started']=True
 return d
def stopped_remove():
 d=inspect()
 if d['State']['Running']:run(['container','stop','--time','2',cid],8);d=inspect()
 require(not d['State']['Running'] and d['State']['Pid']==0,'actual_stopped');run(['container','rm',cid]);result['owned_container_removed']=True
def stage(raw,path):path.write_bytes(raw);path.chmod(0o644)
try:
 os.umask(0o077);require(os.getuid()!=0 and owned(ROOT),'owned_root');owner=json.loads(read(ROOT/'ownership.json',16384));disk()
 require(not PHASE.exists() and not PHASE.is_symlink(),'fresh_phase');PHASE.mkdir(mode=0o700);created=True;(PHASE/'empty-config').mkdir(mode=0o700)
 info=json.loads(run(['info','--format','{{json .}}']));require(info['ID']==ENGINE and info['Containers']==0 and info['Images']==1,'same_engine')
 inventory=json.loads(read(ROOT/'wheel-inventory-with-source-notices/inventory-receipt.json',32768))
 require(inventory['exit']==0 and inventory['worker_reaped'] and inventory['wheels']==81 and inventory['inventory_sha256']==CATALOG,'actual_inventory')
 catalog=read(ROOT/'wheel-inventory-with-source-notices/inventory.json',8388608);require(hashlib.sha256(catalog).hexdigest()==CATALOG,'catalog_pin')
 metadata=read(ROOT/'wheel-intake/linux-wheels.json',262144);lock=read(ROOT/'wheel-intake/requirements.linux-cp312.lock',16384)
 require(hashlib.sha256(metadata).hexdigest()==META and hashlib.sha256(lock).hexdigest()==LOCK,'metadata_pins')
 for folder in ('wheels','inputs','notices'):
  (PHASE/folder).mkdir(mode=0o755);(PHASE/folder).chmod(0o755)
 stage(metadata,PHASE/'inputs/linux-wheels.json');stage(lock,PHASE/'inputs/requirements.linux-cp312.lock')
 for row in json.loads(metadata):
  raw=read(ROOT/'wheel-intake/wheelhouse'/row['filename'],22000000)
  require(len(raw)==row['previous_cached_compressed_bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256'],'wheel_pin')
  stage(raw,PHASE/'wheels'/row['filename']);disk()
 for package in json.loads(catalog)['packages']:
  for n in package['notices']:
   raw=read(ROOT/'wheel-inventory-with-source-notices/notices'/n['body_file'],1048576)
   require(len(raw)==n['bytes'] and hashlib.sha256(raw).hexdigest()==n['sha256'],'notice_pin')
   stage(raw,PHASE/'notices'/n['body_file'])
 mounts=[dict(Type='bind',Source=str(PHASE/x),Target='/'+x,ReadOnly=True) for x in ('wheels','inputs','notices')]
 (PHASE/'install-source.py').write_text(CODE)
 args=['container','create','--name','qm-install-'+nonce,'--label','org.quantmesh.dependency-install='+nonce,'--pull','never',
  '--network','none','--cap-drop','ALL','--security-opt','no-new-privileges=true','--pids-limit','64','--cpus','1','--memory','768m',
  '--memory-swap','768m','--user','0:0','--env','PYTHONDONTWRITEBYTECODE=1','--tmpfs','/tmp:rw,noexec,nosuid,nodev,size=64m',
  '--log-opt','max-size=1m','--log-opt','max-file=1']
 for m in mounts:args+=['--mount','type=bind,source='+m['Source']+',target='+m['Target']+',readonly']
 args+=['--entrypoint','/usr/local/bin/python3',IMAGE,'-B','-I','-S','-c',CODE]
 create_requested=True;cid=run(args).decode().strip();require(re.fullmatch(r'[0-9a-f]{64}',cid),'full_cid');result['container_id']=cid
 d=inspect();h=d['HostConfig'];c=d['Config']
 require(c['Entrypoint']==['/usr/local/bin/python3'] and c['Cmd']==['-B','-I','-S','-c',CODE] and c['User']=='0:0'
  and not h['ReadonlyRootfs'] and h['NetworkMode']=='none' and h['CapDrop']==['ALL'] and not h['Privileged']
  and h['PidsLimit']==64 and h['Memory']==805306368 and h['MemorySwap']==805306368 and h['NanoCpus']==1000000000
  and h['Tmpfs']=={'/tmp':'rw,noexec,nosuid,nodev,size=64m'} and 'no-new-privileges' in ' '.join(h['SecurityOpt'])
  and len(d['Mounts'])==3 and all(m['Type']=='bind' and not m['RW'] and m['Source']==str(PHASE/m['Destination'].lstrip('/')) for m in d['Mounts'])
  and {m['Destination'] for m in d['Mounts']}=={'/wheels','/inputs','/notices'} and not d['State']['Running'],'actual_created_boundary')
 result['start_requested']=True;run(['container','start',cid]);deadline=time.monotonic()+180
 while True:
  d=inspect();disk()
  if not d['State']['Running']:break
  require(time.monotonic()<deadline,'install_deadline');time.sleep(.5)
 require(result['container_started'] and d['State']['ExitCode']==0 and d['State']['Pid']==0 and not d['State']['OOMKilled'],'actual_install_exit')
 raw=run(['container','logs',cid],limit=131072);(PHASE/'install-output.json').write_bytes(raw);observation=json.loads(raw)
 require(observation['exit']==0 and observation['installed_package_count']==81 and observation['base_bootstrap_pip_removed'],'actual_81_install')
 image_commit_requested=True;derived=run(['container','commit',cid],60).decode().strip();require(re.fullmatch(r'sha256:[0-9a-f]{64}',derived),'derived_image_id')
 saved=json.loads(run(['image','inspect',derived]))[0];base=json.loads(run(['image','inspect',IMAGE]))[0]
 require(saved['Id']==derived and saved['RootFS']['Layers'][:len(base['RootFS']['Layers'])]==base['RootFS']['Layers']
  and len(saved['RootFS']['Layers'])==len(base['RootFS']['Layers'])+1 and saved['Config']['Labels']=={'org.quantmesh.dependency-install':nonce},'actual_derived_image')
 result.update(exit=0,observation=observation,derived_image_id=derived,derived_rootfs_layers=saved['RootFS']['Layers'],
  install_source_sha256=hashlib.sha256(CODE.encode()).hexdigest(),actual_dependency_installation=True,
  mutable_rootfs_for_install_only=True,root_inside_container_only=True,readonly_input_mounts=mounts,
  whole_materialization_limit_bytes=5000000000,source_baseline_retained=True)
except BaseException as e:
 result.update(exit=1,failure_kind=type(e).__name__)
 if type(e)is ValueError:result['reason']=str(e)
finally:
 if cid:
  try:stopped_remove()
  except BaseException as e:result.update(exit=1,owned_container_quiescence='NOT_PROVEN',cleanup_failure_kind=type(e).__name__)
 elif created and create_requested:
  result['partial_create_quiescence']='NOT_PROVEN'
  try:
   rows=run(['container','ls','-aq','--no-trunc','--filter','label=org.quantmesh.dependency-install='+nonce]).decode().splitlines()
   if rows:require(len(rows)==1 and re.fullmatch(r'[0-9a-f]{64}',rows[0]),'one_partial_cid');cid=rows[0];stopped_remove()
  except BaseException:result.update(exit=1,partial_create_quiescence='NOT_PROVEN')
 if image_commit_requested and not derived:result['image_commit_completion']='NOT_PROVEN'
 if created:
  try:
   after=json.loads(run(['info','--format','{{json .}}']));require(after['ID']==ENGINE and after['Containers']==0,'final_owned_cleanup')
   result['final_engine']=dict(ID=ENGINE,Images=after['Images'],Containers=0)
  except BaseException:result.update(exit=1,final_engine='NOT_PROVEN')
  free=shutil.disk_usage('/').free;result.update(host_free_bytes=free,whole_host_introduced_bytes=owner['free_before']-free,
   elapsed_seconds=round(time.monotonic()-started,3),at_utc=datetime.now(timezone.utc).isoformat(),phase_root=str(PHASE))
  if free<50000000000 or owner['free_before']-free>5000000000:result.update(exit=1,disk_gate='FAILED')
  require(owned(PHASE),'receipt_owner');(PHASE/'install-receipt.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result),flush=True)
raise SystemExit(result['exit'])
