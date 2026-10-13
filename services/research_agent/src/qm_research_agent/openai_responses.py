"""Service-owned, text-only Responses adapter over the existing gateway wire.

No SDK, environment credential/proxy discovery, retry or runtime activation.
The price table is source metadata; the durable ledger reserves a conservative
$1 per effect, without refunding token estimates or promising provider invoices.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import math
import os
import re
import sys
from dataclasses import dataclass
from decimal import Decimal

import httpcore
import httpx
from pydantic import SecretStr

from qm_research_agent.orchestrator import AdvisoryRunner, ApprovedRemoteGateway
from quantmesh.ai.errors import ModelConfigurationError, ModelProtocolError, ModelUnavailableError
from quantmesh.ai.transport import ModelTransport

OPENAI_ORIGIN = "https://api.openai.com"
RESPONSES_URL = OPENAI_ORIGIN + "/v1/responses"
DEFAULT_MODEL = "gpt-6.1-sol"
PRICE_VERSION = "openai-gpt-6.1-sol-standard-2026-10-13"
HTTP_DEADLINE_SECONDS = 30.0
MAX_BYTES = 65536
MAX_OUTPUT_TOKENS = 1024

# DNS is isolated because cancelling loop.getaddrinfo cannot stop its executor
# thread, and asyncio.run would wait for that thread during shutdown. The helper
# receives only a fixed public hostname/port/owner PID, never request/key bytes.
_DNS_PROGRAM = """
import ctypes,json,os,signal,socket,sys
libc=ctypes.CDLL(None,use_errno=True)
if libc.prctl(1,signal.SIGKILL)!=0 or os.getppid()!=int(sys.argv[3]): sys.exit(1)
rows=socket.getaddrinfo(sys.argv[1],int(sys.argv[2]),type=socket.SOCK_STREAM)
addresses=list(dict.fromkeys(row[4][0] for row in rows))
sys.stdout.write(json.dumps(addresses[:16]))
"""


class _OwnedResolverBackend(httpcore.AsyncNetworkBackend):
    """One killable resolver, then the pinned backend connects to a numeric IP.

    The HTTP origin and TLS SNI remain api.openai.com in httpcore. No HTTP retry is
    added. Parent process-group/cgroup certification still belongs to runtime gates.
    """

    def __init__(self, delegate):
        self.delegate = delegate

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        if host != "api.openai.com" or port != 443 or sys.platform != "linux":
            raise ModelUnavailableError("openai_execution_unavailable")
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-B",
            "-I",
            "-c",
            _DNS_PROGRAM,
            host,
            str(port),
            str(os.getpid()),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env={"PYTHONDONTWRITEBYTECODE": "1"},
        )
        try:
            raw, _ = await process.communicate()
            if process.returncode or len(raw) > 8192:
                raise ModelUnavailableError("openai_transport_unavailable")
            addresses = json.loads(raw)
            if not isinstance(addresses, list) or not addresses:
                raise ModelUnavailableError("openai_transport_unavailable")
            address = str(ipaddress.ip_address(addresses[0]))
            if not ipaddress.ip_address(address).is_global:
                raise ModelUnavailableError("openai_transport_unavailable")
            return await self.delegate.connect_tcp(
                address,
                port,
                timeout=timeout,
                local_address=local_address,
                socket_options=socket_options,
            )
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()

    async def connect_unix_socket(self, *args, **kwargs):
        raise ModelUnavailableError("openai_execution_unavailable")

    async def sleep(self, seconds):
        await asyncio.sleep(seconds)


def _owned_resolver(client):
    # Pinned httpx0.28.1 exposes no public network_backend argument. Keep this
    # single version-guarded internal hook isolated; never fall back to an
    # uncancellable default DNS executor if the admitted dependency changes.
    if httpx.__version__ != "0.28.1":
        raise ModelUnavailableError("openai_execution_unavailable")
    transport = client._transport
    if isinstance(transport, httpx.MockTransport):
        return  # explicit in-memory offline HTTP fixture, never a DNS witness
    if type(transport) is not httpx.AsyncHTTPTransport:
        raise ModelUnavailableError("openai_execution_unavailable")
    pool = transport._pool
    if type(pool) is not httpcore.AsyncConnectionPool:
        raise ModelUnavailableError("openai_execution_unavailable")
    pool._network_backend = _OwnedResolverBackend(pool._network_backend)


@dataclass(frozen=True, init=False)
class OpenAIPriceTable:
    """Official October13 standard rates per million; alias, not a snapshot.

    Source: https://developers.openai.com/api/docs/models/gpt-6.1-sol
    Long contexts, regional processing and other service tiers are not qualified.
    No rate is inferred from environment, response text or user input.
    """

    version: str = PRICE_VERSION
    model: str = DEFAULT_MODEL
    tier: str = "standard"
    max_standard_input_tokens: int = 272000
    input_usd: Decimal = Decimal("2.00")
    cached_input_usd: Decimal = Decimal("0.10")
    cache_write_usd: Decimal = Decimal("2.50")
    output_usd: Decimal = Decimal("10.00")


def _configuration(key, allowed_origins, remote_consent, model, price_version):
    if (
        not isinstance(key, SecretStr)
        or not re.fullmatch(r"[A-Za-z0-9_.-]{1,4096}", key.get_secret_value())
        or not isinstance(allowed_origins, frozenset)
        or OPENAI_ORIGIN not in allowed_origins
        or remote_consent is not True
        or model != DEFAULT_MODEL
        or price_version != PRICE_VERSION
    ):
        raise ModelConfigurationError("openai_configuration_invalid")


def _integer(value, maximum):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ModelProtocolError("openai_response_invalid")
    return value


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ModelProtocolError("openai_response_invalid")
        result[key] = value
    return result


def _constant(value):
    raise ModelProtocolError("openai_response_invalid")


class OpenAIResponsesTransport(ModelTransport):
    """Explicit private configuration; HTTP client lives only within one effect.

    Async HTTP is an implementation detail of the synchronous typed transport.
    asyncio.timeout bounds the entire exchange rather than resetting a read timer
    for each chunk. No httpx client, event loop or socket survives/pickles in state.
    """

    def __init__(
        self,
        *,
        key: SecretStr,
        allowed_origins: frozenset[str],
        remote_consent: bool,
        model: str = DEFAULT_MODEL,
        price_version: str = PRICE_VERSION,
    ):
        _configuration(key, allowed_origins, remote_consent, model, price_version)
        self._key, self._model, self.price_version = key, model, price_version

    def __repr__(self):
        return "<OpenAIResponsesTransport private>"

    def _encode(self, body):
        try:
            if (
                not isinstance(body, dict)
                or set(body) - {"model", "messages", "temperature", "max_tokens", "response_format"}
                or body.get("model") != self._model
            ):
                raise ValueError
            maximum = body.get("max_tokens")
            if type(maximum) is not int or not 1 <= maximum <= MAX_OUTPUT_TOKENS:
                raise ValueError
            temperature = body.get("temperature")
            if (
                type(temperature) not in (float, int)
                or not math.isfinite(temperature)
                or not 0 <= temperature <= 2
            ):
                raise ValueError
            messages = body.get("messages")
            if not isinstance(messages, list) or not messages:
                raise ValueError
            for message in messages:
                if (
                    not isinstance(message, dict)
                    or set(message) != {"role", "content"}
                    or message["role"] not in {"system", "user", "assistant"}
                    or not isinstance(message["content"], str)
                    or not message["content"]
                ):
                    raise ValueError
            encoded = {
                "model": self._model,
                "input": messages,
                "reasoning": {"effort": "low"},
                "max_output_tokens": maximum,
                "store": False,
                "background": False,
                "stream": False,
                "service_tier": "default",
            }
            if "response_format" in body:
                response_format = body["response_format"]
                if (
                    not isinstance(response_format, dict)
                    or set(response_format) != {"type", "json_schema"}
                    or response_format["type"] != "json_schema"
                ):
                    raise ValueError
                schema = response_format["json_schema"]
                if (
                    not isinstance(schema, dict)
                    or set(schema) != {"name", "schema", "strict"}
                    or not isinstance(schema["name"], str)
                    or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", schema["name"])
                    or not isinstance(schema["schema"], dict)
                    or schema["strict"] is not True
                ):
                    raise ValueError
                encoded["text"] = {"format": {"type": "json_schema", **schema}}
            raw = json.dumps(
                encoded, ensure_ascii=False, allow_nan=False, separators=(",", ":")
            ).encode("utf-8")
            if len(raw) > MAX_BYTES:
                raise ValueError
            return raw, maximum
        except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
            raise ModelProtocolError("openai_request_invalid") from None

    async def _exchange(self, raw):
        async with asyncio.timeout(HTTP_DEADLINE_SECONDS):
            async with httpx.AsyncClient(
                timeout=30.0, verify=True, trust_env=False, follow_redirects=False
            ) as client:
                _owned_resolver(client)
                async with client.stream(
                    "POST",
                    RESPONSES_URL,
                    content=raw,
                    headers={
                        "Authorization": "Bearer " + self._key.get_secret_value(),
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "Accept-Encoding": "identity",
                    },
                ) as response:
                    if not 200 <= response.status_code < 300:
                        raise ModelUnavailableError("openai_http_unavailable")
                    length = response.headers.get("Content-Length")
                    if length is not None and (
                        not re.fullmatch(r"[0-9]{1,10}", length) or int(length) > MAX_BYTES
                    ):
                        raise ModelProtocolError("openai_response_invalid")
                    if response.headers.get("Content-Encoding", "identity") != "identity":
                        raise ModelProtocolError("openai_response_invalid")
                    chunks, total = [], 0
                    async for chunk in response.aiter_bytes(chunk_size=4096):
                        total += len(chunk)
                        if total > MAX_BYTES:
                            raise ModelProtocolError("openai_response_invalid")
                        chunks.append(chunk)
                    if length is not None and int(length) != total:
                        raise ModelProtocolError("openai_response_invalid")
                    return b"".join(chunks)

    def _normalize(self, raw, maximum):
        try:
            payload = json.loads(
                raw.decode("utf-8"), object_pairs_hook=_unique, parse_constant=_constant
            )
            if (
                not isinstance(payload, dict)
                or payload.get("object") != "response"
                or payload.get("status") != "completed"
                or payload.get("model") != self._model
                or payload.get("error") is not None
                or payload.get("incomplete_details") is not None
                or payload.get("service_tier") != "default"
            ):
                raise ValueError
            output = payload.get("output")
            if not isinstance(output, list) or not output:
                raise ValueError
            messages = []
            for item in output:
                if not isinstance(item, dict):
                    raise ValueError
                if item.get("type") == "reasoning":
                    # Non-published reasoning metadata is never used as output,
                    # citations, tool authority or a subsequent conversation.
                    if item.get("status") not in (None, "completed"):
                        raise ValueError
                elif item.get("type") == "message":
                    messages.append(item)
                else:
                    raise ValueError
            if len(messages) != 1:
                raise ValueError
            message = messages[0]
            if message.get("role") != "assistant" or message.get("status") != "completed":
                raise ValueError
            content = message.get("content")
            if (
                not isinstance(content, list)
                or len(content) != 1
                or not isinstance(content[0], dict)
                or content[0].get("type") != "output_text"
                or not isinstance(content[0].get("text"), str)
                or not content[0]["text"].strip()
                or content[0].get("annotations", []) != []
                or content[0].get("refusal") is not None
            ):
                raise ValueError
            usage = payload.get("usage")
            if not isinstance(usage, dict) or set(usage) != {
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "input_tokens_details",
                "output_tokens_details",
            }:
                raise ValueError
            input_tokens = _integer(
                usage["input_tokens"], OpenAIPriceTable().max_standard_input_tokens
            )
            output_tokens = _integer(usage["output_tokens"], maximum)
            total = _integer(usage["total_tokens"], input_tokens + output_tokens)
            input_details, output_details = (
                usage["input_tokens_details"],
                usage["output_tokens_details"],
            )
            if (
                total != input_tokens + output_tokens
                or not isinstance(input_details, dict)
                or set(input_details) != {"cached_tokens", "cache_write_tokens"}
                or not isinstance(output_details, dict)
                or set(output_details) != {"reasoning_tokens"}
            ):
                raise ValueError
            cached = _integer(input_details["cached_tokens"], input_tokens)
            written = _integer(input_details["cache_write_tokens"], input_tokens)
            reasoning = _integer(output_details["reasoning_tokens"], output_tokens)
            if cached + written > input_tokens:
                raise ValueError
            return {
                "model": payload["model"],
                "choices": [{"message": {"content": content[0]["text"]}, "finish_reason": "stop"}],
                "usage": {
                    "prompt_tokens": input_tokens,
                    "completion_tokens": output_tokens,
                    "total_tokens": total,
                    "cached_input_tokens": cached,
                    "cache_write_tokens": written,
                    "reasoning_tokens": reasoning,
                },
            }
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
            raise ModelProtocolError("openai_response_invalid") from None

    def complete(self, body: dict) -> object:
        raw, maximum = self._encode(body)
        # This synchronous contract is invoked by the owned effect worker, not
        # within an ASGI event loop. Reject rather than nest or leak a coroutine.
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise ModelUnavailableError("openai_execution_unavailable")
        try:
            response = asyncio.run(self._exchange(raw))
        except (ModelProtocolError, ModelUnavailableError):
            raise
        except Exception:
            raise ModelUnavailableError("openai_transport_unavailable") from None
        return self._normalize(response, maximum)


class OpenAIResponsesGateway(ApprovedRemoteGateway):
    """Existing remote-consent admission, with a fixed Responses transport."""

    def __init__(
        self,
        *,
        key: SecretStr,
        allowed_origins: frozenset[str],
        remote_consent: bool,
        model: str = DEFAULT_MODEL,
        price_version: str = PRICE_VERSION,
    ):
        _configuration(key, allowed_origins, remote_consent, model, price_version)
        super().__init__(
            base_url=OPENAI_ORIGIN,
            model=model,
            key=key,
            allowed_origins=allowed_origins,
            remote_consent=remote_consent,
        )
        self._transport = OpenAIResponsesTransport(
            key=key,
            model=model,
            price_version=price_version,
            allowed_origins=allowed_origins,
            remote_consent=remote_consent,
        )

    def __repr__(self):
        return "<OpenAIResponsesGateway private>"


def make_openai_advisory(
    store,
    effects,
    *,
    key: SecretStr,
    allowed_origins: frozenset[str],
    remote_consent: bool,
    model: str = DEFAULT_MODEL,
    price_version: str = PRICE_VERSION,
):
    """Construct only; the existing job/portfolio ledger decides every effect.

    One conservative $1 reservation uses up a default job's estimate allowance.
    Token-derived prices never refund admission or certify a bill. This factory
    does not enable runtime/bootstrap, create a worker, or make a model request.
    """
    gateway = OpenAIResponsesGateway(
        key=key,
        allowed_origins=allowed_origins,
        remote_consent=remote_consent,
        model=model,
        price_version=price_version,
    )
    return (
        AdvisoryRunner(
            store, effects, provider="openai", price=Decimal("1.00"), price_version=price_version
        ),
        gateway,
    )
