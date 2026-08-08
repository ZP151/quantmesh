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


class RetrievalError(ModelError):
    """A retrieval violation (ingestion, index, ranking, source access)."""


class CitationResolutionError(ModelError):
    """A citation failed to resolve (unknown kind, missing id, bad span)."""


class ToolError(ModelError):
    """A tool-registry violation (unknown tool, forbidden call)."""


class UnknownToolError(ToolError):
    """A tool name is not registered in the tool policy table."""


class ToolRefusalError(ToolError):
    """A role tried to call a tool its allowed_roles do not permit."""


class RedactionError(ModelError):
    """A redaction violation (non-string context, invalid secret input)."""
