"""Model gateway tests (M8, issue #45, Phase A).

The gateway surface: wire models and the fail-closed decoder, the
scripted transport (deterministic records + JSONL scripts with line
attribution), the httpx live transport (loopback posture, key
redaction, never touching the network — httpx is faked), and the
gateway's structured path (parse + pydantic validation at the
boundary, no partial object escape).
"""

import json
import sys
import types

import httpx
import pytest
from pydantic import BaseModel, Field, ValidationError

from quantmesh.ai.errors import (
    ModelConfigurationError,
    ModelOutputError,
    ModelProtocolError,
    ModelUnavailableError,
)
from quantmesh.ai.gateway import ModelGateway
from quantmesh.ai.transport import (
    DEFAULT_CHAT_PATH,
    MODEL_API_KEY_ENV,
    HttpModelTransport,
    ScriptedModelTransport,
)
from quantmesh.ai.wire import (
    ChatMessage,
    ModelRequest,
    build_chat_body,
    parse_completion,
)
from quantmesh.settings import settings

MODEL = "fixture-model"
KEY = "0123456789abcdef" * 2  # 32 chars, key-like
PROMPT = "analyze this market"


class AnalystClaim(BaseModel):
    statement: str
    confidence: float = Field(ge=0.0, le=1.0)


def _request(text: str = PROMPT) -> ModelRequest:
    return ModelRequest(messages=[ChatMessage(role="user", content=text)])


def _scripted(*records: dict) -> ScriptedModelTransport:
    return ScriptedModelTransport(list(records))


def _gateway(*records: dict) -> ModelGateway:
    return ModelGateway(_scripted(*records), model_name=MODEL)


def _completion_payload(
    content: str,
    *,
    model: str | None = MODEL,
    finish_reason: str | None = "stop",
    usage: dict | None = None,
) -> dict:
    return {
        "choices": [{"message": {"content": content}, "finish_reason": finish_reason}],
        "model": model,
        "usage": usage,
    }


class TestWireModels:
    def test_message_role_literal(self) -> None:
        assert ChatMessage(role="system", content="you are a critic").role == "system"
        with pytest.raises(ValidationError):
            ChatMessage(role="god", content="hi")

    def test_message_empty_content_refused(self) -> None:
        with pytest.raises(ValidationError):
            ChatMessage(role="user", content="")

    def test_request_min_one_message(self) -> None:
        with pytest.raises(ValidationError):
            ModelRequest(messages=[])

    def test_request_temperature_bounds(self) -> None:
        with pytest.raises(ValidationError):
            ModelRequest(messages=[ChatMessage(role="user", content="x")], temperature=2.5)
        with pytest.raises(ValidationError):
            ModelRequest(messages=[ChatMessage(role="user", content="x")], temperature=-0.1)
        assert ModelRequest(messages=[ChatMessage(role="user", content="x")], temperature=0.0)

    def test_request_max_tokens_bounds(self) -> None:
        with pytest.raises(ValidationError):
            ModelRequest(messages=[ChatMessage(role="user", content="x")], max_tokens=0)
        with pytest.raises(ValidationError):
            ModelRequest(messages=[ChatMessage(role="user", content="x")], max_tokens=-5)


class TestBuildChatBody:
    def test_canonical_shape(self) -> None:
        request = _request()
        body = build_chat_body(model_name=MODEL, request=request)
        assert body["model"] == MODEL
        assert body["messages"] == [{"role": "user", "content": PROMPT}]
        assert body["temperature"] == 0.0
        assert body["max_tokens"] == 1024
        assert "response_format" not in body

    def test_temperature_and_max_tokens_passthrough(self) -> None:
        request = ModelRequest(
            messages=[
                ChatMessage(role="system", content="critic"),
                ChatMessage(role="user", content="x"),
            ],
            temperature=0.7,
            max_tokens=64,
        )
        body = build_chat_body(model_name=MODEL, request=request)
        assert body["temperature"] == 0.7
        assert body["max_tokens"] == 64
        assert [m["role"] for m in body["messages"]] == ["system", "user"]

    def test_structured_carries_json_schema(self) -> None:
        body = build_chat_body(model_name=MODEL, request=_request(), schema=AnalystClaim)
        response_format = body["response_format"]
        assert response_format["type"] == "json_schema"
        schema = response_format["json_schema"]
        assert schema["name"] == "AnalystClaim"
        assert schema["strict"] is True
        confidence = schema["schema"]["properties"]["confidence"]
        assert confidence["type"] == "number"
        assert confidence["minimum"] == 0.0
        assert confidence["maximum"] == 1.0

    def test_structured_absent_without_schema(self) -> None:
        body = build_chat_body(model_name=MODEL, request=_request())
        assert "response_format" not in body


class TestParseCompletion:
    def test_happy_path(self) -> None:
        response = parse_completion(
            _completion_payload("hello", usage={"prompt_tokens": 3, "completion_tokens": 1}),
            model_name=MODEL,
        )
        assert response.content == "hello"
        assert response.model_name == MODEL
        assert response.finish_reason == "stop"
        assert response.usage == {"prompt_tokens": 3, "completion_tokens": 1}

    def test_model_falls_back_to_caller_name(self) -> None:
        payload = _completion_payload("hello", model=None)
        assert parse_completion(payload, model_name=MODEL).model_name == MODEL

    def test_wire_model_wins(self) -> None:
        payload = _completion_payload("hello", model="wire-model")
        assert parse_completion(payload, model_name=MODEL).model_name == "wire-model"

    def test_optional_fields_default(self) -> None:
        response = parse_completion({"choices": [{"message": {"content": "x"}}]}, model_name=MODEL)
        assert response.model_name == MODEL
        assert response.finish_reason is None
        assert response.usage is None

    def test_non_mapping_payload(self) -> None:
        with pytest.raises(ModelProtocolError, match="not a mapping"):
            parse_completion(["choices"], model_name=MODEL)

    def test_missing_choices(self) -> None:
        with pytest.raises(ModelProtocolError, match="no choices"):
            parse_completion({"other": 1}, model_name=MODEL)

    def test_empty_choices(self) -> None:
        with pytest.raises(ModelProtocolError, match="no choices"):
            parse_completion({"choices": []}, model_name=MODEL)

    def test_choice_not_a_mapping(self) -> None:
        with pytest.raises(ModelProtocolError, match="choice is not a mapping"):
            parse_completion({"choices": ["x"]}, model_name=MODEL)

    def test_missing_message(self) -> None:
        with pytest.raises(ModelProtocolError, match="no message mapping"):
            parse_completion({"choices": [{"finish_reason": "stop"}]}, model_name=MODEL)

    def test_content_not_a_string(self) -> None:
        with pytest.raises(ModelProtocolError, match="content is not a string"):
            parse_completion(
                {"choices": [{"message": {"content": 42}}]}, model_name=MODEL
            )

    def test_finish_reason_not_a_string(self) -> None:
        with pytest.raises(ModelProtocolError, match="finish_reason is not a string"):
            parse_completion(
                {"choices": [{"message": {"content": "x"}, "finish_reason": 7}]},
                model_name=MODEL,
            )

    def test_usage_not_integer_mapping(self) -> None:
        with pytest.raises(ModelProtocolError, match="usage is not a mapping of integers"):
            parse_completion(
                {"choices": [{"message": {"content": "x"}}], "usage": {"n": "many"}},
                model_name=MODEL,
            )

    def test_wire_model_not_a_string(self) -> None:
        with pytest.raises(ModelProtocolError, match="reported model name is not a string"):
            parse_completion(
                {"choices": [{"message": {"content": "x"}}], "model": 3}, model_name=MODEL
            )


class TestScriptedModelTransport:
    def test_records_replay_in_order(self) -> None:
        transport = _scripted(
            {"content": "first", "model": MODEL},
            {"content": "second", "model": MODEL, "finish_reason": "length"},
        )
        assert transport.complete({})["choices"][0]["message"]["content"] == "first"
        second = transport.complete({})
        assert second["choices"][0]["message"]["content"] == "second"
        assert second["choices"][0]["finish_reason"] == "length"

    def test_seen_bodies_recorded(self) -> None:
        transport = _scripted({"content": "x"})
        body = {"model": MODEL, "messages": []}
        transport.complete(body)
        assert transport.seen_bodies == [body]

    def test_from_script_round_trip(self, tmp_path) -> None:
        script = tmp_path / "script.jsonl"
        script.write_text(
            '{"content": "a", "model": "m1"}\n{"content": "b"}\n\n', encoding="utf-8"
        )
        transport = ScriptedModelTransport.from_script(script)
        assert transport.complete({})["choices"][0]["message"]["content"] == "a"
        assert transport.complete({})["model"] is None
        with pytest.raises(ModelUnavailableError, match="script exhausted after 2 responses"):
            transport.complete({})

    def test_from_script_bad_json_line_attribution(self, tmp_path) -> None:
        script = tmp_path / "script.jsonl"
        script.write_text('{"content": "a"}\nnot json\n', encoding="utf-8")
        with pytest.raises(ModelProtocolError, match="script line 2 is not JSON"):
            ScriptedModelTransport.from_script(script)

    def test_from_script_non_mapping_line_attribution(self, tmp_path) -> None:
        script = tmp_path / "script.jsonl"
        script.write_text("[1, 2]\n", encoding="utf-8")
        with pytest.raises(ModelProtocolError, match="script line 1 is not a mapping"):
            ScriptedModelTransport.from_script(script)

    def test_invalid_record_not_a_mapping(self) -> None:
        with pytest.raises(ModelProtocolError, match="script record 1 is not a mapping"):
            _scripted("content")  # type: ignore[arg-type]

    def test_record_missing_content(self) -> None:
        with pytest.raises(ModelProtocolError, match="script record 2 carries no string content"):
            _scripted({"content": "a"}, {"model": MODEL})

    def test_record_non_string_content(self) -> None:
        with pytest.raises(ModelProtocolError, match="script record 1 carries no string content"):
            _scripted({"content": 42})

    def test_payload_escape_hatch(self) -> None:
        transport = _scripted({"payload": {"choices": [{"message": {"content": "raw"}}]}})
        assert transport.complete({}) == {"choices": [{"message": {"content": "raw"}}]}

    def test_payload_mixed_with_other_fields_refused(self) -> None:
        with pytest.raises(ModelProtocolError, match="mixes payload with other fields"):
            _scripted({"payload": {"x": 1}, "content": "y"})

    def test_exhaustion_refuses_with_count(self) -> None:
        transport = _scripted({"content": "a"})
        transport.complete({})
        with pytest.raises(ModelUnavailableError, match="script exhausted after 1 responses"):
            transport.complete({})


class _FakeHttpx:
    """Fake httpx module for the faked-import guard: a scriptable Client."""

    def __init__(self, responses: list, raise_error: Exception | None = None) -> None:
        self.responses = responses
        self.raise_error = raise_error
        self.calls: list[tuple[str, dict | None, dict | None]] = []
        self.constructed_timeout: float | None = None

    def install(self, monkeypatch) -> None:
        module = types.ModuleType("httpx")
        module.Client = lambda timeout=None: self._client(timeout)
        module.ConnectError = _FakeConnectError
        monkeypatch.setitem(sys.modules, "httpx", module)

    def _client(self, timeout: float | None) -> "_FakeClient":
        self.constructed_timeout = timeout
        return _FakeClient(self)

    def post(self, url: str, *, json: dict | None = None, headers: dict | None = None):
        if self.raise_error is not None:
            raise self.raise_error
        self.calls.append((url, json, headers))
        response = self.responses.pop(0)
        if hasattr(response, "status_code"):
            return response
        return httpx.Response(200, json=response)


class _FakeClient:
    def __init__(self, fake: _FakeHttpx) -> None:
        self._fake = fake

    def post(self, url: str, *, json: dict | None = None, headers: dict | None = None):
        return self._fake.post(url, json=json, headers=headers)


class _FakeConnectError(Exception):
    pass


def _install_fake_httpx(monkeypatch, responses=None, raise_error=None) -> _FakeHttpx:
    fake = _FakeHttpx(responses or [], raise_error=raise_error)
    fake.install(monkeypatch)
    return fake


class TestHttpModelTransport:
    def test_loopback_hosts_accepted(self) -> None:
        for url in (
            "http://127.0.0.1:11434",
            "http://localhost:11434",
            "http://[::1]:11434",
        ):
            transport = HttpModelTransport(base_url=url)
            assert "loopback" not in repr(transport)  # constructed fine

    def test_remote_refused_without_allow_remote(self) -> None:
        with pytest.raises(
            ModelConfigurationError,
            match=r"host 'api\.example\.com' is not loopback.*allow_remote=True",
        ):
            HttpModelTransport(base_url="https://api.example.com/v1")

    def test_remote_accepted_with_allow_remote(self) -> None:
        transport = HttpModelTransport(
            base_url="https://api.example.com/v1", allow_remote=True
        )
        assert "api.example.com" in repr(transport)

    def test_non_http_scheme_refused(self) -> None:
        with pytest.raises(ModelConfigurationError, match="must be http\\(s\\)"):
            HttpModelTransport(base_url="ftp://127.0.0.1/models")

    def test_missing_host_refused(self) -> None:
        with pytest.raises(ModelConfigurationError, match="carries no host"):
            HttpModelTransport(base_url="http://")

    def test_defaults_to_settings_url(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "model_gateway_url", "http://127.0.0.1:8080")
        transport = HttpModelTransport()
        assert "127.0.0.1:8080" in repr(transport)

    def test_key_from_env(self, monkeypatch) -> None:
        monkeypatch.setenv(MODEL_API_KEY_ENV, KEY)
        transport = HttpModelTransport()
        assert "key=set" in repr(transport)

    def test_explicit_key_wins_over_env(self, monkeypatch) -> None:
        monkeypatch.setenv(MODEL_API_KEY_ENV, "env-secret")
        transport = HttpModelTransport(api_key=KEY)
        assert "env-secret" not in repr(transport)
        assert "key=set" in repr(transport)

    def test_repr_never_contains_key(self, monkeypatch) -> None:
        monkeypatch.setenv(MODEL_API_KEY_ENV, KEY)
        transport = HttpModelTransport()
        assert KEY not in repr(transport)
        assert KEY not in str(transport)

    def test_construction_error_never_contains_key(self, monkeypatch) -> None:
        monkeypatch.setenv(MODEL_API_KEY_ENV, KEY)
        with pytest.raises(ModelConfigurationError) as caught:
            HttpModelTransport(base_url="https://api.example.com/v1")
        assert KEY not in str(caught.value)

    def test_complete_happy_path(self, monkeypatch) -> None:
        fake = _install_fake_httpx(
            monkeypatch,
            responses=[_completion_payload("hello", usage={"prompt_tokens": 3})],
        )
        transport = HttpModelTransport(api_key=KEY)
        payload = transport.complete({"model": MODEL, "messages": []})
        url, body, headers = fake.calls[0]
        assert url == f"http://127.0.0.1:11434{DEFAULT_CHAT_PATH}"
        assert body == {"model": MODEL, "messages": []}
        assert headers == {"Authorization": f"Bearer {KEY}"}
        assert payload["choices"][0]["message"]["content"] == "hello"

    def test_complete_without_key_sends_no_header(self, monkeypatch) -> None:
        fake = _install_fake_httpx(monkeypatch, responses=[_completion_payload("x")])
        HttpModelTransport().complete({"model": MODEL})
        assert fake.calls[0][2] is None

    def test_key_appears_only_in_header(self, monkeypatch) -> None:
        fake = _install_fake_httpx(monkeypatch, responses=[_completion_payload("x")])
        body = {"model": MODEL, "messages": [{"role": "user", "content": PROMPT}]}
        HttpModelTransport(api_key=KEY).complete(body)
        _, sent_body, headers = fake.calls[0]
        assert headers == {"Authorization": f"Bearer {KEY}"}
        assert KEY not in json.dumps(sent_body)

    def test_http_refusal(self, monkeypatch) -> None:
        import httpx

        _install_fake_httpx(
            monkeypatch, responses=[httpx.Response(400, text="bad request")]
        )
        with pytest.raises(ModelUnavailableError, match=r"refused \(HTTP 400\): 'bad request'"):
            HttpModelTransport().complete({"model": MODEL})

    def test_non_json_body(self, monkeypatch) -> None:
        import httpx

        _install_fake_httpx(monkeypatch, responses=[httpx.Response(200, text="<html>")])
        with pytest.raises(ModelUnavailableError, match="non-JSON body"):
            HttpModelTransport().complete({"model": MODEL})

    def test_transport_error_wrapped(self, monkeypatch) -> None:
        _install_fake_httpx(
            monkeypatch, raise_error=_FakeConnectError("connection refused")
        )
        with pytest.raises(ModelUnavailableError, match="connection refused"):
            HttpModelTransport().complete({"model": MODEL})

    def test_request_timeout_plumbed(self, monkeypatch) -> None:
        fake = _install_fake_httpx(monkeypatch, responses=[_completion_payload("x")])
        HttpModelTransport(request_timeout_s=3.5).complete({"model": MODEL})
        assert fake.constructed_timeout == 3.5


class TestModelGateway:
    def test_complete_happy_path(self) -> None:
        gateway = _gateway({"content": "answer", "model": MODEL, "finish_reason": "stop"})
        response = gateway.complete(_request())
        assert response.content == "answer"
        assert response.model_name == MODEL
        assert response.finish_reason == "stop"

    def test_complete_sends_canonical_body(self) -> None:
        transport = _scripted({"content": "answer"})
        gateway = ModelGateway(transport, model_name=MODEL)
        gateway.complete(_request())
        body = transport.seen_bodies[0]
        assert body["model"] == MODEL
        assert body["messages"] == [{"role": "user", "content": PROMPT}]
        assert "response_format" not in body

    def test_model_name_from_settings(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "model_name", MODEL)
        gateway = ModelGateway(_scripted({"content": "x"}))
        assert gateway.model_name == MODEL
        assert gateway.complete(_request()).content == "x"

    def test_missing_model_refused_at_call(self) -> None:
        gateway = ModelGateway(_scripted({"content": "x"}))
        with pytest.raises(ModelConfigurationError, match="no model name configured"):
            gateway.complete(_request())

    def test_non_string_model_refused(self) -> None:
        with pytest.raises(ModelConfigurationError, match="model name must be a string"):
            ModelGateway(_scripted({"content": "x"}), model_name=7)  # type: ignore[arg-type]

    def test_structured_happy_path(self) -> None:
        gateway = _gateway(
            {"content": json.dumps({"statement": "up", "confidence": 0.8})}
        )
        claim = gateway.complete_structured(_request(), AnalystClaim)
        assert claim.statement == "up"
        assert claim.confidence == 0.8

    def test_structured_sends_json_schema(self) -> None:
        transport = _scripted(
            {"content": json.dumps({"statement": "up", "confidence": 0.8})}
        )
        gateway = ModelGateway(transport, model_name=MODEL)
        gateway.complete_structured(_request(), AnalystClaim)
        response_format = transport.seen_bodies[0]["response_format"]
        assert response_format["type"] == "json_schema"
        assert response_format["json_schema"]["name"] == "AnalystClaim"

    def test_structured_non_json_output(self) -> None:
        gateway = _gateway({"content": "sure, up"})
        with pytest.raises(ModelOutputError, match="output is not JSON"):
            gateway.complete_structured(_request(), AnalystClaim)

    def test_structured_empty_output(self) -> None:
        gateway = _gateway({"content": ""})
        with pytest.raises(ModelOutputError, match="empty response"):
            gateway.complete_structured(_request(), AnalystClaim)

    def test_structured_schema_violation_names_fields(self) -> None:
        gateway = _gateway({"content": json.dumps({"statement": "up", "confidence": 7})})
        with pytest.raises(ModelOutputError, match="confidence"):
            gateway.complete_structured(_request(), AnalystClaim)

    def test_structured_missing_field(self) -> None:
        gateway = _gateway({"content": json.dumps({"confidence": 0.5})})
        with pytest.raises(ModelOutputError, match="statement"):
            gateway.complete_structured(_request(), AnalystClaim)

    def test_structured_no_partial_object(self) -> None:
        gateway = _gateway({"content": "not json"})
        with pytest.raises(ModelOutputError):
            gateway.complete_structured(_request(), AnalystClaim)

    def test_structured_model_name_required(self) -> None:
        gateway = ModelGateway(_scripted({"content": "{}"}))
        with pytest.raises(ModelConfigurationError, match="no model name configured"):
            gateway.complete_structured(_request(), AnalystClaim)

    def test_repr_no_key_material(self) -> None:
        assert KEY not in repr(_gateway({"content": "x"}))


class TestRedactionScan:
    """M5 wallet-isolation discipline: the key never surfaces anywhere."""

    def test_key_absent_from_all_failure_surfaces(self, monkeypatch) -> None:
        monkeypatch.setenv(MODEL_API_KEY_ENV, KEY)
        # The transport fails through the real wrapped-exception path
        # (faked httpx raising a connect error) — no network is touched.
        _install_fake_httpx(
            monkeypatch, raise_error=_FakeConnectError("connection refused")
        )
        transport = HttpModelTransport(base_url="http://127.0.0.1:1")
        surfaces: list[str] = [repr(transport), str(transport)]
        gateway = ModelGateway(transport, model_name=MODEL)
        surfaces.append(repr(gateway))
        for trigger in (
            lambda: gateway.complete(_request()),
            lambda: gateway.complete_structured(_request(), AnalystClaim),
        ):
            try:
                trigger()
            except Exception as error:  # noqa: BLE001 - the point is to scan every surface
                surfaces.append(str(error))
        assert all(KEY not in surface for surface in surfaces)

    def test_hostile_payload_errors_never_echo_key(self, monkeypatch) -> None:
        # A scripted hostile wire shape exercised through the gateway.
        monkeypatch.setenv(MODEL_API_KEY_ENV, KEY)
        gateway = ModelGateway(
            _scripted({"payload": {"choices": []}}), model_name=MODEL
        )
        with pytest.raises(ModelProtocolError) as caught:
            gateway.complete(_request())
        assert KEY not in str(caught.value)
