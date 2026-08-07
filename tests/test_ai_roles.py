"""Structured research roles tests (M8, issue #46, Phase B).

The role charters as pinned data, the output schemas validated at the
gateway boundary (claim-without-citation and every shape violation
refused with a typed error), the deterministic analyst -> critic gate
-> risk -> portfolio pipeline (a flag blocks a claim downstream in
code), setup-only run identity, the structural reference checks, and
the no-order-shape guarantee proven two ways: a schema walk and a
hostile order-shaped script that fails validation.
"""

import inspect
import json

import pytest
from pydantic import BaseModel

from quantmesh.ai.errors import (
    ModelOutputError,
    PipelineError,
    UnknownRoleError,
)
from quantmesh.ai.gateway import ModelGateway
from quantmesh.ai.roles import (
    CHARTERS,
    ROLE_ORDER,
    AnalystReport,
    CriticVerdict,
    PortfolioReview,
    ResearchPipeline,
    ResearchResult,
    RiskReview,
    RoleCharter,
    charter,
)
from quantmesh.ai.transport import ScriptedModelTransport
from quantmesh.ai.wire import ChatMessage, ModelRequest

MODEL = "fixture-model"

CONTEXT = {
    "market_notes": "AAA rallied 8% on volume twice its 20-day average.",
    "universe": "AAA, BBB, CCC (equities, USD, daily bars).",
}
RISK_VERDICTS = {
    "gate-1": "risk decision allowed: AAA long within the leverage bound",
    "gate-2": "risk decision allowed: BBB short within the liquidation floor",
}
PORTFOLIO_INPUTS = {
    "constraint-1": "venue cap: hyperliquid <= 0.6, binding at 0.6",
    "opt-1": "optimizer weights: AAA 0.40, BBB 0.35, CCC 0.25",
}


def _request(text: str = "analyze") -> ModelRequest:
    return ModelRequest(messages=[ChatMessage(role="user", content=text)])


def _claim(
    statement: str = "AAA upside is supported",
    *,
    confidence: float = 0.7,
    direction: str = "long",
    citations: list[str] | None = None,
) -> dict:
    return {
        "statement": statement,
        "confidence": confidence,
        "direction": direction,
        "evidence_citations": citations if citations is not None else ["doc-1"],
    }


def _analyst_json(*claims: dict) -> str:
    return json.dumps({"claims": list(claims)})


def _critic_json(verdict: str, *flags: dict) -> str:
    return json.dumps({"verdict": verdict, "flagged_claims": list(flags)})


def _risk_json(
    posture: str = "aligned",
    referenced: list[str] | None = None,
    *,
    findings: list[dict] | None = None,
) -> str:
    return json.dumps(
        {
            "posture": posture,
            "referenced_verdicts": referenced if referenced is not None else ["gate-1"],
            "findings": findings
            if findings is not None
            else [{"surface": "size", "severity": "low", "detail": "no issue"}],
        }
    )


def _portfolio_json(
    posture: str = "within_constraints",
    referenced: list[str] | None = None,
    *,
    suggestions: list[str] | None = None,
) -> str:
    return json.dumps(
        {
            "posture": posture,
            "referenced_inputs": referenced if referenced is not None else ["constraint-1"],
            "suggestions": suggestions
            if suggestions is not None
            else ["the venue cap is binding; exposure stays inside it"],
        }
    )


def _script(*contents: str) -> ScriptedModelTransport:
    return ScriptedModelTransport(
        [{"content": content, "model": MODEL} for content in contents]
    )


def _pipeline(transport: ScriptedModelTransport) -> ResearchPipeline:
    return ResearchPipeline(
        ModelGateway(transport, model_name=MODEL),
        context=CONTEXT,
        risk_verdicts=RISK_VERDICTS,
        portfolio_inputs=PORTFOLIO_INPUTS,
    )


def _full_script() -> ScriptedModelTransport:
    return _script(
        _analyst_json(_claim()),
        _critic_json("pass"),
        _risk_json(),
        _portfolio_json(),
    )


def _structured(content: str, schema: type[BaseModel]) -> BaseModel:
    """Validate ``content`` against ``schema`` at the gateway boundary."""
    gateway = ModelGateway(_script(content), model_name=MODEL)
    return gateway.complete_structured(_request(), schema)


class TestCharters:
    def test_canonical_roles_and_order(self) -> None:
        assert ROLE_ORDER == ("analyst", "critic", "risk", "portfolio")
        assert set(CHARTERS) == set(ROLE_ORDER)

    def test_every_charter_is_fully_pinned(self) -> None:
        for role in ROLE_ORDER:
            spec = CHARTERS[role]
            assert spec.role == role
            assert spec.system_prompt
            assert spec.tools
            assert spec.output_schema_id

    def test_charter_accessor(self) -> None:
        assert charter("analyst").output_schema_id == "analyst-report-v1"
        assert charter("risk").tools == ("read_risk_context",)

    def test_unknown_role_refused(self) -> None:
        with pytest.raises(UnknownRoleError, match="executor"):
            charter("executor")
        with pytest.raises(UnknownRoleError, match="trader"):
            charter("trader")

    def test_digest_deterministic_and_sensitive(self) -> None:
        spec = CHARTERS["analyst"]
        assert spec.digest == spec.digest
        altered = RoleCharter(
            role=spec.role,
            system_prompt=spec.system_prompt + " (altered)",
            tools=spec.tools,
            output_schema_id=spec.output_schema_id,
        )
        assert altered.digest != spec.digest


class TestSchemas:
    def test_claim_without_citations_refused(self) -> None:
        with pytest.raises(ModelOutputError, match="evidence_citations"):
            _structured(_analyst_json(_claim(citations=[])), AnalystReport)

    def test_claim_empty_citation_refused(self) -> None:
        with pytest.raises(ModelOutputError, match="evidence_citations"):
            _structured(_analyst_json(_claim(citations=[""])), AnalystReport)

    def test_claim_confidence_out_of_range_refused(self) -> None:
        with pytest.raises(ModelOutputError, match="confidence"):
            _structured(_analyst_json(_claim(confidence=1.5)), AnalystReport)

    def test_claim_bad_direction_refused(self) -> None:
        with pytest.raises(ModelOutputError, match="direction"):
            _structured(_analyst_json(_claim(direction="buy")), AnalystReport)

    def test_critic_bad_verdict_literal_refused(self) -> None:
        with pytest.raises(ModelOutputError, match="verdict"):
            _structured(_critic_json("approve"), CriticVerdict)

    def test_flagged_claim_empty_reason_refused(self) -> None:
        with pytest.raises(ModelOutputError, match="reason"):
            _structured(_critic_json("flag", {"claim_index": 0, "reason": ""}), CriticVerdict)

    def test_risk_empty_referenced_verdicts_refused(self) -> None:
        with pytest.raises(ModelOutputError, match="referenced_verdicts"):
            _structured(_risk_json(referenced=[]), RiskReview)

    def test_risk_bad_severity_refused(self) -> None:
        with pytest.raises(ModelOutputError, match="severity"):
            _structured(
                _risk_json(findings=[{"surface": "x", "severity": "fatal", "detail": "y"}]),
                RiskReview,
            )

    def test_portfolio_empty_suggestion_refused(self) -> None:
        with pytest.raises(ModelOutputError, match="suggestions"):
            _structured(_portfolio_json(suggestions=[""]), PortfolioReview)

    def test_portfolio_bad_posture_refused(self) -> None:
        with pytest.raises(ModelOutputError, match="posture"):
            _structured(_portfolio_json(posture="buy_more"), PortfolioReview)


class TestNoOrderShape:
    FORBIDDEN_ORDER_FIELDS = {
        "quantity",
        "qty",
        "size",
        "venue",
        "order_id",
        "price",
        "limit_price",
        "side",
    }

    def _collect_models(self) -> set[type[BaseModel]]:
        from typing import get_args

        models: set[type[BaseModel]] = set()

        def walk(model: type[BaseModel]) -> None:
            if model in models:
                return
            models.add(model)
            for field in model.model_fields.values():
                candidates = (field.annotation, *get_args(field.annotation))
                for candidate in candidates:
                    if isinstance(candidate, type) and issubclass(candidate, BaseModel):
                        walk(candidate)

        for root in (AnalystReport, CriticVerdict, RiskReview, PortfolioReview):
            walk(root)
        return models

    def test_no_order_shaped_field_in_any_schema(self) -> None:
        for model in sorted(self._collect_models(), key=lambda m: m.__name__):
            for name in model.model_fields:
                assert name not in self.FORBIDDEN_ORDER_FIELDS, (
                    f"{model.__name__}.{name} is order-shaped"
                )

    def test_order_shaped_json_refused_at_the_boundary(self) -> None:
        order_shaped = json.dumps(
            {
                "order_id": "o-1",
                "quantity": 5,
                "venue": "hyperliquid",
                "price": 100.0,
            }
        )
        with pytest.raises(ModelOutputError, match="order_id"):
            _structured(order_shaped, AnalystReport)

    def test_order_shaped_claim_inside_report_refused_without_partial_escape(self) -> None:
        hostile = json.dumps(
            {
                "claims": [
                    _claim(),
                    {
                        "statement": "buy AAA at the market",
                        "confidence": 0.9,
                        "direction": "long",
                        "evidence_citations": ["doc-1"],
                        "quantity": 1000,
                    },
                ]
            }
        )
        with pytest.raises(ModelOutputError, match="quantity"):
            _structured(hostile, AnalystReport)

    def test_roles_module_never_imports_execution_surfaces(self) -> None:
        import quantmesh.ai.roles as roles

        source = inspect.getsource(roles)
        for forbidden in (
            "quantmesh.paper",
            "quantmesh.execution",
            "quantmesh.hyperliquid.exchange",
            "quantmesh.moomoo",
        ):
            assert forbidden not in source, f"roles.py must not reach {forbidden}"


class TestCriticGate:
    def test_pass_verdict_allows_every_claim(self) -> None:
        transport = _script(
            _analyst_json(_claim("first"), _claim("second")),
            _critic_json("pass"),
            _risk_json(),
            _portfolio_json(),
        )
        result = _pipeline(transport).run()
        assert result.critic.verdict.verdict == "pass"
        assert [c.statement for c in result.critic.allowed] == ["first", "second"]
        assert result.critic.blocked == ()

    def test_flag_blocks_claim_downstream(self) -> None:
        transport = _script(
            _analyst_json(_claim("unsupported claim"), _claim("supported claim")),
            _critic_json("flag", {"claim_index": 0, "reason": "no citation resolves"}),
            _risk_json(),
            _portfolio_json(),
        )
        pipeline = _pipeline(transport)
        result = pipeline.run()
        assert result.critic.verdict.verdict == "flag"
        assert [c.statement for c in result.critic.allowed] == ["supported claim"]
        assert [c.statement for c in result.critic.blocked] == ["unsupported claim"]
        # The gate is in code: the blocked claim never reaches later stages.
        bodies = transport.seen_bodies
        assert len(bodies) == 4
        risk_prompt = bodies[2]["messages"][-1]["content"]
        portfolio_prompt = bodies[3]["messages"][-1]["content"]
        assert "unsupported claim" not in risk_prompt
        assert "unsupported claim" not in portfolio_prompt
        assert "supported claim" in risk_prompt
        assert "supported claim" in portfolio_prompt

    def test_empty_analyst_report_flows_through_the_gate(self) -> None:
        transport = _script(
            _analyst_json(),
            _critic_json("pass"),
            _risk_json(),
            _portfolio_json(),
        )
        result = _pipeline(transport).run()
        assert result.analyst_report.claims == []
        assert result.critic.allowed == ()
        assert result.critic.blocked == ()

    def test_flag_index_out_of_range_refused(self) -> None:
        transport = _script(
            _analyst_json(_claim()),
            _critic_json("flag", {"claim_index": 5, "reason": "nope"}),
            _risk_json(),
            _portfolio_json(),
        )
        with pytest.raises(PipelineError, match="out of range"):
            _pipeline(transport).run()

    def test_flag_with_no_flagged_claims_refused(self) -> None:
        transport = _script(
            _analyst_json(_claim()),
            _critic_json("flag"),
            _risk_json(),
            _portfolio_json(),
        )
        with pytest.raises(PipelineError, match="names no flagged claims"):
            _pipeline(transport).run()

    def test_pass_with_flagged_claims_refused(self) -> None:
        transport = _script(
            _analyst_json(_claim()),
            _critic_json("pass", {"claim_index": 0, "reason": "contradiction"}),
            _risk_json(),
            _portfolio_json(),
        )
        with pytest.raises(PipelineError, match="carries flagged claims"):
            _pipeline(transport).run()


class TestPipeline:
    def test_full_run_success(self) -> None:
        result = _pipeline(_full_script()).run()
        assert isinstance(result, ResearchResult)
        assert len(result.run_id) == 16
        assert int(result.run_id, 16) >= 0
        assert result.analyst_report.claims[0].statement == "AAA upside is supported"
        assert result.critic.verdict.verdict == "pass"
        assert result.risk_review.referenced_verdicts == ["gate-1"]
        assert result.risk_review.posture == "aligned"
        assert result.portfolio_review.referenced_inputs == ["constraint-1"]
        assert result.portfolio_review.suggestions[0].startswith("the venue cap")

    def test_stage_order_is_fixed(self) -> None:
        transport = _full_script()
        _pipeline(transport).run()
        bodies = transport.seen_bodies
        assert len(bodies) == 4
        system_prompts = [b["messages"][0]["content"] for b in bodies]
        user_prompts = [b["messages"][-1]["content"] for b in bodies]
        assert system_prompts[0] == CHARTERS["analyst"].system_prompt
        assert system_prompts[1] == CHARTERS["critic"].system_prompt
        assert system_prompts[2] == CHARTERS["risk"].system_prompt
        assert system_prompts[3] == CHARTERS["portfolio"].system_prompt
        assert "Research context:" in user_prompts[0]
        assert "## Analyst report" in user_prompts[1]
        assert "## Supplied risk-gate verdicts" in user_prompts[2]
        assert "## Supplied constraint/optimizer outputs" in user_prompts[3]
        assert "gate-1" in user_prompts[2]
        assert "constraint-1" in user_prompts[3]

    def test_run_id_stable_and_records_identical_across_runs(self) -> None:
        script = [
            {"content": _analyst_json(_claim()), "model": MODEL},
            {"content": _critic_json("pass"), "model": MODEL},
            {"content": _risk_json(), "model": MODEL},
            {"content": _portfolio_json(), "model": MODEL},
        ]
        first = _pipeline(ScriptedModelTransport(list(script))).run()
        second = _pipeline(ScriptedModelTransport(list(script))).run()
        assert first.run_id == second.run_id
        assert first.analyst_report.model_dump_json() == second.analyst_report.model_dump_json()
        assert first.critic.verdict.model_dump_json() == second.critic.verdict.model_dump_json()
        assert first.risk_review.model_dump_json() == second.risk_review.model_dump_json()
        assert first.portfolio_review.model_dump_json() == second.portfolio_review.model_dump_json()

    def test_run_id_sensitive_to_context(self) -> None:
        base = _pipeline(_full_script())
        changed = ResearchPipeline(
            ModelGateway(_full_script(), model_name=MODEL),
            context={**CONTEXT, "market_notes": "AAA flat on no volume."},
            risk_verdicts=RISK_VERDICTS,
            portfolio_inputs=PORTFOLIO_INPUTS,
        )
        assert base.run_id != changed.run_id

    def test_run_id_independent_of_model_outputs(self) -> None:
        script_a = _script(
            _analyst_json(_claim("claim from response A")),
            _critic_json("pass"),
            _risk_json(),
            _portfolio_json(),
        )
        script_b = _script(
            _analyst_json(_claim("claim from response B")),
            _critic_json("pass"),
            _risk_json(),
            _portfolio_json(),
        )
        run_a = _pipeline(script_a).run()
        run_b = _pipeline(script_b).run()
        assert run_a.run_id == run_b.run_id
        assert run_a.analyst_report.claims[0].statement != run_b.analyst_report.claims[0].statement

    def test_run_id_sensitive_to_charter(self) -> None:
        pipeline = _pipeline(_full_script())
        altered = ResearchPipeline(
            ModelGateway(_full_script(), model_name=MODEL),
            context=CONTEXT,
            risk_verdicts=RISK_VERDICTS,
            portfolio_inputs=PORTFOLIO_INPUTS,
            charters={
                **CHARTERS,
                "analyst": RoleCharter(
                    role="analyst",
                    system_prompt=CHARTERS["analyst"].system_prompt + " (altered)",
                    tools=CHARTERS["analyst"].tools,
                    output_schema_id=CHARTERS["analyst"].output_schema_id,
                ),
            },
        )
        assert altered.run_id != pipeline.run_id

    def test_empty_context_refused(self) -> None:
        with pytest.raises(PipelineError, match="empty research context"):
            ResearchPipeline(
                ModelGateway(_full_script(), model_name=MODEL),
                context={},
                risk_verdicts=RISK_VERDICTS,
                portfolio_inputs=PORTFOLIO_INPUTS,
            )

    def test_non_string_context_refused(self) -> None:
        with pytest.raises(PipelineError, match="content must be a string"):
            ResearchPipeline(
                ModelGateway(_full_script(), model_name=MODEL),
                context={"universe": 5},  # type: ignore[dict-item]
                risk_verdicts=RISK_VERDICTS,
                portfolio_inputs=PORTFOLIO_INPUTS,
            )
        with pytest.raises(PipelineError, match="name must be a string"):
            ResearchPipeline(
                ModelGateway(_full_script(), model_name=MODEL),
                context={7: "a non-string key"},  # type: ignore[dict-item]
                risk_verdicts=RISK_VERDICTS,
                portfolio_inputs=PORTFOLIO_INPUTS,
            )

    def test_empty_risk_verdicts_refused(self) -> None:
        with pytest.raises(PipelineError, match="risk-gate verdicts"):
            ResearchPipeline(
                ModelGateway(_full_script(), model_name=MODEL),
                context=CONTEXT,
                risk_verdicts={},
                portfolio_inputs=PORTFOLIO_INPUTS,
            )

    def test_empty_portfolio_inputs_refused(self) -> None:
        with pytest.raises(PipelineError, match="constraint/optimizer outputs"):
            ResearchPipeline(
                ModelGateway(_full_script(), model_name=MODEL),
                context=CONTEXT,
                risk_verdicts=RISK_VERDICTS,
                portfolio_inputs={},
            )

    def test_missing_charter_refused(self) -> None:
        with pytest.raises(PipelineError, match="missing role charters"):
            ResearchPipeline(
                ModelGateway(_full_script(), model_name=MODEL),
                context=CONTEXT,
                risk_verdicts=RISK_VERDICTS,
                portfolio_inputs=PORTFOLIO_INPUTS,
                charters={role: CHARTERS[role] for role in ROLE_ORDER if role != "analyst"},
            )

    def test_unknown_role_charter_refused(self) -> None:
        with pytest.raises(UnknownRoleError, match="executor"):
            ResearchPipeline(
                ModelGateway(_full_script(), model_name=MODEL),
                context=CONTEXT,
                risk_verdicts=RISK_VERDICTS,
                portfolio_inputs=PORTFOLIO_INPUTS,
                charters={
                    **CHARTERS,
                    "executor": RoleCharter(
                        role="executor",
                        system_prompt="place orders",
                        tools=(),
                        output_schema_id="executor-v1",
                    ),
                },
            )

    def test_risk_reference_to_unsupplied_verdict_refused(self) -> None:
        transport = _script(
            _analyst_json(_claim()),
            _critic_json("pass"),
            _risk_json(referenced=["gate-9"]),
            _portfolio_json(),
        )
        with pytest.raises(PipelineError, match="gate-9"):
            _pipeline(transport).run()

    def test_portfolio_reference_to_unsupplied_input_refused(self) -> None:
        transport = _script(
            _analyst_json(_claim()),
            _critic_json("pass"),
            _risk_json(),
            _portfolio_json(referenced=["constraint-9"]),
        )
        with pytest.raises(PipelineError, match="constraint-9"):
            _pipeline(transport).run()

    def test_hostile_analyst_output_fails_validation_no_result_escapes(self) -> None:
        transport = _script(
            json.dumps(
                {
                    "claims": [
                        {
                            "statement": "buy AAA now",
                            "confidence": 0.9,
                            "direction": "long",
                            "evidence_citations": ["doc-1"],
                            "quantity": 1000,
                        }
                    ]
                }
            ),
            _critic_json("pass"),
            _risk_json(),
            _portfolio_json(),
        )
        with pytest.raises(ModelOutputError, match="quantity"):
            _pipeline(transport).run()
