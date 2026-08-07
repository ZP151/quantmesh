"""Local AI research layer integration points (M8)."""

from quantmesh.ai.errors import (
    ModelConfigurationError,
    ModelError,
    ModelOutputError,
    ModelProtocolError,
    ModelUnavailableError,
)
from quantmesh.ai.gateway import ModelGateway
from quantmesh.ai.transport import (
    DEFAULT_CHAT_PATH,
    MODEL_API_KEY_ENV,
    HttpModelTransport,
    ModelTransport,
    ScriptedModelTransport,
)
from quantmesh.ai.wire import (
    ChatMessage,
    ModelRequest,
    ModelResponse,
    build_chat_body,
    parse_completion,
)

__all__ = [
    "ChatMessage",
    "DEFAULT_CHAT_PATH",
    "HttpModelTransport",
    "MODEL_API_KEY_ENV",
    "ModelConfigurationError",
    "ModelError",
    "ModelGateway",
    "ModelOutputError",
    "ModelProtocolError",
    "ModelRequest",
    "ModelResponse",
    "ModelTransport",
    "ModelUnavailableError",
    "ScriptedModelTransport",
    "build_chat_body",
    "parse_completion",
]
