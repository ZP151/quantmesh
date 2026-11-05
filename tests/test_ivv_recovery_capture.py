"""Recovery capture tests use only temporary files and scripted external seams."""

import importlib.util
import json
from pathlib import Path

import pytest

from quantmesh.research import ivv_recovery as contract

BASE = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, BASE / "tools/research" / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def ledger(tmp_path, sync=lambda path: None):
    task = module("ivv_additional_task")
    return task.RecoveryLedger(tmp_path, contract.DEFAULT_POLICY, contract, sync_dir=sync)


def test_connection_intent_and_possible_send_survive_lost_ack(tmp_path):
    book = ledger(tmp_path)
    attempt = book.begin("a" * 64, now=100)
    assert attempt == "connection-000001"
    book.may_connect(attempt)
    assert json.loads((tmp_path / (attempt + ".may.json")).read_bytes())["state"] == "MAY_HAVE_SENT"
    with pytest.raises(ValueError, match="owned_cleanup_unknown"):
        ledger(tmp_path).begin("a" * 64, now=101)


def test_uncertain_durability_never_reopens_attempt(tmp_path):
    def fail(path):
        raise OSError("modeled flush failure")

    book = ledger(tmp_path, fail)
    with pytest.raises(OSError):
        book.begin("a" * 64, now=100)
    with pytest.raises(ValueError, match="owned_cleanup_unknown"):
        ledger(tmp_path).begin("a" * 64, now=101)


def close():
    return dict(
        child_reaped=True,
        recursive_populated=0,
        owned_fds_closed=True,
        resource_limit_event=False,
        active_owned_processes=0,
    )


def test_clean_owner_allows_bounded_successor_but_same_refusal_needs_repair(tmp_path):
    book = ledger(tmp_path)
    attempt = book.begin("a" * 64, now=100)
    book.close(attempt, close(), failure="RUNTIME_ORIGIN", method_sha256="a" * 64)
    with pytest.raises(ValueError, match="unrepaired_structural_failure"):
        book.begin("a" * 64, now=101)
    assert book.begin("b" * 64, now=101) == "connection-000002"


@pytest.mark.parametrize(
    "field,value",
    [
        ("child_reaped", False),
        ("recursive_populated", 1),
        ("owned_fds_closed", False),
        ("active_owned_processes", 1),
    ],
)
def test_unknown_owner_blocks_even_changed_method(tmp_path, field, value):
    book = ledger(tmp_path)
    attempt = book.begin("a" * 64, now=100)
    proof = close()
    proof[field] = value
    book.close(attempt, proof, failure="UNKNOWN", method_sha256="a" * 64)
    with pytest.raises(ValueError, match="owned_cleanup_unknown"):
        book.begin("b" * 64, now=101)


def test_request_intent_and_may_send_precede_effect_and_unknown_is_charged(tmp_path):
    book = ledger(tmp_path)
    attempt = book.begin("a" * 64, now=100)
    book.may_connect(attempt)
    request = book.request(attempt, 1002, {}, now=101)
    assert request == "request-000001"
    assert (
        json.loads((tmp_path / f"{attempt}-{request}.may.json").read_bytes())["state"]
        == "MAY_HAVE_SENT"
    )
    with pytest.raises(ValueError, match="request_rate"):
        book.request(attempt, 3104, {}, now=101.1)
    assert book.usage()["business_requests"] == 1


def test_context_budget_is_cumulative_across_policy_versions(tmp_path):
    book = ledger(tmp_path)
    for i in range(3):
        attempt = book.begin("a" * 64, now=100 + i)
        book.close(attempt, close(), failure=None, method_sha256="a" * 64)
    with pytest.raises(ValueError, match="context_budget"):
        book.begin("b" * 64, now=105)


def test_fixed_recovery_entry_exists_without_changing_old_entry():
    helper = module("capture_opend_ivv_daily")
    runner = module("ivv_trusted_runner")
    assert callable(getattr(helper, "capture_recovery_attempt", None))
    assert callable(getattr(runner, "run_recovery_attempt", None))
    assert helper.ADDITIONAL_AUTH != contract.AUTHORITY


def test_recovery_capture_real_observer_persists_before_send_and_archives_journal(tmp_path):
    from test_ivv_capture_contract import DATES, Clock, ScriptedBackend
    from test_ivv_capture_contract import contract as old_plan

    helper = module("capture_opend_ivv_daily")
    book_root = tmp_path / "ledger"
    book_root.mkdir()
    book = ledger(book_root)
    clock = Clock()
    attempt = book.begin("a" * 64, now=clock.mono())
    plan = old_plan(helper)
    plan.update(
        schema_id="qm.ivv.capture-plan" + contract.FAMILY,
        scope_id=contract.capture_scope_id(),
        approval_sha256=contract.capture_effect(),
        execution_sha256=contract.AUTHORITY,
        effect_id=contract.LOGICAL_TASK_ID + "-capture",
        _recovery_ledger=book,
        _recovery_attempt=attempt,
        _verified_binding=dict(
            **contract.policy_provenance(book.policy),
            policy_sha256=book.policy_sha,
            hard_limit_enforced=False,
            channel_assurance="UNVERIFIED_TRUSTED_EXTERNAL",
        ),
    )
    root = tmp_path / "capture"
    observed = []

    def backend(observer, writer, plan, clock):
        assert (book_root / (attempt + ".may.json")).is_file()
        value = ScriptedBackend(helper, observer, writer, clock, root)
        original = value.invoke

        def invoke(tag, params):
            result = original(tag, params)
            assert book.usage()["business_requests"] == len(observer.sent)
            observed.append(tag)
            return result

        value.invoke = invoke
        return value

    result = helper._run_capture(
        plan,
        root,
        backend_factory=backend,
        clock=clock,
        sync_dir=lambda _: None,
        synthetic=True,
        dates=DATES,
    )
    assert result["state"] == "CAPTURED_UNREVIEWED"
    for key, value in contract.policy_provenance(contract.DEFAULT_POLICY).items():
        assert result[key] == value
    assert observed == list(helper.ORDER)
    assert result["counts"]["application_sends"] == 7
    ref = result["recovery"]["request_journal_ref"]
    raw = (root / "request-journal.json").read_bytes()
    assert ref == dict(
        algorithm="sha256",
        digest=contract.digest(raw),
        byte_length=len(raw),
        media_type="application/json",
    )
    assert result["recovery"]["history_actual"] == "UNKNOWN"
    assert clock.value >= 6
    with pytest.raises(ValueError, match="owned_cleanup_unknown"):
        book.begin("b" * 64, now=clock.mono())


def test_recovery_profile_has_no_future_study_identity_and_exact_locations():
    task = module("ivv_additional_task")
    profile = task.RecoveryProfile(contract, contract.DEFAULT_POLICY, "connection-000001")
    runner = module("ivv_trusted_runner")
    loc = runner._locations(profile.attempt)
    assert (
        str(loc.control).replace(chr(92), "/")
        == "/var/lib/quantmesh-ivv-recovery/attempts/connection-000001/parent"
    )
    assert profile.FAMILY == contract.FAMILY
    assert not hasattr(profile, "job_id")
    for bad in ("../escape", "connection-0", True):
        with pytest.raises(ValueError):
            task.RecoveryProfile(contract, contract.DEFAULT_POLICY, bad)


def test_recovery_root_go_is_preinput_and_exact_actual_actor(tmp_path, monkeypatch):
    from types import SimpleNamespace

    task = module("ivv_additional_task")
    runner = module("ivv_trusted_runner")
    helper = module("capture_opend_ivv_daily")
    profile = task.RecoveryProfile(contract, contract.DEFAULT_POLICY, "connection-000001")
    monkeypatch.setattr(runner, "_locations", lambda mode: SimpleNamespace(control=tmp_path))
    monkeypatch.setattr(runner, "_sync_dir", lambda path: None)
    monkeypatch.setattr(runner, "protected", lambda path: None)
    for name in ("O_NOFOLLOW", "O_CLOEXEC"):
        monkeypatch.setattr(runner.os, name, 0, raising=False)
    monkeypatch.setattr(runner.os, "fchmod", lambda fd, mode: None, raising=False)
    plan = dict(
        scope_id=contract.capture_scope_id(),
        execution_sha256=contract.AUTHORITY,
        approval_sha256=contract.capture_effect(),
        effect_id=contract.LOGICAL_TASK_ID + "-capture",
        policy_ref={"sha256": profile.policy_sha},
        catalog_sha256="a" * 64,
        input_window_digest=helper.WINDOW,
        full_window_sha256=helper.FULL_WINDOW,
        recovery=profile.binding(),
    )
    catalog = {key: "b" * 64 for key in runner._sources(profile.attempt)}
    values = dict(
        _additional=profile,
        _recovery_mode=profile.attempt,
        catalog_ref=catalog,
        budget_ref={"G": 1000, "P": 1000},
    )
    actor = dict(pid=123, uid=0, start_ticks=456, cgroup="/modeled")
    context = ({}, values, None, helper, None, None)
    _, go_ref, _, _ = runner._authorize(
        context, plan, SimpleNamespace(child=actor), SimpleNamespace(first={"modeled_native": True})
    )
    go = json.loads(Path(go_ref["path"]).read_bytes())
    assert go["decision"] == "GO_BOUNDED_CAPTURE_RECOVERY"
    assert go["recovery"] == profile.binding()
    assert go["capture_actor"] == actor
    assert go["approval_sha256"] == contract.capture_effect()
    assert not {"job_id", "research_scope_id", "max_trials"} & set(go)


def connected_recovery_capture(tmp_path, monkeypatch, fault=None, kernel_extra=None):
    import contextlib
    import os
    import sys
    from types import SimpleNamespace

    from test_ivv_additional_task import window_controls
    from test_ivv_capture_contract import Clock, ScriptedBackend
    from test_ivv_dev_diagnostic import kernel_fixture

    task = module("ivv_additional_task")
    runner = module("ivv_trusted_runner")
    d, m, original, root, pins, snapshot = kernel_fixture(
        tmp_path, monkeypatch, additional_controls=window_controls(False)
    )
    original_open = os.open
    monkeypatch.setattr(
        os,
        "open",
        lambda path, flags, *a, **kw: original_open(
            path, flags | getattr(os, "O_BINARY", 0), *a, **kw
        ),
    )
    profile = task.RecoveryProfile(contract, contract.DEFAULT_POLICY, "connection-000001")

    def put(name, value):
        raw = m._canonical(value)
        path = tmp_path / name
        path.write_bytes(raw)
        return {"path": str(path), "sha256": contract.digest(raw)}

    policy_ref = put("recovery-policy.json", profile.policy)
    plan = json.loads(Path(original["path"]).read_bytes())
    plan.update(
        schema_id="qm.ivv.capture-plan" + contract.FAMILY,
        scope_id=contract.capture_scope_id(),
        approval_sha256=contract.capture_effect(),
        execution_sha256=contract.AUTHORITY,
        effect_id=contract.LOGICAL_TASK_ID + "-capture",
        policy_ref=policy_ref,
        recovery=profile.binding(),
    )
    catalog = json.loads(Path(pins["catalog_ref"]["path"]).read_bytes())
    catalog.update(
        python_sha256=kernel_extra["executable_origin"]["initial"]["python_sha256"]
        if kernel_extra
        else "b" * 64,
        additional_task_sha256=contract.digest(Path(task.__file__).read_bytes()),
        recovery_contract_sha256=contract.digest(Path(contract.__file__).read_bytes()),
        trusted_runner_sha256=contract.digest(Path(runner.__file__).read_bytes()),
    )
    catalog_ref = put("recovery-catalog.json", catalog)
    plan["catalog_sha256"] = catalog_ref["sha256"]
    old_read = m._read_root_ref
    auth_ref = {"path": str(tmp_path / "private-authority"), "sha256": contract.AUTHORITY}

    def protected_auth(ref, **kw):
        if ref == auth_ref:
            return b"modeled protected approval read; exact-A witness is separate"
        return old_read(ref, **kw)

    monkeypatch.setattr(m, "_read_root_ref", protected_auth)
    # Only deployment path and native metadata are modeled. Exact held code bytes run.
    original_source_loader = d._released_module

    def released(name, expected):
        if name == "ivv_recovery.py":
            assert expected == contract.digest(Path(contract.__file__).read_bytes())
            return contract
        return original_source_loader(name, expected)

    monkeypatch.setattr(d, "_released_module", released)
    monkeypatch.setattr(runner, "_sync_dir", lambda _: None)
    monkeypatch.setattr(
        runner,
        "_locations",
        lambda _: SimpleNamespace(control=tmp_path, child=tmp_path, receipt=root),
    )
    snapshot["listener_binding_sha256"] = snapshot.pop("channels_binding_sha256")
    actual = {
        key: snapshot[key]
        for key in (
            "provider_actor",
            "endpoint",
            "identity_binding_sha256",
            "configuration_binding_sha256",
            "listener_binding_sha256",
        )
    }
    actor = m._native_actor()
    values = dict(
        _additional=profile,
        _recovery_mode=profile.attempt,
        catalog_ref=catalog,
        budget_ref={"G": 1000, "P": 1000},
    )
    plan["provider_evidence_ref"] = {"path": str(tmp_path / "provider.json"), "sha256": "0" * 64}
    startup = dict(catalog_ref=catalog_ref, authorization_ref=auth_ref)
    ctx = (startup, values, d, m, None, None)
    grant = runner._authorize(
        ctx, plan, SimpleNamespace(child=actor), SimpleNamespace(first=actual)
    )
    final_plan, go_ref, final, prov = grant
    book = task.RecoveryLedger(
        tmp_path / "ledger", profile.policy, contract, sync_dir=lambda _: None
    )
    attempt = book.begin(catalog_ref["sha256"], now=0)
    state = SimpleNamespace(
        helper=m,
        recovery_profile=profile,
        recovery_ledger=book,
        recovery_attempt=attempt,
        trusted_issuer=d,
        additional_task=None,
        session=SimpleNamespace(before_effect=lambda: None),
    )
    monkeypatch.setitem(sys.modules, "_qm_live_ivv_native_" + str(os.getpid()), state)
    pins = dict(
        go_ref=go_ref,
        authorization_ref=auth_ref,
        catalog_ref=catalog_ref,
        expected_policy_sha256=profile.policy_sha,
        expected_authorization_sha256=contract.AUTHORITY,
        expected_go_sha256=go_ref["sha256"],
        permit_path=tmp_path / "permit.json",
    )
    if fault == "study_go":
        go = json.loads(Path(go_ref["path"]).read_bytes())
        go["decision"] = "GO_RECOVERABLE_AFTER_INPUT_ACCEPTANCE"
        pins["go_ref"] = put("bad-go.json", go)
        pins["expected_go_sha256"] = pins["go_ref"]["sha256"]
    if fault == "policy":
        pins["expected_policy_sha256"] = "f" * 64
    if fault in ("study_go", "policy"):
        with pytest.raises(ValueError):
            d._issue_family(m, contract.FAMILY, final_plan, root, **pins)
        assert not root.exists()
        return
    fd, sha = d._issue_family(m, contract.FAMILY, final_plan, root, **pins)

    class NativeClock(Clock):
        def phase(self, until):
            return contextlib.nullcontext()

    class Backend(ScriptedBackend):
        def open(self):
            assert (tmp_path / "ledger" / (attempt + ".may.json")).exists()
            self.o.context_created()
            self.o.initializing()
            self.o.before_send(1001, 1)

    monkeypatch.setattr(m, "_NativeClock", NativeClock)
    monkeypatch.setattr(m, "_OfficialBackend", lambda o, w, p, c: Backend(m, o, w, c, root))
    try:
        args = {k: v for k, v in pins.items() if k.startswith("expected_")}
        if fault == "held_pin":
            with pytest.raises(ValueError):
                m.capture_recovery_attempt(
                    final_plan["path"], root, permit_fd=fd, expected_sha256="f" * 64, **args
                )
            assert not root.exists()
            return
        result = m.capture_recovery_attempt(
            final_plan["path"], root, permit_fd=fd, expected_sha256=sha, **args
        )
    finally:
        os.close(fd)
    assert result["state"] == "CAPTURED_UNREVIEWED"
    for key, value in contract.policy_provenance(contract.DEFAULT_POLICY).items():
        assert result[key] == value
    assert result["source_binding"]["root_go_sha256"] == go_ref["sha256"]
    assert result["recovery"]["connection_attempt_id"] == attempt
    assert result["counts"]["control_sends"]["1001"] == 1
    assert book.usage()["business_requests"] == 7
    assert not (tmp_path / "ledger" / (attempt + ".close.json")).exists()

    # Model only Linux metadata; execute real held-byte seal readers and serializer.
    tracked = {}
    prior_open, prior_fstat, prior_stat = os.open, os.fstat, os.stat

    def opened(path, *args, **kw):
        descriptor = prior_open(path, *args, **kw)
        tracked[descriptor] = Path(path)
        return descriptor

    def private_stamp(info, path):
        if path is not None and path.parent == root:
            values = vars(info).copy()
            values["st_mode"] = 0o100600
            return SimpleNamespace(**values)
        return info

    monkeypatch.setattr(os, "open", opened)
    monkeypatch.setattr(
        os,
        "fstat",
        lambda descriptor: private_stamp(prior_fstat(descriptor), tracked.get(descriptor)),
    )
    monkeypatch.setattr(
        os,
        "stat",
        lambda path, *a, **kw: private_stamp(
            prior_stat(path, *a, **kw), Path(path) if not isinstance(path, int) else None
        ),
    )
    scope = SimpleNamespace(child=actor, parent={**actor, "pid": actor["pid"] + 1}, initial={})
    monitor = SimpleNamespace(
        first=actual,
        series=SimpleNamespace(samples=[]),
        peak=0,
        last={"sample": {"G": 1000, "P": 1000}},
    )
    parent = runner._seal(
        ctx,
        grant,
        scope,
        monitor,
        {"capture_actor": actor, **(kernel_extra or {})},
        {
            "manifest_sha256": contract.digest((root / "capture-manifest.json").read_bytes()),
            "permit_sha256": sha,
        },
        (10, 11),
        8,
    )
    assert parent["state"] == "NORMAL_EXIT" and parent["owned_fds_closed"] is True
    parent_ref = runner.put(tmp_path / "parent-close.json", parent)
    return dict(
        task=task,
        runner=runner,
        helper=m,
        root=root,
        plan=plan,
        final=final,
        go_ref=go_ref,
        catalog_ref=catalog_ref,
        policy_ref=policy_ref,
        auth_ref=auth_ref,
        parent_ref=parent_ref,
        pins=pins,
        profile=profile,
    )


@pytest.mark.parametrize("fault", [None, "study_go", "held_pin", "policy"])
def test_real_recovery_issuer_held_admission_and_public_capture(tmp_path, monkeypatch, fault):
    connected_recovery_capture(tmp_path, monkeypatch, fault)


def test_new_registered_batch_keeps_history_and_has_its_own_recorded_budget(tmp_path):
    import copy

    task = module("ivv_additional_task")
    first = ledger(tmp_path)
    for i in range(3):
        attempt = first.begin("a" * 64, now=100 + i)
        first.close(attempt, close(), failure=None, method_sha256="a" * 64)
    policy = copy.deepcopy(contract.DEFAULT_POLICY)
    policy["batch"]["batch_id"] = "ivv-recovery-batch-02"
    later = task.RecoveryLedger(tmp_path, policy, contract, sync_dir=lambda _: None)
    assert later.begin("a" * 64, now=2100) == "connection-000004"
    assert later.usage()["contexts"] == 4
    assert len(list(tmp_path.glob("connection-*.intent.json"))) == 4


def test_observed_reply_remains_distinct_from_possible_send(tmp_path):
    book = ledger(tmp_path)
    attempt = book.begin("a" * 64, now=0)
    book.may_connect(attempt)
    request = book.request(attempt, 1002, {}, now=1)
    ref = dict(algorithm="sha256", digest="b" * 64, media_type="application/json", byte_length=42)
    book.observed(attempt, request, ref)
    rows = book.journal(attempt)["records"]
    assert {r["state"] for r in rows} == {"INTENT", "MAY_HAVE_SENT", "RESPONSE_OBSERVED"}
    assert book.usage()["business_requests"] == 1


def test_new_transport_failure_stage_retains_origin_and_unknown_counts():
    runner = module("ivv_trusted_runner")
    origin = dict(
        schema="qm.ivv.runtime-origin-failure.v1",
        phase="INITIAL",
        predicate="EXECUTABLE",
        outcome="FIRST_FALSE",
    )
    value = dict(
        state="STOP",
        publication_sha256="a" * 64,
        stage="RELEASED_RECOVERY_ATTEMPT",
        automatic_retry=False,
        provider_mutation=False,
        unit_returncode=1,
        reason="RUNTIME_ORIGIN",
        actual_contexts=0,
        origin_failure=origin,
    )
    selected = runner.select_failure_status(value, "a" * 64)
    assert selected["actual_contexts"] == "UNKNOWN"
    assert selected["origin_failure"] == origin


def test_sdk_close_unknown_with_proven_owned_cleanup_allows_new_attempt(tmp_path):
    book = ledger(tmp_path)
    attempt = book.begin("a" * 64, now=0)
    book.may_connect(attempt)
    record = book.close(attempt, close(), failure="SDK_CLOSE_UNKNOWN", method_sha256="a" * 64)
    assert record["owner_state"] == "CLOSED" and record["external_effects"] == "UNKNOWN"
    assert book.begin("a" * 64, now=1) == "connection-000002"
    assert book.usage()["contexts"] == 2


def test_runner_adopts_only_matching_reserved_intent_once(tmp_path):
    book = ledger(tmp_path)
    attempt = book.begin("a" * 64, now=0)
    with pytest.raises(ValueError):
        book.enter(attempt, "b" * 64, "c" * 64)
    book.enter(attempt, "a" * 64, "c" * 64)
    with pytest.raises(FileExistsError):
        book.enter(attempt, "a" * 64, "c" * 64)


def test_writer_serializes_shared_aggregate_bound_under_concurrent_callbacks(tmp_path, monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    helper = module("capture_opend_ivv_daily")
    writer = helper._Writer(tmp_path / "capture", lambda _: None)
    writer.written = 7 * helper.MIB - 5  # modeled prior writes at the budget boundary
    entered, second, release = threading.Event(), threading.Event(), threading.Event()
    original = helper.os.write
    counter = [0]

    def write(fd, raw):
        counter[0] += 1
        if counter[0] == 1:
            entered.set()
            assert release.wait(2)
        else:
            second.set()
        return original(fd, raw)

    monkeypatch.setattr(helper.os, "write", write)

    def work(name):
        try:
            writer.write(name, b"1234")
            return "written"
        except helper.CaptureRejected:
            return "bounded"

    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(work, "one.json")
        assert entered.wait(2)
        two = pool.submit(work, "two.json")
        second.wait(0.05)
        release.set()
        assert sorted([one.result(), two.result()]) == ["bounded", "written"]
    assert writer.written <= 7 * helper.MIB


def test_concurrent_control_callbacks_have_unique_durable_request_ids(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    book = ledger(tmp_path)
    attempt = book.begin("a" * 64, now=0)
    book.may_connect(attempt)
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(lambda _: book.request(attempt, 1004, {}, now=1), range(12)))
    assert len(set(ids)) == 12
    assert book.usage()["keepalive"] == 12


@pytest.mark.parametrize(
    "failure,abort_errors,next_allowed",
    [
        ("SDK_CLOSE_UNKNOWN", [], True),
        ("CAPTURE_TIMEOUT", [], True),
        ("RUNTIME_ORIGIN", [], False),
        ("SDK_CLOSE_UNKNOWN", ["FORCED_REAP_UNKNOWN"], False),
    ],
)
def test_real_parent_entry_distinguishes_failed_capture_from_owned_cleanup(
    tmp_path, monkeypatch, failure, abort_errors, next_allowed
):
    import contextlib
    from types import SimpleNamespace

    r, task = module("ivv_trusted_runner"), module("ivv_additional_task")
    book = task.RecoveryLedger(tmp_path, contract.DEFAULT_POLICY, contract, sync_dir=lambda _: None)
    profile = task.RecoveryProfile(contract, contract.DEFAULT_POLICY, "connection-000001")
    catalog = {k: "a" * 64 for k in r._sources(profile.attempt)}
    method = r.digest(r.raw_json(catalog))
    attempt = book.begin(method, now=0)
    values = dict(
        _additional=profile, _recovery_mode=attempt, _recovery_task=task, catalog_ref=catalog
    )
    startup = {"catalog_ref": {"sha256": "b" * 64}}
    ctx = startup, values, None, None, None, None
    monkeypatch.setattr(
        r, "_locations", lambda _: SimpleNamespace(control=tmp_path, ledger=tmp_path)
    )
    monkeypatch.setattr(r, "_bootstrap", lambda *a, **kw: ctx)
    monkeypatch.setattr(r, "_seed", lambda *a, **kw: {"started_monotonic": 0})
    monkeypatch.setattr(r, "_stdio", lambda: None)
    monkeypatch.setattr(r, "_fds", lambda: {0, 1, 2, 73})
    monkeypatch.setattr(
        r,
        "_recovery_lifecycle",
        lambda *a: contextlib.nullcontext(SimpleNamespace(fd=73, close=lambda: None)),
    )

    class ProcPath:
        def __init__(self, value):
            pass

        def iterdir(self):
            return iter([1])

    monkeypatch.setattr(r, "Path", ProcPath)
    monkeypatch.setattr(r, "time", SimpleNamespace(monotonic=lambda: 1))
    monkeypatch.setattr(task, "_sync_directory", lambda _: None)

    class Socket:
        def close(self):
            pass

    monkeypatch.setattr(r.socket, "socketpair", lambda *a: (Socket(), Socket()))
    monkeypatch.setattr(r.socket, "SOCK_SEQPACKET", 5, raising=False)
    monkeypatch.setattr(r.socket, "SOCK_CLOEXEC", 0, raising=False)
    monkeypatch.setattr(r.socket, "AF_UNIX", 1, raising=False)
    monkeypatch.setattr(r, "_Channel", lambda s: SimpleNamespace(origin=(0, 1)))
    monkeypatch.setattr(r.os, "fork", lambda: 123, raising=False)

    class Scope:
        def __init__(self, stack, **kw):
            self.parent = {"pid": 77, "start_ticks": 1}
            self.reaped = False
            self.leaf = 1

        def bind(self, pid):
            assert pid == 123

        def abort(self):
            self.reaped = not abort_errors
            return abort_errors

    monkeypatch.setattr(r, "_Scope", Scope)

    def refuse(*a):
        raise r.Refused(failure)

    monkeypatch.setattr(r, "_supervise", refuse)
    monkeypatch.setattr(
        r, "_persist_recovery_owner", lambda *args: None
    )  # acquired-kernel binding seam covered separately
    with pytest.raises(ValueError, match=failure):
        r.run_recovery_attempt({"sha256": "c" * 64}, attempt)
    proof = json.loads((tmp_path / (attempt + ".close.json")).read_bytes())
    assert proof["owner_state"] == ("UNKNOWN" if abort_errors else "CLOSED")
    assert not (tmp_path / "parent-close.json").exists()
    if next_allowed:
        assert book.begin(method, now=2) == "connection-000002"
    else:
        with pytest.raises(ValueError):
            book.begin(method, now=2)


@pytest.mark.parametrize(
    "fault", [None, "cross_epoch", "wrong_go", "abnormal_close", "bad_original"]
)
def test_candidate_manifest_uses_immutable_same_epoch_originals_only(tmp_path, fault):
    from quantmesh.data.objects import ObjectRef, ObjectStore

    task = module("ivv_additional_task")
    store = ObjectStore(tmp_path / "objects")

    def put(value):
        return store.put_bytes("application/json", contract.canonical(value)).model_dump()

    sem = {name: "modeled-provider-fact" for name in contract.SEMANTIC_FIELDS}
    sem["source_id"] = "moomoo-opend-us-equities"
    sem["source_use"] = "historical-daily-research"
    sem["revision_note"] = "provider revision unknown"
    sem["window"] = {"first": "2026-05-08", "last": "2026-10-29"}
    sem["inputs"] = dict.fromkeys(("bars", "distributions", "schedule"))
    for name in sem["inputs"]:
        sem["inputs"][name] = put({"modeled_input": name})
    facts = put({"basis": "modeled actual facts, no acceptance"})

    def capture(attempt):
        binding = {
            "logical_task_id": contract.LOGICAL_TASK_ID,
            "batch_id": "ivv-recovery-batch-01",
            "connection_attempt_id": attempt,
            "policy_sha256": "a" * 64,
        }
        go = put(
            dict(
                schema_id="qm.ivv.root-go" + contract.FAMILY,
                decision="GO_BOUNDED_CAPTURE_RECOVERY",
                recovery=binding,
                scope_id=contract.capture_scope_id(),
                approval_sha256=contract.capture_effect(),
                execution_sha256=contract.AUTHORITY,
            )
        )
        raw = put(
            dict(
                schema_id="qm.ivv.capture" + contract.FAMILY,
                state="CAPTURED_UNREVIEWED",
                synthetic=False,
                primary_failure=None,
                close_failure=None,
                normal_close={
                    "context_closed": True,
                    "callbacks_stopped": True,
                    "data_socket_closed": True,
                },
                scope_id=contract.capture_scope_id(),
                source_binding={"root_go_sha256": go["digest"]},
                recovery={
                    **binding,
                    "history_actual": "UNKNOWN",
                    "request_journal_ref": put({"modeled": "journal"}),
                },
            )
        )
        parent = put(
            dict(
                schema_id="qm.ivv.capture-parent-close" + contract.FAMILY,
                state="NORMAL_EXIT",
                termination="NORMAL",
                helper_exit_code=0,
                active_owned_processes=0,
                owned_fds_closed=True,
                resource_limit_event=False,
                force_killed=False,
                capture_manifest_sha256=raw["digest"],
            )
        )
        return [raw, go, parent]

    sets = [capture("connection-000001")]
    if fault == "cross_epoch":
        sets.append(capture("connection-000002"))
    if fault == "wrong_go":
        sets[0][1] = capture("connection-000002")[1]
    if fault == "abnormal_close":
        value = json.loads(store.get_bytes(ObjectRef.model_validate(sets[0][2])))
        value["termination"] = "FORCED"
        sets[0][2] = put(value)

    def read(ref):
        if fault == "bad_original":
            return b"{}"
        return store.get_bytes(ObjectRef.model_validate(ref))

    if fault:
        with pytest.raises(ValueError):
            task.build_input_manifest(contract, sem, sets, facts, read)
    else:
        result = task.build_input_manifest(contract, sem, sets, facts, read)
        assert result["capture_epoch"] == "ivv-recovery-batch-01/connection-000001"
        assert result["capture_go_refs"] == [sets[0][1]]
        assert result["asof_pit"] == dict(
            status="unknown", provider_asof=None, provider_version=None, basis_refs=[]
        )
        assert not {"input_acceptance_ref", "job_id"} & set(result)


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "cross_namespace",
        "manager_active",
        "pid_drift",
        "foreign",
        "mount",
        "named_inode",
        "close",
    ],
)
def test_exact_owner_recovery_kernel_body_never_kills_unknown(monkeypatch, fault):
    import os
    from types import SimpleNamespace

    runner = module("ivv_trusted_runner")
    attempt = "connection-000001"
    unit = "/system.slice/qm-ivv-recovery-" + attempt + ".service"
    manager = dict(pid=300, start_ticks=500, uid=0, cgroup=unit + "/manager")
    child = dict(pid=301, start_ticks=501, uid=0, cgroup=unit + "/ivv-owned-300-500")
    binding = dict(
        connection_attempt_id=attempt,
        manager=manager,
        child=child,
        mount={"id": 33 if fault == "cross_namespace" else 44, "namespace": [2, 99, 0o100444, 0]},
        group=[1, 10, 0o40700, 0],
        manager_dir=[1, 11, 0o40700, 0],
        leaf=[1, 12, 0o40700, 0],
    )
    live, kills, closed = [True], [], []

    def process(pid):
        if pid == 300 and fault == "manager_active":
            return manager, 1
        if pid == 301 and live[0]:
            return ({**child, "start_ticks": 999} if fault == "pid_drift" else child), 1
        raise FileNotFoundError()

    monkeypatch.setattr(runner, "_process", process)
    original_exists = Path.exists
    monkeypatch.setattr(
        Path,
        "exists",
        lambda path: (
            False if str(path).replace("\\", "/").startswith("/proc/") else original_exists(path)
        ),
    )
    monkeypatch.setattr(runner, "_cgroup_mount", lambda: 45 if fault == "mount" else 44)
    monkeypatch.setattr(runner, "_mount_id", lambda fd: 44)
    monkeypatch.setattr(runner, "protected", lambda path: None)

    def opened(path, *a, **kw):
        name = str(path)
        return 12 if name.endswith("ivv-owned-300-500") else 11 if name.endswith("manager") else 10

    monkeypatch.setattr(os, "open", opened)
    monkeypatch.setattr(
        os, "fstat", lambda fd: SimpleNamespace(st_dev=1, st_ino=fd, st_mode=0o40700, st_uid=0)
    )
    monkeypatch.setattr(
        os,
        "stat",
        lambda path, *a, **kw: SimpleNamespace(
            st_dev=1,
            st_ino=999 if fault == "named_inode" else opened(path),
            st_mode=0o40700,
            st_uid=0,
        ),
    )

    def close_fd(fd):
        closed.append(fd)
        if fault == "close":
            raise OSError("modeled close uncertainty")

    monkeypatch.setattr(runner, "_close_fd", close_fd)
    monkeypatch.setattr(os, "pidfd_open", lambda pid: 90, raising=False)
    monkeypatch.setattr(
        runner._Scope,
        "dirs",
        staticmethod(lambda fd: {"manager", "ivv-owned-300-500"} if fd == 10 else set()),
    )

    def kread(fd, name, *a):
        if name == "cgroup.procs":
            return (
                "301 999"
                if fault == "foreign" and fd == 12
                else "301"
                if fd == 12 and live[0]
                else ""
            )
        if name == "cgroup.events":
            return "populated " + str(int(live[0] if fd in (10, 12) else False))
        raise AssertionError(name)

    monkeypatch.setattr(runner, "_kread", kread)

    def signal_fd(fd, sig):
        kills.append(fd)
        live[0] = False

    monkeypatch.setattr(runner.signal, "SIGKILL", 9, raising=False)
    monkeypatch.setattr(runner.signal, "pidfd_send_signal", signal_fd, raising=False)
    monkeypatch.setattr(runner.select, "select", lambda *args: ([90], [], []))
    if fault not in (None, "cross_namespace"):
        with pytest.raises((ValueError, OSError)):
            runner._recover_bound_owner(binding)
        if fault != "close":
            assert kills == []
    else:
        proof = runner._recover_bound_owner(binding)
        assert kills == [90] and set(closed) == {10, 11, 12, 90}
        assert proof == {
            "owned_cleanup_proven": True,
            "external_effects": "UNKNOWN",
            "input_publishable": False,
        }


def test_recovery_ledger_never_reads_outside_owned_directory(tmp_path):
    book = ledger(tmp_path)
    with pytest.raises(ValueError, match="recovery_journal_name"):
        book._read("../escape.json")


@pytest.mark.parametrize(
    "fault", [None, "lease", "missing", "close", "persist", "interrupted", "structural"]
)
def test_recovered_receipt_is_append_only_and_never_upgrades_old_unknown(
    tmp_path, monkeypatch, fault
):
    import contextlib
    import os
    import sys
    from types import SimpleNamespace

    runner = module("ivv_trusted_runner")
    book = ledger(tmp_path)
    attempt = book.begin("a" * 64, now=0)
    if fault not in ("interrupted", "structural"):
        book.close(attempt, {}, failure="SDK_CLOSE_UNKNOWN", method_sha256="a" * 64)
    original = (
        (tmp_path / (attempt + ".close.json")).read_bytes()
        if (tmp_path / (attempt + ".close.json")).exists()
        else None
    )
    if fault == "structural":
        (tmp_path / "runner-failure.json").write_bytes(
            b'{"state":"STOP","reason":"RUNTIME_ORIGIN"}'
        )
    binding = {"modeled_exact_kernel_binding": attempt}
    if fault != "missing":
        book._write(attempt + ".owner.json", binding)
    monkeypatch.setattr(
        runner, "_locations", lambda _: SimpleNamespace(ledger=tmp_path, control=tmp_path)
    )
    monkeypatch.setattr(runner, "protected", lambda _: None)
    monkeypatch.setattr(runner, "_recovery_lease", lambda *a: contextlib.nullcontext())
    monkeypatch.setattr(os, "O_NOFOLLOW", getattr(os, "O_NOFOLLOW", 0), raising=False)
    monkeypatch.setattr(os, "O_CLOEXEC", getattr(os, "O_CLOEXEC", 0), raising=False)
    calls = []

    def flock(*args):
        if fault == "lease":
            raise BlockingIOError("modeled active lease")

    monkeypatch.setitem(sys.modules, "fcntl", SimpleNamespace(flock=flock, LOCK_EX=2, LOCK_NB=4))

    def kernel(value):
        calls.append(value)
        return dict(owned_cleanup_proven=True, external_effects="UNKNOWN", input_publishable=False)

    monkeypatch.setattr(runner, "_recover_bound_owner", kernel)
    if fault == "close":

        def fail_close(fd):
            os.close(fd)
            raise OSError("modeled lease close uncertainty")

        monkeypatch.setattr(runner, "_close_fd", fail_close)
    if fault == "persist":
        prior = book._write

        def write(name, value):
            if name.endswith(".recovered.json"):
                raise OSError("modeled persistence failure")
            return prior(name, value)

        monkeypatch.setattr(book, "_write", write)
    if fault in ("lease", "missing", "close", "persist"):
        with pytest.raises((OSError, ValueError)):
            runner.recover_previous_attempt(book, lambda path, maximum: path.read_bytes())
        assert not (tmp_path / (attempt + ".recovered.json")).exists()
        with pytest.raises(ValueError, match="owned_cleanup_unknown"):
            book.begin("a" * 64, now=1)
        if fault in ("lease", "missing"):
            assert not calls
    else:
        runner.recover_previous_attempt(book, lambda path, maximum: path.read_bytes())
        assert calls == [binding]
        receipt = book._read(attempt + ".recovered.json")
        assert receipt["input_publishable"] is False and receipt["external_effects"] == "UNKNOWN"
        if fault == "structural":
            with pytest.raises(ValueError, match="unrepaired_structural_failure"):
                book.begin("a" * 64, now=1)
        else:
            assert book.begin("a" * 64, now=1) == "connection-000002"
    if original is not None:
        assert (tmp_path / (attempt + ".close.json")).read_bytes() == original
    else:
        assert book._read(attempt + ".close.json")["owner_state"] == "UNKNOWN"


def test_owner_binding_is_exclusive_durable_before_child_release(tmp_path, monkeypatch):
    import os
    from types import SimpleNamespace

    events = []
    book = ledger(tmp_path, sync=lambda _: events.append("directory_fsync"))
    attempt = book.begin("a" * 64, now=0)
    events.clear()
    runner = module("ivv_trusted_runner")
    real_fstat = os.fstat
    monkeypatch.setattr(
        os,
        "fstat",
        lambda fd: (
            SimpleNamespace(st_dev=1, st_ino=-fd, st_mode=0o40700, st_uid=0)
            if fd < 0
            else real_fstat(fd)
        ),
    )
    scope = SimpleNamespace(
        parent={"pid": 1},
        child={"pid": 2},
        mount=44,
        group=-1,
        man=-2,
        leaf=-3,
        check_pid=lambda: events.append("pid"),
        check_leaf=lambda: events.append("leaf"),
    )
    real_stat = os.stat
    monkeypatch.setattr(
        os,
        "stat",
        lambda path, *a, **kw: (
            SimpleNamespace(st_dev=2, st_ino=99, st_mode=0o100444, st_uid=0)
            if str(path) == "/proc/self/ns/mnt"
            else real_stat(path, *a, **kw)
        ),
    )
    runner._persist_recovery_owner(book, attempt, scope)
    events.append("release")
    assert events == ["pid", "leaf", "directory_fsync", "pid", "leaf", "release"]
    with pytest.raises(FileExistsError):
        runner._persist_recovery_owner(book, attempt, scope)


@pytest.mark.parametrize("expected", ["connection-000002", "../bad"])
def test_r1_expected_connection_is_checked_before_any_intent(tmp_path, expected):
    book = ledger(tmp_path)
    with pytest.raises(ValueError):
        book.begin("a" * 64, now=0, expected_connection=expected)
    assert not list(tmp_path.glob("*.intent.json"))


@pytest.mark.parametrize("failure", ["BOOTSTRAP", "SEED", "ENTRY", "STDIO", "FD_CHECK"])
def test_r1_actual_entry_holds_lifecycle_before_preowner_failures(monkeypatch, failure):
    import contextlib
    from types import SimpleNamespace

    runner = module("ivv_trusted_runner")
    events = []

    @contextlib.contextmanager
    def lifecycle(startup, attempt):
        events.append("BOUND_GATE")
        try:
            yield SimpleNamespace(fd=73, close=lambda: events.append("LEASE_CLOSED"))
        finally:
            events.append("GATE_CLOSED")

    monkeypatch.setattr(runner, "_recovery_lifecycle", lifecycle, raising=False)

    def refused(startup, *, additional, lifecycle=None):
        assert events == ["BOUND_GATE"]
        assert lifecycle.fd == 73
        raise runner.Refused(failure)

    monkeypatch.setattr(runner, "_run", refused)
    with pytest.raises(ValueError, match=failure):
        runner.run_recovery_attempt({"sha256": "a" * 64}, "connection-000001")
    assert events == ["BOUND_GATE", "GATE_CLOSED"]


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "active",
        "invocation",
        "foreign",
        "foreign_group",
        "failed_terminal",
        "retained_success",
        "failed_gc",
        "mount",
        "inode",
        "drift",
    ],
)
def test_r1_actual_preowner_cleanup_requires_bound_terminal_empty_unit(monkeypatch, fault):
    import types

    runner = module("ivv_trusted_runner")
    for flag in ("O_DIRECTORY", "O_NOFOLLOW", "O_CLOEXEC"):
        monkeypatch.setattr(runner.os, flag, 0, raising=False)
    book = types.SimpleNamespace(root=Path("/owned"), _write=lambda *a: None)
    unit = "qm-ivv-recovery-connection-000001.service"
    actor = dict(pid=111, start_ticks=12, uid=0, cgroup="/system.slice/" + unit + "/manager")
    fields = dict(Id=unit, MainPID="111", InvocationID="a" * 32)
    terminal = dict(fields, MainPID="0", ActiveState="inactive", SubState="dead")
    if fault == "failed_terminal":
        terminal.update(ActiveState="failed", SubState="failed")
    if fault == "retained_success":
        terminal.update(ActiveState="active", SubState="exited")
    if fault == "failed_gc":
        terminal["InvocationID"] = ""
    if fault == "invocation":
        terminal["InvocationID"] = "b" * 32
    binding = dict(
        connection_attempt_id="connection-000001",
        startup_sha256="a" * 64,
        manager=actor,
        unit=fields,
        group=[1, 2, 16832, 0],
        mount={"id": 5, "namespace": [1, 3, 16832, 0]},
    )

    def process(pid):
        if fault == "active":
            return actor, 1
        raise FileNotFoundError()

    monkeypatch.setattr(runner, "_process", process)
    calls = []

    def query(name, **kwargs):
        calls.append(name)
        return (
            dict(terminal, SubState="exited") if fault == "drift" and len(calls) > 1 else terminal
        )

    monkeypatch.setattr(runner, "_manager_fields", query)
    monkeypatch.setattr(runner, "_cgroup_mount", lambda: 17)
    monkeypatch.setattr(runner, "_mount_id", lambda fd: 18 if fault == "mount" else 17)
    monkeypatch.setattr(
        runner._Scope, "dirs", lambda fd: {"foreign"} if fault == "foreign_group" else set()
    )
    monkeypatch.setattr(runner.os, "open", lambda *a: 80)
    monkeypatch.setattr(
        runner.os,
        "fstat",
        lambda fd: types.SimpleNamespace(st_dev=1, st_ino=2, st_mode=16832, st_uid=0),
    )
    monkeypatch.setattr(runner.Path, "exists", lambda p: False)
    monkeypatch.setattr(
        runner.Path,
        "lstat",
        lambda p: types.SimpleNamespace(
            st_dev=1, st_ino=3 if fault == "inode" else 2, st_mode=16832, st_uid=0
        ),
    )
    monkeypatch.setattr(
        runner,
        "_kread",
        lambda fd, name: (
            ("999" if fault == "foreign" else "") if name == "cgroup.procs" else "populated 0"
        ),
    )
    closed = []
    monkeypatch.setattr(runner, "_close_fd", closed.append)
    stopped = []
    monkeypatch.setattr(runner, "_stop_quiescent_unit", lambda *a: stopped.append(a))
    if fault not in (None, "failed_terminal", "retained_success"):
        with pytest.raises(ValueError):
            runner._recover_preowner(binding, book)
    else:
        assert runner._recover_preowner(binding, book) == dict(
            owned_cleanup_proven=True, external_effects="UNKNOWN", input_publishable=False
        )
    assert bool(stopped) == (fault == "retained_success")
    if fault not in ("active", "invocation", "failed_gc"):
        assert closed == [80]


@pytest.mark.parametrize("fault", ["BOOTSTRAP", "SEED", "ENTRY", "STDIO", "FD_CHECK"])
def test_r1_real_prebootstrap_failure_persists_binding_and_can_recover_owned_state(
    tmp_path, monkeypatch, fault
):
    import contextlib
    import os
    import sys
    from types import SimpleNamespace

    r, task = module("ivv_trusted_runner"), module("ivv_additional_task")
    book = ledger(tmp_path)
    attempt = "connection-000001"
    profile = task.RecoveryProfile(contract, contract.DEFAULT_POLICY, attempt)
    catalog = {k: "a" * 64 for k in r._sources(attempt)}
    method = r.digest(r.raw_json(catalog))
    book.begin(method, now=0)
    events = []
    binding = {"connection_attempt_id": attempt, "modeled_kernel_actor": "same exact actor"}

    @contextlib.contextmanager
    def lease(path):
        events.append("LEASE_HELD")
        try:
            yield SimpleNamespace(fd=73, close=lambda: events.append("LEASE_CLOSED"))
        finally:
            events.append("LEASE_RELEASED")

    monkeypatch.setattr(
        r, "_locations", lambda _: SimpleNamespace(control=tmp_path, ledger=tmp_path)
    )
    monkeypatch.setattr(r, "_recovery_lease", lease)
    monkeypatch.setattr(r, "_preowner_binding", lambda *a: binding)

    def put(path, value):
        task._claim(path, value, sync_dir=lambda _: events.append("FSYNC_DIR"))
        return {"path": str(path), "sha256": r.digest(r.raw_json(value))}

    monkeypatch.setattr(r, "put", put)
    monkeypatch.setattr(r.select, "select", lambda *a: ([0], [], []))
    real_read, real_open = os.read, os.open
    monkeypatch.setattr(
        os,
        "read",
        lambda fd, n: (
            (r.digest(r.raw_json(binding)) + "\n").encode() if fd == 0 else real_read(fd, n)
        ),
    )
    monkeypatch.setattr(
        os,
        "open",
        lambda path, *a, **kw: 90 if str(path) == "/dev/null" else real_open(path, *a, **kw),
    )
    monkeypatch.setattr(os, "O_CLOEXEC", 0, raising=False)
    monkeypatch.setattr(os, "dup2", lambda *a: None)
    monkeypatch.setattr(r, "_close_fd", lambda fd: None if fd == 90 else os.close(fd))
    values = dict(
        _additional=profile, _recovery_mode=attempt, _recovery_task=task, catalog_ref=catalog
    )

    def refuse(code):
        raise r.Refused(code)

    def bootstrap(*a, **kw):
        assert book._read(attempt + ".preowner.json") == binding
        assert "FSYNC_DIR" in events and "LEASE_RELEASED" not in events
        if fault == "BOOTSTRAP":
            refuse(fault)
        return {}, values, None, None, None, None

    monkeypatch.setattr(r, "_bootstrap", bootstrap)
    monkeypatch.setattr(
        r, "_seed", lambda *a, **kw: refuse(fault) if fault == "SEED" else {"started_monotonic": 0}
    )
    if fault == "ENTRY":
        monkeypatch.setattr(task.RecoveryLedger, "enter", lambda *a: refuse(fault))
    monkeypatch.setattr(r, "_stdio", lambda: refuse(fault) if fault == "STDIO" else None)
    monkeypatch.setattr(r, "_fds", lambda: {0, 1, 2, 73, 99})
    original_path = r.Path
    monkeypatch.setattr(
        r,
        "Path",
        lambda p: (
            SimpleNamespace(iterdir=lambda: iter([1]))
            if p == "/proc/self/task"
            else original_path(p)
        ),
    )
    assert r.main(["--recovery-attempt", attempt, "c" * 64]) == 1
    assert events.index("FSYNC_DIR") < events.index("LEASE_RELEASED")
    assert not (tmp_path / (attempt + ".close.json")).exists()
    # External kernel cleanup is modeled; the real missing-child-owner branch,
    # ledger UNKNOWN and cleanup-only receipt are exercised and persisted.
    monkeypatch.setattr(
        r,
        "_recover_preowner",
        lambda *a: dict(
            owned_cleanup_proven=True, external_effects="UNKNOWN", input_publishable=False
        ),
    )
    monkeypatch.setattr(r, "protected", lambda p: None)
    monkeypatch.setattr(os, "O_NOFOLLOW", 0, raising=False)
    monkeypatch.setitem(
        sys.modules, "fcntl", SimpleNamespace(flock=lambda *a: None, LOCK_EX=2, LOCK_NB=4)
    )
    r.recover_previous_attempt(book, lambda path, maximum: path.read_bytes())
    assert book._read(attempt + ".close.json")["owner_state"] == "UNKNOWN"
    assert book._read(attempt + ".recovered.json")["input_publishable"] is False
    with pytest.raises(ValueError, match="unrepaired_structural_failure"):
        book.begin(method, now=1)
    assert (
        book.begin("d" * 64, now=1, expected_connection="connection-000002") == "connection-000002"
    )


@pytest.mark.parametrize(
    "fault", [None, "controller_active", "identity", "dispatch", "unit", "lease"]
)
def test_r1_predispatch_requires_original_controller_exit_and_same_exclusive_claim(
    tmp_path, monkeypatch, fault
):
    from types import SimpleNamespace

    r = module("ivv_trusted_runner")
    book = ledger(tmp_path)
    actor = dict(pid=123, start_ticks=456, uid=0, cgroup="/system.slice/ssh.service")
    binding = dict(
        controller=actor,
        claim_inode=[1, 2, 0o100444, 0],
        unit="qm-ivv-recovery-connection-000001.service",
    )
    attempt = book.begin(
        "a" * 64, now=0, expected_connection="connection-000001", pre_dispatch=binding
    )
    intent = book._read(attempt + ".intent.json")
    lease = r._RecoveryLease(81)
    lease.controller = dict(actor, pid=222)
    book._claim_lease = None if fault == "lease" else lease
    if fault == "dispatch":
        book._write(attempt + ".dispatch.json", {})

    def proc(pid):
        if fault == "controller_active":
            return actor, 1
        if pid == 222:
            return lease.controller, 1
        raise FileNotFoundError()

    monkeypatch.setattr(r, "_controller_actor", proc, raising=False)
    monkeypatch.setattr(r.os, "getpid", lambda: 222)
    monkeypatch.setattr(
        r.os,
        "fstat",
        lambda fd: SimpleNamespace(
            st_dev=1, st_ino=3 if fault == "identity" else 2, st_mode=0o100444, st_uid=0
        ),
    )
    real_lstat = r.Path.lstat
    monkeypatch.setattr(
        r.Path,
        "lstat",
        lambda p: (
            SimpleNamespace(st_dev=1, st_ino=2, st_mode=0o100444, st_uid=0)
            if p.name == "connection-000000.claim-lock.json"
            else real_lstat(p)
        ),
    )
    real_exists = r.Path.exists
    monkeypatch.setattr(
        r.Path,
        "exists",
        lambda p: (
            False if str(p).replace("\\", "/").startswith(("/proc/", "/sys/")) else real_exists(p)
        ),
    )
    monkeypatch.setattr(
        r,
        "_manager_fields",
        lambda unit: dict(
            Id=unit,
            MainPID="0",
            InvocationID="a" * 32 if fault == "unit" else "",
            ActiveState="inactive",
        ),
    )
    if fault:
        with pytest.raises(ValueError):
            r._recover_predispatch(book, intent)
    else:
        assert r._recover_predispatch(book, intent) == dict(
            owned_cleanup_proven=True, external_effects="UNKNOWN", input_publishable=False
        )


def test_r1_normal_parent_close_does_not_skip_terminal_unit_gate(tmp_path):
    book = ledger(tmp_path)
    attempt = book.begin("a" * 64, now=0)
    binding = {"modeled": "exact original manager"}
    book._write(attempt + ".preowner.json", binding)
    book.close(
        attempt,
        dict(
            child_reaped=True,
            recursive_populated=0,
            owned_fds_closed=True,
            resource_limit_event=False,
            active_owned_processes=0,
        ),
        failure=None,
        method_sha256="a" * 64,
    )
    with pytest.raises(ValueError, match="owned_unit_cleanup_unknown"):
        book.begin("a" * 64, now=1)
    book._write(
        attempt + ".unit-cleanup.json",
        dict(
            preowner_sha256=contract.digest(contract.canonical(binding)),
            owned_cleanup_proven=True,
            external_effects="UNKNOWN",
            input_publishable=False,
        ),
    )
    assert book.begin("a" * 64, now=1) == "connection-000002"


def test_r1_predispatch_receipt_uses_same_atomic_intent_and_preserves_debit(tmp_path, monkeypatch):
    import contextlib
    import os
    import sys
    from types import SimpleNamespace

    runner = module("ivv_trusted_runner")
    book = ledger(tmp_path)
    binding = dict(
        controller={"pid": 11},
        claim_inode=[1, 2, 0o100444, 0],
        unit="qm-ivv-recovery-connection-000001.service",
    )
    attempt = book.begin(
        "a" * 64, now=0, expected_connection="connection-000001", pre_dispatch=binding
    )
    original = (tmp_path / (attempt + ".intent.json")).read_bytes()
    monkeypatch.setattr(
        runner, "_locations", lambda _: SimpleNamespace(ledger=tmp_path, control=tmp_path)
    )
    monkeypatch.setattr(runner, "protected", lambda p: None)
    monkeypatch.setattr(runner, "_recovery_lease", lambda *a: contextlib.nullcontext())
    monkeypatch.setattr(os, "O_NOFOLLOW", 0, raising=False)
    monkeypatch.setattr(os, "O_CLOEXEC", 0, raising=False)
    monkeypatch.setitem(
        sys.modules, "fcntl", SimpleNamespace(flock=lambda *a: None, LOCK_EX=2, LOCK_NB=4)
    )
    seen = []

    def kernel(actual_book, intent):
        assert actual_book is book and intent["pre_dispatch"] == binding
        seen.append(intent)
        return dict(owned_cleanup_proven=True, external_effects="UNKNOWN", input_publishable=False)

    monkeypatch.setattr(runner, "_recover_predispatch", kernel)
    runner.recover_previous_attempt(book, lambda p, n: p.read_bytes())
    assert len(seen) == 1 and book._read(attempt + ".close.json")["owner_state"] == "UNKNOWN"
    assert book._read(attempt + ".recovered.json")["owner_binding_sha256"] == contract.digest(
        original
    )
    assert (
        book.begin("a" * 64, now=1, expected_connection="connection-000002") == "connection-000002"
    )
    assert (
        book.usage()["contexts"] == 2
        and (tmp_path / (attempt + ".intent.json")).read_bytes() == original
    )


def test_r1_quiescent_stop_retains_exact_helper_after_wait_uncertainty(monkeypatch):
    from types import SimpleNamespace

    r = module("ivv_trusted_runner")
    events = []
    fields = dict(MainPID="0", SubState="exited")
    monkeypatch.setattr(r, "_manager_fields", lambda *a, **kw: fields)

    class Child:
        def wait(self, timeout):
            events.append("wait")
            if events.count("wait") < 3:
                raise TimeoutError("modeled wait uncertainty")
            return 0

        def poll(self):
            return None

        def kill(self):
            events.append("kill exact helper")

    monkeypatch.setattr(
        r, "subprocess", SimpleNamespace(Popen=lambda *a, **kw: Child(), DEVNULL=-1)
    )
    monkeypatch.setattr(r.time, "sleep", lambda t: None)
    with pytest.raises(TimeoutError):
        r._stop_quiescent_unit("qm-ivv-recovery-connection-000001.service", fields)
    assert events == ["wait", "kill exact helper", "wait", "wait"]
