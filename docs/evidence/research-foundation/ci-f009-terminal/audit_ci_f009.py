import hashlib,json,re,subprocess,zipfile
from pathlib import Path
import xml.etree.ElementTree as ET
out=Path('output'); run=38407671413; head='f0093aa6d7853ebad9f70f938fbfae7500b4e1b1'
checkout=json.loads((out/f'0038-ci{run}-checkout.json').read_bytes())
assert checkout['sha']=='dd4b22ceabcc7f2d6251546a653717feac8a5d5a'
assert {p['sha'] for p in checkout['parents']}=={head,'7da320f7d6c3ac81cd7cb92b691e0b969bbcba48'}
tree=subprocess.check_output(['git','rev-parse',head+'^{tree}'],text=True).strip()
assert tree==checkout['tree']['sha']
pr=json.loads((out/f'0038-ci{run}-pr.json').read_bytes())
assert pr['headRefOid']==head and pr['state']=='OPEN' and pr['isDraft']
required={'classify','fast','release','research_service','python'}
jobs=json.loads((out/f'0038-ci{run}-jobs.json').read_bytes())['jobs']
assert {j['name'] for j in jobs if j['conclusion']=='success'}==required
assert all(j['status']=='completed' and j['conclusion']=='success' for j in jobs if j['name'] in required)
review=json.loads((out/f'0038-ci{run}-reviews.json').read_bytes())['data']['repository']['pullRequest']
assert review['headRefOid']==head and not [x for x in review['reviewThreads']['nodes'] if not x['isResolved']]
log=(out/f'0038-ci{run}-success.log').read_text(encoding='utf-8-sig')
steps=[m.groups() for line in log.splitlines() if line.startswith('release\tCertify exact checkout\t') and (m:=re.search(r'\sPASS\s+([0-9.]+)s\s+(.+)$',line))]
assert len(steps)==18 and 'pytest: 4557 passed, 139 skipped' in log and '419 passed' in log and 'RELEASE GATE PASSED' in log
artifact=next(x for x in json.loads((out/f'0038-ci{run}-artifacts.json').read_bytes())['artifacts'] if x['name']=='research-service-offline-linux-cp312')
assert artifact['workflow_run']['head_sha']==head and not artifact['expired'] and artifact['size_in_bytes']<65536
dest=out/'0038-remote-service-cif0093aa';dest.mkdir(exist_ok=False)
with (dest/'artifact.zip').open('wb') as f:
    subprocess.run(['gh','api',f"repos/ZP151/quantmesh/actions/artifacts/{artifact['id']}/zip"],stdout=f,check=True)
assert 'sha256:'+hashlib.sha256((dest/'artifact.zip').read_bytes()).hexdigest()==artifact['digest']
hashes={}
with zipfile.ZipFile(dest/'artifact.zip') as z:
    assert len(z.namelist())==7 and len(set(z.namelist()))==7
    for name in z.namelist():
        assert '/' not in name and '\\' not in name and name.endswith(('.json','.xml','.log'))
        assert z.getinfo(name).file_size<65536
        data=z.read(name);(dest/name).write_bytes(data);hashes[name]=hashlib.sha256(data).hexdigest()
receipt=json.loads((dest/'service-gate.json').read_bytes())
assert receipt['profile']=='OFFLINE_SCRIPTED_ONLY' and receipt['postgres']=='pending' and receipt['exit']==0 and receipt['failures']==[]
assert receipt['tests']=={'tests':207,'failures':0,'errors':0,'skipped':5} and len(receipt['licenses'])==81
assert receipt['lock_sha256']==hashlib.sha256(Path('services/research_agent/requirements.linux-cp312.lock').read_bytes()).hexdigest()
assert all(c['exit']==0 for c in receipt['commands']) and len(receipt['commands'])==5
xml=next(p for p in dest.glob('pytest-*.xml')); suites=list(ET.parse(xml).getroot().iter('testsuite'))
assert sum(int(s.attrib['tests']) for s in suites)==207 and sum(int(s.attrib.get('skipped',0)) for s in suites)==5
assert all(int(s.attrib.get(k,0))==0 for s in suites for k in ('errors','failures'))
summary=dict(run=run,head=head,conclusion='success',actual_checkout=checkout['sha'],tree=tree,trees_match=True,
             required_jobs=sorted(required),release_steps=18,python_passed=4557,python_skipped=139,frontend_passed=419,
             service_passed=202,service_PG_skipped=5,locked_packages=81,service_profile='OFFLINE_SCRIPTED_ONLY',
             artifact_sha256=artifact['digest'],artifact_raw_sha256=hashes,actionable_reviews=0,
             production_deployed=False,actual_provider=False,numerical_certificate=False,full_option_A_complete=False)
(out/f'0038-ci{run}-verified-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k!='artifact_raw_sha256'}))
