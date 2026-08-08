"""Phase D tool-registry tests (M8, issue #48).

The permission matrix (every role x every tool), enforcement at call
time with typed refusals, the charter/policy consistency pin, the
default read-only surfaces, and the structural no-execution-surface
proofs.
"""

import inspect
from collections.abc import Callable, Mapping

import pytest

from quantmesh.ai import tools as tools_module
from quantmesh.ai.errors import ToolRefusalError, UnknownRoleError, UnknownToolError
from quantmesh.ai.retrieval import DocumentIndex, DocumentSource
from quantmesh.ai.roles import ROLE_ORDER, charter
from quantmesh.ai.tools import (
    TOOL_NAMES,
    TOOL_POLICIES,
    ToolRegistry,
    bind_default_surfaces,
)


def _write_text(root, name: str, content: str):
    path = root / name
    path.write_text(content, encoding="utf-8")
    return path


def _fake_surfaces(calls: list[tuple[str, Mapping[str, object]]]):
    def make(name: str) -> Callable[[Mapping[str, object]], str]:
        def surface(args: Mapping[str, object]) -> str:
            calls.append((name, dict(args)))
            return f"{name}->ok"

        return surface

    return {name: make(name) for name in TOOL_NAMES}


class TestPolicies:
    def test_canonical_five_tools(self) -> None:
        assert TOOL_NAMES == (
            "retrieve_documents",
            "read_experiment",
            "read_report",
            "read_risk_context",
            "read_portfolio_snapshot",
        )

    def test_every_policy_has_description_and_roles(self) -> None:
        for name, policy in TOOL_POLICIES.items():
            assert name in TOOL_NAMES
            assert policy.name == name
            assert policy.description
            assert policy.allowed_roles
            assert set(policy.allowed_roles) <= set(ROLE_ORDER)

    def test_charter_tool_tuples_match_policy_allowed_roles(self) -> None:
        # The Phase B charters pre-bind tool names; the registry's
        # allowed_roles must agree with them exactly, or a role could
        # be granted or stripped without either table noticing.
        for role in ROLE_ORDER:
            from_charters = set(charter(role).tools)
            from_policies = {
                name for name, policy in TOOL_POLICIES.items() if role in policy.allowed_roles
            }
            assert from_charters == from_policies

    def test_no_order_shaped_tool_names(self) -> None:
        for name in TOOL_NAMES:
            assert not any(
                fragment in name for fragment in ("order", "trade", "cancel", "position")
            )


class TestRegistryConstruction:
    def test_requires_all_five_surfaces(self) -> None:
        with pytest.raises(ValueError, match="missing tool surfaces"):
            ToolRegistry(surfaces={"retrieve_documents": lambda args: "x"})

    def test_refuses_unknown_surface(self) -> None:
        surfaces = _fake_surfaces([])
        surfaces["place_order"] = lambda args: "x"
        with pytest.raises(ValueError, match="unknown tool surface"):
            ToolRegistry(surfaces=surfaces)

    def test_refuses_unknown_policy(self) -> None:
        from quantmesh.ai.tools import ToolPolicy

        policies = dict(TOOL_POLICIES)
        policies["place_order"] = ToolPolicy(
            name="place_order", description="nope", allowed_roles=("analyst",)
        )
        with pytest.raises(UnknownToolError, match="unknown tool"):
            ToolRegistry(surfaces=_fake_surfaces([]), policies=policies)

    def test_refuses_policy_with_unknown_role(self) -> None:
        from quantmesh.ai.tools import ToolPolicy

        policies = dict(TOOL_POLICIES)
        policies["retrieve_documents"] = ToolPolicy(
            name="retrieve_documents",
            description="x",
            allowed_roles=("analyst", "trader"),
        )
        with pytest.raises(UnknownRoleError, match="trader"):
            ToolRegistry(surfaces=_fake_surfaces([]), policies=policies)


class TestDispatch:
    def test_allowed_role_dispatch_calls_surface(self) -> None:
        calls: list[tuple[str, Mapping[str, object]]] = []
        registry = ToolRegistry(surfaces=_fake_surfaces(calls))
        result = registry.dispatch("analyst", "retrieve_documents", {"query": "btc"})
        assert result == "retrieve_documents->ok"
        assert calls == [("retrieve_documents", {"query": "btc"})]

    def test_permission_matrix_analyst(self) -> None:
        registry = ToolRegistry(surfaces=_fake_surfaces([]))
        assert registry.allowed("analyst", "retrieve_documents")
        assert registry.allowed("analyst", "read_experiment")
        assert registry.allowed("analyst", "read_report")
        assert not registry.allowed("analyst", "read_risk_context")
        assert not registry.allowed("analyst", "read_portfolio_snapshot")

    def test_permission_matrix_critic(self) -> None:
        registry = ToolRegistry(surfaces=_fake_surfaces([]))
        assert registry.allowed("critic", "retrieve_documents")
        for name in TOOL_NAMES[1:]:
            assert not registry.allowed("critic", name)

    def test_permission_matrix_risk_and_portfolio(self) -> None:
        registry = ToolRegistry(surfaces=_fake_surfaces([]))
        assert registry.allowed("risk", "read_risk_context")
        assert registry.allowed("portfolio", "read_portfolio_snapshot")
        for role, name in (("risk", "retrieve_documents"), ("portfolio", "read_report")):
            assert not registry.allowed(role, name)

    def test_forbidden_call_refuses_naming_role_and_tool(self) -> None:
        registry = ToolRegistry(surfaces=_fake_surfaces([]))
        with pytest.raises(ToolRefusalError, match="risk.*read_report|read_report.*risk"):
            registry.dispatch("risk", "read_report", {})

    def test_unknown_tool_refused(self) -> None:
        registry = ToolRegistry(surfaces=_fake_surfaces([]))
        with pytest.raises(UnknownToolError, match="place_order"):
            registry.dispatch("analyst", "place_order", {})

    def test_unknown_role_refused(self) -> None:
        registry = ToolRegistry(surfaces=_fake_surfaces([]))
        with pytest.raises(UnknownRoleError):
            registry.dispatch("trader", "read_report", {})

    def test_forbidden_call_never_touches_surface(self) -> None:
        calls: list[tuple[str, Mapping[str, object]]] = []
        registry = ToolRegistry(surfaces=_fake_surfaces(calls))
        with pytest.raises(ToolRefusalError):
            registry.dispatch("portfolio", "read_report", {})
        assert calls == []


class TestDefaultSurfaces:
    def test_retrieve_documents_renders_passages(self, tmp_path) -> None:
        index = DocumentIndex(root=tmp_path / "docs")
        index.ingest_file(
            _write_text(tmp_path, "a.txt", "BTC rally momentum"), kind="news", doc_id="d-1"
        )
        surfaces = bind_default_surfaces(
            documents=DocumentSource(index),
            experiments=object(),  # type: ignore[arg-type]
            reports=lambda report_id: f"report:{report_id}",
            risk_context=lambda: "risk context",
            portfolio_snapshot=lambda: "portfolio snapshot",
        )
        registry = ToolRegistry(surfaces=surfaces)
        rendered = registry.dispatch(
            "analyst", "retrieve_documents", {"query": "btc", "top_k": 2}
        )
        assert rendered == "[document:d-1] BTC rally momentum"

    def test_retrieve_documents_no_match(self, tmp_path) -> None:
        index = DocumentIndex(root=tmp_path / "docs")
        surfaces = bind_default_surfaces(
            documents=DocumentSource(index),
            experiments=object(),  # type: ignore[arg-type]
            reports=lambda report_id: f"report:{report_id}",
            risk_context=lambda: "risk context",
            portfolio_snapshot=lambda: "portfolio snapshot",
        )
        registry = ToolRegistry(surfaces=surfaces)
        assert (
            registry.dispatch("analyst", "retrieve_documents", {"query": "zzz"})
            == "no passages matched"
        )

    def test_read_tools_delegate(self) -> None:
        calls: list[str] = []
        surfaces = bind_default_surfaces(
            documents=object(),  # type: ignore[arg-type]
            experiments=object(),  # type: ignore[arg-type]
            reports=lambda report_id: calls.append("report") or f"report:{report_id}",
            risk_context=lambda: calls.append("risk") or "risk context",
            portfolio_snapshot=lambda: calls.append("portfolio") or "portfolio snapshot",
        )
        registry = ToolRegistry(surfaces=surfaces)
        assert registry.dispatch("analyst", "read_report", {"report_id": "r-1"}) == "report:r-1"
        assert registry.dispatch("risk", "read_risk_context", {}) == "risk context"
        assert (
            registry.dispatch("portfolio", "read_portfolio_snapshot", {})
            == "portfolio snapshot"
        )
        assert calls == ["report", "risk", "portfolio"]

    def test_arg_type_refusals(self, tmp_path) -> None:
        index = DocumentIndex(root=tmp_path / "docs")
        surfaces = bind_default_surfaces(
            documents=DocumentSource(index),
            experiments=object(),  # type: ignore[arg-type]
            reports=lambda report_id: f"report:{report_id}",
            risk_context=lambda: "risk context",
            portfolio_snapshot=lambda: "portfolio snapshot",
        )
        registry = ToolRegistry(surfaces=surfaces)
        with pytest.raises(ValueError, match="must be a string"):
            registry.dispatch("analyst", "retrieve_documents", {"query": 7})
        with pytest.raises(ValueError, match="must be a string"):
            registry.dispatch("analyst", "read_report", {"report_id": None})


class TestNoExecutionSurface:
    def test_tools_module_never_imports_execution_surfaces(self) -> None:
        source = inspect.getsource(tools_module)
        for fragment in (
            "quantmesh.paper",
            "quantmesh.execution",
            "hyperliquid.exchange",
            "moomoo",
        ):
            assert fragment not in source, f"tools module imports {fragment}"

    def test_no_execution_shaped_policy_fields(self) -> None:
        for policy in TOOL_POLICIES.values():
            assert "order" not in policy.name
            assert "trade" not in policy.name
