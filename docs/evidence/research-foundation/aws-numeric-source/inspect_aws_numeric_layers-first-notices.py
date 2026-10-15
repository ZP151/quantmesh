"""Nonroot virtual OCI overlay/notice bytes; no rootfs extraction or execution."""
import gzip,hashlib,json,os,signal,stat,sys,tarfile,time,shutil
from pathlib import Path,PurePosixPath

ROOT=Path('/home/ubuntu/quantmesh-numeric-materialization-4e00a5cecd0047fa9d5aa71c020a077a')
NONCE='4e00a5cecd0047fa9d5aa71c020a077a'
MANIFEST='2ed6491b93cd49272ee6de2b5a38440c3448360322c089fc23e370722d74179d'
CONFIG='4f228bc1cbcfc794e4878312cfc241d368eff55a21c08d1e2bb263116c4ef524'
PHASE=ROOT/'virtual-notice-intake'
started=time.monotonic();deadline=started+180
created=False;child=None;pidfd=None;reaped=False
result=dict(scope='verified OCI bytes/virtual overlay only',docker_mutation=False,container_started=False,
            rootfs_extracted=False,actual_runtime_qualified=False,numerical_certificate=False,
            full_option_A_complete=False)

def require(ok,tag):
    if not ok:raise ValueError(tag)

def owned(p):
    st=p.lstat()
    return p.resolve()==p and st.st_uid==os.getuid() and stat.S_ISDIR(st.st_mode) and stat.S_IMODE(st.st_mode)==0o700

def bounded_read(p,limit,collect=True):
    require(p.resolve()==p and not any(q.is_symlink() for q in (p,*p.parents)),'input_links')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid==os.getuid()
                and before.st_nlink==1 and 0<=before.st_size<=limit,'input_ownership_size')
        h=hashlib.sha256();chunks=[];count=0
        while b:=os.read(fd,min(65536,limit-count+1)):
            count+=len(b);require(count<=limit,'input_read_bound');h.update(b)
            if collect:chunks.append(b)
        def identity(st):return (st.st_dev,st.st_ino,st.st_size,st.st_mode,st.st_nlink,st.st_uid,st.st_mtime_ns,st.st_ctime_ns)
        require(identity(before)==identity(os.fstat(fd))==identity(p.lstat()) and count==before.st_size,'input_stable')
        return b''.join(chunks),h.hexdigest()
    finally:os.close(fd)

def digest_file(p):return bounded_read(p,128000000,False)[1]

def normalized(name,base=()):
    require(type(name) is str and len(name)<=2048 and '\\' not in name and '\0' not in name,'virtual_path')
    parts=[] if name.startswith('/') else list(base)
    for p in name.split('/'):
        if p in ('','.'):continue
        if p=='..':
            require(bool(parts),'virtual_escape');parts.pop()
        else:parts.append(p)
    return '/'.join(parts)

def inspect():
    manifest_raw,manifest_sha=bounded_read(ROOT/'blobs'/MANIFEST,65536)
    config_raw,config_sha=bounded_read(ROOT/'blobs'/CONFIG,65536)
    require(manifest_sha==MANIFEST and config_sha==CONFIG,'manifest_pin')
    manifest=json.loads(manifest_raw);config=json.loads(config_raw)
    require(manifest['config']['digest']=='sha256:'+CONFIG and len(manifest['layers'])==len(config['rootfs']['diff_ids'])==4,'layer_chain')
    nodes={};retained={};layers=[];file_bytes=0;member_count=0;retained_bytes=0
    for index,layer in enumerate(manifest['layers']):
        sha=layer['digest'].removeprefix('sha256:');blob=ROOT/'blobs'/sha
        require(len(sha)==64 and blob.stat().st_size==layer['size'] and digest_file(blob)==sha,'compressed_layer_pin')
        diff=hashlib.sha256();expanded=0
        with gzip.open(blob,'rb') as f:
            while b:=f.read(65536):
                expanded+=len(b);require(expanded<=250000000,'expanded_layer_bound');diff.update(b)
        require('sha256:'+diff.hexdigest()==config['rootfs']['diff_ids'][index],'diff_id_pin')
        staged=[];whiteouts=[]
        with tarfile.open(blob,mode='r|gz') as archive:
            for ordinal,member in enumerate(archive):
                member_count+=1;require(member_count<=20000,'member_bound')
                require(not member.name.startswith('/'),'absolute_member')
                path=normalized(member.name)
                if not path:
                    require(member.isdir(),'empty_member');continue
                parent,_,name=path.rpartition('/')
                if name.startswith('.wh.'):
                    require(member.isfile() and member.size==0,'whiteout_type')
                    target=parent if name=='.wh..wh..opq' else normalized(name[4:],parent.split('/') if parent else ())
                    whiteouts.append((target,name=='.wh..wh..opq'))
                    continue
                node=dict(layer=index,mode=member.mode,size=member.size)
                if member.isdir():node['kind']='directory'
                elif member.issym():node.update(kind='symlink',target=normalized(member.linkname,parent.split('/') if parent else ()))
                elif member.islnk():node.update(kind='hardlink',target=normalized(member.linkname))
                elif member.isfile():
                    require(0<=member.size<=128000000,'file_size_bound')
                    file_bytes+=member.size;require(file_bytes<=350000000,'total_file_byte_bound')
                    h=hashlib.sha256();prefix=b'';count=0
                    with archive.extractfile(member) as f:
                        while b:=f.read(65536):
                            if count==0:prefix=b[:4]
                            count+=len(b);h.update(b)
                    require(count==member.size,'file_exact_size')
                    node.update(kind='regular',sha256=h.hexdigest(),elf=prefix==b'\x7fELF',
                                payload_layer=index,payload_ordinal=ordinal,payload_name=member.name)
                else:raise ValueError('unsupported_tar_member')
                staged.append((path,node))
        # OCI whiteouts apply to lower layers only, independently of their
        # position in this archive. Never erase new entries in the same layer.
        for target,opaque in whiteouts:
            for old in tuple(nodes):
                if (not opaque and old==target) or old.startswith(target+'/') or (opaque and not target):
                    del nodes[old]
        for path,node in staged:
            parts=path.split('/')
            for i in range(1,len(parts)):
                ancestor='/'.join(parts[:i])
                if ancestor in nodes:
                    require(nodes[ancestor]['kind']=='directory','unsupported_member_link_or_file_ancestor')
                else:nodes[ancestor]=dict(kind='directory',implicit=True,layer=index,mode=None,size=0)
            if node['kind']=='hardlink':
                # Snapshot the existing regular inode payload now. Forward,
                # symlink and nonregular hardlinks are explicitly unsupported.
                target=nodes.get(node['target'])
                require(target is not None and target['kind']=='regular','unsupported_hardlink_target')
                node=dict(target,layer=index,hardlink_original_target=node['target'])
            if node['kind']!='directory':
                for old in tuple(nodes):
                    if old.startswith(path+'/'):del nodes[old]
            nodes[path]=node;require(len(nodes)<=20000,'overlay_node_bound')
        layers.append(dict(index=index,compressed_sha256=sha,compressed_bytes=layer['size'],
                           uncompressed_sha256=diff.hexdigest(),uncompressed_bytes=expanded))
        free=shutil.disk_usage('/').free
        require(owner['free_before']-free<=500000000 and free>=50000000000,'phase1_disk_bound')

    def resolve(path):
        parts=normalized(path).split('/')
        for hop in range(33):
            changed=False
            for i in range(1,len(parts)+1):
                candidate='/'.join(parts[:i]);node=nodes.get(candidate)
                if node and node['kind'] in ('symlink','hardlink'):
                    parts=normalized(node['target']+'/'+ '/'.join(parts[i:])).split('/')
                    changed=True;break
                if i<len(parts) and node:
                    require(node['kind']=='directory','virtual_non_directory_ancestor')
            if not changed:return '/'.join(parts)
        raise ValueError('virtual_link_cycle')

    # Read only final selected regular payloads, using their actual layer and
    # TAR ordinal. A hardlink keeps the original inode bytes even if its former
    # source pathname was replaced/whiteouted in a later layer.
    selected={}
    for path,node in nodes.items():
        name=path.rsplit('/',1)[-1].lower()
        if node['kind']=='regular' and (path=='var/lib/dpkg/status' or 'copyright' in name
                                        or 'license' in name or name.startswith('copying')):
            key=(node['payload_layer'],node['payload_ordinal'])
            selected.setdefault(key,[]).append(path)
    require(len(selected)<=4096,'notice_count_bound')
    for index,layer in enumerate(manifest['layers']):
        wanted={ordinal:paths for (n,ordinal),paths in selected.items() if n==index}
        if not wanted:continue
        with tarfile.open(ROOT/'blobs'/layer['digest'][7:],mode='r|gz') as archive:
            for ordinal,member in enumerate(archive):
                if ordinal not in wanted:continue
                paths=wanted[ordinal];node=nodes[paths[0]]
                require(member.isfile() and member.name==node['payload_name'] and member.size<=2000000,'notice_payload_identity')
                with archive.extractfile(member) as f:raw=f.read(2000001)
                require(len(raw)==member.size and hashlib.sha256(raw).hexdigest()==node['sha256'],'notice_exact_payload')
                retained_bytes+=len(raw);require(retained_bytes<=16000000,'retained_notice_bound')
                for path in paths:retained[path]=raw

    status_path=resolve('var/lib/dpkg/status');require(status_path in retained,'actual_dpkg_status')
    packages=[]
    for block in retained[status_path].decode('utf-8').split('\n\n'):
        fields={}
        for line in block.splitlines():
            if line and not line[0].isspace() and ': ' in line:
                k,v=line.split(': ',1);fields[k]=v
        if fields.get('Status')!='install ok installed':continue
        name=fields['Package'];require(name and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789+.-' for c in name),'package_name')
        notice=resolve('usr/share/doc/'+name+'/copyright')
        packages.append(dict(package=name,version=fields['Version'],source=fields.get('Source',name),
                             notice_virtual_path=notice,notice_sha256=nodes.get(notice,{}).get('sha256'),
                             actual_notice_present=notice in retained))
    require(0<len(packages)<=256,'package_count')
    required=('base-files','debian-archive-keyring','libcrypt1','libsemanage-common','libsemanage2','tzdata')
    rows={p['package']:p for p in packages}
    require(all(p in rows and rows[p]['actual_notice_present'] for p in required),'NULL_binary_notices')
    python_path=resolve('usr/local/lib/python3.12/LICENSE.txt')
    require(nodes.get(python_path,{}).get('sha256')=='3b2f81fe21d181c499c59a256c8e1968455d6689d269aa85373bfb6af41da3bf'
            and python_path in retained,'actual_python_license')
    notices=PHASE/'notice-by-sha256';notices.mkdir(mode=0o700)
    seen=set()
    for path,raw in retained.items():
        if path not in nodes or nodes[path]['kind']!='regular' or nodes[path]['sha256'] in seen:continue
        sha=nodes[path]['sha256'];seen.add(sha)
        (notices/sha).write_bytes(raw)
    (PHASE/'virtual-file-inventory.json').write_text(json.dumps(nodes,sort_keys=True,separators=(',',':'))+'\n')
    (PHASE/'installed-package-notices.json').write_text(json.dumps(packages,indent=2)+'\n')
    missing=[p['package'] for p in packages if not p['actual_notice_present']]
    result.update(exit=0,layers=layers,virtual_nodes=len(nodes),tar_members=member_count,
                  total_regular_file_bytes=file_bytes,actual_ELF_files=sum(n.get('elf',False) for n in nodes.values()),
                  installed_binary_packages=len(packages),missing_package_notices=missing,
                  required_NULL_binary_mappings=[rows[p] for p in required],
                  python_notice=dict(path=python_path,sha256=nodes[python_path]['sha256']),
                  preserved_unique_notice_files=len(seen),source_version_metadata_only=True,
                  full_license_closure_qualified=False,ELF_dependency_closure_qualified=False)

try:
    os.umask(0o077)
    require(not sys.argv[1:] and os.getuid()!=0 and signal.getsignal(signal.SIGCHLD)==signal.SIG_DFL,'nonroot_fixed_entry')
    require(owned(ROOT),'owned_root')
    owner=json.loads(bounded_read(ROOT/'ownership.json',16384)[0])
    receipt=json.loads(bounded_read(ROOT/'blob-intake-receipt.json',16384)[0])
    require(owner['nonce']==NONCE and owner['uid']==os.getuid() and owner['manifest_sha256']==MANIFEST
            and owner['config_sha256']==CONFIG and receipt['exit']==0 and receipt['download_worker_reaped'],'actual_intake_binding')
    require(not PHASE.exists() and not PHASE.is_symlink(),'new_phase')
    PHASE.mkdir(mode=0o700);created=True
    require(owned(PHASE),'owned_phase')
    child=os.fork()
    if child==0:
        try:
            try:inspect()
            except BaseException as e:
                result.update(exit=1,failure_kind=type(e).__name__)
                if type(e) is ValueError:result['reason']=str(e)
            (PHASE/'worker-result.json').write_text(json.dumps(result)+'\n')
        finally:os._exit(0)
    pidfd=os.pidfd_open(child)
    while True:
        ended,status=os.waitpid(child,os.WNOHANG)
        if ended:
            reaped=True;require(os.waitstatus_to_exitcode(status)==0,'worker_exit')
            result=json.loads(bounded_read(PHASE/'worker-result.json',65536)[0]);break
        require(time.monotonic()<deadline,'inspect_watchdog')
        free=shutil.disk_usage('/').free
        require(owner['free_before']-free<=500000000 and free>=50000000000,'phase1_disk_bound')
        time.sleep(0.05)
except BaseException as e:
    result.update(exit=1,failure_kind=type(e).__name__)
    if type(e) is ValueError:result['reason']=str(e)
finally:
    if child and not reaped:
        ended,status=os.waitpid(child,os.WNOHANG)
        if ended:reaped=True
        else:
            if pidfd is not None:signal.pidfd_send_signal(pidfd,signal.SIGKILL)
            else:os.kill(child,signal.SIGKILL)
            stop=time.monotonic()+5
            while time.monotonic()<stop:
                ended,status=os.waitpid(child,os.WNOHANG)
                if ended:reaped=True;break
                time.sleep(0.05)
    if pidfd is not None:os.close(pidfd)
    if child and not reaped:result.update(exit=1,worker_quiescence='NOT_PROVEN')
    if created:
        require(owned(ROOT) and owned(PHASE),'receipt_ownership')
        free=shutil.disk_usage('/').free
        result.update(root=str(ROOT),phase_root=str(PHASE),worker_reaped=reaped,
                      elapsed_seconds=round(time.monotonic()-started,3),host_free_bytes=free,
                      phase1_host_introduced_bytes=owner['free_before']-free,
                      files=[dict(path=str(p.relative_to(PHASE)),bytes=p.stat().st_size,sha256=digest_file(p))
                             for p in PHASE.rglob('*') if p.is_file()])
        (PHASE/'notice-intake-receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    # Full file hashes stay on AWS. The compact receipt has no keys/user payload.
    print(json.dumps({k:v for k,v in result.items() if k!='files'}),flush=True)
raise SystemExit(result['exit'])
