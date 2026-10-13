import concurrent.futures, hashlib, json, lzma, os, pathlib, re, shutil, subprocess, sys, tempfile, urllib.request

OUT = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path((OUT/'native-root.txt').read_text().strip()) if (OUT/'native-root.txt').exists() else pathlib.Path(tempfile.mkdtemp(prefix='quantmesh-tmux-audit-', dir='/tmp'))
ROOT.chmod(0o700)
(OUT/'native-root.txt').write_text(str(ROOT)+'\n')
RECEIPTS=[]
def sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def run(args):
    p=subprocess.run(args,capture_output=True,text=True,timeout=30)
    RECEIPTS.append({'argv':args,'exit':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
    assert p.returncode==0, str(args)
    return p.stdout
def download(url,path,expected=None,size=None):
    path=pathlib.Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists():
        with urllib.request.urlopen(url,timeout=45) as r, path.open('wb') as f: shutil.copyfileobj(r,f)
    digest=sha(path)
    assert expected is None or digest==expected,(url,digest,expected)
    assert size is None or path.stat().st_size==int(size)
    RECEIPTS.append({'uri':url,'path':str(path),'sha256':digest,'bytes':path.stat().st_size})
    return path
def stanzas(text):
    for block in text.split('\n\n'):
        row={}; key=None
        for line in block.splitlines():
            if line.startswith(' ') and key: row[key]+='\n'+line
            elif ':' in line: key,val=line.split(':',1); row[key]=val.lstrip()
        if row: yield row

try:
    key=ROOT/'ubuntu-archive-keyring.gpg'; shutil.copyfile('/usr/share/keyrings/ubuntu-archive-keyring.gpg',key)
    fingerprints=run(['gpg','--batch','--no-options','--homedir',str(ROOT),'--no-default-keyring','--keyring',str(key),'--with-colons','--fingerprint'])
    assert 'F6ECB3762474EDA9D21B7022871920D1991BC93C' in fingerprints
    packages=[]; sources=[]
    archives=[('current','https://archive.ubuntu.com/ubuntu/',p) for p in ['noble','noble-updates','noble-security']]
    archives += [('20260924T180000Z','https://snapshot.ubuntu.com/ubuntu/20260924T180000Z/',p) for p in ['noble-updates','noble-security']]
    for archive,base,pocket in archives:
        store=ROOT/pocket if archive=='current' else ROOT/archive/pocket
        release=download(base+'dists/'+pocket+'/InRelease',store/'InRelease')
        status=run(['gpgv','--homedir',str(ROOT),'--keyring',str(key),'--status-fd','1',str(release)])
        assert '[GNUPG:] VALIDSIG F6ECB3762474EDA9D21B7022871920D1991BC93C ' in status
        hashes={}
        section=False
        for line in release.read_text().splitlines():
            if line=='SHA256:': section=True; continue
            if section and not line.startswith(' '): break
            if section:
                digest,size,name=line.split(); hashes[name]=(digest,size)
        for suffix,target in [('main/binary-amd64/Packages.xz',packages),('main/source/Sources.xz',sources)]:
            digest,size=hashes[suffix]
            path=download(base+'dists/'+pocket+'/'+suffix,store/suffix,digest,size)
            for row in stanzas(lzma.decompress(path.read_bytes()).decode()):
                row['_pocket']=pocket; row['_base']=base; target.append(row)
    (ROOT/'packages.json').write_text(json.dumps(packages))
    (ROOT/'sources.json').write_text(json.dumps(sources))
    tmux=[p for p in packages if p.get('Package')=='tmux']
    (OUT/'tmux-alternatives.json').write_text(json.dumps(tmux,indent=2))
    matches=[p for p in tmux if p['Version']=='3.4-1ubuntu0.1' and p['Architecture']=='amd64']
    assert matches,'Exact version unavailable; inspect tmux-alternatives.json'
    # The full reachable ELF closure is read-only discovered without executing candidate bytes.
    queue=[pathlib.Path('/usr/bin/tmux'),pathlib.Path('/usr/bin/python3.12'),pathlib.Path('/usr/lib/x86_64-linux-gnu/utempter/utempter')]
    for module in ['_ctypes','_json','_struct','select','fcntl','termios','math','_posixsubprocess','_socket','array','_datetime','resource','_hashlib','_random','_sha512','_sha2','_lzma']:
        queue.extend(pathlib.Path('/usr/lib/python3.12/lib-dynload').glob(module+'.*.so'))
    paths={}; owners={}; graph={}
    while queue:
        p=queue.pop().resolve()
        if str(p) in paths: continue
        assert p.is_file(),str(p)
        dynamic=run(['readelf','-d',str(p)])
        interpreter=run(['readelf','-l',str(p)])
        deps=re.findall(r'Shared library: \[([^\]]+)\]',dynamic)
        next_paths=[]
        for name in deps:
            candidates=[pathlib.Path('/usr/lib/x86_64-linux-gnu')/name,pathlib.Path('/lib/x86_64-linux-gnu')/name]
            q=next((q.resolve() for q in candidates if q.exists()),None); assert q,name
            next_paths.append(q)
        match=re.search(r'Requesting program interpreter: ([^\]]+)',interpreter)
        if match: next_paths.append(pathlib.Path(match[1]).resolve())
        owner=run(['dpkg-query','-S',str(p)]).split(': /')[0].splitlines()[0]
        info=run(['dpkg-query','-W','-f=${Package}\t${Version}\t${Architecture}\t${source:Package}\t${source:Version}\n',owner]).strip().split('\t')
        paths[str(p)]={'sha256':sha(p),'owner':info[0],'version':info[1]}
        owners[info[0]]=info; graph[str(p)]=[str(q) for q in next_paths]; queue.extend(next_paths)
    # Python imports also require its packaged stdlib/license closure; source is shared with interpreter.
    for name in ['libpython3.12-minimal','libpython3.12-stdlib','libc-bin']:
        info=run(['dpkg-query','-W','-f=${Package}\t${Version}\t${Architecture}\t${source:Package}\t${source:Version}\n',name]).strip().split('\t'); owners[info[0]]=info
    manifest={'native_root':str(ROOT),'keyring_sha256':sha(key),'paths':paths,'graph':graph,'packages':[],'sources':[]}
    selected_sources={}
    for name,version,arch,src,srcver in owners.values():
        choices=[p for p in packages if p.get('Package')==name and p.get('Version')==version and p.get('Architecture')==arch]
        assert choices,f'Exact installed closure package unavailable: {name} {version}'
        p=choices[-1]; pkg=download(p['_base']+p['Filename'],ROOT/'packages'/pathlib.Path(p['Filename']).name,p['SHA256'],p['Size'])
        dest=ROOT/'extract'/name; dest.mkdir(parents=True,exist_ok=True)
        run(['dpkg-deb','-x',str(pkg),str(dest)])
        # Verify each executing system byte against authenticated package bytes.
        for filename,meta in paths.items():
            if meta['owner']==name:
                rel=filename.lstrip('/'); q=dest/rel
                if not q.exists() and rel.startswith('usr/'): q=dest/rel[4:]
                assert q.is_file(),str(q)
                assert sha(q)==meta['sha256'],filename
        notice=dest/'usr/share/doc'/name/'copyright'
        docdir=dest/'usr/share/doc'/name
        if not notice.is_file() and docdir.is_symlink():
            target=docdir.readlink().name
            notice=ROOT/'extract'/target/'usr/share/doc'/target/'copyright'
        assert notice.is_file(),name
        manifest['packages'].append({'name':name,'version':version,'architecture':arch,'source':src,'source_version':srcver,'uri':p['_base']+p['Filename'],'package_sha256':sha(pkg),'notice':str(notice),'notice_sha256':sha(notice)})
        selected_sources[(src,srcver)]=None
    for src,version in selected_sources:
        choices=[s for s in sources if s.get('Package')==src and s.get('Version')==version]
        assert choices,f'Exact source unavailable: {src} {version}'
        s=choices[-1]; files=[]
        for line in s['Checksums-Sha256'].strip().splitlines():
            digest,size,name=line.split(); url=s['_base']+s['Directory']+'/'+name
            q=download(url,ROOT/'source'/src/name,digest,size); files.append({'uri':url,'path':str(q),'sha256':sha(q),'bytes':q.stat().st_size})
        manifest['sources'].append({'name':src,'version':version,'files':files})
    (ROOT/'manifest.json').write_text(json.dumps(manifest,indent=2))
    (OUT/'audit-manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps({'status':'acquired_signed_bytes_not_runtime_admitted','root':str(ROOT),'packages':len(manifest['packages']),'sources':len(manifest['sources']),'elfs':len(paths)}))
finally:
    (OUT/'acquisition-receipts.json').write_text(json.dumps(RECEIPTS,indent=2))
