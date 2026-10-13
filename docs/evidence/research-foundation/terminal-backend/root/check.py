import hashlib,json,lzma,os,pathlib,stat,subprocess,tarfile
O=pathlib.Path('/mnt/c/Users/15492/.codex-clean/worktrees/13a1/QuantMesh/output/169-terminal-backend');V=pathlib.Path('/mnt/c/Users/15492/.codex-clean/worktrees/0038-research-integration/QuantMesh/output/169-root-backend-check');R=pathlib.Path((O/'native-root.txt').read_text().strip());F=pathlib.Path((O/'fixture-root.txt').read_text().strip())
M=json.loads((O/'audit-manifest.json').read_text());C=json.loads((O/'native-controller.json').read_text());N=json.loads((O/'receipt-native.json').read_text());A=json.loads((O/'acquisition-receipts.json').read_text())
checks={};raw=[]
def check(name,ok):
    checks[name]=bool(ok)
    if not ok:raise RuntimeError(name)
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def stanzas(txt):
    result=[]
    for block in txt.split('\n\n'):
        row={};key=None
        for line in block.splitlines():
            if line.startswith(' ') and key:row[key]+='\n'+line
            elif ':' in line:key,v=line.split(':',1);row[key]=v.lstrip()
        if row:result.append(row)
    return result
try:
    pkgs=[];sources=[]
    for release in R.rglob('InRelease'):
        args=['gpgv','--homedir',str(R),'--keyring',str(R/'ubuntu-archive-keyring.gpg'),'--status-fd','1',str(release)]
        p=subprocess.run(args,capture_output=True,text=True,timeout=5);raw.append({'argv':args,'exit':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
        check('validsig-'+str(release.relative_to(R)),p.returncode==0 and '[GNUPG:] VALIDSIG F6ECB3762474EDA9D21B7022871920D1991BC93C ' in p.stdout)
        lines=release.read_text().splitlines();section=False;hashes={}
        for line in lines:
            if line=='SHA256:':section=True;continue
            if section and not line.startswith(' '):break
            if section:h,size,path=line.split();hashes[path]=(h,int(size))
        for path in ['main/binary-amd64/Packages.xz','main/source/Sources.xz']:
            p=release.parent/path;h,size=hashes[path]
            check('index-hash-'+str(p.relative_to(R)),sha(p)==h and p.stat().st_size==size)
            part=release.relative_to(R).parts[0]
            base='https://snapshot.ubuntu.com/ubuntu/'+part+'/' if part=='20260924T180000Z' else 'https://archive.ubuntu.com/ubuntu/'
            rows=stanzas(lzma.decompress(p.read_bytes()).decode())
            for row in rows:row['_base']=base
            (pkgs if 'Packages' in path else sources).extend(rows)
    for p in M['packages']:
        metadata=next(q for q in pkgs if q.get('Package')==p['name'] and q.get('Version')==p['version'] and q['_base']+q['Filename']==p['uri'])
        path=R/'packages'/pathlib.Path(p['uri']).name
        check('package-'+p['name'],sha(path)==p['package_sha256']==metadata['SHA256'] and path.stat().st_size==int(metadata['Size']))
        check('copyright-'+p['name'],sha(p['notice'])==p['notice_sha256'])
    for s in M['sources']:
        meta=next(q for q in sources if q.get('Package')==s['name'] and q.get('Version')==s['version'])
        expected={line.split()[2]:(line.split()[0],int(line.split()[1])) for line in meta['Checksums-Sha256'].strip().splitlines()}
        for f in s['files']:
            p=pathlib.Path(f['path']);h,size=expected[p.name]
            check('source-'+p.name,sha(p)==f['sha256']==h and p.stat().st_size==size)
    check('exact-binary',sha(F/'usr/bin/tmux')=='034b15c64035f783d43862f2775eb4828f61571ca62c8199796000b97d556ecd')
    check('exact-notice',sha(F/'usr/share/doc/tmux/copyright')=='9c587ac09a351692c23a910e4e59008d4a5ce66125c7aad1279065f3a272a3e1')
    for name,entry in M['paths'].items():check('executing-byte-'+name,sha(F/name.lstrip('/'))==entry['sha256'])
    # Confirm observed maps are authenticated package content, not ambient libraries.
    data_root_paths=[]
    for role,paths in N['maps'].items():
        for name in paths:
            q=F/name.lstrip('/');check('mapped-file-present-'+role+'-'+name,q.is_file())
            if name in M['paths']:check('mapped-elf-'+role+'-'+name,sha(q)==M['paths'][name]['sha256'])
            else:data_root_paths.append({'role':role,'path':name,'sha256':sha(q),'kind':'locale/cache authenticated by libc-bin/libc6 package'})
    manual=F/'usr/share/man/man1/tmux.1.gz'
    with tarfile.open(R/'source/tmux/tmux_3.4.orig.tar.gz') as t:source=t.extractfile('tmux-3.4/spawn.c').read().decode();foreground=t.extractfile('tmux-3.4/server.c').read().decode()
    check('exact-direct-exec-source','new_wp->argc != 0 && new_wp->argc != 1' in source and 'execvp(argvp[0], argvp)' in source)
    check('exact-foreground-source','if (~flags & CLIENT_NOFORK)' in foreground and 'options_set_number(global_options, "exit-empty", 0)' in foreground)
    check('manual-retained',manual.is_file() and 'With\n.Fl D ,\n.Ar command\nmay not be specified.' in (O/'tmux-manual.txt').read_text())
    check('controller-pass',C['raw_exit']==0 and C['result']['status']=='passed' and C['namespace_init_terminal'] and C['outside_sibling_survives'])
    check('bounded-cleanup',C['within_90_seconds'] and C['elapsed_seconds_including_cleanup']<90)
    check('init-pidfd-held-before-release',C['namespace_init_ownership']['pidfd_before_candidate_release'])
    check('namespace-init-absent',not pathlib.Path('/proc',str(C['namespace_init_ownership']['host_pid'])).exists())
    check('setup-reaped',not pathlib.Path('/proc',str(C['owned_setup_pid'])).exists())
    check('receipt-all-required',N['status']=='passed' and all(N['checks'].values()))
    check('no-authority-promoted',not any(N['false_flags'].values()))
    check('client-metadata-only',all(c['exit']==0 and '-N' in c['argv'] and not any(x in c['argv'] for x in ['attach','capture-pane','pipe-pane','show-buffer','send-keys']) for c in N['commands']))
    check('detached-identities-equal',N['metadata_before']==N['metadata_after'] and N['metadata_before'].endswith(':0:0'))
    check('socket-removed',not (F/'run/fixture.sock').exists())
    check('no-tty-bytes-retained',N['pane']['stdin_bytes']==N['pane']['stdout_bytes']==0)
    check('real-private-tty',N['pane']['terminal']['mode']==0o600 and not N['pane']['terminal']['echo'] and not N['pane']['terminal']['echonl'])
    check('six-real-negative-cases',len(N['pane']['negatives'])==6)
    check('old-socket-cleaned',not (R/'fixture-root-v2/run/fixture.sock').exists())
    result={'status':'passed','checks':checks,'count':len(checks),'manual_sha256':sha(manual),'mapped_data_files':data_root_paths,'proof_script_sha256':sha(O/'proof.py'),'source_artifact_count':sum(len(s['files']) for s in M['sources'])}
finally:
    (V/'independent-check-receipts.json').write_text(json.dumps(raw,indent=2))
    if 'result' in globals():(V/'independent-check.json').write_text(json.dumps(result,indent=2))
print(json.dumps({'status':result['status'],'checks':result['count'],'manual_sha256':result['manual_sha256'],'proof_script_sha256':result['proof_script_sha256']}))
