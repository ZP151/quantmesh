"""Bootstrap boundaries; native cases run in the owned CPython 3.12 environment."""

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="native Linux bootstrap")


def runtime_module():
    # Missing bootstrap is an explicit RED assertion, not a collection error.
    assert importlib.util.find_spec("qm_research_agent.runtime") is not None
    return importlib.import_module("qm_research_agent.runtime")


@pytest.fixture
def owned(tmp_path):
    root = tmp_path / "owned"
    root.mkdir(mode=0o700)
    for name in ("lake", "artifacts", "credentials"):
        (root / name).mkdir(mode=0o700)
    data = {
        "operator_id": "operator",
        "expected_build": "a" * 40,
        "lake_root": str(root / "lake"),
        "artifact_root": str(root / "artifacts"),
        "credential_directory": str(root / "credentials"),
    }
    return root, data


def write_private(path, raw):
    path.write_bytes(raw)
    path.chmod(0o600)
    return path


def test_bootstrap_exists_and_default_has_no_dataset_discovery(owned):
    _, data = owned
    config = runtime_module().ServiceRuntimeConfig.model_validate(data)
    assert config.configured_dataset_ids == ()
    with pytest.raises(ValidationError):
        config.operator_id = "other"


@pytest.mark.parametrize(
    "update",
    [
        {"host": "0.0.0.0"},
        {"host": "localhost"},
        {"port": 8111},
        {"schema_version": 2},
        {"expected_build": "A" * 40},
        {"operator_id": "../operator"},
        {"model_endpoint": "https://invalid"},
        {"configured_dataset_ids": ["equities", "equities"]},
        {"configured_dataset_ids": ["../equities"]},
        {"lake_root": "relative"},
        {"port": True},
    ],
)
def test_config_rejects_authority_expansion(owned, update):
    _, data = owned
    with pytest.raises((ValidationError, ValueError)):
        runtime_module().ServiceRuntimeConfig.model_validate({**data, **update})


def test_roots_reject_link_missing_shared_and_overlap(owned):
    root, data = owned
    module = runtime_module()
    (root / "link").symlink_to(root / "lake", target_is_directory=True)
    for value in (root / "link", root / "missing", root):
        with pytest.raises(ValueError):
            module.ServiceRuntimeConfig.model_validate({**data, "lake_root": str(value)})
    (root / "lake").chmod(0o755)
    with pytest.raises(ValueError):
        module.ServiceRuntimeConfig.model_validate(data)


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql://fixture:password@127.0.0.1:55432/fixture?sslmode=disable",
        "postgresql://fixture:password@[::1]:55432/fixture?sslmode=disable",
        "postgresql://fixture:password@private.example/fixture",
        "postgresql://fixture:password@private.example/fixture?sslmode=verify-full",
    ],
)
def test_dsn_accepts_literal_local_or_verified_tls(dsn):
    assert runtime_module()._validate_dsn(dsn).get_secret_value() == dsn


@pytest.mark.parametrize(
    "suffix",
    [
        "@localhost/fixture?sslmode=disable",
        "@127.1/fixture?sslmode=disable",
        "@private.example/fixture?sslmode=disable",
        "@127.0.0.1/fixture?sslmode=require",
        "@127.0.0.1/fixture?sslmode=disable&sslmode=disable",
        "@127.0.0.1/fixture?sslmode=",
        "@127.0.0.1/fixture?options=anything",
        "@127.0.0.1/fixture#secret",
        "@127.0.0.1:bad/fixture",
        "@127.0.0.1/",
        "@127.0.0.1/fixture?sslmode=disable&",
    ],
)
def test_dsn_rejections_do_not_leak(suffix):
    with pytest.raises(ValueError) as error:
        runtime_module()._validate_dsn("postgresql://fixture:private-marker" + suffix)
    assert "private-marker" not in str(error.value)


def test_private_reader_refuses_links_fifo_devices_modes_size_and_hardlinks(owned):
    root, _ = owned
    module = runtime_module()
    directory = root / "credentials"
    good = write_private(directory / "good", b"private-marker")
    assert module._read_private(good, 32) == b"private-marker"
    (directory / "link").symlink_to(good)
    os.mkfifo(directory / "fifo", 0o600)
    (directory / "device").symlink_to("/dev/null")
    write_private(directory / "large", b"x" * 33)
    write_private(directory / "shared", b"private-marker").chmod(0o644)
    os.link(good, directory / "hardlink")
    for name in ("link", "fifo", "device", "large", "shared", "good", "hardlink", "absent"):
        with pytest.raises(ValueError) as error:
            module._read_private(directory / name, 32)
        assert "private-marker" not in str(error.value)
        assert str(root) not in str(error.value)


def test_private_reader_detects_replacement(owned, monkeypatch):
    root, _ = owned
    module = runtime_module()
    path = write_private(root / "credentials/api_token", b"private-marker")
    real_read = os.read
    replaced = False

    def replace_after_read(fd, count):
        nonlocal replaced
        raw = real_read(fd, count)
        if not replaced:
            replaced = True
            path.unlink()
            write_private(path, b"replacement-marker")
        return raw

    monkeypatch.setattr(os, "read", replace_after_read)
    with pytest.raises(ValueError):
        module._read_private(path, 64)


def test_load_requires_actual_admission_before_credentials(owned, monkeypatch):
    root, data = owned
    module = runtime_module()
    config = write_private(root / "config.json", json.dumps(data).encode())

    def reject(*args):
        raise module.RuntimeRejected("runtime_unqualified")

    monkeypatch.setattr(module, "_admit_runtime", reject)
    with pytest.raises(module.RuntimeRejected, match="runtime_unqualified"):
        module.load_runtime(config)


def test_load_uses_only_explicit_files_and_redacts_runtime(owned, monkeypatch):
    root, data = owned
    module = runtime_module()
    write_private(root / "credentials/api_token", b"fixture-private-marker-123456")
    write_private(
        root / "credentials/postgres_dsn",
        b"postgresql://fixture:private-password@127.0.0.1/fixture?sslmode=disable",
    )
    config = write_private(root / "config.json", json.dumps(data).encode())
    monkeypatch.setenv("POSTGRES_DSN", "private-ambient-marker")
    monkeypatch.setenv("QUANTMESH_MODEL_API_KEY", "private-ambient-marker")
    monkeypatch.setattr(module, "_admit_runtime", lambda expected: (expected, "b" * 64))
    result = module.load_runtime(config)
    assert result.api_token.get_secret_value() == "fixture-private-marker-123456"
    assert result.actual_build == "a" * 40
    rendered = repr(result) + json.dumps(result.preflight())
    assert "private-marker" not in rendered
    assert "private-password" not in rendered
    assert "ambient" not in rendered
    assert str(root) not in rendered
    with pytest.raises(Exception):
        result.actual_build = "b" * 40


def test_default_cli_preflight_never_builds_database_app_or_listener(owned, monkeypatch, capsys):
    root, data = owned
    module = runtime_module()
    write_private(root / "credentials/api_token", b"fixture-private-marker-123456")
    write_private(
        root / "credentials/postgres_dsn",
        b"postgresql://fixture:password@127.0.0.1/fixture?sslmode=disable",
    )
    config = write_private(root / "config.json", json.dumps(data).encode())
    monkeypatch.setattr(module, "_admit_runtime", lambda expected: (expected, "b" * 64))

    def forbidden(*args, **kwargs):
        raise AssertionError("preflight started an effect")

    monkeypatch.setattr(module, "build_app", forbidden)
    assert module.main(["--config", str(config)]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["mode"] == "preflight"
    assert receipt["actual_build"] == "a" * 40
    assert receipt["capabilities"] == {"worker": "pending_containment", "model": "unavailable"}


def test_cli_errors_never_echo_input_or_traceback(capsys):
    module = runtime_module()
    assert module.main(["--api-token", "private-marker"]) != 0
    rendered = capsys.readouterr()
    assert "private-marker" not in rendered.out + rendered.err
    assert "Traceback" not in rendered.err


def test_source_admission_rejects_wrong_head_dirty_and_shadow(tmp_path):
    module = runtime_module()
    repo = tmp_path / "repo"
    repo.mkdir(mode=0o700)

    def git(*args):
        return (
            subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.DEVNULL)
            .decode()
            .strip()
        )

    git("init")
    source = repo / "src/module.py"
    source.parent.mkdir()
    source.write_text("value = 1\n")
    git("add", ".")
    git(
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-m",
        "fixture",
    )
    head = git("rev-parse", "HEAD")
    assert module._admit_source(repo, head) == head
    with pytest.raises(ValueError):
        module._admit_source(repo, "0" * 40)
    source.write_text("value = 2\n")
    with pytest.raises(ValueError):
        module._admit_source(repo, head)
    git("checkout", "--", "src/module.py")
    (repo / "sitecustomize.py").write_text("raise RuntimeError('shadow')\n")
    with pytest.raises(ValueError):
        module._admit_source(repo, head)
    (repo / "sitecustomize.py").unlink()
    (repo / ".gitignore").write_text("*.py\n")
    git("add", ".gitignore")
    git(
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-m",
        "ignore",
    )
    head = git("rev-parse", "HEAD")
    (repo / "src/shadow.py").write_text("value = 3\n")
    with pytest.raises(ValueError):
        module._admit_source(repo, head)


def test_unqualified_platform_rejects_before_any_database(monkeypatch):
    module = runtime_module()
    monkeypatch.setattr(module.platform, "system", lambda: "Windows")
    with pytest.raises(module.RuntimeRejected, match="runtime_unqualified"):
        module._admit_runtime("a" * 40)


def test_module_entrypoint_help_has_no_secret_options():
    root = Path(__file__).absolute().parents[3]
    environment = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            [str(root), str(root / "src"), str(root / "services/research_agent/src")]
        ),
    }
    result = subprocess.run(
        [sys.executable, "-m", "qm_research_agent", "--help"],
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--serve" in result.stdout
    assert "--api-token" not in result.stdout


def test_source_admission_does_not_trust_skip_worktree(tmp_path):
    module = runtime_module()
    repo = tmp_path / "repo"
    repo.mkdir(mode=0o700)

    def git(*args):
        return (
            subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.DEVNULL)
            .decode()
            .strip()
        )

    git("init")
    source = repo / "module.py"
    source.write_text("value = 1\n")
    git("add", ".")
    git(
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-m",
        "fixture",
    )
    head = git("rev-parse", "HEAD")
    git("update-index", "--skip-worktree", "module.py")
    source.write_text("value = 2\n")
    with pytest.raises(ValueError):
        module._admit_source(repo, head)


def test_source_admission_refuses_ignored_bytecode(tmp_path):
    module = runtime_module()
    repo = tmp_path / "repo"
    repo.mkdir(mode=0o700)

    def git(*args):
        return (
            subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.DEVNULL)
            .decode()
            .strip()
        )

    git("init")
    (repo / ".gitignore").write_text("__pycache__/\n")
    git("add", ".")
    git(
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-m",
        "fixture",
    )
    head = git("rev-parse", "HEAD")
    cache = repo / "__pycache__"
    cache.mkdir()
    (cache / "module.cpython-312.pyc").write_bytes(b"shadow")
    with pytest.raises(ValueError):
        module._admit_source(repo, head)


def test_duplicate_config_keys_reject_before_admission(owned, monkeypatch):
    root, _ = owned
    module = runtime_module()
    config = write_private(root / "config.json", b'{"operator_id":"one","operator_id":"two"}')

    def forbidden(*args):
        raise AssertionError("duplicate config entered admission")

    monkeypatch.setattr(module, "_admit_runtime", forbidden)
    with pytest.raises(module.RuntimeRejected, match="configuration_invalid"):
        module.load_runtime(config)


def test_build_app_rechecks_admission_before_sql(owned, monkeypatch):
    _, data = owned
    module = runtime_module()
    from pydantic import SecretStr

    config = module.ServiceRuntimeConfig.model_validate(data)
    runtime = module.ServiceRuntime(
        config, SecretStr("fixture-private-token"), SecretStr("private-dsn"), "a" * 40, "b" * 64
    )

    def reject(*args):
        raise module.RuntimeRejected("source_unqualified")

    monkeypatch.setattr(module, "_admit_runtime", reject)
    with pytest.raises(module.RuntimeRejected, match="source_unqualified"):
        module.build_app(runtime)


def test_explicit_serve_fixes_single_private_listener(owned, monkeypatch):
    _, data = owned
    module = runtime_module()
    from pydantic import SecretStr
    import uvicorn

    runtime = module.ServiceRuntime(
        module.ServiceRuntimeConfig.model_validate(data),
        SecretStr("fixture-private-token"),
        SecretStr("private-dsn"),
        "a" * 40,
        "b" * 64,
    )
    monkeypatch.setattr(module, "load_runtime", lambda path: runtime)
    app = object()
    monkeypatch.setattr(module, "build_app", lambda value: app)
    calls = []
    monkeypatch.setattr(uvicorn, "run", lambda target, **options: calls.append((target, options)))
    assert module.main(["--config", "/explicit/config", "--serve"]) == 0
    assert calls == [
        (
            app,
            {
                "host": "127.0.0.1",
                "port": 8110,
                "workers": 1,
                "reload": False,
                "proxy_headers": False,
                "access_log": False,
                "log_level": "critical",
                "log_config": None,
            },
        )
    ]
