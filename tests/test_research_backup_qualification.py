"""New backup boundary: refused authority and exact nonempty snapshot bytes."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import qualify_research_backup as backup


@pytest.mark.parametrize("field", ["dsn", "repository", "password", "command", "host", "port"])
def test_profile_never_accepts_borrowed_authority(field):
    with pytest.raises(ValueError):
        backup.Profile.from_mapping({field: "private-marker"})


@pytest.mark.parametrize("key", ["schema_version", "root", "expected_build"])
def test_profile_requires_exact_fields(key):
    raw = {"schema_version": 1, "root": "/var/tmp/borrowed", "expected_build": "a" * 40}
    raw.pop(key)
    with pytest.raises(ValueError):
        backup.Profile.from_mapping(raw)


def test_default_cli_preflight_has_no_database_repository_or_output(tmp_path, monkeypatch, capsys):
    profile = tmp_path / "profile.json"
    profile.write_text("{}")
    stub = SimpleNamespace(root=tmp_path, expected_build="a" * 40)
    monkeypatch.setattr(backup.Profile, "from_mapping", lambda raw: stub)

    def forbidden(*args, **kwargs):
        pytest.fail("preflight side effect")

    monkeypatch.setattr(backup, "run_fixture", forbidden)
    monkeypatch.setattr(backup, "admit_runtime", lambda p: {"actual_build": p.expected_build})
    output = tmp_path / "not-created"
    assert backup.main(["--profile", str(profile), "--output", str(output)]) == 0
    assert not output.exists()
    assert "private-marker" not in capsys.readouterr().out


@pytest.mark.parametrize("value", ["../escape", "/outside", "a/../../escape"])
def test_containment_rejects_escape(tmp_path, value):
    with pytest.raises(ValueError):
        backup.owned_path(tmp_path, Path(value))


def test_containment_rejects_existing_restore_target_and_links(tmp_path):
    existing = tmp_path / "restore"
    existing.mkdir()
    with pytest.raises(ValueError):
        backup.fresh_directory(tmp_path, existing)
    linked = tmp_path / "link"
    try:
        linked.symlink_to(existing, target_is_directory=True)
    except OSError:
        pytest.skip("symlink permission unavailable")
    with pytest.raises(ValueError):
        backup.owned_path(tmp_path, linked / "file")


def test_private_reader_refuses_links_hardlinks_modes(tmp_path):
    import os
    import sys

    if sys.platform != "linux":
        pytest.skip("native permission refusal")
    tmp_path.chmod(0o700)
    path = tmp_path / "file"
    backup.write_private(path, b"data")
    assert backup.read_owned(tmp_path, path) == b"data"
    path.chmod(0o644)
    with pytest.raises(ValueError):
        backup.read_owned(tmp_path, path)
    path.chmod(0o600)
    os.link(path, tmp_path / "second")
    with pytest.raises(ValueError):
        backup.read_owned(tmp_path, path)


@pytest.fixture
def bundle(tmp_path):
    root = tmp_path / "payload"
    root.mkdir(mode=0o700)
    backup.write_private(root / "research.dump", b"bounded-dump")
    artifact = b'{"fixture":true}'
    sha = hashlib.sha256(artifact).hexdigest()
    (root / "artifacts" / "job").mkdir(parents=True, mode=0o700)
    (root / "artifacts").chmod(0o700)
    backup.write_private(root / "artifacts" / "job" / f"{sha}.json", artifact)
    manifest = {
        "schema_version": 1,
        "schema_digest": backup.SCHEMA,
        "protocol_digest": backup.PROTOCOL,
        "research_schema": "qm_research",
        "dump_sha256": hashlib.sha256(b"bounded-dump").hexdigest(),
        "dump_size": 12,
        "state": {"versions": [[1]], "jobs": [["job"]], "outbox": [], "effects": []},
        "artifacts": [
            {
                "job_id": "job",
                "object_key": f"job/{sha}.json",
                "sha256": sha,
                "byte_size": len(artifact),
            }
        ],
    }
    backup.write_private(root / "manifest.json", backup.canonical(manifest))
    return root, manifest, backup.digest(root / "manifest.json")


def test_exact_nonempty_manifest_and_bytes_validate(bundle):
    root, manifest, anchor = bundle
    assert backup.validate_bundle(root, anchor) == manifest


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "substitution",
        "manifest",
        "schema",
        "protocol",
        "empty",
        "ownership",
        "dump",
        "extra",
    ],
)
def test_incomplete_or_changed_bundle_cannot_publish_receipt(bundle, mutation):
    root, manifest, anchor = bundle
    ref = manifest["artifacts"][0]
    path = root / "artifacts" / ref["object_key"]
    if mutation == "missing":
        path.unlink()
    elif mutation == "substitution":
        path.write_bytes(b"substituted")
    elif mutation == "dump":
        (root / "research.dump").write_bytes(b"different")
    elif mutation == "manifest":
        (root / "manifest.json").write_bytes(b"{}")
    elif mutation == "extra":
        backup.write_private(root / "artifacts" / "extra", b"not-referenced")
    else:
        if mutation == "schema":
            manifest["state"]["versions"] = [[999]]
        elif mutation == "protocol":
            manifest["protocol_digest"] = "0" * 64
        elif mutation == "empty":
            manifest["artifacts"] = []
        elif mutation == "ownership":
            ref["job_id"] = "other-job"
        (root / "manifest.json").write_bytes(backup.canonical(manifest))
        anchor = backup.digest(root / "manifest.json")
    with pytest.raises(ValueError):
        backup.validate_bundle(root, anchor)


def test_receipt_requires_actual_encrypted_snapshot_and_checked_bundle(bundle):
    root, _, anchor = bundle
    with pytest.raises(ValueError):
        backup.backup_receipt(root, anchor, {"snapshot_id": ""})
    with pytest.raises(ValueError):
        backup.backup_receipt(root, anchor, {"snapshot_id": "a" * 64, "check_exit": 1})


def test_wrong_signing_notice_or_tool_pin_is_not_an_admitted_tool(tmp_path):
    for name in ["restic", "prefix", "audit"]:
        (tmp_path / name).mkdir()
    with pytest.raises(ValueError):
        backup.admit_tools(tmp_path)


def test_cli_refusal_scrubs_configuration(tmp_path, capsys):
    path = tmp_path / "profile.json"
    path.write_text(json.dumps({"dsn": "private-marker"}))
    assert backup.main(["--profile", str(path), "--output", str(tmp_path / "out")]) == 2
    assert "private-marker" not in capsys.readouterr().out


def test_command_output_bound_does_not_limit_owned_database_files(tmp_path):
    import sys

    if sys.platform != "linux":
        pytest.skip("native bounded subprocess")
    data = tmp_path / "wal"
    program = "import pathlib; pathlib.Path('wal').write_bytes(b'x' * 16777216); print('ok')"
    code, raw = backup.bounded_process([sys.executable, "-c", program], {}, tmp_path, 10)
    assert code == 0 and raw == b"ok\n"
    assert data.stat().st_size == 16777216


def test_bounded_command_refuses_output_flood_and_timeout(tmp_path):
    import sys

    if sys.platform != "linux":
        pytest.skip("native bounded subprocess")
    for program, deadline in [
        ("import time; time.sleep(2)", 0.05),
        ("import os; os.write(1,b'x'*3000000)", 5),
    ]:
        with pytest.raises(ValueError):
            backup.bounded_process([sys.executable, "-c", program], {}, tmp_path, deadline)


def test_only_new_corrupt_copy_is_made_writable(tmp_path):
    import sys

    if sys.platform != "linux":
        pytest.skip("native encrypted pack permissions")
    repo = tmp_path / "repository"
    (repo / "data" / "ab").mkdir(parents=True)
    pack = repo / "data" / "ab" / ("a" * 64)
    pack.write_bytes(b"ciphertext")
    pack.chmod(0o444)
    before = pack.read_bytes()
    clone, changed = backup.corrupt_copy(tmp_path, repo)
    assert pack.read_bytes() == before and pack.stat().st_mode & 0o777 == 0o444
    assert (clone / changed).read_bytes() != before


def test_stale_pid_cannot_stop_an_owned_or_borrowed_process(tmp_path, monkeypatch):
    process = SimpleNamespace(
        pid=123456, poll=lambda: None, send_signal=lambda _: pytest.fail("unverified stop")
    )
    commands = SimpleNamespace(root=tmp_path)
    cluster = backup.Cluster(
        commands,
        tmp_path,
        tmp_path / "data",
        "fixture",
        "secret",
        "nonce",
        54321,
        process,
        "old-ticks",
    )
    monkeypatch.setattr(backup, "process_ticks", lambda pid: "different-ticks")
    with pytest.raises(ValueError):
        cluster.stop()


@pytest.mark.parametrize("error", [ValueError("pin"), OSError("file"), TimeoutError("wall")])
def test_infrastructure_failure_is_not_a_negative_witness(tmp_path, monkeypatch, error):
    source = SimpleNamespace()
    receipt = {"negative_witnesses": {}}
    monkeypatch.setattr(backup, "current_state", lambda source: {})

    def action():
        raise error

    with pytest.raises(type(error)):
        backup.expect_failure("wrong_key", action, receipt, source, {})
    assert receipt["negative_witnesses"] == {}


def test_expected_crypto_refusal_requires_exit_and_matching_tool_evidence():
    with pytest.raises(ValueError):
        backup.crypto_refusal("wrong_key", 12, b"unrelated error")
    with pytest.raises(ValueError):
        backup.crypto_refusal("wrong_key", 1, b"wrong password")
    with pytest.raises(backup.NegativeRefused):
        backup.crypto_refusal(
            "wrong_key",
            12,
            b'{"message_type":"exit_error","code":12,"message":"wrong password or no key found"}',
        )


def test_whole_fixture_deadline_covers_noncommand_work():
    import sys
    import time

    if sys.platform != "linux":
        pytest.skip("native owned process timer")
    guard = backup.FixtureDeadline(0.02)
    try:
        with pytest.raises(ValueError):
            time.sleep(0.2)
    finally:
        guard.close()


def test_server_log_is_drained_but_capped_without_limiting_data_files(tmp_path):
    import subprocess
    import sys

    if sys.platform != "linux":
        pytest.skip("native owned log pipe")
    process = subprocess.Popen(
        [sys.executable, "-c", "import os; os.write(1,b'x'*3000000)"], stdout=subprocess.PIPE
    )
    collector = backup.ServerLog(process.stdout, tmp_path / "server.log")
    assert process.wait(timeout=5) == 0
    collector.finish()
    assert collector.failed
    assert (tmp_path / "server.log").stat().st_size <= backup.MAX_OUTPUT


def test_refused_stop_still_removes_generated_pgpass(tmp_path, monkeypatch):
    backup.write_private(tmp_path / "pgpass", b"private-marker")
    process = SimpleNamespace(
        pid=123456, poll=lambda: None, send_signal=lambda _: pytest.fail("unverified stop")
    )
    cluster = backup.Cluster(
        SimpleNamespace(root=tmp_path),
        tmp_path,
        tmp_path / "data",
        "fixture",
        "secret",
        "nonce",
        54321,
        process,
        "old-ticks",
    )
    monkeypatch.setattr(backup, "process_ticks", lambda pid: "different-ticks")
    with pytest.raises(ValueError):
        cluster.stop()
    assert not (tmp_path / "pgpass").exists()


def test_failed_server_spawn_removes_generated_private_inputs(tmp_path, monkeypatch):
    import time

    def initdb(tool, argv):
        Path(argv[1]).mkdir()

    commands = SimpleNamespace(
        root=tmp_path, output=tmp_path, run=initdb, deadline=time.monotonic() + 10
    )

    def fail(*args, **kwargs):
        raise OSError("synthetic spawn refusal")

    monkeypatch.setattr(backup.subprocess, "Popen", fail)
    with pytest.raises(OSError):
        backup.Cluster.start(commands, "new-cluster")
    assert not (tmp_path / "new-cluster" / "pgpass").exists()
    assert not (tmp_path / "new-cluster" / "init-password").exists()
