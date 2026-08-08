"""Structured research roles (M8, issue #46, Phase B).

Role charters as pinned data, pydantic output schemas with no
order-shaped field, and ``ResearchPipeline``: a deterministic
analyst -> critic gate -> risk -> portfolio stage order. The critic
gate blocks claims in deterministic code (never in the model's
cooperation), and the risk/portfolio references are structurally
validated against the supplied context ids. Every stage validates at
the gateway boundary (structured-only), and ``run_id`` is setup-only
— it never includes model outputs (the M7 discipline).
"""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from quantmesh.ai.decisions import DecisionLog, DecisionRecord, ModelMeta
from quantmesh.ai.errors import PipelineError, UnknownRoleError
from quantmesh.ai.gateway import ModelGateway
from quantmesh.ai.retrieval import Citation
from quantmesh.ai.wire import ChatMessage, ModelRequest

__all__ = [
    "AnalystReport",
    "CHARTERS",
    "Claim",
    "CriticGateResult",
    "CriticVerdict",
    "FlaggedClaim",
    "PortfolioReview",
    "ResearchPipeline",
    "ResearchResult",
    "RiskFinding",
    "RiskReview",
    "ROLE_ORDER",
    "RoleCharter",
    "charter",
]

ROLE_ORDER = ("analyst", "critic", "risk", "portfolio")

# Phase D binds these names to the tool registry; the charters declare
# the tool surface each role may hold, never an execution surface.
ANALYST_TOOLS = ("retrieve_documents", "read_experiment", "read_report")
CRITIC_TOOLS = ("retrieve_documents",)
RISK_TOOLS = ("read_risk_context",)
PORTFOLIO_TOOLS = ("read_portfolio_snapshot",)

_PIPELINE_VERSION = "quantmesh-research-pipeline-v1"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class RoleCharter:
    """A pinned role definition: who the role is, what it may use, and
    the schema its output must satisfy."""

    role: str
    system_prompt: str
    tools: tuple[str, ...]
    output_schema_id: str

    @property
    def digest(self) -> str:
        """Setup-only identity of the charter itself (never outputs)."""
        return _sha256(
            _canonical_json(
                {
                    "role": self.role,
                    "system_prompt": self.system_prompt,
                    "tools": list(self.tools),
                    "output_schema_id": self.output_schema_id,
                }
            )
        )


CHARTERS: Mapping[str, RoleCharter] = {
    "analyst": RoleCharter(
        role="analyst",
        system_prompt=(
            "You are the analyst role of a quantitative research pipeline. "
            "Produce claims from the provided research context only. Every "
            "claim must state a directional stance (long/short/neutral), a "
            "confidence in [0,1], and at least one citation id from the "
            "provided sources; a claim without a citation is invalid and "
            "must never appear. You produce research claims with evidence "
            "— never orders, never instructions with authority."
        ),
        tools=ANALYST_TOOLS,
        output_schema_id="analyst-report-v1",
    ),
    "critic": RoleCharter(
        role="critic",
        system_prompt=(
            "You are the critic role of a quantitative research pipeline. "
            "Review the analyst's claims adversarially: a claim that is "
            "unsupported by its citations, contradicts the context, or is "
            "incoherent must be flagged with the claim's index and a "
            "reason. Verdict 'pass' means every claim survives; verdict "
            "'flag' means at least one claim is blocked. You never produce "
            "claims yourself."
        ),
        tools=CRITIC_TOOLS,
        output_schema_id="critic-verdict-v1",
    ),
    "risk": RoleCharter(
        role="risk",
        system_prompt=(
            "You are the risk review role of a quantitative research "
            "pipeline. Review the risk surfaces of the research context "
            "against the supplied risk-gate verdicts. Your posture must be "
            "relative to those verdicts: 'aligned', 'divergent', or "
            "'unassessable', and you must reference at least one supplied "
            "verdict id verbatim in referenced_verdicts. You review risk — "
            "you never modify orders, positions, or limits."
        ),
        tools=RISK_TOOLS,
        output_schema_id="risk-review-v1",
    ),
    "portfolio": RoleCharter(
        role="portfolio",
        system_prompt=(
            "You are the portfolio review role of a quantitative research "
            "pipeline. Review the research output against the supplied "
            "constraint and optimizer outputs. Your posture must be "
            "'within_constraints', 'breaching', or 'unassessable', and you "
            "must reference at least one supplied output id verbatim in "
            "referenced_inputs. Suggestions are research observations only "
            "— never orders, never executable instructions."
        ),
        tools=PORTFOLIO_TOOLS,
        output_schema_id="portfolio-review-v1",
    ),
}


def charter(role: str) -> RoleCharter:
    """The pinned charter for ``role``; unknown roles are refused."""
    try:
        return CHARTERS[role]
    except KeyError:
        raise UnknownRoleError(f"unknown research role: {role!r}") from None


def _refuse_empty_strings(items: list[str], *, field: str) -> list[str]:
    for item in items:
        if not item.strip():
            raise ValueError(f"{field} entries must not be empty")
    return items


class Claim(BaseModel):
    """A research claim: a directional statement backed by citations."""

    # Unknown fields are refused, never silently dropped: an order-shaped
    # field smuggled into a claim fails validation instead of vanishing.
    model_config = ConfigDict(extra="forbid")

    statement: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    direction: Literal["long", "short", "neutral"]
    evidence_citations: list[str] = Field(
        min_length=1, description="at least one citation id, resolvable in Phase C"
    )

    @field_validator("evidence_citations")
    @classmethod
    def _citations_non_empty(cls, citations: list[str]) -> list[str]:
        return _refuse_empty_strings(citations, field="evidence_citations")


class AnalystReport(BaseModel):
    """The analyst's validated output; claims may be empty (nothing citable)."""

    model_config = ConfigDict(extra="forbid")

    claims: list[Claim] = Field(default_factory=list)


class FlaggedClaim(BaseModel):
    """A critic's pointer to an unsupported claim (index into the report)."""

    model_config = ConfigDict(extra="forbid")

    claim_index: int = Field(ge=0)
    reason: str = Field(min_length=1)


class CriticVerdict(BaseModel):
    """The critic's verdict; the gate resolves indices in deterministic code."""

    model_config = ConfigDict(extra="forbid")

    verdict: Literal["pass", "flag"]
    flagged_claims: list[FlaggedClaim] = Field(default_factory=list)


class RiskFinding(BaseModel):
    """One risk-surface observation from the risk stage."""

    model_config = ConfigDict(extra="forbid")

    surface: str = Field(min_length=1)
    severity: Literal["low", "medium", "high"]
    detail: str = Field(min_length=1)


class RiskReview(BaseModel):
    """The risk stage output; referenced verdicts are checked structurally."""

    model_config = ConfigDict(extra="forbid")

    posture: Literal["aligned", "divergent", "unassessable"]
    referenced_verdicts: list[str] = Field(
        min_length=1, description="supplied risk-gate verdict ids, verbatim"
    )
    findings: list[RiskFinding] = Field(default_factory=list)

    @field_validator("referenced_verdicts")
    @classmethod
    def _verdicts_non_empty(cls, verdicts: list[str]) -> list[str]:
        return _refuse_empty_strings(verdicts, field="referenced_verdicts")


class PortfolioReview(BaseModel):
    """The portfolio stage output; referenced inputs are checked structurally."""

    model_config = ConfigDict(extra="forbid")

    posture: Literal["within_constraints", "breaching", "unassessable"]
    referenced_inputs: list[str] = Field(
        min_length=1, description="supplied constraint/optimizer output ids, verbatim"
    )
    suggestions: list[str] = Field(
        default_factory=list, description="research observations, never instructions"
    )

    @field_validator("referenced_inputs")
    @classmethod
    def _inputs_non_empty(cls, inputs: list[str]) -> list[str]:
        return _refuse_empty_strings(inputs, field="referenced_inputs")

    @field_validator("suggestions")
    @classmethod
    def _suggestions_non_empty(cls, suggestions: list[str]) -> list[str]:
        return _refuse_empty_strings(suggestions, field="suggestions")


@dataclass(frozen=True)
class CriticGateResult:
    """The gate outcome: what survived, what was blocked, and the verdict."""

    verdict: CriticVerdict
    allowed: tuple[Claim, ...]
    blocked: tuple[Claim, ...]


@dataclass(frozen=True)
class ResearchResult:
    """The pipeline's full run: setup-only id + every stage's validated output."""

    run_id: str
    analyst_report: AnalystReport
    critic: CriticGateResult
    risk_review: RiskReview
    portfolio_review: PortfolioReview


_StageT = TypeVar("_StageT", bound=BaseModel)


def _format_context(context: Mapping[str, str]) -> str:
    """Canonical context block: sorted by name, so insertion order never
    changes the prompt (and therefore never changes model outputs)."""
    return "\n\n".join(
        f"## {name}\n{context[name]}" for name in sorted(context)
    )


_CITATION_KINDS = ("document", "experiment", "audit")


def _claim_citations(claims: tuple[Claim, ...]) -> list[Citation]:
    """Parse 'kind:id' claim citation ids into resolvable Citation objects.

    Every parseable id is recorded — a fabricated citation is audit
    material too; resolution happens downstream. Ids that do not parse
    into a known kind are left out of the citation list (the verdict
    and output digest still record them).
    """
    citations: list[Citation] = []
    for claim in claims:
        for citation_id in claim.evidence_citations:
            kind, _, source_id = citation_id.partition(":")
            if kind in _CITATION_KINDS and source_id:
                citations.append(Citation(source_kind=kind, source_id=source_id))
    return citations


def _apply_critic_gate(verdict: CriticVerdict, report: AnalystReport) -> CriticGateResult:
    """Resolve the critic's verdict against the analyst report in code.

    Fail-closed: 'pass' with flagged claims, 'flag' with none, and any
    out-of-range index are all refused — the gate never silently guesses.
    """
    if verdict.verdict == "pass":
        if verdict.flagged_claims:
            raise PipelineError("critic verdict 'pass' carries flagged claims")
        return CriticGateResult(verdict=verdict, allowed=tuple(report.claims), blocked=())
    if not verdict.flagged_claims:
        raise PipelineError("critic verdict 'flag' names no flagged claims")
    claim_count = len(report.claims)
    blocked_indices: set[int] = set()
    for flagged in verdict.flagged_claims:
        if flagged.claim_index >= claim_count:
            raise PipelineError(
                f"flagged claim index {flagged.claim_index} out of range "
                f"(report has {claim_count} claims)"
            )
        blocked_indices.add(flagged.claim_index)
    allowed = tuple(
        claim for index, claim in enumerate(report.claims) if index not in blocked_indices
    )
    blocked = tuple(report.claims[index] for index in sorted(blocked_indices))
    return CriticGateResult(verdict=verdict, allowed=allowed, blocked=blocked)


class ResearchPipeline:
    """The deterministic four-stage research pipeline.

    ``context`` is the redacted input context (name -> content); the
    risk stage structurally requires the supplied M5 risk-gate verdict
    ids and the portfolio stage the supplied M7 constraint/optimizer
    output ids — both non-empty, and every id a stage references must
    be one of them. Construction fails closed on missing charters,
    unknown roles, and empty supplies; ``run_id`` is setup-only over
    role set + charter digests + context digests, never model outputs.

    When ``decision_log`` is supplied, every stage records a
    content-addressed ``DecisionRecord`` (model metadata required at
    construction — never fabricated) whose citations come from the
    analyst claims' ``kind:id`` citation ids (kind one of
    document/experiment/audit — recorded as audit entries even when a
    citation does not resolve; resolution is the drill's job) and whose
    critic record carries the gate's refusal when claims were blocked.
    ``recorded_at`` pins the audit timestamp for byte-deterministic
    drills; decision identity excludes it, so pinning never changes
    ids. Without a log the pipeline is a pure computation.
    """

    def __init__(
        self,
        gateway: ModelGateway,
        *,
        context: Mapping[str, str],
        risk_verdicts: Mapping[str, str],
        portfolio_inputs: Mapping[str, str],
        charters: Mapping[str, RoleCharter] | None = None,
        decision_log: DecisionLog | None = None,
        model_meta: ModelMeta | None = None,
        recorded_at: datetime | None = None,
    ) -> None:
        resolved = dict(CHARTERS) if charters is None else dict(charters)
        missing = [role for role in ROLE_ORDER if role not in resolved]
        if missing:
            raise PipelineError(f"missing role charters: {missing}")
        extra = sorted(set(resolved) - set(ROLE_ORDER))
        if extra:
            raise UnknownRoleError(f"unknown role(s): {extra}")
        if not context:
            raise PipelineError("empty research context: no sources to cite")
        for name, content in context.items():
            if not isinstance(name, str):
                raise PipelineError(f"context name must be a string, got {type(name).__name__}")
            if not isinstance(content, str):
                raise PipelineError(
                    f"context {name!r} content must be a string, got {type(content).__name__}"
                )
        if not risk_verdicts:
            raise PipelineError("the risk stage requires supplied risk-gate verdicts")
        if not portfolio_inputs:
            raise PipelineError(
                "the portfolio stage requires supplied constraint/optimizer outputs"
            )
        if decision_log is not None and model_meta is None:
            raise PipelineError(
                "decision-log recording requires model metadata (model_meta)"
            )
        self._gateway = gateway
        self._context = dict(context)
        self._risk_verdicts = dict(risk_verdicts)
        self._portfolio_inputs = dict(portfolio_inputs)
        self._charters = resolved
        self._decision_log = decision_log
        self._model_meta = model_meta
        self._recorded_at = recorded_at

    @property
    def run_id(self) -> str:
        """Setup-only identity: role set + charter digests + context digests."""
        material = {
            "version": _PIPELINE_VERSION,
            "roles": list(ROLE_ORDER),
            "charter_digests": {
                role: self._charters[role].digest for role in ROLE_ORDER
            },
            "context": {
                name: _sha256(self._context[name]) for name in sorted(self._context)
            },
        }
        return _sha256(_canonical_json(material))[:16]

    def _stage(
        self,
        role: str,
        prompt: str,
        schema: type[_StageT],
    ) -> _StageT:
        request = ModelRequest(
            messages=[
                ChatMessage(role="system", content=self._charters[role].system_prompt),
                ChatMessage(role="user", content=prompt),
            ],
            temperature=0.0,
            max_tokens=2048,
        )
        return self._gateway.complete_structured(request, schema)

    def _record(
        self,
        role: str,
        prompt: str,
        output: BaseModel,
        *,
        citations: list[Citation] | None = None,
        refusal: str | None = None,
    ) -> None:
        """Record one stage decision; without an injected log this is a no-op."""
        if self._decision_log is None:
            return
        if self._model_meta is None:
            raise PipelineError("decision-log recording requires model metadata")
        self._decision_log.record(
            DecisionRecord.for_stage(
                run_id=self.run_id,
                role=role,
                model=self._model_meta,
                prompt=prompt,
                schema_id=self._charters[role].output_schema_id,
                output=output,
                citations=citations,
                refusal=refusal,
                recorded_at=self._recorded_at,
            )
        )

    def _require_references(
        self,
        referenced: list[str],
        supplied: Mapping[str, str],
        *,
        what: str,
    ) -> None:
        unknown = sorted(set(referenced) - set(supplied))
        if unknown:
            raise PipelineError(f"references unsupplied {what} ids: {unknown}")

    def run(self) -> ResearchResult:
        """Execute the fixed analyst -> critic -> risk -> portfolio order."""
        context_block = _format_context(self._context)

        analyst_prompt = f"Research context:\n\n{context_block}"
        analyst_report = self._stage("analyst", analyst_prompt, AnalystReport)
        self._record(
            "analyst",
            analyst_prompt,
            analyst_report,
            citations=_claim_citations(tuple(analyst_report.claims)),
        )

        critic_prompt = (
            f"Research context:\n\n{context_block}\n\n"
            f"## Analyst report\n{analyst_report.model_dump_json()}\n\n"
            "Flag every claim index that lacks support. Verdict 'pass' only "
            "if every claim survives."
        )
        verdict = self._stage("critic", critic_prompt, CriticVerdict)
        gate = _apply_critic_gate(verdict, analyst_report)
        gate_refusal = None
        if gate.blocked:
            blocked_indices = sorted(
                index
                for index, claim in enumerate(analyst_report.claims)
                if claim in gate.blocked
            )
            gate_refusal = (
                f"critic gate blocked {len(gate.blocked)} claim(s): "
                f"indices {blocked_indices}"
            )
        self._record("critic", critic_prompt, verdict, refusal=gate_refusal)

        gated_report = AnalystReport(claims=list(gate.allowed))
        verdict_block = "\n".join(
            f"- {verdict_id}: {summary}"
            for verdict_id, summary in sorted(self._risk_verdicts.items())
        )
        risk_prompt = (
            f"Research context:\n\n{context_block}\n\n"
            f"## Analyst report (after the critic gate)\n{gated_report.model_dump_json()}\n\n"
            f"## Critic verdict\n{verdict.model_dump_json()}\n\n"
            f"## Supplied risk-gate verdicts\n{verdict_block}\n"
            "Reference supplied verdict ids verbatim in referenced_verdicts."
        )
        risk_review = self._stage("risk", risk_prompt, RiskReview)
        self._require_references(
            risk_review.referenced_verdicts, self._risk_verdicts, what="risk-gate verdict"
        )
        self._record("risk", risk_prompt, risk_review)

        portfolio_block = "\n".join(
            f"- {output_id}: {summary}"
            for output_id, summary in sorted(self._portfolio_inputs.items())
        )
        portfolio_prompt = (
            f"Research context:\n\n{context_block}\n\n"
            f"## Analyst report (after the critic gate)\n{gated_report.model_dump_json()}\n\n"
            f"## Critic verdict\n{verdict.model_dump_json()}\n\n"
            f"## Risk review\n{risk_review.model_dump_json()}\n\n"
            f"## Supplied constraint/optimizer outputs\n{portfolio_block}\n"
            "Reference supplied output ids verbatim in referenced_inputs."
        )
        portfolio_review = self._stage("portfolio", portfolio_prompt, PortfolioReview)
        self._require_references(
            portfolio_review.referenced_inputs,
            self._portfolio_inputs,
            what="constraint/optimizer output",
        )
        self._record("portfolio", portfolio_prompt, portfolio_review)

        return ResearchResult(
            run_id=self.run_id,
            analyst_report=analyst_report,
            critic=gate,
            risk_review=risk_review,
            portfolio_review=portfolio_review,
        )
