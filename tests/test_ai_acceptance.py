"""Phase E acceptance drills (M8, issue #49).

The two roadmap exit criteria proven on fixture universes (scripted
transports throughout, no network anywhere):

1. Hostile model output is schema-rejected with a typed error and no
   partial object escapes; an order-shaped payload is refused at
   validation; a tool call to a non-existent execution surface is
   refused; and the whole ai package imports no order-sending surface
   (ast-level import scan over every module) — the risk stage's only
   authority is the structural reference check against supplied
   verdicts.

2. Research claims link to source data: an end-to-end pipeline over a
   fixture document, experiment-registry record and audit-log slice
   produces claims whose citations all resolve; a fabricated citation
   is flagged by the critic, the gate blocks the claim (it never
   reaches later stages — proven by the captured request bodies), and
   the decision log records the refusal. Cross-root determinism: the
   same drill over two decisions_dir roots with a pinned recorded_at
   produces byte-identical decision JSONL.
"""

import ast
import importlib
import inspect
import json
import pkgutil
from datetime import UTC, datetime

import pytest

from quantmesh import ai as ai_package
from quantmesh.ai.decisions import DecisionLog, ModelMeta
from quantmesh.ai.errors import (
    CitationResolutionError,
    ModelOutputError,
    PipelineError,
    ToolRefusalError,
    UnknownToolError,
)
from quantmesh.ai.gateway import ModelGateway
from quantmesh.ai.retrieval import (
    AuditSource,
    Citation,
    DocumentIndex,
    DocumentSource,
    ExperimentSource,
    resolve_citation,
)
from quantmesh.ai.roles import ResearchPipeline
from quantmesh.ai.tools import ToolRegistry, bind_default_surfaces
from quantmesh.ai.transport import ScriptedModelTransport
from quantmesh.domain.models import Instrument, InstrumentType, Side, Venue
from quantmesh.domain.orders import Order, OrderStatus, OrderType
from quantmesh.execution.journal import OrderJournal
from quantmesh.research.experiments import (
    EXPERIMENTS_FILE,
    Experiment,
    ExperimentRegistry,
    experiment_id,
)

MODEL = "fixture-model"
META = ModelMeta(name=MODEL, version="v1.0", endpoint_kind="scripted")
COMMIT = "0" * 40
PINNED_AT = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)

RISK_VERDICTS = {"gate-1": "risk decision allowed: exposure within the leverage bound"}
PORTFOLIO_INPUTS = {"constraint-1": "venue cap: hyperliquid <= 0.6, binding"}

# The order-SENDING surfaces the ai package must never import. The M2
# journal is the documented exception — a read-only record store
# (ADR-0010 decision 3), explicitly allowed and asserted.
ORDER_SENDING_SURFACES = (
    "quantmesh.paper",
    "quantmesh.moomoo.execution",
    "quantmesh.hyperliquid.exchange",
    "quantmesh.hyperliquid.risk",
    "quantmesh.execution.matcher",
    "quantmesh.execution.accounting",
    "quantmesh.execution.store",
    "quantmesh.execution.reconciliation",
)


def _experiment(dataset: str) -> Experiment:
    return Experiment(
        id=experiment_id(dataset, 1, COMMIT, {}),
        dataset=dataset,
        revision=1,
        commit=COMMIT,
        parameters={},
        metrics={"sharpe": 1.1},
        created_at=datetime.now(UTC),
    )


def _order(order_id: str) -> Order:
    return Order(
        order_id=order_id,
        instrument=Instrument(
            symbol="BTC",
            venue=Venue.HYPERLIQUID,
            instrument_type=InstrumentType.PERPETUAL,
        ),
        side=Side.BUY,
        quantity=1.0,
        order_type=OrderType.MARKET,
        created_at=datetime.now(UTC),
        status=OrderStatus.FILLED,
        filled_quantity=1.0,
    )


def _write_text(root, name: str, content: str):
    path = root / name
    path.write_text(content, encoding="utf-8")
    return path


def _write_experiments(root, *experiments: Experiment) -> ExperimentRegistry:
    """Hand-written registry manifest; reading never runs the lake pin gate."""
    path = root / EXPERIMENTS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(experiment.model_dump_json() for experiment in experiments) + "\n",
        encoding="utf-8",
    )
    return ExperimentRegistry(root=root)


@pytest.fixture
def universe(tmp_path) -> dict:
    """One fixture document, one experiment record, one audit-log row."""
    docs = DocumentIndex(root=tmp_path / "docs")
    docs.ingest_file(
        _write_text(
            tmp_path,
            "filing.txt",
            "AAA expanded its buyback program; the filing discloses a "
            "200M share repurchase authorization effective next quarter.",
        ),
        kind="filing",
        doc_id="d-1",
    )
    exp = _experiment("btc_returns")
    experiments = _write_experiments(tmp_path / "exps", exp)
    journal = OrderJournal(root=tmp_path / "orders")
    journal.record(_order("o-1"))
    context = {
        "retrieved": (
            f"[document:d-1] AAA expanded its buyback program; the filing "
            "discloses a 200M share repurchase authorization effective next "
            "quarter.\n"
            f"[experiment:{exp.id}] {exp.model_dump_json()}\n"
            f"[audit:o-1] {journal.get('o-1').model_dump_json()}"
        )
    }
    return {
        "docs": docs,
        "experiments": experiments,
        "journal": journal,
        "experiment_id": exp.id,
        "context": context,
    }


def _script(*contents: str) -> ScriptedModelTransport:
    return ScriptedModelTransport(
        [{"content": content, "model": MODEL} for content in contents]
    )


def _claim(statement: str, citation: str) -> dict:
    return {
        "statement": statement,
        "confidence": 0.7,
        "direction": "long",
        "evidence_citations": [citation],
    }


def _analyst_json(*claims: dict) -> str:
    return json.dumps({"claims": list(claims)})


def _critic_json(verdict: str, *flags: dict) -> str:
    return json.dumps({"verdict": verdict, "flagged_claims": list(flags)})


def _risk_json() -> str:
    return json.dumps(
        {
            "posture": "aligned",
            "referenced_verdicts": ["gate-1"],
            "findings": [],
        }
    )


def _portfolio_json() -> str:
    return json.dumps(
        {
            "posture": "within_constraints",
            "referenced_inputs": ["constraint-1"],
            "suggestions": ["exposure stays inside the binding venue cap"],
        }
    )


def _pipeline(transport, context, **kwargs) -> ResearchPipeline:
    return ResearchPipeline(
        ModelGateway(transport, model_name=MODEL),
        context=context,
        risk_verdicts=RISK_VERDICTS,
        portfolio_inputs=PORTFOLIO_INPUTS,
        **kwargs,
    )


def _sources(universe) -> dict:
    return {
        "document": DocumentSource(universe["docs"]),
        "experiment": ExperimentSource(universe["experiments"]),
        "audit": AuditSource(universe["journal"]),
    }


class TestExitCriterionOne:
    """Schema-validated output; the risk APIs cannot be bypassed."""

    def test_hostile_analyst_json_is_refused_with_no_partial_object(
        self, universe
    ) -> None:
        log = DecisionLog(root=universe["docs"].root.parent / "decisions")
        transport = _script(
            "definitely not json",
            _critic_json("pass"),
            _risk_json(),
            _portfolio_json(),
        )
        pipeline = _pipeline(
            transport, universe["context"], decision_log=log, model_meta=META
        )
        with pytest.raises(ModelOutputError, match="not JSON"):
            pipeline.run()
        # No partial object escaped, and nothing was recorded: the run
        # aborted at the first stage.
        assert log.all() == []

    def test_order_shaped_analyst_payload_is_refused(self, universe) -> None:
        order_shaped = {
            "claims": [
                {
                    "statement": "buy AAA",
                    "confidence": 0.9,
                    "direction": "long",
                    "evidence_citations": ["document:d-1"],
                    "quantity": 100,
                    "venue": "hyperliquid",
                    "order_type": "market",
                }
            ]
        }
        transport = _script(
            json.dumps(order_shaped),
            _critic_json("pass"),
            _risk_json(),
            _portfolio_json(),
        )
        pipeline = _pipeline(transport, universe["context"])
        with pytest.raises(ModelOutputError, match="quantity|venue"):
            pipeline.run()

    def test_hostile_tool_call_to_execution_surface_is_refused(self, universe) -> None:
        registry = ToolRegistry(
            surfaces=bind_default_surfaces(
                documents=DocumentSource(universe["docs"]),
                experiments=ExperimentSource(universe["experiments"]),
                reports=lambda report_id: f"report:{report_id}",
                risk_context=lambda: "risk context",
                portfolio_snapshot=lambda: "portfolio snapshot",
            )
        )
        with pytest.raises(UnknownToolError, match="place_order"):
            registry.dispatch("analyst", "place_order", {"symbol": "AAA", "quantity": 1})

    def test_permission_enforcement_holds_at_dispatch(self, universe) -> None:
        registry = ToolRegistry(
            surfaces=bind_default_surfaces(
                documents=DocumentSource(universe["docs"]),
                experiments=ExperimentSource(universe["experiments"]),
                reports=lambda report_id: f"report:{report_id}",
                risk_context=lambda: "risk context",
                portfolio_snapshot=lambda: "portfolio snapshot",
            )
        )
        with pytest.raises(ToolRefusalError, match="portfolio.*read_report|read_report.*portfolio"):
            registry.dispatch("portfolio", "read_report", {"report_id": "r-1"})

    def test_risk_stage_cannot_bypass_supplied_verdicts(self, universe) -> None:
        transport = _script(
            _analyst_json(_claim("AAA upside is supported", "document:d-1")),
            _critic_json("pass"),
            json.dumps(
                {
                    "posture": "aligned",
                    "referenced_verdicts": ["invented-verdict"],
                    "findings": [],
                }
            ),
            _portfolio_json(),
        )
        pipeline = _pipeline(transport, universe["context"])
        with pytest.raises(PipelineError, match="unsupplied risk-gate verdict"):
            pipeline.run()

    def test_ai_package_imports_no_order_sending_surface(self) -> None:
        imported: list[str] = []
        for info in pkgutil.walk_packages(ai_package.__path__, ai_package.__name__ + "."):
            if info.ispkg:
                continue
            module = importlib.import_module(info.name)
            tree = ast.parse(inspect.getsource(module))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.append(node.module)
        for name in imported:
            assert not name.startswith(ORDER_SENDING_SURFACES), (
                f"ai module imports order-sending surface {name}"
            )
        # The read-only M2 journal is the one permitted execution-package
        # import (the audit source reads it as data; ADR-0010 decision 3).
        assert "quantmesh.execution.journal" in imported


class TestExitCriterionTwo:
    """Claims link to source data and reproducible experiments."""

    def test_claims_carry_resolvable_citations(self, universe) -> None:
        exp_id = universe["experiment_id"]
        transport = _script(
            json.dumps(
                {
                    "claims": [
                        {
                            "statement": "AAA buyback authorization supports upside",
                            "confidence": 0.7,
                            "direction": "long",
                            "evidence_citations": ["document:d-1"],
                        },
                        {
                            "statement": "the experiment shows positive sharpe",
                            "confidence": 0.6,
                            "direction": "neutral",
                            "evidence_citations": [f"experiment:{exp_id}"],
                        },
                        {
                            "statement": "the audit log shows a filled buy",
                            "confidence": 0.5,
                            "direction": "neutral",
                            "evidence_citations": ["audit:o-1"],
                        },
                    ]
                }
            ),
            _critic_json("pass"),
            _risk_json(),
            _portfolio_json(),
        )
        log = DecisionLog(root=universe["docs"].root.parent / "decisions")
        pipeline = _pipeline(
            transport,
            universe["context"],
            decision_log=log,
            model_meta=META,
            recorded_at=PINNED_AT,
        )
        result = pipeline.run()

        assert len(result.analyst_report.claims) == 3
        assert result.critic.verdict.verdict == "pass"
        assert result.critic.blocked == ()
        assert result.risk_review.posture == "aligned"
        assert result.portfolio_review.posture == "within_constraints"

        # Every claim citation resolves to its source record.
        sources = _sources(universe)
        for claim in result.analyst_report.claims:
            for citation_id in claim.evidence_citations:
                kind, _, source_id = citation_id.partition(":")
                resolved = resolve_citation(
                    Citation(source_kind=kind, source_id=source_id), sources
                )
                assert resolved.source_kind == kind
                assert resolved.source_id == source_id
                assert resolved.text

        # The decision log holds one content-addressed record per stage,
        # with the claims' citations recorded as Citation objects.
        records = log.all()
        assert [record.role for record in records] == [
            "analyst",
            "critic",
            "risk",
            "portfolio",
        ]
        assert all(record.run_id == result.run_id for record in records)
        assert all(record.refusal is None for record in records)
        analyst = records[0]
        assert [citation.source_kind for citation in analyst.citations] == [
            "document",
            "experiment",
            "audit",
        ]
        assert [citation.source_id for citation in analyst.citations] == [
            "d-1",
            exp_id,
            "o-1",
        ]
        assert analyst.verdict  # canonical analyst JSON
        assert records[1].verdict == "pass"
        assert records[2].verdict == "aligned"
        assert records[3].verdict == "within_constraints"

    def test_fabricated_citation_is_flagged_blocked_and_recorded(
        self, universe
    ) -> None:
        transport = _script(
            _analyst_json(
                _claim("AAA will double on authority of this fabricated source", "document:zzz")
            ),
            _critic_json("flag", {"claim_index": 0, "reason": "citation does not exist"}),
            _risk_json(),
            _portfolio_json(),
        )
        log = DecisionLog(root=universe["docs"].root.parent / "decisions")
        pipeline = _pipeline(
            transport,
            universe["context"],
            decision_log=log,
            model_meta=META,
            recorded_at=PINNED_AT,
        )
        result = pipeline.run()

        # The critic flagged the fabricated citation; the gate blocked
        # the claim in code.
        assert result.critic.verdict.verdict == "flag"
        assert len(result.critic.blocked) == 1
        assert result.critic.allowed == ()
        assert "zzz" in result.critic.blocked[0].evidence_citations[0]

        # The blocked claim never reaches the risk or portfolio stages
        # (proven by the captured request bodies).
        bodies = transport.seen_bodies
        assert "fabricated" not in json.dumps(bodies[2])
        assert "fabricated" not in json.dumps(bodies[3])

        # The decision log records the refusal: the analyst record keeps
        # the fabricated citation as audit material, the critic record
        # carries the flag verdict and the gate's refusal summary.
        records = log.all()
        analyst, critic = records[0], records[1]
        assert [citation.source_id for citation in analyst.citations] == ["zzz"]
        assert critic.verdict == "flag"
        assert critic.refusal == "critic gate blocked 1 claim(s): indices [0]"

        # The fabricated citation cannot be resolved to any source.
        sources = _sources(universe)
        with pytest.raises(CitationResolutionError, match="zzz"):
            resolve_citation(Citation(source_kind="document", source_id="zzz"), sources)

    def test_cross_root_decision_logs_are_byte_identical(self, universe, tmp_path) -> None:
        exp_id = universe["experiment_id"]

        def drill(root) -> None:
            transport = _script(
                json.dumps(
                    {
                        "claims": [
                            {
                                "statement": "AAA buyback supports upside",
                                "confidence": 0.7,
                                "direction": "long",
                                "evidence_citations": ["document:d-1"],
                            },
                            {
                                "statement": "the experiment shows positive sharpe",
                                "confidence": 0.6,
                                "direction": "neutral",
                                "evidence_citations": [f"experiment:{exp_id}"],
                            },
                        ]
                    }
                ),
                _critic_json("pass"),
                _risk_json(),
                _portfolio_json(),
            )
            log = DecisionLog(root=root)
            result = _pipeline(
                transport,
                universe["context"],
                decision_log=log,
                model_meta=META,
                recorded_at=PINNED_AT,
            ).run()
            return result.run_id

        first_root = tmp_path / "decisions-a"
        second_root = tmp_path / "decisions-b"
        assert drill(first_root) == drill(second_root)
        first = (first_root / "decisions.jsonl").read_text(encoding="utf-8")
        second = (second_root / "decisions.jsonl").read_text(encoding="utf-8")
        assert first == second
