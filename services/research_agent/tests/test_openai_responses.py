"""Offline Responses protocol + real local ledger, never provider/native proof.

HTTP is an in-memory httpx transport. Integration replaces only the owned
subprocess boundary so that the same HTTP fixture stays inside the test process.
Gateway, graph, store, reservation, response and artifact validation are real.
"""

import asyncio
import importlib
import importlib.util
import json
import os
import pickle
import subprocess
import sys
from dataclasses import FrozenInstanceError
from datetime import timedelta
from decimal import Decimal

import httpx
import pytest
from conftest import publish, succeeded
from pydantic import BaseModel, SecretStr
from qm_research_agent.budgets import EffectLedger, PortfolioBudgetPolicy
from qm_research_agent.orchestrator import ApprovedRemoteGateway
from test_research_jobs import request_for

from quantmesh.ai.errors import ModelConfigurationError, ModelError
from quantmesh.ai.transport import ModelTransport
from quantmesh.ai.wire import ChatMessage, ModelRequest, build_chat_body
from quantmesh.research.job_store import SQLiteJobStore

MODEL = "gpt-6.1-sol"
VERSION = "openai-gpt-6.1-sol-standard-2026-10-13"
ORIGINS = frozenset({"https://api.openai.com"})
KEY = "fixture-explicit-not-a-real-key"
HTTP_CLIENT = httpx.AsyncClient


def provider():
    assert importlib.util.find_spec("qm_research_agent.openai_responses") is not None, (
        "missing service-owned Responses compatibility boundary"
    )
    return importlib.import_module("qm_research_agent.openai_responses")


def gateway(**changes):
    kwargs = dict(key=SecretStr(KEY), allowed_origins=ORIGINS, remote_consent=True)
    kwargs.update(changes)
    return provider().OpenAIResponsesGateway(**kwargs)


def body():
    return build_chat_body(
        model_name=MODEL,
        request=ModelRequest(
            messages=[ChatMessage(role="user", content="Fixture approved report")]
        ),
    )


def completion(text="{}"):
    return {
        "id": "resp_fixture",
        "object": "response",
        "status": "completed",
        "model": MODEL,
        "error": None,
        "incomplete_details": None,
        "service_tier": "default",
        "output": [
            {"type": "reasoning", "id": "rs_fixture", "summary": []},
            {
                "type": "message",
                "id": "msg_fixture",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {"type": "output_text", "text": text, "annotations": [], "logprobs": []}
                ],
            },
        ],
        "usage": {
            "input_tokens": 10,
            "output_tokens": 7,
            "total_tokens": 17,
            "input_tokens_details": {"cached_tokens": 2, "cache_write_tokens": 3},
            "output_tokens_details": {"reasoning_tokens": 4},
        },
    }


@pytest.fixture(autouse=True)
def block_real_network(monkeypatch):
    async def deny(*args, **kwargs):
        raise AssertionError("unmocked network is forbidden in provider tests")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", deny)
    monkeypatch.setattr(
        httpx.HTTPTransport, "handle_request", lambda *a, **k: pytest.fail("network")
    )


def http_fixture(monkeypatch, handler):
    original = HTTP_CLIENT
    calls, clients, options = [], [], []

    def observe(request):
        calls.append(request)
        return handler(request)

    def client(**kwargs):
        options.append(kwargs.copy())
        result = original(**kwargs, transport=httpx.MockTransport(observe))
        clients.append(result)
        return result

    monkeypatch.setattr(httpx, "AsyncClient", client)
    return calls, clients, options


def test_mapping_strict_schema_usage_and_closed_client(monkeypatch):
    calls, clients, options = http_fixture(
        monkeypatch, lambda req: httpx.Response(200, json=completion('{"verdict":"inconclusive"}'))
    )

    class Verdict(BaseModel):
        verdict: str

    model = gateway()
    assert isinstance(model, ApprovedRemoteGateway) and isinstance(model._transport, ModelTransport)
    result = model.complete_structured(
        ModelRequest(messages=[ChatMessage(role="user", content="approved fixture")]), Verdict
    )
    assert result.verdict == "inconclusive"
    encoded = json.loads(calls[0].content)
    assert str(calls[0].url) == "https://api.openai.com/v1/responses"
    assert set(encoded) == {
        "model",
        "input",
        "reasoning",
        "max_output_tokens",
        "store",
        "background",
        "stream",
        "service_tier",
        "text",
    }
    assert encoded["reasoning"] == {"effort": "low"}
    assert encoded["max_output_tokens"] == 1024 and encoded["service_tier"] == "default"
    assert (
        encoded["store"] is False and encoded["background"] is False and encoded["stream"] is False
    )
    assert encoded["text"]["format"]["type"] == "json_schema"
    assert encoded["text"]["format"]["strict"] is True
    assert calls[0].headers["Authorization"] == "Bearer " + KEY
    assert options == [
        {"timeout": 30.0, "verify": True, "trust_env": False, "follow_redirects": False}
    ]
    assert clients[0].is_closed
    response = model.complete(ModelRequest(messages=[ChatMessage(role="user", content="fixture")]))
    assert response.usage == {
        "prompt_tokens": 10,
        "completion_tokens": 7,
        "total_tokens": 17,
        "cached_input_tokens": 2,
        "cache_write_tokens": 3,
        "reasoning_tokens": 4,
    }
    assert response.model_name == MODEL and response.model_version is None


def test_explicit_config_no_env_discovery_pickle_and_frozen_price(monkeypatch):
    for name in (
        "OPENAI_API_KEY",
        "QUANTMESH_MODEL_API_KEY",
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "ALL_PROXY",
        "SSL_CERT_FILE",
    ):
        monkeypatch.setenv(name, "hostile-fixture-must-not-be-used")
    calls, clients, _ = http_fixture(
        monkeypatch, lambda req: httpx.Response(200, json=completion())
    )
    model = pickle.loads(pickle.dumps(gateway()))
    assert KEY not in repr(model) and KEY not in repr(model._transport)
    model._transport.complete(body())
    assert calls[0].headers["Authorization"] == "Bearer " + KEY and clients[0].is_closed
    prices = provider().OpenAIPriceTable()
    assert prices.version == VERSION and prices.model == MODEL and prices.tier == "standard"
    assert (
        prices.input_usd,
        prices.cached_input_usd,
        prices.cache_write_usd,
        prices.output_usd,
    ) == (Decimal("2"), Decimal("0.10"), Decimal("2.50"), Decimal("10"))
    with pytest.raises(FrozenInstanceError):
        prices.output_usd = Decimal("0")


@pytest.mark.parametrize(
    "changes",
    [
        {"key": None},
        {"key": "ambient"},
        {"key": SecretStr("")},
        {"key": SecretStr("bad\r\nkey")},
        {"remote_consent": False},
        {"allowed_origins": frozenset({"https://other.example"})},
        {"model": "unknown"},
        {"model": "gpt-6.1-sol-2026-10-13"},
        {"price_version": "unknown"},
    ],
)
def test_unknown_config_refuses_before_http(monkeypatch, changes):
    calls, _, _ = http_fixture(monkeypatch, lambda req: pytest.fail("unexpected request"))
    with pytest.raises(ModelConfigurationError) as caught:
        gateway(**changes)
    assert KEY not in str(caught.value) and not calls


@pytest.mark.parametrize(
    "change",
    [
        {"model": "other"},
        {"tools": []},
        {"previous_response_id": "secret"},
        {"store": True},
        {"messages": []},
        {"messages": [{"role": "tool", "content": "foo"}]},
        {"messages": [{"role": "user", "content": [{"type": "input_image"}]}]},
        {"max_tokens": True},
        {"max_tokens": 0},
        {"max_tokens": 1025},
        {"temperature": float("nan")},
        {"messages": [{"role": "user", "content": "x" * 65536}]},
        {"response_format": {"type": "json_object"}},
    ],
)
def test_request_boundary_refuses_without_network(monkeypatch, change):
    calls, _, _ = http_fixture(monkeypatch, lambda req: pytest.fail("unexpected request"))
    with pytest.raises(ModelError):
        gateway()._transport.complete({**body(), **change})
    assert not calls


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "incomplete"),
        ("error", {"message": "RAW_ERROR_PROMPT_SENTINEL"}),
        ("incomplete_details", {"reason": "max_output_tokens"}),
        ("model", "unknown-model"),
        ("service_tier", "priority"),
        ("usage", None),
        ("output", []),
    ],
)
def test_incomplete_or_unknown_response_is_sanitized(monkeypatch, field, value):
    payload = completion()
    payload[field] = value
    calls, clients, _ = http_fixture(monkeypatch, lambda req: httpx.Response(200, json=payload))
    with pytest.raises(ModelError) as caught:
        gateway()._transport.complete(body())
    assert "RAW_ERROR_PROMPT_SENTINEL" not in str(caught.value) and KEY not in str(caught.value)
    assert len(calls) == 1 and clients[0].is_closed


@pytest.mark.parametrize(
    "path,value",
    [
        (("input_tokens",), True),
        (("output_tokens",), -1),
        (("total_tokens",), 18),
        (("input_tokens",), 10.0),
        (("input_tokens",), "10"),
        (("output_tokens",), 1025),
        (("input_tokens_details", "cached_tokens"), 11),
        (("input_tokens_details", "cache_write_tokens"), 9),
        (("output_tokens_details", "reasoning_tokens"), 8),
        (("input_tokens_details", "cached_tokens"), None),
        (("output_tokens_details",), {}),
    ],
)
def test_usage_exact_integer_consistency_fail_closed(monkeypatch, path, value):
    payload = completion()
    target = payload["usage"]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    http_fixture(monkeypatch, lambda req: httpx.Response(200, json=payload))
    with pytest.raises(ModelError):
        gateway()._transport.complete(body())


@pytest.mark.parametrize(
    "extra",
    [
        {"type": "function_call", "name": "place_order"},
        {"type": "web_search_call"},
        {"type": "message", "role": "assistant", "status": "completed", "content": []},
    ],
)
def test_tool_or_extra_output_rejects(monkeypatch, extra):
    payload = completion()
    payload["output"].append(extra)
    http_fixture(monkeypatch, lambda req: httpx.Response(200, json=payload))
    with pytest.raises(ModelError):
        gateway()._transport.complete(body())


class Chunks(httpx.AsyncByteStream):
    def __init__(self, chunks, delay=0):
        self.chunks, self.delay, self.closed = chunks, delay, False

    async def __aiter__(self):
        for chunk in self.chunks:
            await asyncio.sleep(self.delay)
            yield chunk

    async def aclose(self):
        self.closed = True


@pytest.mark.parametrize(
    "status,raw,headers",
    [
        (307, b"RAW_ERROR_PROMPT_SENTINEL", {"Location": "https://other.example"}),
        (429, b"RAW_ERROR_PROMPT_SENTINEL", {}),
        (500, b"RAW_ERROR_PROMPT_SENTINEL", {}),
        (200, b"not-json", {}),
        (200, b'{"status":"completed","usage":NaN}', {}),
        (200, b"{}", {"Content-Length": "65537"}),
        (200, b"{}", {"Content-Length": "1"}),
        (200, b"{}", {"Content-Length": "bad"}),
    ],
)
def test_http_failures_no_retry_response_client_close(monkeypatch, status, raw, headers):
    stream = Chunks([raw])
    calls, clients, _ = http_fixture(
        monkeypatch, lambda req: httpx.Response(status, headers=headers, stream=stream)
    )
    with pytest.raises(ModelError) as caught:
        gateway()._transport.complete(body())
    assert len(calls) == 1 and clients[0].is_closed and stream.closed
    assert "RAW_ERROR_PROMPT_SENTINEL" not in str(caught.value) and KEY not in str(caught.value)


def test_streamed_excess_and_aggregate_deadline(monkeypatch):
    module = provider()
    oversized = Chunks([b"x" * 32768] * 3)
    calls, clients, _ = http_fixture(
        monkeypatch,
        lambda req: httpx.Response(200, headers={"Content-Length": "1"}, stream=oversized),
    )
    with pytest.raises(ModelError):
        gateway()._transport.complete(body())
    assert len(calls) == 1 and oversized.closed and clients[0].is_closed
    # Exercise the real aggregate deadline with a short test-only bound.
    monkeypatch.setattr(module, "HTTP_DEADLINE_SECONDS", 0.01)
    slow = Chunks([b"{}"], delay=0.05)
    calls, clients, _ = http_fixture(monkeypatch, lambda req: httpx.Response(200, stream=slow))
    with pytest.raises(ModelError):
        gateway()._transport.complete(body())
    assert len(calls) == 1 and slow.closed and clients[0].is_closed


def setup_loop(monkeypatch, store, handler, *, cap="50"):
    calls, clients, _ = http_fixture(monkeypatch, handler)
    effects = EffectLedger(
        store,
        policy=PortfolioBudgetPolicy("openai-offline-fixture", Decimal(cap), Decimal("200")),
        category="operating",
    )
    engine, model = provider().make_openai_advisory(
        store, effects, key=SecretStr(KEY), allowed_origins=ORIGINS, remote_consent=True
    )
    import qm_research_agent.orchestrator as orchestrator

    monkeypatch.setattr(
        orchestrator, "bounded_complete", lambda model, request, budget: model.complete(request)
    )
    return engine, model, effects, calls, clients


def test_actual_runner_reserves_before_http_and_replays_after_reopen(local, monkeypatch):
    store, lake, clock = local
    job, ref = succeeded(store, lake)
    observed = []

    def handle(request):
        with store._transaction() as con:
            observed.append(con.execute("SELECT price,status FROM model_effects").fetchall())
        return httpx.Response(
            200,
            json=completion(
                json.dumps(
                    {
                        "verdict": "inconclusive",
                        "summary": "OFFLINE_HTTP_FIXTURE_ONLY",
                        "citations": [ref.artifact_id],
                    }
                )
            ),
        )

    engine, model, effects, calls, clients = setup_loop(monkeypatch, store, handle)
    assert engine.price == Decimal("1.00") and engine.price_version == VERSION
    lease = store.claim_analysis("first", clock[0])
    original = engine.run_analysis(job, ref, model, lease=lease)
    assert (
        original.state == "succeeded" and original.provider == "openai" and original.model == MODEL
    )
    assert original.usage.input_tokens == 10 and original.usage.output_tokens == 7
    assert original.estimated_price_version == VERSION and original.citations == [ref]
    assert observed == [[("1", "reserved")]] and clients[0].is_closed
    output = (store.artifact_root / original.output_artifact.object_key).read_bytes()
    assert b"OFFLINE_HTTP_FIXTURE_ONLY" in output
    clock[0] += timedelta(seconds=61)
    reopened = SQLiteJobStore(store.path, lake_root=lake, clock=lambda: clock[0])
    replacement = reopened.claim_analysis("restarted", clock[0])
    effects = EffectLedger(reopened, policy=effects.policy, category=effects.category)
    restarted, same_model = provider().make_openai_advisory(
        reopened, effects, key=SecretStr(KEY), allowed_origins=ORIGINS, remote_consent=True
    )
    assert restarted.run_analysis(job, ref, same_model, lease=replacement) == original
    assert len(calls) == 1 and reopened.finish_analysis(replacement, original)
    assert reopened.get("operator", job.job_id).state == "succeeded"


@pytest.mark.parametrize("category", ["operating", "development"])
def test_portfolio_exhaustion_zero_http_calls(local, monkeypatch, category):
    store, lake, clock = local
    job, ref = succeeded(store, lake)
    calls, _, _ = http_fixture(monkeypatch, lambda req: pytest.fail("unexpected HTTP"))
    policy = PortfolioBudgetPolicy("openai-offline-fixture", Decimal("0"), Decimal("0"))
    effects = EffectLedger(store, policy=policy, category=category)
    engine, model = provider().make_openai_advisory(
        store, effects, key=SecretStr(KEY), allowed_origins=ORIGINS, remote_consent=True
    )
    lease = store.claim_analysis("first", clock[0])
    result = engine.run_analysis(job, ref, model, lease=lease)
    assert result.error_code == "budget_exhausted" and result.provider is None and not calls
    assert effects.read(job.job_id, ref.sha256) is None


@pytest.mark.parametrize("budget", [{"max_model_calls": 0}, {"max_estimated_model_usd": 0.5}])
def test_unknown_price_and_per_job_call_cap_zero_http(local, monkeypatch, budget):
    store, lake, clock = local
    job = store.submit(
        "operator",
        "zero",
        request_for(lake, analysis_requested=True, budget=budget),
    )
    ref = publish(store, job)
    engine, model, effects, calls, _ = setup_loop(
        monkeypatch, store, lambda req: pytest.fail("unexpected HTTP")
    )
    lease = store.claim_analysis("first", clock[0])
    result = engine.run_analysis(store.get("operator", job.job_id), ref, model, lease=lease)
    assert result.error_code == "budget_exhausted" and not calls
    engine.price = None
    result = engine.run_analysis(job, ref, model, lease=lease)
    assert result.error_code == "model_unavailable" and not calls
    assert effects.read(job.job_id, ref.sha256) is None


def test_explicit_refusal_content_is_never_success(monkeypatch):
    payload = completion()
    payload["output"][1]["content"] = [{"type": "refusal", "refusal": "RAW_REFUSAL_SENTINEL"}]
    calls, clients, _ = http_fixture(monkeypatch, lambda req: httpx.Response(200, json=payload))
    with pytest.raises(ModelError) as caught:
        gateway()._transport.complete(body())
    assert "RAW_REFUSAL_SENTINEL" not in str(caught.value)
    assert len(calls) == 1 and clients[0].is_closed


@pytest.mark.skipif(sys.platform != "linux", reason="owned resolver acceptance requires Linux")
@pytest.mark.parametrize("use_owned_resolver", [False, True])
def test_stalled_dns_executor_cannot_extend_synchronous_deadline(tmp_path, use_owned_resolver):
    # Actual owned Python process, fake DNS executor only; no real DNS/API call.
    code = r"""
import asyncio,json,time,httpx,socket
from pydantic import SecretStr
from quantmesh.ai.wire import ModelRequest,ChatMessage,build_chat_body
from qm_research_agent import openai_responses as p
p.HTTP_DEADLINE_SECONDS=0.3
def fake_dns(*args,**kwargs):
    time.sleep(5)
    raise RuntimeError('fixture resolver stopped')
socket.getaddrinfo=fake_dns
# The real HTTP backend's resolver helper is also stalled, without real DNS.
# On the old implementation, parent loop.getaddrinfo blocks its executor.
p._DNS_PROGRAM=DNS_PROGRAM_FIXTURE
RESOLVER_SELECTION_FIXTURE
transport=p.OpenAIResponsesTransport(key=SecretStr('fixture-explicit-not-a-real-key'),
    allowed_origins=frozenset({'https://api.openai.com'}),remote_consent=True)
request=build_chat_body(model_name='gpt-6.1-sol',request=ModelRequest(messages=[ChatMessage(role='user',content='fixture')]))
started=time.monotonic()
try: transport.complete(request)
except Exception as error:
    print(json.dumps({'seconds':time.monotonic()-started,'error':str(error)}),flush=True)
"""
    resolver_pid = tmp_path / "resolver.pid"
    fake_resolver = (
        f"import os,time; open({str(resolver_pid)!r},'w').write(str(os.getpid())); time.sleep(3)"
    )
    code = code.replace("DNS_PROGRAM_FIXTURE", repr(fake_resolver))
    code = code.replace(
        "RESOLVER_SELECTION_FIXTURE",
        "" if use_owned_resolver else "p._owned_resolver=lambda client:None",
    )
    env = {
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": os.pathsep.join(sys.path),
        "HOME": str(tmp_path),
    }
    process = subprocess.Popen(
        [sys.executable, "-B", "-c", code], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    try:
        try:
            stdout, stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            pytest.fail("synchronous transport exceeded deadline while resolver executor shut down")
        assert process.returncode == 0, stderr.decode()
        (tmp_path / "caller-receipt.json").write_bytes(stdout)
        elapsed = json.loads(stdout)["seconds"]
        if use_owned_resolver:
            assert elapsed < 1.0
            assert resolver_pid.exists(), "stalled owned resolver actually started"
            with pytest.raises(ProcessLookupError):
                os.kill(int(resolver_pid.read_text()), 0)
        else:
            # The control documents the actual bug, rather than counting cold
            # interpreter imports inside an arbitrary parent timeout.
            assert elapsed >= 4.5
            assert not resolver_pid.exists()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        process.stdout.close()
        process.stderr.close()


@pytest.mark.skipif(sys.platform != "linux", reason="owned resolver acceptance requires Linux")
def test_owned_resolver_ignores_caller_module_shadow(tmp_path, monkeypatch):
    module = provider()
    marker = tmp_path / "unexpected-caller-import"
    (tmp_path / "socket.py").write_text(
        f"from pathlib import Path; Path({str(marker)!r}).write_text('loaded')\n"
    )
    monkeypatch.chdir(tmp_path)
    # This actual stdlib child imports socket but never performs DNS or TCP.
    monkeypatch.setattr(
        module, "_DNS_PROGRAM", "import socket,json; print(json.dumps(['1.1.1.1']))"
    )
    sentinel = object()

    class NumericEdge:
        async def connect_tcp(self, host, port, **kwargs):
            assert (host, port) == ("1.1.1.1", 443)
            return sentinel

    result = asyncio.run(
        module._OwnedResolverBackend(NumericEdge()).connect_tcp("api.openai.com", 443)
    )
    assert result is sentinel
    assert not marker.exists(), "resolver imported a module from the caller directory"


@pytest.mark.skipif(sys.platform != "linux", reason="owned resolver acceptance requires Linux")
def test_owned_resolver_numeric_address_no_secret_in_child(monkeypatch):
    module = provider()
    # Execute an owned stdlib resolver fixture, then stop at the mock TCP edge.
    # No DNS, TCP or TLS handshake occurs, and the original HTTP origin stays
    # with httpcore rather than becoming a caller-supplied endpoint.
    monkeypatch.setattr(module, "_DNS_PROGRAM", "import json; print(json.dumps(['1.1.1.1']))")
    observed = []
    sentinel = object()

    class NumericEdge:
        async def connect_tcp(self, host, port, **kwargs):
            observed.append((host, port))
            return sentinel

    result = asyncio.run(
        module._OwnedResolverBackend(NumericEdge()).connect_tcp("api.openai.com", 443)
    )
    assert result is sentinel and observed == [("1.1.1.1", 443)]


def test_timeout_retains_unknown_effect_across_reconstruction(local, monkeypatch):
    store, lake, clock = local
    job, ref = succeeded(store, lake)

    def timeout(request):
        raise httpx.ReadTimeout("RAW_ERROR_PROMPT_SENTINEL", request=request)

    engine, model, effects, calls, clients = setup_loop(monkeypatch, store, timeout)
    lease = store.claim_analysis("first", clock[0])
    result = engine.run_analysis(job, ref, model, lease=lease)
    assert result.error_code == "unknown_effect" and result.usage.estimated_model_usd is None
    assert effects.read(job.job_id, ref.sha256)[0] == "reserved"
    assert len(calls) == 1 and clients[0].is_closed
    clock[0] += timedelta(seconds=61)
    replacement = store.claim_analysis("restart", clock[0])
    reconstructed, model = provider().make_openai_advisory(
        store,
        EffectLedger(store, policy=effects.policy, category=effects.category),
        key=SecretStr(KEY),
        allowed_origins=ORIGINS,
        remote_consent=True,
    )
    assert (
        reconstructed.run_analysis(job, ref, model, lease=replacement).error_code
        == "unknown_effect"
    )
    assert len(calls) == 1 and store.finish_analysis(replacement, result)
    assert store.get("operator", job.job_id).state == "succeeded"
