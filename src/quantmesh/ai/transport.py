"""Model gateway transports (M8, issue #45, Phase A).

``ModelTransport`` is the injected boundary: ``ScriptedModelTransport``
makes every test and acceptance drill deterministic (JSONL records with
fail-closed line attribution, plus a ``payload`` escape hatch for
hostile wire shapes), and ``HttpModelTransport`` is the live path over
httpx (a core dependency) against the OpenAI-compatible
``/v1/chat/completions`` surface.

Local-first posture (ADR-0010): the base URL defaults to a loopback
endpoint; a non-loopback host is refused at construction unless
``allow_remote=True`` is passed explicitly — a construction-time
decision, never env-driven. The API key (``QUANTMESH_MODEL_API_KEY``,
if set) is injected as the Authorization header per request and never
serialized: it appears in no repr, no exception, and no log line.
"""

import json
from abc import ABC, abstractmethod
from os import environ
from urllib.parse import urlsplit

from quantmesh.ai.errors import (
    ModelConfigurationError,
    ModelProtocolError,
    ModelUnavailableError,
)
from quantmesh.settings import settings

__all__ = [
    "DEFAULT_CHAT_PATH",
    "HttpModelTransport",
    "MODEL_API_KEY_ENV",
    "ModelTransport",
    "ScriptedModelTransport",
]

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
DEFAULT_CHAT_PATH = "/v1/chat/completions"
MODEL_API_KEY_ENV = "QUANTMESH_MODEL_API_KEY"


class ModelTransport(ABC):
    """The injected wire boundary: request body in, wire payload out."""

    @abstractmethod
    def complete(self, body: dict) -> object:
        """Send an OpenAI-compatible chat body; return the raw payload."""


class ScriptedModelTransport(ModelTransport):
    """Deterministic canned responses, from inline records or a JSONL script.

    Each record maps ``{"content": str, "model": str, "finish_reason":
    str, "usage": {...}}`` — content required, the rest optional. A
    record may instead carry exactly ``{"payload": <raw wire payload>}``
    to replay hostile shapes verbatim for the fail-closed drills.
    Records replay in order; a malformed record is a typed refusal
    naming it; exhausting the script is a typed refusal naming the
    count.
    """

    def __init__(self, records: list[dict]) -> None:
        validated: list[dict] = []
        for index, record in enumerate(records, start=1):
            if not isinstance(record, dict):
                raise ModelProtocolError(f"script record {index} is not a mapping")
            if "payload" in record:
                if len(record) != 1:
                    raise ModelProtocolError(
                        f"script record {index} mixes payload with other fields"
                    )
                validated.append(record)
                continue
            content = record.get("content")
            if not isinstance(content, str):
                raise ModelProtocolError(
                    f"script record {index} carries no string content"
                )
            validated.append(record)
        self._records = validated
        self._seen = 0
        self.seen_bodies: list[dict] = []  # recorded for test assertions

    @classmethod
    def from_script(cls, path) -> "ScriptedModelTransport":
        """Load a JSONL script; malformed lines refuse with attribution."""
        with open(path, encoding="utf-8") as handle:
            records: list[dict] = []
            for line_number, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    record = json.loads(stripped)
                except ValueError as error:
                    raise ModelProtocolError(
                        f"script line {line_number} is not JSON: {error}"
                    ) from None
                if not isinstance(record, dict):
                    raise ModelProtocolError(
                        f"script line {line_number} is not a mapping"
                    )
                records.append(record)
        return cls(records)

    def complete(self, body: dict) -> object:
        self.seen_bodies.append(body)
        if self._seen >= len(self._records):
            raise ModelUnavailableError(
                f"script exhausted after {self._seen} responses"
            )
        record = self._records[self._seen]
        self._seen += 1
        if "payload" in record:
            return record["payload"]
        return {
            "choices": [
                {
                    "message": {"content": record["content"]},
                    "finish_reason": record.get("finish_reason"),
                }
            ],
            "model": record.get("model"),
            "usage": record.get("usage"),
        }


class HttpModelTransport(ModelTransport):
    """Live OpenAI-compatible chat completions over httpx.

    Explicit construction only; a non-loopback base URL is refused
    unless ``allow_remote=True`` (a construction-time decision, never
    env-driven). ``api_key`` defaults to ``QUANTMESH_MODEL_API_KEY``
    and is injected as the Authorization header per request; it never
    appears in reprs or exceptions.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        request_timeout_s: float | None = None,
        allow_remote: bool = False,
        chat_path: str = DEFAULT_CHAT_PATH,
    ) -> None:
        base = base_url or settings.model_gateway_url
        parsed = urlsplit(base)
        if parsed.scheme not in ("http", "https"):
            raise ModelConfigurationError(
                f"model gateway URL must be http(s), got {base!r}"
            )
        hostname = (parsed.hostname or "").lower()
        if not hostname:
            raise ModelConfigurationError(
                f"model gateway URL carries no host: {base!r}"
            )
        if hostname not in LOOPBACK_HOSTS and not allow_remote:
            raise ModelConfigurationError(
                f"model gateway host {hostname!r} is not loopback; a remote endpoint "
                "requires explicit construction with allow_remote=True (never env-driven)"
            )
        self._base = base.rstrip("/")
        self._chat_path = chat_path
        self._api_key = environ.get(MODEL_API_KEY_ENV) if api_key is None else api_key
        self._request_timeout_s = (
            request_timeout_s
            if request_timeout_s is not None
            else settings.model_request_timeout_s
        )
        self._http = None  # lazily imported; tests never touch the network

    def __repr__(self) -> str:
        return (
            f"<HttpModelTransport base={self._base!r} "
            f"key={'set' if self._api_key else 'unset'}>"
        )

    def _client(self):
        if self._http is None:
            import httpx

            self._http = httpx.Client(timeout=self._request_timeout_s)
        return self._http

    def complete(self, body: dict) -> object:
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else None
        try:
            response = self._client().post(
                f"{self._base}{self._chat_path}", json=body, headers=headers
            )
        except Exception as error:
            raise ModelUnavailableError(f"model gateway request failed: {error}") from error
        if response.status_code >= 400:
            raise ModelUnavailableError(
                f"model gateway refused (HTTP {response.status_code}): "
                f"{response.text[:120]!r}"
            )
        try:
            return response.json()
        except ValueError:
            raise ModelUnavailableError(
                f"model gateway returned a non-JSON body (HTTP {response.status_code})"
            ) from None
