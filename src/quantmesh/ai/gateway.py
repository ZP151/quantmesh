"""Model gateway (M8, issue #45, Phase A).

``ModelGateway`` is the deterministic research surface: ``complete``
returns a validated ``ModelResponse``; ``complete_structured`` parses
the model's text as JSON and validates it against a pydantic schema at
the boundary — any failure is a typed ``ModelOutputError`` and no
partial object escapes. The gateway is structured-only: freetext is
refused, deliberately unlike TradingAgents' freetext fallback
(ADR-0010 decision 2).
"""

import json
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from quantmesh.ai.errors import ModelConfigurationError, ModelOutputError
from quantmesh.ai.transport import ModelTransport
from quantmesh.ai.wire import (
    ModelRequest,
    ModelResponse,
    build_chat_body,
    parse_completion,
)
from quantmesh.settings import settings

__all__ = ["ModelGateway"]

_StructuredT = TypeVar("_StructuredT", bound=BaseModel)


class ModelGateway:
    """The structured research surface over an injected transport.

    ``model_name`` defaults to ``settings.model_name``; an empty model
    name refuses at call time with the missing model named (a gateway
    may be constructed before a model is configured).
    """

    def __init__(
        self,
        transport: ModelTransport,
        *,
        model_name: str | None = None,
    ) -> None:
        self._transport = transport
        resolved = model_name if model_name is not None else settings.model_name
        if not isinstance(resolved, str):
            raise ModelConfigurationError(
                f"model name must be a string, got {type(resolved).__name__}"
            )
        self._model_name = resolved

    @property
    def model_name(self) -> str:
        return self._model_name

    def __repr__(self) -> str:
        return f"<ModelGateway model={self._model_name!r}>"

    def _require_model(self) -> None:
        if not self._model_name:
            raise ModelConfigurationError(
                "no model name configured: set settings.model_name or pass "
                "model_name to the ModelGateway constructor"
            )

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Plain chat completion over the wire contract."""
        self._require_model()
        body = build_chat_body(model_name=self._model_name, request=request)
        payload = self._transport.complete(body)
        return parse_completion(payload, model_name=self._model_name)

    def complete_structured(
        self,
        request: ModelRequest,
        schema: type[_StructuredT],
    ) -> _StructuredT:
        """Structured completion validated against ``schema`` at the boundary."""
        self._require_model()
        body = build_chat_body(
            model_name=self._model_name, request=request, schema=schema
        )
        payload = self._transport.complete(body)
        response = parse_completion(payload, model_name=self._model_name)
        content = response.content.strip()
        if not content:
            raise ModelOutputError(f"{schema.__name__}: the model returned an empty response")
        try:
            data = json.loads(content)
        except ValueError as error:
            raise ModelOutputError(
                f"{schema.__name__}: model output is not JSON: {error}"
            ) from None
        try:
            return schema.model_validate(data)
        except ValidationError as error:
            summary = "; ".join(
                f"{'.'.join(str(part) for part in entry['loc'])}: {entry['msg']}"
                for entry in error.errors()[:3]
            )
            raise ModelOutputError(
                f"{schema.__name__}: model output violates the schema: {summary}"
            ) from None
