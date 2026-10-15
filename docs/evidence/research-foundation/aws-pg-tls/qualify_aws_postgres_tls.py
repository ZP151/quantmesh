"""One new owned loopback fixture, real TLS/SCRAM/role negatives; no service."""
import hashlib
import json
import os
import re
import secrets
import shutil
import signal
import socket
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('/home/ubuntu/quantmesh-pg-tls-qualification-576db8859b72410b8fe8895845b2ae6e')
NONCE = '576db8859b72410b8fe8895845b2ae6e'
SOURCE = '555610c24d53e4316da5b7d3fc25c279d96856d5e0e23ee308c328c5fa881d9f'
BINARIES = {
    'postgres': '0e73b9e4352c9455be2b363fdbb0087010174fdb9eef09a9a4eb995a0cc93e5d',
    'initdb': '04d8558acde1312384cc2a82af4f70922967b508be2ca74bc1d8cda9fc1bbd17',
    'pg_controldata': '03c12790df238bcbcad1e15da302c139df0af9e7b33d1d1ed31e4d82f3ad85f6',
    'psql': '69a9a6da69b809fe031e9f6c60ec441d2c25c6d4b2bf7a9f8f2e31ca784246f1',
}
PREFIX = ROOT / 'prefix'
capture_failure_fixture = sys.argv[1:] == ['--capture-failure-fixture']
FIXTURE = ROOT / ('protocol-capture-failure' if capture_failure_fixture else 'protocol')
DATA = FIXTURE / 'data'
OWNER = 'qm_fixture_owner'
APP = 'qm_fixture_app'
OTHER = 'qm_fixture_other'
result = {'scope': 'owned disposable PG18.6 TLS/SCRAM/roles protocol only',
          'nonce': NONCE, 'root': str(ROOT), 'checks': [],
          'production_services_enabled': False, 'service_store_qualified': False,
          'actual_reports_restored': False, 'numerical_certificate': False}
process = None
pidfd = None
identity = None
fixture_created_here = False
phase = 'preflight'
spawn_parent = None
spawn_args = None


def digest(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def require(condition, tag):
    if not condition:
        raise ValueError(tag)


def owned_directory(path, mode=None):
    info = path.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
            and path.resolve() == path, 'owned_directory')
    if mode is not None:
        require(stat.S_IMODE(info.st_mode) == mode, 'directory_mode')


def binary(name):
    path = PREFIX / 'bin' / name
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
            and path.resolve() == path and digest(path) == BINARIES[name], 'binary_hash')
    return str(path)


def private_file(path, text):
    with path.open('x', encoding='ascii') as handle:
        os.chmod(path, 0o600)
        handle.write(text)


def execute(argv, *, stdin=None, environment=None, timeout=20):
    # Never retain raw stdout/stderr from a command carrying SQL/private material.
    return subprocess.run(argv, input=stdin, env=environment or env, cwd=FIXTURE,
                          capture_output=True, text=True, timeout=timeout, check=False)


def command(argv, *, stdin=None, timeout=20):
    response = execute(argv, stdin=stdin, timeout=timeout)
    require(response.returncode == 0, 'command_exit')
    return response.stdout


def current_identity(expected, *, require_ready=True):
    if process is None or process.poll() is not None:
        raise ValueError('postmaster_not_live')
    pid = process.pid
    proc = Path('/proc') / str(pid)
    start = (proc / 'stat').read_text().rsplit(')', 1)[1].split()[19]
    executable = Path(os.readlink(proc / 'exe'))
    require(pid == expected['pid'] and start == expected['start_ticks']
            and expected['data'] == str(DATA), 'pid_identity')
    require(executable == PREFIX / 'bin/postgres'
            and digest(executable) == BINARIES['postgres'], 'process_executable')
    require((proc / 'cmdline').read_bytes().split(b'\0')[:-1]
            == [str(executable).encode(), b'-D', str(DATA).encode()], 'process_argv')
    if require_ready:
        lines = (DATA / 'postmaster.pid').read_text().splitlines()
        require(len(lines) >= 8 and lines[0] == str(pid)
                and lines[1] == str(DATA) and lines[3] == str(port)
                and lines[5] == '127.0.0.1' and lines[7].strip() == 'ready', 'postmaster_identity')
    control = execute([binary('pg_controldata'), str(DATA)])
    require(control.returncode == 0
            and re.search(r'Database system identifier:\s*(\d+)', control.stdout).group(1)
            == expected['system_identifier'], 'system_identifier')
    owned_directory(DATA, 0o700)
    if require_ready:
        require((FIXTURE / 'server.log').stat().st_size < 4194304, 'server_log_bound')
        require(owner['free_before'] - shutil.disk_usage('/').free <= 5000000000
                and shutil.disk_usage('/').free >= 50000000000, 'resource_bound')


def sql(statement, *, role=OWNER, password_file='owner.pgpass', host='localhost',
        ca='ca.crt', sslmode='verify-full', success=True, error_pattern=None):
    current_identity(identity)
    client_env = dict(env, PGHOST=host, PGHOSTADDR='127.0.0.1', PGPORT=str(port),
                      PGDATABASE='postgres', PGUSER=role, PGSSLMODE=sslmode,
                      PGSSLROOTCERT=str(FIXTURE / ca),
                      PGPASSFILE=str(FIXTURE / password_file), PGCONNECT_TIMEOUT='5',
                      PGSSLCERT=str(FIXTURE / 'absent-client.crt'),
                      PGSSLKEY=str(FIXTURE / 'absent-client.key'))
    response = execute([binary('psql'), '-X', '-w', '-A', '-t', '-F', '|',
                        '--set=ON_ERROR_STOP=1'], stdin=statement, environment=client_env)
    current_identity(identity)
    require((response.returncode == 0) == success, 'protocol_exit')
    if error_pattern is not None:
        require(re.search(error_pattern, response.stderr, re.IGNORECASE) is not None,
                'expected_refusal_reason')
    return response.stdout.strip()


def check(name, value=None):
    result['checks'].append({'name': name, 'exit': 0, 'observed': value})
    print(json.dumps({'phase': name, 'exit': 0}), flush=True)


try:
    os.umask(0o077)
    require(os.getuid() != 0, 'non_root')
    require(sys.argv[1:] in ([], ['--capture-failure-fixture']), 'fixed_arguments')
    require(signal.getsignal(signal.SIGCHLD) == signal.SIG_DFL, 'no_child_reaper')
    require(hasattr(os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal'), 'pidfd_available')
    preflight_pidfd = os.pidfd_open(os.getpid())
    os.close(preflight_pidfd)
    owned_directory(ROOT, 0o700)
    owner = json.loads((ROOT / 'ownership.json').read_text())
    require(owner['nonce'] == NONCE and owner['uid'] == os.getuid()
            and owner['source_sha256'] == SOURCE, 'owner_binding')
    require(digest(ROOT / 'postgresql-18.6.tar.bz2') == SOURCE, 'source_hash')
    build = json.loads((ROOT / 'build-receipt.json').read_text())
    require(build['nonce'] == NONCE and build['version'] == 'postgres (PostgreSQL) 18.6'
            and all(build['binaries'][name] == value for name, value in BINARIES.items()),
            'build_binding')
    for name in BINARIES:
        binary(name)
    require(not FIXTURE.exists() and not FIXTURE.is_symlink(), 'new_fixture_only')
    FIXTURE.mkdir(mode=0o700)
    fixture_created_here = True
    (FIXTURE / 'home').mkdir(mode=0o700)
    (FIXTURE / 'socket').mkdir(mode=0o700)
    env = {'PATH': '/usr/bin:/bin', 'HOME': str(FIXTURE / 'home'), 'LANG': 'C', 'LC_ALL': 'C'}
    phase = 'private_tls_material'
    for ca_name in ('ca', 'wrong-ca'):
        command(['/usr/bin/openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                 '-days', '2', '-sha256', '-keyout', str(FIXTURE / (ca_name + '.key')),
                 '-out', str(FIXTURE / (ca_name + '.crt')),
                 '-subj', '/CN=QuantMesh disposable ' + ca_name,
                 '-addext', 'basicConstraints=critical,CA:TRUE',
                 '-addext', 'keyUsage=critical,keyCertSign,cRLSign'])
    command(['/usr/bin/openssl', 'req', '-newkey', 'rsa:2048', '-nodes', '-sha256',
             '-keyout', str(FIXTURE / 'server.key'), '-out', str(FIXTURE / 'server.csr'),
             '-subj', '/CN=localhost'])
    private_file(FIXTURE / 'server.ext', 'subjectAltName=DNS:localhost,IP:127.0.0.1\n'
                 'basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\n'
                 'extendedKeyUsage=serverAuth\n')
    command(['/usr/bin/openssl', 'x509', '-req', '-days', '2', '-sha256',
             '-in', str(FIXTURE / 'server.csr'), '-CA', str(FIXTURE / 'ca.crt'),
             '-CAkey', str(FIXTURE / 'ca.key'), '-CAcreateserial',
             '-extfile', str(FIXTURE / 'server.ext'), '-out', str(FIXTURE / 'server.crt')])
    passwords = {role: secrets.token_hex(32) for role in (OWNER, APP, OTHER)}
    private_file(FIXTURE / 'owner.password', passwords[OWNER] + '\n')
    phase = 'new_cluster_initialization'
    command([binary('initdb'), '-D', str(DATA), '--username=' + OWNER,
             '--auth=scram-sha-256', '--encoding=UTF8', '--locale=C',
             '--pwfile=' + str(FIXTURE / 'owner.password')], timeout=40)
    owned_directory(DATA, 0o700)
    control = command([binary('pg_controldata'), str(DATA)])
    system_identifier = re.search(r'Database system identifier:\s*(\d+)', control).group(1)
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    require(port > 1024, 'private_port')
    for role, filename in ((OWNER, 'owner.pgpass'), (APP, 'app.pgpass'), (OTHER, 'other.pgpass')):
        private_file(FIXTURE / filename, '*:' + str(port) + ':postgres:' + role + ':' + passwords[role] + '\n')
    private_file(FIXTURE / 'wrong.pgpass', '*:' + str(port) + ':postgres:' + APP + ':' + secrets.token_hex(32) + '\n')
    private_file(FIXTURE / 'missing.pgpass', '')
    configuration = "listen_addresses='127.0.0.1'\nport=" + str(port) + "\n"
    configuration += "unix_socket_directories='" + str(FIXTURE / 'socket') + "'\n"
    configuration += "ssl=on\nssl_min_protocol_version='TLSv1.2'\n"
    configuration += "ssl_cert_file='" + str(FIXTURE / 'server.crt') + "'\n"
    configuration += "ssl_key_file='" + str(FIXTURE / 'server.key') + "'\n"
    configuration += "password_encryption='scram-sha-256'\nmax_connections=12\nshared_buffers='32MB'\n"
    configuration += "logging_collector=off\nlog_statement='none'\nlog_min_error_statement='panic'\n"
    configuration += "log_connections=off\nlog_disconnections=off\n"
    (DATA / 'postgresql.conf').write_text(configuration)
    (DATA / 'pg_hba.conf').write_text('local all all reject\n'
                                     'hostnossl all all 127.0.0.1/32 reject\n'
                                     'hostssl all all 127.0.0.1/32 scram-sha-256\n')
    phase = 'owned_postmaster_start'
    spawn_parent = os.getpid()
    spawn_args = [binary('postgres'), '-D', str(DATA)]
    with (FIXTURE / 'server.log').open('xb') as server_log:
        process = subprocess.Popen(spawn_args, env=env,
                                   cwd=FIXTURE, stdout=server_log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
    if capture_failure_fixture:
        phase = 'forced_ownership_capture_failure'
        raise ValueError('capture_failure_fixture')
    pidfd = os.pidfd_open(process.pid)
    start_ticks = (Path('/proc') / str(process.pid) / 'stat').read_text().rsplit(')', 1)[1].split()[19]
    identity = {'pid': process.pid, 'start_ticks': start_ticks, 'data': str(DATA),
                'system_identifier': system_identifier}
    deadline = time.monotonic() + 15
    while True:
        require(process.poll() is None, 'postmaster_early_exit')
        if (DATA / 'postmaster.pid').exists():
            rows = (DATA / 'postmaster.pid').read_text().splitlines()
            if len(rows) >= 8 and rows[7].strip() == 'ready':
                break
        require(time.monotonic() < deadline, 'startup_bound')
        time.sleep(0.1)
    current_identity(identity)
    result['identity'] = identity
    result['port'] = port
    # Identity mismatches must refuse before SQL or signalling. Actual live process remains untouched.
    for name, replacement in (('start_ticks', str(int(start_ticks) + 1)),
                              ('data', str(FIXTURE / 'foreign-data'))):
        rejected = False
        try:
            current_identity(dict(identity, **{name: replacement}))
        except ValueError:
            rejected = True
        require(rejected, 'identity_negative')
        current_identity(identity)
        check('refuse_wrong_' + name)
    phase = 'TLS_and_roles'
    positive = sql('SELECT current_user, ssl, version, bits FROM pg_stat_ssl WHERE pid=pg_backend_pid();\n')
    parts = positive.split('|')
    require(len(parts) == 4 and parts[0] == OWNER and parts[1] == 't'
            and parts[2] in ('TLSv1.2', 'TLSv1.3') and int(parts[3]) >= 128, 'actual_tls')
    require(sql('SELECT system_identifier FROM pg_control_system();\n') == system_identifier,
            'sql_system_identifier')
    check('verify_full_owner_TLS', {'protocol': parts[2], 'bits': int(parts[3]), 'ssl': True})
    for role in (APP, OTHER):
        require(re.fullmatch(r'[0-9a-f]{64}', passwords[role]) is not None, 'password_format')
        sql('CREATE ROLE ' + role + " LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD '"
            + passwords[role] + "';\n")
    sql('REVOKE CREATE ON SCHEMA public FROM PUBLIC;\n'
        'CREATE SCHEMA app AUTHORIZATION ' + OWNER + ';\n'
        'CREATE TABLE app.protocol_rows(id integer PRIMARY KEY, value text NOT NULL);\n'
        'GRANT USAGE ON SCHEMA app TO ' + APP + ';\n'
        'GRANT SELECT,INSERT,UPDATE,DELETE ON app.protocol_rows TO ' + APP + ';\n'
        'CREATE SCHEMA other AUTHORIZATION ' + OTHER + ';\n'
        'CREATE TABLE other.private_data(id integer);\n')
    attrs = sql("SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls,"
                "rolpassword LIKE 'SCRAM-SHA-256$%' FROM pg_authid WHERE rolname='" + APP + "';\n")
    require(attrs == 'f|f|f|f|f|t', 'dedicated_role_attributes')
    check('dedicated_app_SCRAM_least_privilege', attrs)
    app_tls = sql('SELECT current_user,ssl,version FROM pg_stat_ssl WHERE pid=pg_backend_pid();\n',
                  role=APP, password_file='app.pgpass')
    require(app_tls in (APP + '|t|TLSv1.2', APP + '|t|TLSv1.3'), 'app_tls')
    sql("INSERT INTO app.protocol_rows VALUES(1,'initial');\nUPDATE app.protocol_rows SET value='updated' WHERE id=1;\n",
        role=APP, password_file='app.pgpass')
    require(sql('SELECT id,value FROM app.protocol_rows;\n', role=APP, password_file='app.pgpass')
            == '1|updated', 'app_crud')
    sql('DELETE FROM app.protocol_rows;\n', role=APP, password_file='app.pgpass')
    check('dedicated_app_TLS_and_own_CRUD', {'role': APP, 'fixture_only': True})
    for name, overrides, reason in (
        ('wrong_CA', {'ca': 'wrong-ca.crt'}, r'certificate verify failed'),
        ('wrong_name', {'host': 'wrong-name.invalid'}, r'does not match host name'),
        ('plaintext', {'sslmode': 'disable'}, r'pg_hba.conf rejects connection.*no encryption'),
        ('missing_password', {'password_file': 'missing.pgpass'}, r'no password supplied'),
        ('wrong_password', {'password_file': 'wrong.pgpass'}, r'password authentication failed'),
    ):
        phase = 'reject_' + name
        sql('SELECT 1;\n', role=APP, password_file=overrides.pop('password_file', 'app.pgpass'),
            success=False, error_pattern=reason, **overrides)
        check('reject_' + name)
    for name, statement in (
        ('other_schema', 'SELECT * FROM other.private_data;'),
        ('owner_role', 'SET ROLE ' + OWNER + ';'),
        ('create_role', 'CREATE ROLE qm_fixture_forbidden;'),
        ('create_database', 'CREATE DATABASE qm_fixture_forbidden;'),
    ):
        phase = 'reject_' + name
        sql('\\set VERBOSITY verbose\n' + statement + '\n', role=APP,
            password_file='app.pgpass', success=False, error_pattern=r'42501')
        check('reject_' + name)
    phase = 'current_shared_providers'
    providers = {}
    for name in ('postgres', 'psql'):
        linked = command(['/usr/bin/ldd', binary(name)])
        require('not found' not in linked, 'shared_provider_missing')
        for candidate in re.findall(r'(?:=>\s*)?(/[^\s()]+)', linked):
            path = Path(candidate).resolve(strict=True)
            require(path.is_file(), 'shared_provider_file')
            providers[str(path)] = digest(path)
    require(any('libssl.so' in path for path in providers)
            and any('libcrypto.so' in path for path in providers)
            and any('libicu' in path for path in providers), 'actual_linked_features')
    result['shared_provider_sha256'] = providers
    result['binary_sha256'] = BINARIES
    result['public_certificate_sha256'] = {name: digest(FIXTURE / name)
                                            for name in ('ca.crt', 'server.crt', 'wrong-ca.crt')}
    for file in FIXTURE.iterdir():
        if file.suffix == '.key' or file.name.endswith(('.pgpass', '.password')):
            require(stat.S_IMODE(file.stat().st_mode) == 0o600, 'secret_mode')
    # Exercise the actual former cleanup blocker on this fixture's log only.
    # Acceptance must reject it, while ownership-only validation still permits
    # the verified pidfd stop. Never borrow another process to test cleanup.
    phase = 'owned_stop_after_log_bound'
    with (FIXTURE / 'server.log').open('ab') as log:
        log.write(b'fixture-cleanup-bound\n' * 200000)
    log_bound_rejected = False
    try:
        current_identity(identity)
    except ValueError as error:
        log_bound_rejected = str(error) == 'server_log_bound'
    require(log_bound_rejected, 'cleanup_counterexample')
    current_identity(identity, require_ready=False)
    check('ownership_stop_survives_rejected_log_bound')
    result['TLS_protocol_qualified'] = True
    result['SCRAM_role_protocol_qualified'] = True
    result['exit'] = 0
except BaseException as error:
    result['exit'] = 1
    result['failure'] = {'phase': phase, 'kind': type(error).__name__}
    if type(error) is ValueError and re.fullmatch(r'[a-z_]{1,64}', str(error)):
        result['failure']['reason'] = str(error)
finally:
    phase = 'verified_owned_stop'
    stopped = process is None
    if process is not None:
        if process.poll() is not None:
            stopped = True
        else:
            try:
                if identity is None:
                    # No SQL runs until capture completes. This direct, un-reaped
                    # Popen child cannot have its PID reused: no SIGCHLD reaper,
                    # threads or other waitpid path exists in this single script.
                    # A spawn/capture failure must not require ready/proc reads.
                    require(spawn_parent == os.getpid() and process.args == spawn_args
                            == [binary('postgres'), '-D', str(DATA)]
                            and signal.getsignal(signal.SIGCHLD) == signal.SIG_DFL,
                            'direct_child_ownership')
                    result['stop_identity'] = 'unreaped_direct_child_before_SQL'
                    process.send_signal(signal.SIGINT)
                else:
                    current_identity(identity, require_ready=False)
                    signal.pidfd_send_signal(pidfd, signal.SIGINT)
                    result['stop_identity'] = 'pidfd_start_exe_data_system_identifier'
                process.wait(timeout=15)
                stopped = True
            except BaseException as error:
                result['exit'] = 1
                result['stop_failure'] = {'kind': type(error).__name__, 'borrowed_kill': False}
    if pidfd is not None:
        os.close(pidfd)
    result['owned_postmaster_stopped'] = stopped
    if process is not None and stopped:
        result['postmaster_exit'] = process.returncode
        # Only inspect: never kill or connect to a different process that takes this port.
        with socket.socket() as final_socket:
            final_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                final_socket.bind(('127.0.0.1', port))
                result['owned_port_released'] = True
            except OSError:
                result['owned_port_released'] = False
                result['exit'] = 1
    result['at_utc'] = datetime.now(timezone.utc).isoformat()
    if fixture_created_here:
        result['introduced_host_filesystem_bytes'] = owner['free_before'] - shutil.disk_usage('/').free
        result['free_host_filesystem_bytes'] = shutil.disk_usage('/').free
    if fixture_created_here:
        owned_directory(ROOT, 0o700)
        owned_directory(FIXTURE, 0o700)
        private_file(FIXTURE / 'protocol-receipt.json', json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)
    raise SystemExit(result['exit'])
