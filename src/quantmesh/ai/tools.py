"""Read-only research tool registry (M8, issue #48, Phase D).

Five research tools, each bound to a per-role permission set that
matches the Phase B charter `tools` tuples exactly (a test pins the
two tables to each other so they cannot diverge). Enforcement is at
call time in deterministic code: an unknown tool is a typed
`UnknownToolError`, a role calling a tool outside its `allowed_roles`
is a typed `ToolRefusalError` naming the role and the tool. The
registry contains **no execution surface** — there is no order, no
kernel entry, and no adapter call among the five tools, and the module
imports none (structural, proven by test).
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from quantmesh.ai.errors import ToolRefusalError, UnknownRoleError, UnknownToolError
from quantmesh.ai.retrieval import RetrievalSource, RetrievedPassage
from quantmesh.ai.roles import ROLE_ORDER

__all__ = [
    "TOOL_NAMES",
    "TOOL_POLICIES",
    "ToolPolicy",
    "ToolRegistry",
    "bind_default_surfaces",
]

TOOL_NAMES = (
    "retrieve_documents",
    "read_experiment",
    "read_report",
    "read_risk_context",
    "read_portfolio_snapshot",
)


@dataclass(frozen=True)
class ToolPolicy:
    """Pinned policy data for one tool: who may call it, and why it exists."""

    name: str
    description: str
    allowed_roles: tuple[str, ...]


TOOL_POLICIES: Mapping[str, ToolPolicy] = {
    "retrieve_documents": ToolPolicy(
        name="retrieve_documents",
        description=(
            "Lexical search over the local document index; returns ranked "
            "passages with resolvable citation ids."
        ),
        allowed_roles=("analyst", "critic"),
    ),
    "read_experiment": ToolPolicy(
        name="read_experiment",
        description="Read one M3 experiment registry record by its id.",
        allowed_roles=("analyst",),
    ),
    "read_report": ToolPolicy(
        name="read_report",
        description="Read one research report registry record by its id.",
        allowed_roles=("analyst",),
    ),
    "read_risk_context": ToolPolicy(
        name="read_risk_context",
        description="Read the supplied M5 risk-gate context for review.",
        allowed_roles=("risk",),
    ),
    "read_portfolio_snapshot": ToolPolicy(
        name="read_portfolio_snapshot",
        description="Read the supplied M7 portfolio snapshot for review.",
        allowed_roles=("portfolio",),
    ),
}


def _render_passages(passages: list[RetrievedPassage]) -> str:
    return "\n".join(
        f"[{passage.citation.source_kind}:{passage.citation.source_id}] "
        f"{passage.content}"
        for passage in passages
    ) or "no passages matched"


def bind_default_surfaces(
    *,
    documents: RetrievalSource,
    experiments: RetrievalSource,
    reports: Callable[[str], str],
    risk_context: Callable[[], str],
    portfolio_snapshot: Callable[[], str],
) -> Mapping[str, Callable[[Mapping[str, object]], str]]:
    """The five read-only research surfaces bound to injected readers.

    `reports` reads one report record by id and renders it; the risk
    and portfolio callables render their supplied context. Every
    surface is a reader — none can place or modify an order.
    """
    def retrieve_documents(args: Mapping[str, object]) -> str:
        query = _require_str(args, "query")
        top_k = _require_int(args, "top_k", default=5)
        return _render_passages(documents.search(query, top_k))

    def read_experiment(args: Mapping[str, object]) -> str:
        return experiments.resolve(_require_str(args, "experiment_id")).text

    def read_report(args: Mapping[str, object]) -> str:
        return reports(_require_str(args, "report_id"))

    def read_risk_context(args: Mapping[str, object]) -> str:
        return risk_context()

    def read_portfolio_snapshot(args: Mapping[str, object]) -> str:
        return portfolio_snapshot()

    return {
        "retrieve_documents": retrieve_documents,
        "read_experiment": read_experiment,
        "read_report": read_report,
        "read_risk_context": read_risk_context,
        "read_portfolio_snapshot": read_portfolio_snapshot,
    }


def _require_str(args: Mapping[str, object], name: str) -> str:
    value = args.get(name)
    if not isinstance(value, str):
        raise ValueError(f"tool argument {name!r} must be a string, got {type(value).__name__}")
    return value


def _require_int(args: Mapping[str, object], name: str, *, default: int) -> int:
    value = args.get(name, default)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"tool argument {name!r} must be an int, got {type(value).__name__}")
    return value


class ToolRegistry:
    """The tool policy table plus its bound surfaces, enforced at call time."""

    def __init__(
        self,
        surfaces: Mapping[str, Callable[[Mapping[str, object]], str]],
        policies: Mapping[str, ToolPolicy] | None = None,
    ) -> None:
        resolved = TOOL_POLICIES if policies is None else dict(policies)
        missing = [name for name in TOOL_NAMES if name not in resolved]
        if missing:
            raise ValueError(f"missing tool policies: {missing}")
        extra = sorted(set(resolved) - set(TOOL_NAMES))
        if extra:
            raise UnknownToolError(f"unknown tool(s): {extra}")
        for name, policy in resolved.items():
            if policy.allowed_roles and not set(policy.allowed_roles) <= set(ROLE_ORDER):
                unknown = sorted(set(policy.allowed_roles) - set(ROLE_ORDER))
                raise UnknownRoleError(f"tool {name!r} allows unknown role(s): {unknown}")
        missing_surfaces = sorted(set(TOOL_NAMES) - set(surfaces))
        if missing_surfaces:
            raise ValueError(f"missing tool surfaces: {missing_surfaces}")
        extra_surfaces = sorted(set(surfaces) - set(TOOL_NAMES))
        if extra_surfaces:
            raise ValueError(f"unknown tool surface(s): {extra_surfaces}")
        self._policies = resolved
        self._surfaces = dict(surfaces)

    def allowed(self, role: str, name: str) -> bool:
        """Whether `role` may call `name` (unknown tools are False)."""
        policy = self._policies.get(name)
        return policy is not None and role in policy.allowed_roles

    def dispatch(self, role: str, name: str, args: Mapping[str, object] | None = None) -> str:
        """Call `name` as `role`; unknown tools and forbidden roles fail closed."""
        policy = self._policies.get(name)
        if policy is None:
            raise UnknownToolError(f"unknown tool: {name!r}")
        if role not in ROLE_ORDER:
            raise UnknownRoleError(f"unknown research role: {role!r}")
        if role not in policy.allowed_roles:
            raise ToolRefusalError(
                f"role {role!r} is not allowed to call tool {name!r}"
            )
        return self._surfaces[name](dict(args or {}))

    def names(self) -> tuple[str, ...]:
        return TOOL_NAMES

    def policies(self) -> Mapping[str, ToolPolicy]:
        return dict(self._policies)
