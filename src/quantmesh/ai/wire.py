"""Model gateway wire contract (M8, issue #45, Phase A).

The OpenAI-compatible chat-completions surface, owned as a contract:
``ChatMessage``/``ModelRequest``/``ModelResponse`` are the pydantic
models every path shares, ``build_chat_body`` is the canonical request
encoding (with the JSON-schema ``response_format`` for structured
output), and ``parse_completion`` is the fail-closed decoder: a wire
payload that violates the pinned shape is a typed
``ModelProtocolError``, and no partial response ever escapes.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

from quantmesh.ai.errors import ModelProtocolError

__all__ = [
    "ChatMessage",
    "ModelRequest",
    "ModelResponse",
    "build_chat_body",
    "parse_completion",
]


class ChatMessage(BaseModel):
    """One chat turn in the wire format."""

    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class ModelRequest(BaseModel):
    """The canonical completion request every path shares."""

    messages: list[ChatMessage] = Field(min_length=1)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, gt=0)


class ModelResponse(BaseModel):
    """A validated completion; ``model_version`` is operator metadata the
    OpenAI-compatible wire does not carry (it lives in the model string),
    and stays None unless a future transport supplies it."""

    content: str
    model_name: str
    model_version: str | None = None
    finish_reason: str | None = None
    usage: dict[str, int] | None = None


def build_chat_body(
    *,
    model_name: str,
    request: ModelRequest,
    schema: type[BaseModel] | None = None,
) -> dict[str, Any]:
    """Encode the canonical request body.

    With ``schema`` the body carries the JSON-schema
    ``response_format`` so the endpoint emits schema-validatable JSON
    (the structured path); without it the body is plain chat.
    """
    body: dict[str, Any] = {
        "model": model_name,
        "messages": [
            {"role": message.role, "content": message.content}
            for message in request.messages
        ],
        "temperature": request.temperature,
        "max_tokens": request.max_tokens,
    }
    if schema is not None:
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": schema.__name__,
                "schema": schema.model_json_schema(),
                "strict": True,
            },
        }
    return body


def parse_completion(payload: object, *, model_name: str) -> ModelResponse:
    """Decode a raw completion payload, fail-closed on the pinned shape."""
    if not isinstance(payload, dict):
        raise ModelProtocolError(
            f"completion payload is not a mapping: {type(payload).__name__}"
        )
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ModelProtocolError("completion payload carries no choices")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise ModelProtocolError("the first choice is not a mapping")
    message = choice.get("message")
    if not isinstance(message, dict):
        raise ModelProtocolError("the first choice carries no message mapping")
    content = message.get("content")
    if not isinstance(content, str):
        raise ModelProtocolError("the first choice's content is not a string")
    finish_reason = choice.get("finish_reason")
    if finish_reason is not None and not isinstance(finish_reason, str):
        raise ModelProtocolError("finish_reason is not a string")
    usage = payload.get("usage")
    if usage is not None and (
        not isinstance(usage, dict)
        or not all(isinstance(value, int) for value in usage.values())
    ):
        raise ModelProtocolError("usage is not a mapping of integers")
    wire_model = payload.get("model")
    if wire_model is not None and not isinstance(wire_model, str):
        raise ModelProtocolError("the reported model name is not a string")
    return ModelResponse(
        content=content,
        model_name=wire_model or model_name,
        finish_reason=finish_reason,
        usage=usage,
    )
