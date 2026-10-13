import base64
from pathlib import Path

root = Path(__file__).resolve().parents[1]
old = (root / 'output/qualify_aws_postgres_tls-before-receipt-guard.py').read_bytes()
fixed = (root / 'output/qualify_aws_postgres_tls.py').read_bytes()
template = '''import base64, contextlib, hashlib, io, json, os, stat, sys
from pathlib import Path
root=Path('/home/ubuntu/quantmesh-pg-tls-qualification-576db8859b72410b8fe8895845b2ae6e')
assert root.resolve()==root and root.stat().st_uid==os.getuid()!=0
parent=root/'ownership-negatives'
parent.mkdir(mode=0o700)
records=[]
for name,payload,vulnerable in CASES:
    stage=parent/name
    stage.mkdir(mode=0o700)
    target=stage/'target'
    target.mkdir(mode=0o700)
    link=stage/'link'
    link.symlink_to(target, target_is_directory=True)
    original=base64.b64decode(payload).decode()
    source=original
    if vulnerable:
        source=source.replace("FIXTURE = ROOT / 'protocol'", 'FIXTURE = Path('+repr(str(link))+')', 1)
    else:
        source=source.replace("FIXTURE = ROOT / ('protocol-capture-failure' if capture_failure_fixture else 'protocol')",
                              'FIXTURE = Path('+repr(str(link))+')', 1)
    assert source!=original
    captured=io.StringIO()
    code=None
    with contextlib.redirect_stdout(captured),contextlib.redirect_stderr(captured):
        try:
            exec(compile(source, '<owned-preflight-counterexample>', 'exec'), {'__name__':'__main__'})
        except SystemExit as error:
            code=error.code
    raw=captured.getvalue()
    assert code==1 and len(raw)<65536
    (stage/'sanitized-result.json').write_text(raw)
    receipt=target/'protocol-receipt.json'
    wrote=receipt.exists()
    assert wrote==vulnerable
    assert list(target.iterdir())==([receipt] if vulnerable else [])
    records.append(dict(case=name, original_source_sha256=hashlib.sha256(original.encode()).hexdigest(),
                        adapted_source_sha256=hashlib.sha256(source.encode()).hexdigest(),
                        expected_preflight_exit=code, rejected_fixture_written=wrote,
                        result_sha256=hashlib.sha256(raw.encode()).hexdigest(),
                        postgres_started=False, owned_new_target_only=True))
summary=dict(scope='actual approved host isolated preflight ownership counterexample only',
             RED='old guard writes through a rejected preexisting fixture symlink',
             GREEN='fixed guard refuses without writing target', cases=records, exit=0)
(parent/'summary.json').write_text(json.dumps(summary,indent=2)+'\\n')
print(json.dumps(summary))
'''
cases = [('old-guard-red', base64.b64encode(old).decode(), True),
         ('fixed-guard-green', base64.b64encode(fixed).decode(), False)]
template = template.replace('CASES', repr(cases))
(root / 'output/0038-aws-postgres-preflight-negatives.py').write_text(template, encoding='utf-8')
print('prepared bounded owned preflight harness; no local execution/materialization')
