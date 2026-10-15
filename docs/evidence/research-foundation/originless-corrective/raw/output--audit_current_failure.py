import hashlib
import json
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parent
archive = root / '0038-ci38381619194-release-diagnostics.zip'
with zipfile.ZipFile(archive) as packet:
    members = packet.infolist()
    assert len(members) == 17 and all(not p.is_dir() and p.file_size < 700000 for p in members)
    hashes = {p.filename: dict(bytes=p.file_size, sha256=hashlib.sha256(packet.read(p)).hexdigest()) for p in members}
    suite = next(p for p in members if p.filename.endswith('/16-full-pytest-suite.log'))
    raw = packet.read(suite)
    log = raw.decode()
    summary = [line for line in log.splitlines() if line.startswith('FAILED tests/test_worker_build.py')]
    assert len(summary) == 6 and '6 failed, 4540 passed, 113 skipped' in log
    assert log.count('os.environ.get("PYTHONDONTWRITEBYTECODE") != "1"') >= 6
    events = next(p for p in members if p.filename.endswith('/events.jsonl'))
    (root / '0038-ci38381619194-events.jsonl').write_bytes(packet.read(events))
    result = dict(run=38381619194, head='7498a73f881ea23fdf10d81b4796c3e721e75eba', conclusion='failure',
                  archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(), members=hashes,
                  failed=summary, failed_count=6, passed=4540, skipped=113,
                  corrective_fixture='local RED6 -> GREEN7; missing-marker negative preserved',
                  native_originless_gap='separate unresolved compatibility issue',
                  image_or_production_certificate=False)
    (root / '0038-ci38381619194-artifact-audit.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({key:result[key] for key in ('run','conclusion','failed_count','passed','skipped','failed')}))
