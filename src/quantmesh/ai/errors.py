"""Model gateway typed errors (M8, issues #45/#46)."""


class ModelError(ValueError):
    """Base for every model-gateway failure."""


class ModelConfigurationError(ModelError):
    """A construction or settings violation (host posture, missing model)."""


class ModelUnavailableError(ModelError):
    """The endpoint was unreachable, refused, or the script was exhausted."""


class ModelProtocolError(ModelError):
    """A wire payload violates the pinned OpenAI-compatible contract."""


class ModelOutputError(ModelError):
    """Model text failed to parse or validate against the schema."""


class UnknownRoleError(ModelError):
    """A role name is not one of the canonical research roles."""


class PipelineError(ModelError):
    """A research-pipeline violation (stage order, gate, references)."""
