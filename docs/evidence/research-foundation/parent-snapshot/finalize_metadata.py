"""Seal a metadata-only dead-variable cleanup; tested runtime bytes stay exact."""
import hashlib,json
from run_checks import FILES,OUT,ROOT,measure

def sha(raw):return hashlib.sha256(raw).hexdigest()
hashes=json.loads((OUT/'source-hashes.json').read_text())['files']
for name in FILES:assert sha((ROOT/name).read_bytes())==hashes[name]['sha256']
index=json.loads((OUT/'SHA256.json').read_text())
for name,record in index.items():
    if name!='seal_handoff.py':
        raw=(OUT/name).read_bytes();assert len(raw)==record['bytes'] and sha(raw)==record['sha256']
# Only an unused, unconsumed temporary dict was removed from the packing script.
# Runtime/tests/raw stdout/exit/resource/source packet bytes are untouched.
for name in ('seal_handoff.py','finalize_metadata.py'):
    raw=(OUT/name).read_bytes();index[name]={'bytes':len(raw),'sha256':sha(raw)}
(OUT/'SHA256.json').write_text(json.dumps(index,separators=(',',':'))+'\n')
assert measure()['scope_upper']<=600000
print(json.dumps(dict(resources=measure(),seal_sha256=sha((OUT/'SHA256.json').read_bytes()))))
