"""Bounded nonroot official OCI bytes only. No Docker mutation/execution."""
import hashlib
import json
import os
import re
import shutil
import signal
import ssl
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

MANIFEST = '2ed6491b93cd49272ee6de2b5a38440c3448360322c089fc23e370722d74179d'
CONFIG = '4f228bc1cbcfc794e4878312cfc241d368eff55a21c08d1e2bb263116c4ef524'
LAYERS = [
    ('7fd1ebe418b5079d4aa36f416af9b143d127bc75b0155d71cb5fd559b5e04d39',28249323),
    ('6e0ba8ba048777f5354b5a7cb497ae5261116fac8246160c06fc045c8300c582',3342298),
    ('86a9e13e035d8e44ae37bfebc52c7fc68898fde19b4b26dd0585f2231fcfaf2c',15966608),
    ('f9d2fb07d6f062d06ddc7aa58191cc5359c728f54af6cebe69a37d2c89e72a0d',249),
]
nonce = uuid.uuid4().hex
root = Path('/home/ubuntu') / ('quantmesh-numeric-materialization-' + nonce)
result = dict(scope='actual official OCI bytes only/nonroot/no Docker effects',nonce=nonce,root=str(root),
              docker_mutation=False,container_started=False,numerical_certificate=False,
              production_services_enabled=False,full_option_A_complete=False,artifacts=[])
phase = 'preflight'
created = False
free_before = None
started = time.monotonic()
watchdog_fixture = sys.argv[1:] == ['--watchdog-counterexample']
require_argv = sys.argv[1:] in ([], ['--watchdog-counterexample'])
wall_limit = 2 if watchdog_fixture else 180
deadline = started + wall_limit


def require(value, tag):
    if not value:
        raise ValueError(tag)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
    urllib.request.HTTPSHandler(context=ssl.create_default_context()),NoRedirect())


def bounded_host(host):
    # Only the registry and its Docker/CDN HTTPS blob hosts may receive requests.
    # The bearer token is removed before following any redirect.
    return host in ('auth.docker.io', 'registry-1.docker.io',
                    'production.cloudflare.docker.com', 'production.cloudfront.docker.com') or bool(
        re.fullmatch(r'docker-images-prod\.[0-9a-f]{32}\.r2\.cloudflarestorage\.com',host))


def fetch(url, *, headers=None, limit, destination=None, expected_size=None, expected_sha=None):
    # Follow only HTTPS vendor-returned public blob redirects. Rebuild the
    # request without Authorization on each redirect; no credentials/config
    # discovery, no URL/body/header/error echo or external private payload.
    current = url
    request_headers = dict(headers or {})
    response = None
    for hop in range(6):
        parsed = urllib.parse.urlsplit(current)
        require(parsed.scheme == 'https' and parsed.hostname and bounded_host(parsed.hostname)
                and parsed.port in (None,443) and not parsed.username and not parsed.password,
                'https_destination')
        remaining = deadline - time.monotonic()
        require(remaining > 0, 'download_deadline')
        request = urllib.request.Request(current, headers=request_headers)
        try:
            response = opener.open(request, timeout=min(10,remaining))
            break
        except urllib.error.HTTPError as error:
            if error.code not in (301,302,303,307,308):
                error.close()
                raise ValueError('HTTP_refusal') from None
            location = error.headers.get('Location')
            error.close()
            require(location and hop < 5, 'redirect_bound')
            current = urllib.parse.urljoin(current, location)
            request_headers = {k:v for k,v in request_headers.items() if k.lower() != 'authorization'}
    require(response is not None, 'response_required')
    count = 0
    digest = hashlib.sha256()
    memory = bytearray() if destination is None else None
    handle = destination.open('xb') if destination is not None else None
    try:
        with response:
            require(response.status == 200, 'response_status')
            while True:
                require(time.monotonic() < deadline, 'download_deadline')
                chunk = response.read(min(65536, limit-count+1))
                if not chunk:
                    break
                count += len(chunk)
                require(count <= limit, 'download_byte_bound')
                digest.update(chunk)
                if handle is not None:
                    handle.write(chunk)
                else:
                    memory.extend(chunk)
                if free_before is not None:
                    free = shutil.disk_usage('/').free
                    require(free_before-free <= 500000000 and free >= 50000000000, 'disk_bound')
            require(time.monotonic() < deadline, 'download_deadline')
    finally:
        response.close()
        if handle is not None:
            handle.close()
    require(expected_size is None or count == expected_size, 'exact_blob_size')
    require(expected_sha is None or digest.hexdigest() == expected_sha, 'exact_blob_hash')
    return bytes(memory) if memory is not None else dict(bytes=count,sha256=digest.hexdigest())


def failure(error, phase):
    result.update(exit=1,failure=dict(phase=phase,kind=type(error).__name__),retained_partial_content=True)
    if type(error) is ValueError and re.fullmatch(r'[A-Za-z_0-9]{1,64}',str(error)):
        result['failure']['reason']=str(error)


def download():
    global phase
    try:
        if watchdog_fixture:
            signal.pause()  # Actual owned stuck-worker counterexample, no network.
        phase = 'official_anonymous_registry_token'
        token_body = fetch('https://auth.docker.io/token?service=registry.docker.io&scope=repository%3Alibrary%2Fpython%3Apull',limit=32768)
        token = json.loads(token_body)['token']
        require(type(token) is str and len(token)<16000 and '\r' not in token and '\n' not in token,'bounded_token')
        # Public repository read token stays only in memory, never file/argv/log.
        auth = {'Authorization':'Bearer '+token}
        phase = 'pinned_manifest'
        manifest_path = root/'blobs'/MANIFEST
        receipt = fetch('https://registry-1.docker.io/v2/library/python/manifests/sha256:'+MANIFEST,
                        headers=dict(auth,Accept='application/vnd.oci.image.manifest.v1+json'),
                        limit=65536,destination=manifest_path,expected_sha=MANIFEST)
        manifest = json.loads(manifest_path.read_bytes())
        require(manifest['schemaVersion']==2 and manifest['config']['digest']=='sha256:'+CONFIG,
                'manifest_config_binding')
        require([(x['digest'],x['size']) for x in manifest['layers']]==[('sha256:'+d,s) for d,s in LAYERS],
                'manifest_layer_binding')
        result['artifacts'].append(dict(kind='manifest',**receipt))
        phase = 'pinned_configuration'
        config_path = root/'blobs'/CONFIG
        receipt = fetch('https://registry-1.docker.io/v2/library/python/blobs/sha256:'+CONFIG,
                        headers=auth,limit=65536,destination=config_path,
                        expected_size=manifest['config']['size'],expected_sha=CONFIG)
        config = json.loads(config_path.read_bytes())
        require(config['architecture']=='amd64' and config['os']=='linux'
                and 'PYTHON_VERSION=3.12.15' in config['config']['Env']
                and len(config['rootfs']['diff_ids'])==4,'config_profile')
        result['artifacts'].append(dict(kind='config',**receipt))
        for index,(digest,size) in enumerate(LAYERS):
            phase = 'pinned_layer_'+str(index)
            receipt = fetch('https://registry-1.docker.io/v2/library/python/blobs/sha256:'+digest,
                            headers=auth,limit=size,destination=root/'blobs'/digest,
                            expected_size=size,expected_sha=digest)
            result['artifacts'].append(dict(kind='layer',index=index,**receipt))
        result.update(exit=0,actual_blob_bytes=sum(a['bytes'] for a in result['artifacts']),
                      actual_manifest_sha256=MANIFEST,actual_config_sha256=CONFIG,
                      rootfs_diff_ids=config['rootfs']['diff_ids'],source_python_version='3.12.15',
                      actual_Engine_image_qualified=False,actual_runtime_notices_qualified=False)
    except BaseException as error:
        failure(error,phase)
    (root/'worker-result.json').write_text(json.dumps(result)+'\n')


child = None
pidfd = None
reaped = False
try:
    require(require_argv,'fixed_argv')
    require(signal.getsignal(signal.SIGCHLD) == signal.SIG_DFL,'sole_child_reaper')
    os.umask(0o077)
    require(os.getuid() != 0 and root.parent.resolve() == root.parent, 'nonroot_canonical_parent')
    previous = Path('/home/ubuntu/quantmesh-pg-tls-qualification-576db8859b72410b8fe8895845b2ae6e')
    require(previous.resolve() == previous and previous.stat().st_uid == os.getuid(), 'actual_host_witness')
    previous_after = json.loads((previous/'after-receipt.json').read_text())
    require(previous_after['own_live_postmasters'] == [] and previous_after['protocol_exit'] == 0,
            'owned_PG_prerequisite')
    require(not root.exists() and not root.is_symlink(), 'new_root')
    root.mkdir(mode=0o700)
    created = True
    require(root.resolve() == root and root.stat().st_uid == os.getuid()
            and stat.S_IMODE(root.stat().st_mode) == 0o700, 'owned_root')
    free_before = shutil.disk_usage('/').free
    require(free_before >= 50500000000, 'disk_reservation')
    owner = dict(nonce=nonce,uid=os.getuid(),root=str(root),free_before=free_before,
                 phase1_introduced_limit=500000000,whole_materialization_introduced_limit=5000000000,
                 host_free_floor=50000000000,manifest_sha256=MANIFEST,config_sha256=CONFIG,
                 previous_PG_introduced_bytes=831553536)
    (root/'ownership.json').write_text(json.dumps(owner,indent=2)+'\n')
    (root/'blobs').mkdir(mode=0o700)
    phase = 'owned_download_worker'
    child = os.fork()
    if child == 0:
        try:
            download()
        finally:
            os._exit(0)
    # The parent alone owns/reaps this direct nonroot child. A pidfd prevents
    # PID reuse during timeout cancellation. No child/daemon/privileged work.
    pidfd = os.pidfd_open(child)
    while True:
        ended,status = os.waitpid(child,os.WNOHANG)
        if ended:
            reaped = True
            require(os.waitstatus_to_exitcode(status)==0,'download_worker_exit')
            receipt=root/'worker-result.json'
            require(receipt.is_file() and not receipt.is_symlink() and receipt.stat().st_size<=16384,'worker_receipt')
            result=json.loads(receipt.read_bytes())
            break
        require(time.monotonic()<deadline,'download_watchdog')
        free=shutil.disk_usage('/').free
        require(free_before-free<=500000000 and free>=50000000000,'disk_bound')
        time.sleep(min(0.05,max(0,deadline-time.monotonic())))
except BaseException as error:
    failure(error,phase)
finally:
    # After a fork but failed pidfd capture, this is still the sole unreaped
    # direct child under default SIGCHLD; waitpid proves ownership before kill.
    if child and not reaped:
        ended,status=os.waitpid(child,os.WNOHANG)
        if ended:
            reaped=True
        else:
            if pidfd is not None:
                signal.pidfd_send_signal(pidfd,signal.SIGKILL)
            else:
                os.kill(child,signal.SIGKILL)
            stop_deadline=time.monotonic()+5
            while time.monotonic()<stop_deadline:
                ended,status=os.waitpid(child,os.WNOHANG)
                if ended:
                    reaped=True
                    break
                time.sleep(0.05)
    if pidfd is not None:
        os.close(pidfd)
    result.update(download_worker_reaped=reaped,watchdog_counterexample=watchdog_fixture,
                  watchdog_seconds=wall_limit,stop_reap_budget_seconds=5)
    if not reaped and child:
        result['exit']=1
        result['worker_quiescence']='NOT_PROVEN'
    if created:
        require(root.resolve()==root and root.stat().st_uid==os.getuid()
                and stat.S_IMODE(root.stat().st_mode)==0o700,'receipt_ownership')
        free=shutil.disk_usage('/').free
        result.update(host_free_bytes=free,actual_host_introduced_bytes=free_before-free if free_before else None,
                      raw_files=[dict(name=p.name,bytes=p.stat().st_size) for p in (root/'blobs').glob('*')] if (root/'blobs').exists() else [],
                      elapsed_seconds=round(time.monotonic()-started,3),
                      at_utc=datetime.now(timezone.utc).isoformat())
        (root/'blob-intake-receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)
raise SystemExit(result['exit'])
