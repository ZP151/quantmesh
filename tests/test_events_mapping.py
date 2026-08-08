"""Cross-platform event mapping: evidence discipline, ledger and the
M6 acceptance drill (issue #37, Phase D).

The mapping suite pins the reconciliation discipline (ADR-0008 decision
5): pairs exist only with recorded evidence, matched needs two
independent evidence items, one evidence leaves a pair pending,
conflicting strong candidates are ambiguous, and nothing is ever
guessed. The acceptance drill then runs the M6 pipeline end to end on
the recorded fixture datasets: fixture events through the real
adapters, mapped with honest evidence, implied probabilities from the
recorded wire prices, and a calibration ``ForecastReport`` with Brier,
reliability bins and liquidity confidence.

The honest verdict over the fixture data is the interesting one: every
fixture market is binary with a generic Yes/No outcome set, so every
candidate pair carries exactly one evidence item (the outcome set) and
stays PENDING — including the Fed correspondence every reader knows is
real. The algorithm refuses to claim it, because the Sept 2026
Polymarket questions and the Apr 2027 Kalshi question differ in title,
expiry and resolution rule. A drill-only synthetic pair (``DRILL-``
ids, clearly not fixture data) demonstrates the MATCHED path with all
four evidence kinds and the full Brier/calibration/liquidity path; the
wire fixtures are never modified.
"""

from datetime import UTC, datetime, timedelta

import pytest

from quantmesh.events.calibration import implied_probability
from quantmesh.events.forecast import (
    ForecastMarket,
    ForecastObservation,
    ForecastReportRegistry,
    ForecastWindowSpec,
    forecast_artifact_paths,
    forecast_report_id,
    run_forecast_report,
)
from quantmesh.events.mapping import (
    MAPPINGS_FILE,
    EventMappingReport,
    EventPairing,
    EvidenceKind,
    MappingLedger,
    MappingRecord,
    MappingStatus,
    map_events,
    normalize_event_text,
    pair_key,
)
from quantmesh.events.models import EventMarket, EventVenue, MarketQuote, Outcome, ResolutionRule
from quantmesh.kalshi.market_data import KalshiFixtureProvider
from quantmesh.polymarket.market_data import PolyFixtureProvider

_T0 = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
_HOUR = timedelta(hours=1)

# A realistic Fed question used by the unit tests (both sides share it,
# so it matches); the drill uses its own DRILL-labelled title below.
_FED_TITLE = (
    "Will the upper bound of the federal funds rate be above 3.50% "
    "following the Fed's Apr 28, 2027 meeting?"
)
_DRILL_TITLE = "DRILL DEMO QUESTION: does the drill contract settle?"

KALSHI_FED_ID = "KXFED-27APR-T3.50"
KALSHI_MARS_ID = "KXELONMARS-99"
KALSHI_TENNIS_ID = "KXMVECROSSCATEGORY-S2026B117AD0234B-20FD2D82A98"
KALSHI_FIXTURE_IDS = {KALSHI_MARS_ID, KALSHI_TENNIS_ID, KALSHI_FED_ID}


def _event(
    market_id: str,
    *,
    venue: EventVenue,
    title: str = _FED_TITLE,
    expiry: datetime | None = _T0 + 30 * timedelta(days=1),
    rule_text: str = "fixture rule",
    outcomes: list[str] | None = None,
    resolution: list[str] | None = None,
    resolved_at: datetime | None = None,
) -> EventMarket:
    names = outcomes if outcomes is not None else ["Yes", "No"]
    return EventMarket(
        venue=venue,
        venue_market_id=market_id,
        event_ticker=f"event-{market_id}",
        title=title,
        category="drill",
        expiry_at=expiry,
        outcomes=[Outcome(name=name, venue_outcome_id=name) for name in names],
        resolution_rule=ResolutionRule.of(rule_text),
        resolution=list(resolution or []),
        resolved_at=resolved_at,
    )


def _poly(market_id: str, **kwargs) -> EventMarket:
    return _event(market_id, venue=EventVenue.POLYMARKET, **kwargs)


def _kalshi(market_id: str, **kwargs) -> EventMarket:
    return _event(market_id, venue=EventVenue.KALSHI, **kwargs)


class TestNormalization:
    def test_whitespace_case_and_width_insensitive(self):
        assert normalize_event_text("Will the Fed   RAISE?") == normalize_event_text(
            "will\tthe fed raise?"
        )
        assert normalize_event_text("Ⅰ dollar bet") == normalize_event_text("I dollar bet")

    def test_substantive_wording_change_does_not_match(self):
        assert normalize_event_text("Will the Fed raise?") != normalize_event_text(
            "Will the Fed cut?"
        )


class TestPairKey:
    def test_order_invariant(self):
        assert pair_key("a", "b") == pair_key("b", "a")

    def test_distinct_pairs_distinct_keys(self):
        assert pair_key("a", "b") != pair_key("a", "c")


class TestMapEvents:
    def test_matched_pair_with_full_evidence(self):
        report = map_events([_poly("p1")], [_kalshi("k1")])
        assert len(report.pairs) == 1
        pair = report.pairs[0]
        assert pair.status is MappingStatus.MATCHED
        assert [e.kind for e in pair.evidence] == [
            EvidenceKind.EXPIRY,
            EvidenceKind.OUTCOME_SET,
            EvidenceKind.RESOLUTION_RULE,
            EvidenceKind.TITLE,
        ]

    def test_outcome_set_alone_is_pending(self):
        report = map_events(
            [_poly("p1", title="Completely different question", rule_text="rule a")],
            [_kalshi(
                "k1",
                title="Another question entirely",
                rule_text="rule b",
                expiry=_T0 + 45 * _HOUR,
            )],
        )
        assert len(report.pairs) == 1
        pair = report.pairs[0]
        assert pair.status is MappingStatus.PENDING
        assert [e.kind for e in pair.evidence] == [EvidenceKind.OUTCOME_SET]

    def test_title_alone_is_pending(self):
        report = map_events(
            [_poly("p1", outcomes=["Yes", "No"], rule_text="rule a")],
            [_kalshi(
                "k1", outcomes=["Up", "Down"], rule_text="rule b", expiry=_T0 + 45 * _HOUR
            )],
        )
        pair = report.pairs[0]
        assert pair.status is MappingStatus.PENDING
        assert [e.kind for e in pair.evidence] == [EvidenceKind.TITLE]

    def test_two_strong_candidates_are_ambiguous(self):
        # p1 matches k1 on title+outcomes+rule and k2 on outcome
        # set+expiry+rule: neither candidate can be chosen over the
        # other, so both pairs are recorded as ambiguous.
        p1 = _poly("p1", title="Same question?", rule_text="same rule")
        k1 = _kalshi("k1", title="Same question?", rule_text="different rule")
        k2 = _kalshi(
            "k2",
            title="A different question entirely",
            rule_text="same rule",
            expiry=p1.expiry_at,
        )
        report = map_events([p1], [k1, k2])
        assert {pair.status for pair in report.pairs} == {MappingStatus.AMBIGUOUS}
        assert len(report.pairs) == 2
        for pair in report.pairs:
            assert len(pair.evidence) >= 2

    def test_strong_and_weak_candidate_do_not_conflict(self):
        p1 = _poly("p1", title="Same question?", rule_text="rule a", expiry=_T0 + 100 * _HOUR)
        k1 = _kalshi("k1", title="Same question?", rule_text="rule b", expiry=_T0 + 50 * _HOUR)
        k2 = _kalshi(
            "k2", title="Different", rule_text="rule c", expiry=_T0 + 200 * _HOUR
        )
        report = map_events([p1], [k1, k2])
        by_kalshi = {pair.kalshi_market_id: pair for pair in report.pairs}
        assert by_kalshi["k1"].status is MappingStatus.MATCHED
        assert by_kalshi["k2"].status is MappingStatus.PENDING

    def test_unmatched_events_are_reported_not_guessed(self):
        report = map_events(
            [_poly("p1"), _poly(
                "p2",
                title="unrelated question",
                outcomes=["Up", "Down"],
                rule_text="rule x",
                expiry=_T0 + 60 * _HOUR,
            )],
            [_kalshi("k1")],
        )
        assert report.unmatched_polymarket == ["p2"]
        assert report.unmatched_kalshi == []

    def test_expiry_tolerance_boundary(self):
        expiry = _T0 + timedelta(days=30)
        inside = _kalshi(
            "k1",
            title="Question B",
            rule_text="rule b",
            expiry=expiry + timedelta(seconds=3600),
        )
        outside = _kalshi(
            "k2",
            title="Question B",
            rule_text="rule b",
            expiry=expiry + timedelta(seconds=3601),
        )
        report = map_events(
            [_poly("p1", title="Question A", rule_text="rule a")], [inside, outside]
        )
        kinds = {
            pair.kalshi_market_id: [e.kind for e in pair.evidence]
            for pair in report.pairs
        }
        assert EvidenceKind.EXPIRY in kinds["k1"]
        assert EvidenceKind.EXPIRY not in kinds["k2"]

    def test_expiry_on_one_side_only_never_evidences(self):
        report = map_events([_poly("p1", expiry=None)], [_kalshi("k1")])
        pair = report.pairs[0]
        assert EvidenceKind.EXPIRY not in [e.kind for e in pair.evidence]

    def test_pairs_are_sorted_and_deterministic(self):
        first = map_events([_poly("p1"), _poly("p2"), _poly("p3")], [_kalshi("k1")])
        second = map_events([_poly("p3"), _poly("p1"), _poly("p2")], [_kalshi("k1")])
        assert [p.pair_key for p in first.pairs] == [p.pair_key for p in second.pairs]
        assert first.model_dump() == second.model_dump()

    def test_empty_universe_fails_closed(self):
        with pytest.raises(ValueError, match="at least one event"):
            map_events([], [_kalshi("k1")])

    def test_duplicate_ids_fail_closed(self):
        with pytest.raises(ValueError, match="repeat a venue_market_id"):
            map_events([_poly("p1"), _poly("p1")], [_kalshi("k1")])

    def test_outcome_set_ignores_order(self):
        report = map_events(
            [_poly("p1", title="x", rule_text="rule a")],
            [_kalshi(
                "k1",
                title="y",
                rule_text="rule b",
                outcomes=["No", "Yes"],
                expiry=_T0 + 45 * _HOUR,
            )],
        )
        assert [e.kind for e in report.pairs[0].evidence] == [EvidenceKind.OUTCOME_SET]


class TestPairingValidation:
    def test_pending_with_two_evidence_refused(self):
        with pytest.raises(ValueError, match="exactly one"):
            EventPairing(
                pair_key=pair_key("a", "b"),
                polymarket_market_id="a",
                kalshi_market_id="b",
                status=MappingStatus.PENDING,
                evidence=[
                    {"kind": EvidenceKind.EXPIRY, "detail": "x"},
                    {"kind": EvidenceKind.TITLE, "detail": "y"},
                ],
            )

    def test_matched_with_one_evidence_refused(self):
        with pytest.raises(ValueError, match="needs at least 2"):
            EventPairing(
                pair_key=pair_key("a", "b"),
                polymarket_market_id="a",
                kalshi_market_id="b",
                status=MappingStatus.MATCHED,
                evidence=[{"kind": EvidenceKind.TITLE, "detail": "x"}],
            )

    def test_unsorted_evidence_refused(self):
        with pytest.raises(ValueError, match="sorted by kind"):
            EventPairing(
                pair_key=pair_key("a", "b"),
                polymarket_market_id="a",
                kalshi_market_id="b",
                status=MappingStatus.MATCHED,
                evidence=[
                    {"kind": EvidenceKind.TITLE, "detail": "x"},
                    {"kind": EvidenceKind.OUTCOME_SET, "detail": "y"},
                ],
            )

    def test_wrong_pair_key_refused(self):
        with pytest.raises(ValueError, match="does not match the pair"):
            EventPairing(
                pair_key="0" * 16,
                polymarket_market_id="a",
                kalshi_market_id="b",
                status=MappingStatus.PENDING,
                evidence=[{"kind": EvidenceKind.TITLE, "detail": "x"}],
            )


class TestMappingReportValidation:
    def test_paired_and_unmatched_overlap_refused(self):
        with pytest.raises(ValueError, match="both paired and unmatched"):
            EventMappingReport(
                pairs=[
                    EventPairing(
                        pair_key=pair_key("a", "b"),
                        polymarket_market_id="a",
                        kalshi_market_id="b",
                        status=MappingStatus.MATCHED,
                        evidence=[
                            {"kind": EvidenceKind.EXPIRY, "detail": "x"},
                            {"kind": EvidenceKind.TITLE, "detail": "y"},
                        ],
                    )
                ],
                unmatched_polymarket=["a"],
            )


class TestMappingLedger:
    def _matched_report(self) -> EventMappingReport:
        return map_events([_poly("p1")], [_kalshi("k1")])

    def _pending_report(self) -> EventMappingReport:
        return map_events(
            [_poly("p1", title="x", rule_text="rule a")],
            [_kalshi("k1", title="y", rule_text="rule b", expiry=_T0 + 45 * _HOUR)],
        )

    def test_record_all_by_pair(self, tmp_path):
        ledger = MappingLedger(tmp_path / "ledger")
        records = ledger.record(self._matched_report(), commit="cafe1234567")
        assert len(records) == 1
        assert ledger.all()[0].pair_key == records[0].pair_key
        assert [r.pair_key for r in ledger.by_pair(records[0].pair_key)] == [
            records[0].pair_key
        ]

    def test_identical_rerecord_refused(self, tmp_path):
        ledger = MappingLedger(tmp_path / "ledger")
        ledger.record(self._matched_report(), commit="cafe1234567")
        with pytest.raises(ValueError, match="already recorded"):
            ledger.record(self._matched_report(), commit="cafe1234567")

    def test_reresolved_pair_appends_history(self, tmp_path):
        ledger = MappingLedger(tmp_path / "ledger")
        first = ledger.record(self._pending_report(), commit="cafe1234567")[0]
        upgraded = map_events([_poly("p1")], [_kalshi("k1")])  # now matched
        ledger.record(upgraded, commit="cafe1234567")
        history = ledger.by_pair(first.pair_key)
        assert [record.status for record in history] == [
            MappingStatus.PENDING,
            MappingStatus.MATCHED,
        ]

    def test_corrupted_line_fails_closed_with_attribution(self, tmp_path):
        root = tmp_path / "ledger"
        root.mkdir()
        (root / MAPPINGS_FILE).write_text("not json\n", encoding="utf-8")
        with pytest.raises(ValueError, match="line 1 is invalid"):
            MappingLedger(root).all()

    def test_records_persist_across_instances(self, tmp_path):
        root = tmp_path / "ledger"
        MappingLedger(root).record(self._matched_report(), commit="cafe1234567")
        assert len(MappingLedger(root).all()) == 1

    def test_record_validates(self):
        with pytest.raises(ValueError, match="exactly one"):
            MappingRecord(
                pair_key=pair_key("a", "b"),
                status=MappingStatus.PENDING,
                evidence=[
                    {"kind": EvidenceKind.EXPIRY, "detail": "x"},
                    {"kind": EvidenceKind.TITLE, "detail": "y"},
                ],
                commit="cafe1234567",
                recorded_at=_T0,
            )


class TestAcceptanceDrill:
    """The M6 acceptance drill: fixture datasets end to end.

    1. Fixture Polymarket + Kalshi events through the real adapters.
    2. map_events over them — the honest verdict: 18 pending pairs,
       each on the generic Yes/No outcome set alone. The known-real
       Fed correspondence stays PENDING because the September 2026
       Polymarket questions and the April 2027 Kalshi question differ
       in title, expiry and resolution rule: nothing is guessed.
    3. A drill-only synthetic pair (``DRILL-`` ids, clearly not fixture
       data) demonstrates the MATCHED path with all four evidence
       kinds, and its resolution demonstrates the point-in-time Brier
       path.
    4. Implied probabilities from the recorded wire prices, then a
       calibration ForecastReport with Brier, reliability bins and
       liquidity confidence, byte-stable across registry roots.
    """

    def _fixture_report(self) -> EventMappingReport:
        return map_events(PolyFixtureProvider().events(), KalshiFixtureProvider().events())

    def test_fixture_mapping_is_honest(self):
        report = self._fixture_report()
        # Six polymarket events (the NBA matchup + five Fed markets) by
        # three kalshi events (Mars, settled tennis, Fed) — every
        # candidate pair carries exactly the generic Yes/No outcome
        # set and nothing more: 18 pending pairs, nothing matched,
        # nothing unmatched, nothing guessed.
        assert len(report.pairs) == 18
        assert all(pair.status is MappingStatus.PENDING for pair in report.pairs)
        assert all(
            [e.kind for e in pair.evidence] == [EvidenceKind.OUTCOME_SET]
            for pair in report.pairs
        )
        assert report.unmatched_polymarket == []
        assert report.unmatched_kalshi == []
        assert {pair.kalshi_market_id for pair in report.pairs} == KALSHI_FIXTURE_IDS
        assert len({pair.polymarket_market_id for pair in report.pairs}) == 6
        assert (
            sum(pair.kalshi_market_id == KALSHI_FED_ID for pair in report.pairs) == 6
        )

    def test_drill_matched_pair_and_ledger(self, tmp_path):
        drill_poly = _poly(
            "DRILL-POLY-1",
            title=_DRILL_TITLE,
            outcomes=["Contract A", "Contract B"],
            rule_text="the drill pair",
            expiry=_T0 + 20 * _HOUR,
        )
        drill_kalshi = _kalshi(
            "DRILL-KALSHI-1",
            title=_DRILL_TITLE,
            outcomes=["Contract A", "Contract B"],
            rule_text="the drill pair",
            expiry=_T0 + 20 * _HOUR,
            resolution=["Contract A"],
            resolved_at=_T0 + 12 * _HOUR,
        )
        combined = map_events(
            PolyFixtureProvider().events() + [drill_poly],
            KalshiFixtureProvider().events() + [drill_kalshi],
        )
        # 18 fixture pairs stay pending; the drill pair matches on all
        # four evidence kinds; nothing cross-pairs with the drill ids.
        assert len(combined.pairs) == 19
        drill_pair = next(
            pair for pair in combined.pairs if pair.polymarket_market_id == "DRILL-POLY-1"
        )
        assert drill_pair.status is MappingStatus.MATCHED
        assert [e.kind for e in drill_pair.evidence] == [
            EvidenceKind.EXPIRY,
            EvidenceKind.OUTCOME_SET,
            EvidenceKind.RESOLUTION_RULE,
            EvidenceKind.TITLE,
        ]
        ledger = MappingLedger(tmp_path / "ledger")
        ledger.record(combined, commit="cafe1234567")
        assert len(ledger.all()) == 19
        assert ledger.by_pair(drill_pair.pair_key)[0].status is MappingStatus.MATCHED
        with pytest.raises(ValueError, match="already recorded"):
            ledger.record(combined, commit="cafe1234567")

    def _forecast_universe(self) -> list[ForecastMarket]:
        """Fed market (recorded quote) + the drill pair (synthetic).

        The Fed market is unresolved — its window demonstrates the
        None discipline. The drill pair resolves "Contract A" (the
        positive side, outcomes[0]) at T+12h over a 20-hour
        observation grid, so windows closing before T+12h stay
        unresolved while later windows evaluate with Brier, bins and
        liquidity confidence. Drill-only ids; the fixture data itself
        is never modified.
        """
        kalshi = KalshiFixtureProvider()
        fed_event = next(
            event for event in kalshi.events() if event.venue_market_id == KALSHI_FED_ID
        )
        fed_estimate = implied_probability(kalshi.market_quote(KALSHI_FED_ID))

        drill_quote = MarketQuote(
            venue=EventVenue.KALSHI,
            symbol="DRILL-KALSHI-1",
            timestamp=_T0,
            best_bid=0.48,
            best_ask=0.52,
            last_trade_price=0.5,
            bid_depth=2000.0,
            ask_depth=2000.0,
            tick_size=0.02,
            taker_fee_bps=0.0,
        )
        drill_estimate = implied_probability(drill_quote)
        drill_market = _kalshi(
            "DRILL-KALSHI-1",
            title=_DRILL_TITLE,
            outcomes=["Contract A", "Contract B"],
            rule_text="the drill pair",
            expiry=_T0 + 20 * _HOUR,
            resolution=["Contract A"],
            resolved_at=_T0 + 12 * _HOUR,
        )

        fed_observations = [
            ForecastObservation(
                timestamp=_T0 + index * _HOUR,
                probability=fed_estimate.probability,
                liquidity_confidence=fed_estimate.liquidity_confidence,
            )
            for index in range(10)
        ]
        drill_observations = [
            ForecastObservation(
                timestamp=_T0 + index * _HOUR,
                probability=drill_estimate.probability,
                liquidity_confidence=drill_estimate.liquidity_confidence,
            )
            for index in range(20)
        ]
        return [
            ForecastMarket(market=fed_event, observations=fed_observations),
            ForecastMarket(market=drill_market, observations=drill_observations),
        ]

    def test_drill_converges_to_calibrated_forecast_report(self, tmp_path):
        universe = self._forecast_universe()
        spec = ForecastWindowSpec(
            train_observations=5, test_observations=5, step_observations=5
        )
        root_a = tmp_path / "a"
        root_b = tmp_path / "b"
        first = run_forecast_report(
            universe,
            window_spec=spec,
            commit="cafe1234567",
            registry=ForecastReportRegistry(root_a),
        )
        second = run_forecast_report(
            universe,
            window_spec=spec,
            commit="cafe1234567",
            registry=ForecastReportRegistry(root_b),
        )
        assert first.id == second.id == forecast_report_id(
            commit="cafe1234567",
            universe=[entry.market for entry in universe],
            window_spec=spec,
            n_bins=10,
        )
        # Fed market: 10 observations, 1 window, unresolved (None).
        # Drill market: 20 observations, 3 windows; window 0 closes at
        # T+9h before the T+12h resolution (None); window 1's test
        # spans T+10h..T+14h so only T+12h onward resolves (3 of 5);
        # window 2 resolves all 5 — p = 0.5 against outcome 1.0 gives
        # brier 0.25 at full confidence.
        metrics = first.metrics
        assert metrics["n_windows_total"] == 4
        assert metrics["n_evaluated_windows"] == 2
        assert metrics["n_resolved"] == 8
        assert metrics["mean_brier"] == pytest.approx(0.25)
        assert metrics["mean_liquidity_weighted_brier"] == pytest.approx(0.25)
        fed = first.markets[0]
        assert fed.market_id == f"kalshi:{KALSHI_FED_ID}"
        assert fed.windows[0].n_resolved == 0
        assert fed.windows[0].brier is None
        drill = first.markets[1]
        assert drill.market_id == "kalshi:DRILL-KALSHI-1"
        assert [w.n_resolved for w in drill.windows] == [0, 3, 5]
        assert drill.windows[0].brier is None
        assert drill.windows[1].brier == pytest.approx(0.25)
        assert len(drill.windows[1].calibration_bins) == 10
        assert drill.windows[1].calibration_bins[5].count == 3
        assert drill.windows[2].brier == pytest.approx(0.25)
        assert drill.windows[2].calibration_bins[5].count == 5
        # Artifacts are byte-stable across registry roots.
        for name, path_a in forecast_artifact_paths(root_a, first).items():
            assert (
                path_a.read_bytes()
                == forecast_artifact_paths(root_b, second)[name].read_bytes()
            )
        assert ForecastReportRegistry(root_a).get(first.id).id == first.id
