"""Phase C retrieval tests (M8, issue #47).

Covers the pinned lexical-ranker arithmetic, per-source search over
fixture registries/logs, citation resolution with every refusal path,
and the ADR-0006 manifest discipline (atomic appends, fail-closed
reads with line attribution, duplicate ids refused).
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from quantmesh.ai.errors import CitationResolutionError, RetrievalError
from quantmesh.ai.retrieval import (
    DOCUMENTS_FILE,
    AuditSource,
    Citation,
    Document,
    DocumentIndex,
    DocumentSource,
    ExperimentSource,
    RetrievedPassage,
    idf_weights,
    rank_texts,
    resolve_citation,
    tokenize,
)
from quantmesh.domain.models import Instrument, InstrumentType, Side, Venue
from quantmesh.domain.orders import Order, OrderStatus, OrderType
from quantmesh.execution.journal import OrderJournal
from quantmesh.research.experiments import (
    EXPERIMENTS_FILE,
    Experiment,
    ExperimentRegistry,
    experiment_id,
)

COMMIT = "0" * 40


def _experiment(
    dataset: str,
    revision: int = 1,
    *,
    parameters: dict[str, str | int | float | bool | None] | None = None,
    metrics: dict[str, str | int | float | bool | None] | None = None,
) -> Experiment:
    parameters = parameters or {}
    return Experiment(
        id=experiment_id(dataset, revision, COMMIT, parameters),
        dataset=dataset,
        revision=revision,
        commit=COMMIT,
        parameters=parameters,
        metrics=metrics or {},
        created_at=datetime.now(UTC),
    )


def _instrument(symbol: str = "BTC") -> Instrument:
    return Instrument(
        symbol=symbol,
        venue=Venue.HYPERLIQUID,
        instrument_type=InstrumentType.PERPETUAL,
    )


def _order(order_id: str, symbol: str = "BTC") -> Order:
    return Order(
        order_id=order_id,
        instrument=_instrument(symbol),
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
        "".join(experiment.model_dump_json() + "\n" for experiment in experiments),
        encoding="utf-8",
    )
    return ExperimentRegistry(root=root)


# ---------------------------------------------------------------------------
# Tokenizer and ranker (pinned arithmetic)
# ---------------------------------------------------------------------------


class TestTokenizer:
    def test_tokenize_casefolds_and_splits_words(self) -> None:
        assert tokenize("Aaa, Bbb! Ccc.") == ("aaa", "bbb", "ccc")

    def test_tokenize_empty_returns_nothing(self) -> None:
        assert tokenize("!!! ---") == ()


class TestIdfWeights:
    def test_idf_weights_single_document_are_one(self) -> None:
        assert idf_weights(["aaa bbb"]) == {"aaa": 1.0, "bbb": 1.0}

    def test_idf_prefers_rare_tokens(self) -> None:
        weights = idf_weights(["aaa bbb ccc", "bbb ddd", "eee"])
        assert weights["aaa"] == pytest.approx(1.693147, abs=1e-4)
        assert weights["bbb"] == pytest.approx(1.287682, abs=1e-4)
        assert weights["aaa"] > weights["bbb"] > 1.0


class TestRankTexts:
    def test_rank_pinned_arithmetic(self) -> None:
        # doc0 = aaa+bbb = 2.9808, doc1 = bbb = 1.2877, doc2 = no overlap.
        indices = rank_texts("aaa bbb", ["aaa bbb ccc", "bbb ddd", "eee"], top_k=2)
        assert indices == [0, 1]

    def test_rank_top_k_limits_results(self) -> None:
        assert rank_texts("aaa", ["aaa bbb", "bbb ccc"], top_k=1) == [0]

    def test_rank_ties_break_by_index(self) -> None:
        assert rank_texts("x y", ["x y", "y x"], top_k=2) == [0, 1]

    def test_rank_repeated_query_tokens_count_once(self) -> None:
        assert rank_texts("aaa aaa", ["aaa bbb", "aaa aaa bbb"], top_k=2) == [0, 1]

    def test_rank_no_overlap_excluded(self) -> None:
        assert rank_texts("zzz", ["aaa bbb"], top_k=2) == []

    def test_rank_refuses_top_k_below_one(self) -> None:
        with pytest.raises(RetrievalError, match="top_k"):
            rank_texts("aaa", ["aaa"], top_k=0)

    def test_rank_refuses_tokenless_query(self) -> None:
        with pytest.raises(RetrievalError, match="at least one token"):
            rank_texts("!!!", ["aaa"], top_k=1)


# ---------------------------------------------------------------------------
# Citation and passage models
# ---------------------------------------------------------------------------


class TestCitationModel:
    def test_citation_span_defaults_to_none(self) -> None:
        citation = Citation(source_kind="document", source_id="d-1")
        assert citation.span is None

    def test_citation_refuses_negative_span(self) -> None:
        with pytest.raises(ValidationError, match="span"):
            Citation(source_kind="document", source_id="d-1", span=(-1, 3))

    def test_citation_refuses_reversed_span(self) -> None:
        with pytest.raises(ValidationError, match="span"):
            Citation(source_kind="document", source_id="d-1", span=(5, 2))

    def test_citation_refuses_unknown_source_kind(self) -> None:
        with pytest.raises(ValidationError):
            Citation(source_kind="stock", source_id="d-1")

    def test_citation_refuses_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            Citation.model_validate(
                {"source_kind": "document", "source_id": "d-1", "quote": "x"}
            )

    def test_retrieved_passage_refuses_empty_content(self) -> None:
        citation = Citation(source_kind="document", source_id="d-1")
        with pytest.raises(ValidationError):
            RetrievedPassage(citation=citation, content="")

    def test_retrieved_passage_refuses_extra_fields(self) -> None:
        citation = Citation(source_kind="document", source_id="d-1")
        with pytest.raises(ValidationError):
            RetrievedPassage.model_validate(
                {"citation": citation, "content": "x", "score": 1.0}
            )


class TestDocumentModel:
    def test_document_refuses_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            Document.model_validate(
                {
                    "id": "d-1",
                    "kind": "news",
                    "source_path": "news.txt",
                    "ingested_at": datetime.now(UTC),
                    "content": "x",
                    "title": "sneaked in",
                }
            )

    def test_document_refuses_unknown_kind(self) -> None:
        with pytest.raises(ValidationError):
            Document(
                id="d-1",
                kind="blog",
                source_path="blog.txt",
                ingested_at=datetime.now(UTC),
                content="x",
            )

    def test_document_refuses_naive_timestamp(self) -> None:
        with pytest.raises(ValidationError, match="timezone-aware"):
            Document(
                id="d-1",
                kind="news",
                source_path="news.txt",
                ingested_at=datetime(2026, 1, 1),
                content="x",
            )


# ---------------------------------------------------------------------------
# DocumentIndex manifest discipline
# ---------------------------------------------------------------------------


class TestDocumentIndex:
    def test_ingest_writes_manifest_and_roundtrips(self, tmp_path) -> None:
        source = _write_text(tmp_path, "filing.txt", "BTC rally momentum")
        index = DocumentIndex(root=tmp_path / "docs")
        document = index.ingest_file(source, kind="filing", doc_id="f-1")
        assert document.id == "f-1"
        assert document.kind == "filing"
        assert document.source_path == str(source)
        assert document.content == "BTC rally momentum"
        assert (tmp_path / "docs" / DOCUMENTS_FILE).is_file()
        assert DocumentIndex(root=tmp_path / "docs").all() == [document]

    def test_ingest_preserves_append_order(self, tmp_path) -> None:
        index = DocumentIndex(root=tmp_path / "docs")
        index.ingest_file(_write_text(tmp_path, "a.txt", "first"), kind="note", doc_id="a")
        index.ingest_file(_write_text(tmp_path, "b.txt", "second"), kind="note", doc_id="b")
        assert [record.id for record in index.all()] == ["a", "b"]
        lines = (tmp_path / "docs" / DOCUMENTS_FILE).read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2

    def test_ingest_refuses_unknown_kind(self, tmp_path) -> None:
        index = DocumentIndex(root=tmp_path / "docs")
        with pytest.raises(RetrievalError, match="unknown document kind"):
            index.ingest_file(
                _write_text(tmp_path, "a.txt", "x"), kind="blog", doc_id="a"
            )
        assert index.all() == []

    def test_ingest_refuses_empty_id(self, tmp_path) -> None:
        index = DocumentIndex(root=tmp_path / "docs")
        with pytest.raises(RetrievalError, match="must not be empty"):
            index.ingest_file(_write_text(tmp_path, "a.txt", "x"), kind="news", doc_id=" ")

    def test_ingest_refuses_duplicate_id(self, tmp_path) -> None:
        index = DocumentIndex(root=tmp_path / "docs")
        index.ingest_file(_write_text(tmp_path, "a.txt", "first"), kind="note", doc_id="a")
        with pytest.raises(RetrievalError, match="already indexed"):
            index.ingest_file(_write_text(tmp_path, "b.txt", "second"), kind="note", doc_id="a")
        assert len(index.all()) == 1

    def test_ingest_refuses_missing_file(self, tmp_path) -> None:
        index = DocumentIndex(root=tmp_path / "docs")
        with pytest.raises(RetrievalError, match="cannot ingest"):
            index.ingest_file(tmp_path / "nope.txt", kind="news", doc_id="a")

    def test_ingest_refuses_empty_file(self, tmp_path) -> None:
        index = DocumentIndex(root=tmp_path / "docs")
        with pytest.raises(RetrievalError, match="the file is empty"):
            index.ingest_file(_write_text(tmp_path, "a.txt", "  "), kind="news", doc_id="a")

    def test_ingest_refuses_non_utf8_file(self, tmp_path) -> None:
        bad = tmp_path / "bad.txt"
        bad.write_bytes(b"\xff\xfe\x00\x80")
        index = DocumentIndex(root=tmp_path / "docs")
        with pytest.raises(RetrievalError, match="cannot ingest"):
            index.ingest_file(bad, kind="news", doc_id="a")

    def test_get_returns_record(self, tmp_path) -> None:
        index = DocumentIndex(root=tmp_path / "docs")
        index.ingest_file(_write_text(tmp_path, "a.txt", "x"), kind="news", doc_id="a")
        assert index.get("a").content == "x"

    def test_get_missing_raises_value_error(self, tmp_path) -> None:
        index = DocumentIndex(root=tmp_path / "docs")
        with pytest.raises(ValueError, match="no document recorded"):
            index.get("missing")

    def test_all_on_missing_root_is_empty(self, tmp_path) -> None:
        assert DocumentIndex(root=tmp_path / "docs").all() == []

    def test_manifest_corrupted_line_attributed(self, tmp_path) -> None:
        root = tmp_path / "docs"
        root.mkdir()
        (root / DOCUMENTS_FILE).write_text('{"broken": true}\n', encoding="utf-8")
        with pytest.raises(RetrievalError, match="line 1 is invalid"):
            DocumentIndex(root=root).all()

    def test_manifest_duplicate_ids_attributed(self, tmp_path) -> None:
        root = tmp_path / "docs"
        root.mkdir()
        document = Document(
            id="a",
            kind="news",
            source_path="a.txt",
            ingested_at=datetime.now(UTC),
            content="x",
        )
        line = document.model_dump_json()
        (root / DOCUMENTS_FILE).write_text(f"{line}\n{line}\n", encoding="utf-8")
        with pytest.raises(RetrievalError, match="share a document id"):
            DocumentIndex(root=root).all()

    def test_manifest_root_not_a_directory(self, tmp_path) -> None:
        not_a_dir = _write_text(tmp_path, "docs", "x")
        with pytest.raises(RetrievalError, match="not a directory"):
            DocumentIndex(root=not_a_dir).all()


# ---------------------------------------------------------------------------
# Registered sources over fixture registries/logs
# ---------------------------------------------------------------------------


class TestDocumentSource:
    def test_search_returns_ranked_passages(self, tmp_path) -> None:
        index = DocumentIndex(root=tmp_path / "docs")
        index.ingest_file(
            _write_text(tmp_path, "a.txt", "BTC rally momentum"), kind="news", doc_id="d-1"
        )
        index.ingest_file(
            _write_text(tmp_path, "b.txt", "gold prices diverge"), kind="filing", doc_id="d-2"
        )
        passages = DocumentSource(index).search("btc", top_k=2)
        assert [passage.citation.source_id for passage in passages] == ["d-1"]
        assert passages[0].citation.source_kind == "document"
        assert passages[0].content == "BTC rally momentum"

    def test_resolve_returns_record_and_text(self, tmp_path) -> None:
        index = DocumentIndex(root=tmp_path / "docs")
        index.ingest_file(
            _write_text(tmp_path, "a.txt", "BTC rally momentum"), kind="news", doc_id="d-1"
        )
        resolved = DocumentSource(index).resolve("d-1")
        assert resolved.record.id == "d-1"
        assert resolved.text == "BTC rally momentum"

    def test_resolve_missing_id_refused(self, tmp_path) -> None:
        source = DocumentSource(DocumentIndex(root=tmp_path / "docs"))
        with pytest.raises(RetrievalError, match="no document with id"):
            source.resolve("missing")


class TestExperimentSource:
    def test_search_returns_experiment_passage(self, tmp_path) -> None:
        btc = _experiment("btc_returns", parameters={"lookback": 30})
        eth = _experiment("eth_vol")
        registry = _write_experiments(tmp_path / "experiments", btc, eth)
        # The tokenizer treats the underscored dataset name as one token.
        passages = ExperimentSource(registry).search("btc_returns", top_k=2)
        assert len(passages) == 1
        assert passages[0].citation.source_kind == "experiment"
        assert passages[0].citation.source_id == btc.id
        assert passages[0].content == btc.model_dump_json()

    def test_resolve_returns_canonical_text_for_spans(self, tmp_path) -> None:
        experiment = _experiment("btc_returns")
        registry = _write_experiments(tmp_path / "experiments", experiment)
        resolved = ExperimentSource(registry).resolve(experiment.id)
        assert resolved.record == experiment
        assert resolved.text == experiment.model_dump_json()
        assert resolved.text.find("btc_returns") >= 0

    def test_resolve_missing_id_refused(self, tmp_path) -> None:
        registry = ExperimentRegistry(root=tmp_path / "experiments")
        source = ExperimentSource(registry)
        with pytest.raises(RetrievalError, match="no experiment recorded"):
            source.resolve("deadbeefdeadbeef")


class TestAuditSource:
    def test_search_returns_order_passage(self, tmp_path) -> None:
        journal = OrderJournal(root=tmp_path / "orders")
        journal.record(_order("o-1", symbol="BTC"))
        journal.record(_order("o-2", symbol="ETH"))
        passages = AuditSource(journal).search("btc", top_k=2)
        assert len(passages) == 1
        assert passages[0].citation.source_kind == "audit"
        assert passages[0].citation.source_id == "o-1"
        assert passages[0].content == journal.get("o-1").model_dump_json()

    def test_resolve_returns_order_record(self, tmp_path) -> None:
        journal = OrderJournal(root=tmp_path / "orders")
        journal.record(_order("o-1", symbol="BTC"))
        resolved = AuditSource(journal).resolve("o-1")
        assert resolved.record.order_id == "o-1"
        assert "symbol" in resolved.text

    def test_resolve_missing_id_refused(self, tmp_path) -> None:
        source = AuditSource(OrderJournal(root=tmp_path / "orders"))
        with pytest.raises(RetrievalError, match="no order recorded"):
            source.resolve("o-99")


# ---------------------------------------------------------------------------
# Citation resolution (fail-closed)
# ---------------------------------------------------------------------------


def _document_sources(tmp_path) -> dict[str, DocumentSource]:
    index = DocumentIndex(root=tmp_path / "docs")
    index.ingest_file(
        _write_text(tmp_path, "a.txt", "BTC rally momentum"), kind="news", doc_id="d-1"
    )
    return {"document": DocumentSource(index)}


class TestResolveCitation:
    def test_resolves_document_with_span(self, tmp_path) -> None:
        sources = _document_sources(tmp_path)
        citation = Citation(source_kind="document", source_id="d-1", span=(0, 3))
        resolved = resolve_citation(citation, sources)
        assert resolved.source_id == "d-1"
        assert resolved.record.id == "d-1"
        assert resolved.text == "BTC rally momentum"
        assert resolved.text[:3] == "BTC"

    def test_resolves_without_span(self, tmp_path) -> None:
        resolved = resolve_citation(
            Citation(source_kind="document", source_id="d-1"), _document_sources(tmp_path)
        )
        assert resolved.record.id == "d-1"

    def test_unknown_source_kind_refused(self, tmp_path) -> None:
        # The Citation literal already refuses "stock" at validation; the
        # resolver still fails closed if a citation were built around the
        # literal (defense in depth), so construct one bypassing validation.
        citation = Citation.model_construct(source_kind="stock", source_id="d-1")
        with pytest.raises(CitationResolutionError, match="unknown citation source kind"):
            resolve_citation(citation, _document_sources(tmp_path))

    def test_missing_source_in_mapping_refused(self, tmp_path) -> None:
        citation = Citation(source_kind="audit", source_id="o-1")
        with pytest.raises(CitationResolutionError, match="unknown citation source kind"):
            resolve_citation(citation, _document_sources(tmp_path))

    def test_missing_id_refused(self, tmp_path) -> None:
        citation = Citation(source_kind="document", source_id="missing")
        with pytest.raises(CitationResolutionError, match="no document with id"):
            resolve_citation(citation, _document_sources(tmp_path))

    def test_span_out_of_range_refused(self, tmp_path) -> None:
        citation = Citation(source_kind="document", source_id="d-1", span=(100, 200))
        with pytest.raises(CitationResolutionError, match="out of range"):
            resolve_citation(citation, _document_sources(tmp_path))

    def test_experiment_citation_resolves(self, tmp_path) -> None:
        experiment = _experiment("btc_returns")
        registry = _write_experiments(tmp_path / "experiments", experiment)
        sources = {"experiment": ExperimentSource(registry)}
        offset = experiment.model_dump_json().find("btc_returns")
        resolved = resolve_citation(
            Citation(
                source_kind="experiment",
                source_id=experiment.id,
                span=(offset, offset + len("btc_returns")),
            ),
            sources,
        )
        assert resolved.record.id == experiment.id

    def test_audit_citation_resolves(self, tmp_path) -> None:
        journal = OrderJournal(root=tmp_path / "orders")
        journal.record(_order("o-1", symbol="BTC"))
        sources = {"audit": AuditSource(journal)}
        resolved = resolve_citation(
            Citation(source_kind="audit", source_id="o-1"), sources
        )
        assert resolved.record.order_id == "o-1"
