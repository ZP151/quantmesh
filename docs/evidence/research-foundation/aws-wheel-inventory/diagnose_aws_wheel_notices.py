"""Read-only exact pinned wheel filename/notice-selection diagnosis."""
import hashlib,json,os,re,stat,zipfile,email.parser
from pathlib import Path,PurePosixPath
ROOT=Path('/home/ubuntu/quantmesh-numeric-materialization-4e00a5cecd0047fa9d5aa71c020a077a')
assert ROOT.resolve()==ROOT and ROOT.stat().st_uid==os.getuid()
p=ROOT/'wheel-intake/linux-wheels.json';raw=p.read_bytes()
assert hashlib.sha256(raw).hexdigest()=='900a8ab850e85a84aafc2b4061758767902d377704c4cad22fb0041b30d5d5cf'
rows=[]
for row in json.loads(raw):
    p=ROOT/'wheel-intake/wheelhouse'/row['filename'];assert p.resolve()==p
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as f:
        st=os.fstat(f.fileno());assert stat.S_ISREG(st.st_mode) and st.st_uid==os.getuid() and st.st_nlink==1 and st.st_size==row['previous_cached_compressed_bytes']
        h=hashlib.sha256()
        while b:=f.read(65536):h.update(b)
        assert h.hexdigest()==row['sha256'];f.seek(0)
        with zipfile.ZipFile(f) as z:
            names=[i.filename for i in z.infolist() if not i.is_dir()]
            notices=[n for n in names if re.match(r'(?i)^(license|licence|copying|copyright|notice)([._-].*|$)',PurePosixPath(n).name)]
            if not notices:
                metadata=[n for n in names if n.endswith('.dist-info/METADATA')]
                assert len(metadata)==1
                with z.open(metadata[0]) as mf:body=mf.read(1048577)
                assert len(body)<=1048576
                parsed=email.parser.BytesParser().parsebytes(body)
                license_text=parsed.get('License','').encode()
                rows.append(dict(name=row['name'],version=row['version'],wheel_sha256=row['sha256'],
                    dist_info_paths=[n for n in names if '.dist-info/' in n],license_inventory=row['license_inventory'],
                    license_header_bytes=len(license_text),license_header_sha256=hashlib.sha256(license_text).hexdigest(),
                    header_has_grant=b'Permission is hereby granted' in license_text,
                    header_has_disclaimer=b'THE SOFTWARE IS PROVIDED' in license_text,
                    project_urls=parsed.get_all('Project-URL',[])))
        assert st.st_ino==os.fstat(f.fileno()).st_ino==p.lstat().st_ino and st.st_mtime_ns==p.stat().st_mtime_ns
print(json.dumps(dict(read_only=True,missing_notice_selection=rows,wheels=81,native_code_loaded=False)))
