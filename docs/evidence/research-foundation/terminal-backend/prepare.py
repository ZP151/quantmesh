import hashlib,json,pathlib,shutil,subprocess,tarfile
O=pathlib.Path(__file__).resolve().parent
R=pathlib.Path((O/'native-root.txt').read_text().strip())
M=json.loads((O/'audit-manifest.json').read_text())
def sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
for s in M['sources']:
    for f in s['files']: assert sha(f['path'])==f['sha256']
for p in M['packages']: assert sha(p['notice'])==p['notice_sha256']
lic={
'tmux':('ISC/BSD-2/BSD-3/MIT','Unmodified external executable; all source headers, Debian notices and patches retained.'),
'libc6':('LGPL-2.1+ and permissive exceptions','Unmodified dynamically loaded libc, libm, libresolv and loader; corresponding source and Debian build files retained.'),
'libc-bin':('LGPL-2.1+ / permissive locale data','Only authenticated C.utf8 locale DATA are used. Tools in this data-supplier package are not executed.'),
'libsystemd0':('LGPL-2.1+','Library only. GPL-only systemd tools/daemons are outside the executing closure. No real system bus or manager is reachable.'),
'libutempter0':('LGPL-2.1+','Library AND external unmodified helper audited; new private /run/utmp and /var/log/wtmp, no-new-privileges.'),
'libgcrypt20':('LGPL-2.1+ / permissive incorporated code','Library statement distinguishes GPL manual/tools; these tools are not executed.'),
'libgpg-error0':('LGPL-2.1+ / BSD','Library; GPL-only tools/tests/build files are not executed.'),
'libcap2':('BSD-3 selected from BSD/GPL dual grant','libcap library files permit BSD choice; GPL-only tools/tests excluded.'),
'liblzma5':('Public domain / permissive','Exact source COPYING states liblzma public domain; GPL scripts/build files and probably-PD/noderivs non-library files are not executing.'),
'libzstd1':('BSD-3 selected from BSD/GPL dual grant','Library; GPL CLI/test tools excluded.'),
'liblz4-1':('BSD-2','Library; GPL programs/tests excluded.'),
'libtinfo6':('MIT/X11 / BSD-3','Terminfo library; full notices retained.'),
'libevent-core-2.1-7t64':('BSD-3 / BSD-2 / ISC / MIT','Core library only; GPL build tools excluded, full source/notices retained.'),
'libexpat1':('MIT','Full notice/source retained.'),
'zlib1g':('Zlib','Full notice/source retained.'),
'libffi8':('MIT','Full notice/source retained; ctypes fixture tool dependency.'),
'libssl3t64':('Apache-2.0','Unmodified libcrypto for hashlib in reviewed QuantMesh terminal admission; no TLS/network use.'),
'python3.12-minimal':('PSF-2 / CNRI / BeOpen / permissive incorporated code','Fixed stdlib fixture only. Unused extension modules cannot load missing dynamic dependencies; no readline/sqlite/SSL imported.'),
'libpython3.12-minimal':('PSF-2 / permissive incorporated code','Interpreter minimal stdlib; full composite copyright retained.'),
'libpython3.12-stdlib':('PSF-2 / permissive incorporated code','Only fixed stdlib imports; full composite copyright retained.'),
}
assert set(lic)=={p['name'] for p in M['packages']},[p['name'] for p in M['packages']]
notices=R/'notices'; notices.mkdir(exist_ok=True)
for p in M['packages']: shutil.copyfile(p['notice'],notices/(p['name']+'-copyright'))
texts=[]
for s in M['sources']:
    for f in s['files']:
        if '.orig.tar.' not in f['path'] or f['path'].endswith('.asc'): continue
        with tarfile.open(f['path']) as t:
            for n in t.getmembers():
                if n.isfile() and n.size<200000 and (n.name.split('/')[-1].upper().startswith(('LICENSE','LICENCE','COPYING','NOTICE'))):
                    data=t.extractfile(n).read(); target=notices/(s['name']+'-'+n.name.replace('/','_'))
                    target.write_bytes(data); texts.append({'source':s['name'],'member':n.name,'sha256':sha(target),'path':str(target)})
assert any('LGPL' in x['member'].upper() or 'COPYING.LIB' in x['member'].upper() for x in texts)
admission={'scope':'external-unmodified-local-synthetic-fixture-only','packages':[{'name':p['name'],'version':p['version'],'license':lic[p['name']][0],'reason':lic[p['name']][1],'notice_sha256':p['notice_sha256']} for p in M['packages']], 'source_license_texts':texts,'obligations':'Preserve every copyright/license notice, full LGPL texts and exact corresponding source including Debian patches/build files outside Git. Dynamic libraries stay replaceable; no restrictions on LGPL modification/relinking/reverse engineering. This audit does not authorize core linking/embedding or distribution without accompanying notices/source. No executing MPL dependency identified; source archives can contain nonexecuting GPL/other files whose notices remain intact.', 'signature_prerequisite':True,'license_prerequisite':True,'actual_host_or_installation_authority':False}
(O/'license-admission.json').write_text(json.dumps(admission,indent=2))
F=R/'fixture-root-v3'; F.mkdir(mode=0o700,exist_ok=False)
(O/'fixture-root.txt').write_text(str(F)+'\n')
receipts=[]
for p in M['packages']:
    name=pathlib.Path(p['uri']).name; pkg=R/'packages'/name
    assert sha(pkg)==p['package_sha256']
    args=['dpkg-deb','-x',str(pkg),str(F)]; q=subprocess.run(args,capture_output=True,text=True,timeout=20)
    receipts.append({'argv':args,'exit':q.returncode,'stdout':q.stdout,'stderr':q.stderr}); assert q.returncode==0
for name,target in [('lib','usr/lib'),('lib64','usr/lib64'),('bin','usr/bin'),('var/run','/run')]:
    dest=F/name; dest.parent.mkdir(exist_ok=True,parents=True)
    if not dest.exists() and not dest.is_symlink(): dest.symlink_to(target)
for name in ['proc','dev','dev/pts','run','var/log','tmp','proof','home','home/fixture','etc']:
    (F/name).mkdir(exist_ok=True,parents=True)
for name in ['run','var/log','tmp','proof','home/fixture']: (F/name).chmod(0o700)
(F/'etc/passwd').write_text('fixture:x:0:0:Owned fixture:/home/fixture:/usr/bin/python3.12\n')
(F/'etc/group').write_text('fixture:x:0:\n')
for name in ['run/utmp','var/log/wtmp']: (F/name).touch(mode=0o600)
for name in ['null','zero','urandom']: (F/'dev'/name).touch()
(F/'dev/ptmx').symlink_to('pts/ptmx')
helper=O.parents[1]/'tools/qualify_opend_private_terminal.py'
assert sha(helper)=='c18a81701ce432cb93e1ac2243b31add34f3ec10944dc381b92ff8e1d0133b63'
shutil.copyfile(helper,F/'proof/admission.py')
(F/'proof/tmux.conf').write_text('set -g history-limit 0\nset -g exit-unattached off\nset -g update-environment ""\nset -g set-clipboard off\nset -g allow-passthrough off\nset -g automatic-rename off\nset -g default-shell /usr/bin/python3.12\nset -g default-terminal dumb\nset -g status off\nset -g message-limit 0\nset -g prompt-history-limit 0\n')
for filename,meta in M['paths'].items():
    assert sha(F/filename.lstrip('/'))==meta['sha256'],filename
(O/'preparation-receipts.json').write_text(json.dumps(receipts,indent=2))
print(json.dumps({'status':'signed-license-source-manual-prerequisites-satisfied','root':str(F),'licenses_retained':len(texts),'packages':len(M['packages'])}))
