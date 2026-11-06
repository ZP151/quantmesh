"""Init return information only; pinned SDK functions with modeled external I/O.

No real SDK module/context is imported/constructed. Public SDK AST execution proves
possible control paths, not actual provider behavior or a historical root cause.
"""

import json

import pytest
from test_ivv_recovery_capture import module
from test_ivv_reference_parent_chain import observation, official_reference


class IntAlias(int):
    pass


class Uninspectable:
    def __eq__(self, other):
        pytest.fail("non-int delegate return was inspected")

    def __str__(self):
        pytest.fail("delegate return was rendered")


@pytest.mark.parametrize(
    "returned,want",
    [
        (0, "OK"),
        (-1, "NON_OK"),
        (1, "UNKNOWN"),
        (-2, "UNKNOWN"),
        (False, "UNKNOWN"),
        (True, "UNKNOWN"),
        (IntAlias(0), "UNKNOWN"),
        (IntAlias(-1), "UNKNOWN"),
        (None, "UNKNOWN"),
        ("0", "UNKNOWN"),
        (0.0, "UNKNOWN"),
        ((0, "private"), "UNKNOWN"),
        ([], "UNKNOWN"),
        ({}, "UNKNOWN"),
        (Uninspectable(), "UNKNOWN"),
    ],
)
def test_real_override_preserves_delegate_identity_once_and_order(
    tmp_path, monkeypatch, returned, want
):
    f = official_reference(tmp_path, monkeypatch)
    events = []
    seen = []

    class Base:
        status = f.modules[2].ContextStatus.READY

        def __init__(ctx, **kw):
            seen.append(ctx._init_connect_sync())

        def _init_connect_sync(ctx):
            events.append("delegate")
            return returned

    f.modules[0].OpenQuoteContext = Base
    writer = f.helper._Writer(f.root, lambda _: None)
    observer = f.helper._ReferenceObserver(f.plan, writer, f.clock)
    backend = f.helper._ReferenceBackend(observer, writer, f.plan, f.clock, modules=f.modules)
    initializing = observer.initializing

    def initializing_first():
        events.append("initializing")
        initializing()

    def wire(ctx):
        assert ctx._auto_reconnect is False
        events.append("wire")

    observer.initializing = initializing_first
    backend._install_wire = wire
    assert backend.init_delegate_return == "UNKNOWN"
    backend.open()
    assert events == ["initializing", "wire", "delegate"]
    assert len(seen) == 1 and seen[0] is returned
    assert backend.init_delegate_return == want
    assert backend.constructor_status == "READY"  # Scalar cannot alter READY.


def test_real_override_propagates_same_exception_and_leaves_unknown(tmp_path, monkeypatch):
    f = official_reference(tmp_path, monkeypatch)
    base = f.modules[0].OpenQuoteContext.__mro__[1]
    error = RuntimeError("private-error-must-not-be-rendered")
    calls = []

    def raised(ctx):
        calls.append(ctx)
        raise error

    base._init_connect_sync = raised
    writer = f.helper._Writer(f.root, lambda _: None)
    observer = f.helper._ReferenceObserver(f.plan, writer, f.clock)
    backend = f.helper._ReferenceBackend(observer, writer, f.plan, f.clock, modules=f.modules)
    with pytest.raises(RuntimeError) as caught:
        backend.open()
    assert caught.value is error
    assert calls == [backend.ctx]
    assert backend.init_delegate_return == "UNKNOWN"
    assert backend.constructor_returned is False
    backend.close()


@pytest.mark.parametrize(
    "case,want,ready_seen",
    [("normal", "OK", True), ("drop_ready", "OK", True), ("timeout", "NON_OK", False)],
)
def test_pinned_public_sdk_return_distinguishes_ok_then_not_ready_from_non_ok(
    tmp_path, monkeypatch, case, want, ready_seen
):
    # official_reference/full_transport verifies installed SDK10.10.7008 LF SHA
    # d88cc4786ca26b43717d6addf7dca7ce96ba4478c15d7144ad0f2968d8c0dd0d
    # and executes actual _init_connect_sync/_send_init_connect_sync/handler ASTs.
    f = official_reference(tmp_path, monkeypatch, "timeout" if case == "timeout" else "normal")
    base = f.modules[0].OpenQuoteContext.__mro__[1]
    handled = []
    handler = base._handle_init_connect_rsp

    def handle(ctx, data):
        result = handler(ctx, data)
        handled.append(ctx.status)
        return result

    base._handle_init_connect_rsp = handle
    if case == "drop_ready":

        def reconnected(ctx):
            assert ctx.status == f.modules[2].ContextStatus.READY
            ctx._status = f.modules[2].ContextStatus.CLOSED
            return 0, ""

        base.on_api_socket_reconnected = reconnected
    result = f.helper._run_reference_init(
        f.plan, f.root, backend_factory=f.factory, clock=f.clock, sync_dir=lambda _: None
    )
    assert handled == ([f.modules[2].ContextStatus.READY] if ready_seen else [])
    assert result["schema_id"] == "qm.ivv.reference-init-terminal.v2"
    assert result["init_delegate_return"] == want
    assert result["constructor_status"] == ("READY" if case == "normal" else "NOT_READY")
    assert result["state"] == ("REFERENCE_READY_CLOSED" if case == "normal" else "REFERENCE_FAILED")
    assert all(result["normal_close"].values())
    assert f.transport.writes == 1
    assert f.book.usage()["init_connect"] == 1
    assert f.book.usage()["business_requests"] == f.book.usage()["keepalive"] == 0
    r = module("ivv_trusted_runner")
    error = r._reference_result(result)
    obs = r._reference_from_error(error)
    assert r.reason(error) == "REFERENCE_INIT_OBSERVATION"
    assert obs["schema_id"] == "qm.ivv.reference-init-observation.v2"
    assert obs["init_delegate_return"] == want
    assert obs["operation_failed"] is False and obs["parent_closed"] is False
    assert "PRIVATE" not in json.dumps(result)


def terminal(version, scalar="UNKNOWN", status="NOT_READY"):
    value = dict(
        schema_id="qm.ivv.reference-init-terminal." + version,
        state="REFERENCE_FAILED" if status == "NOT_READY" else "REFERENCE_READY_CLOSED",
        reference_control_sha256="a" * 64,
        source_binding={},
        constructor_returned=True,
        constructor_status=status,
        counts=dict(
            contexts=1, initializations=1, init_sends=1, keepalive_sends=0, business_sends=0
        ),
        normal_close=dict(context_closed=True, callbacks_stopped=True, data_socket_closed=True),
        primary_failure=(
            dict(
                stage="initialize",
                **{"class": "CaptureRejected"},
                code="sdk_initial_connection_failed",
            )
            if status == "NOT_READY"
            else None
        ),
        close_failure=None,
    )
    if version == "v2":
        value["init_delegate_return"] = scalar
    return value


@pytest.mark.parametrize(
    "version,scalar", [("v1", None), ("v2", "OK"), ("v2", "NON_OK"), ("v2", "UNKNOWN")]
)
@pytest.mark.parametrize("status", ["READY", "NOT_READY"])
def test_closed_terminal_to_runner_failure_channel_roundtrip(version, scalar, status):
    h, r = module("capture_opend_ivv_daily"), module("ivv_trusted_runner")
    value = terminal(version, scalar, status)
    selected = h._select_reference_terminal(value)
    assert selected == value
    error = r._reference_result(selected)
    obs = dict(
        observation(),
        schema_id="qm.ivv.reference-init-observation." + version,
        constructor_status=status,
    )
    if version == "v2":
        obs["init_delegate_return"] = scalar
    assert r._reference_from_error(error) == obs
    received = r._child_failure(r._failed_packet(error))
    assert r._failure_record(received) == dict(
        state="STOP", reason="REFERENCE_INIT_OBSERVATION", reference_init_observation=obs
    )
    obs["parent_closed"] = True  # Only the normal owning parent can add this.
    status_value = dict(
        state="STOP",
        reason="REFERENCE_INIT_OBSERVATION",
        unit_returncode=1,
        reference_init_observation=obs,
        stage="RELEASED_RECOVERY_ATTEMPT",
        automatic_retry=False,
        provider_mutation=False,
        publication_sha256="b" * 64,
    )
    assert r.select_failure_status(status_value, "b" * 64)["reference_init_observation"] == obs


@pytest.mark.parametrize("kind", ["terminal", "observation"])
@pytest.mark.parametrize(
    "fault",
    [
        "v1_extra",
        "v2_missing",
        "v3",
        "extra",
        "bad_enum",
        "bool",
        "integer",
        "null",
        "list",
        "str_subclass",
        "schema_list",
    ],
)
def test_versioned_closed_selectors_reject_mismatch_extra_or_invalid_enum(kind, fault):
    h, r = module("capture_opend_ivv_daily"), module("ivv_trusted_runner")
    value = (
        terminal("v2")
        if kind == "terminal"
        else dict(
            observation(),
            schema_id="qm.ivv.reference-init-observation.v2",
            init_delegate_return="UNKNOWN",
        )
    )
    if fault == "v1_extra":
        value["schema_id"] = value["schema_id"].replace(".v2", ".v1")
    elif fault == "v2_missing":
        del value["init_delegate_return"]
    elif fault == "v3":
        value["schema_id"] = value["schema_id"].replace(".v2", ".v3")
    elif fault == "extra":
        value["raw_response"] = "private"
    elif fault == "schema_list":
        del value["init_delegate_return"]
        value["schema_id"] = []
    else:
        value["init_delegate_return"] = {
            "bad_enum": "RAISED",
            "bool": False,
            "integer": 0,
            "null": None,
            "list": [],
            "str_subclass": type("StringAlias", (str,), {})("OK"),
        }[fault]
    selector = (
        h._select_reference_terminal if kind == "terminal" else r.select_reference_observation
    )
    with pytest.raises(ValueError if kind == "terminal" else r.Refused):
        selector(value)
