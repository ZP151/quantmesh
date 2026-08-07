"""M7 Phase D tests: deterministic scenario shocks replayed through the
M2 paper kernel, plus the kernel's funding extension (issue #42).

The drills pin the exact fixture arithmetic: a limit buy of 8000 AAA at
the 105 ask leaves cash 159,160 (fees 840 at 10 bps); a 20% gap-down
moves the base quote (95/105/92.5) to 76/84/74, marking equity at
751,160; a 0.76 equity-floor liquidation force-closes at the 76 bid,
leaving cash 766,552 — and a 0.8 floor that the flush cannot restore
fails closed.
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from quantmesh.domain.models import Instrument, InstrumentType, OrderRequest, Quote, Side, Venue
from quantmesh.execution.accounting import PaperAccount, Position
from quantmesh.portfolio import (
    EventMisresolutionShock,
    FundingShock,
    GapShock,
    LiquidationShock,
    PortfolioHolding,
    Scenario,
    ScenarioStep,
    run_scenario,
    scenario_id,
)

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _instrument(symbol="AAA", venue=Venue.MOOMOO) -> Instrument:
    return Instrument(symbol=symbol, venue=venue, instrument_type=InstrumentType.EQUITY)


def _quote(
    symbol="AAA",
    venue=Venue.MOOMOO,
    bid=95.0,
    ask=105.0,
    last=92.5,
    volume=8000.0,
    at=T0,
) -> Quote:
    return Quote(
        instrument=_instrument(symbol, venue),
        timestamp=at,
        bid=bid,
        ask=ask,
        last=last,
        volume=volume,
    )


def _order(
    symbol="AAA", side=Side.BUY, quantity=8000.0, limit_price=105.0
) -> OrderRequest:
    return OrderRequest(
        instrument=_instrument(symbol),
        side=side,
        quantity=quantity,
        limit_price=limit_price,
    )


def _holding(
    symbol="AAA",
    venue=Venue.MOOMOO,
    asset_class="equity",
    event_key=None,
    held_probability=None,
    weight=1.0,
) -> PortfolioHolding:
    return PortfolioHolding(
        venue=venue,
        symbol=symbol,
        asset_class=asset_class,
        event_key=event_key,
        held_probability=held_probability,
        weight=weight,
    )


def _scenario(*steps: ScenarioStep) -> Scenario:
    return Scenario(steps=list(steps), id=scenario_id(steps=list(steps)))


def _aaa_account(cash=1_000_000.0) -> PaperAccount:
    return PaperAccount(cash=cash)


class TestApplyFunding:
    """The kernel extension: signed charges are a fee-like journal entry."""

    def _position(self, symbol="AAA", quantity=100.0) -> Position:
        return Position(instrument=_instrument(symbol), quantity=quantity, average_cost=10.0)

    def test_charge_books_cash_and_total(self) -> None:
        account = PaperAccount(cash=1000.0, positions={"moomoo:AAA": self._position()})
        updated = account.apply_funding({"moomoo:AAA": 50.0})
        assert updated.cash == pytest.approx(950.0)
        assert updated.total_funding == pytest.approx(50.0)

    def test_negative_charge_receives(self) -> None:
        account = PaperAccount(cash=1000.0, positions={"moomoo:AAA": self._position()})
        updated = account.apply_funding({"moomoo:AAA": -50.0})
        assert updated.cash == pytest.approx(1050.0)
        assert updated.total_funding == pytest.approx(-50.0)

    def test_multiple_positions_accumulate(self) -> None:
        account = PaperAccount(
            cash=1000.0,
            positions={
                "moomoo:AAA": self._position(),
                "moomoo:BBB": self._position("BBB"),
            },
        )
        updated = account.apply_funding({"moomoo:AAA": 10.0, "moomoo:BBB": 20.0})
        assert updated.cash == pytest.approx(970.0)
        assert updated.total_funding == pytest.approx(30.0)

    def test_unknown_position_refused(self) -> None:
        account = PaperAccount(cash=1000.0, positions={"moomoo:AAA": self._position()})
        with pytest.raises(ValueError, match="funding charge for unknown position"):
            account.apply_funding({"moomoo:ZZZ": 50.0})

    def test_non_finite_charge_refused(self) -> None:
        account = PaperAccount(cash=1000.0, positions={"moomoo:AAA": self._position()})
        with pytest.raises(ValueError, match="non-finite funding charge"):
            account.apply_funding({"moomoo:AAA": float("nan")})

    def test_charge_beyond_cash_refused(self) -> None:
        account = PaperAccount(cash=1000.0, positions={"moomoo:AAA": self._position()})
        with pytest.raises(ValueError, match="exceed cash"):
            account.apply_funding({"moomoo:AAA": 2000.0})


class TestGapShock:
    def test_up_scales_prices(self) -> None:
        shock = GapShock(
            venue=Venue.MOOMOO, symbol="AAA", direction="up", gap_fraction=0.10
        )
        quote = shock.apply(_quote())
        assert quote.bid == pytest.approx(104.5)
        assert quote.ask == pytest.approx(115.5)
        assert quote.last == pytest.approx(101.75)

    def test_down_scales_prices(self) -> None:
        shock = GapShock(
            venue=Venue.MOOMOO, symbol="AAA", direction="down", gap_fraction=0.20
        )
        quote = shock.apply(_quote())
        assert quote.bid == pytest.approx(76.0)
        assert quote.ask == pytest.approx(84.0)
        assert quote.last == pytest.approx(74.0)

    def test_missing_prices_stay_missing(self) -> None:
        shock = GapShock(
            venue=Venue.MOOMOO, symbol="AAA", direction="up", gap_fraction=0.10
        )
        quote = shock.apply(_quote(bid=None, ask=None, last=None))
        assert quote.bid is None
        assert quote.ask is None
        assert quote.last is None

    def test_gap_fraction_bounds(self) -> None:
        with pytest.raises(ValidationError):
            GapShock(venue=Venue.MOOMOO, symbol="AAA", direction="down", gap_fraction=0.0)
        with pytest.raises(ValidationError):
            GapShock(venue=Venue.MOOMOO, symbol="AAA", direction="down", gap_fraction=1.0)

    def test_target_key(self) -> None:
        shock = GapShock(
            venue=Venue.HYPERLIQUID, symbol="BTC", direction="up", gap_fraction=0.05
        )
        assert shock.target_key == "hyperliquid:BTC"


class TestFundingShockReplay:
    def test_limit_buy_drill(self) -> None:
        account = _aaa_account()
        scenario = _scenario(ScenarioStep(at=T0, orders=[_order()]))
        run = run_scenario(
            account, scenario, quotes={"moomoo:AAA": _quote()}, holdings=[_holding()]
        )
        window = run.windows[0]
        # 8000 x 105 = 840,000, fee 840 at 10 bps: cash 159,160.
        assert window.cash == pytest.approx(159_160.0)
        assert window.positions == {"moomoo:AAA": 8000.0}
        assert window.equity == pytest.approx(899_160.0)
        assert window.total_fees == pytest.approx(840.0)
        assert window.total_funding == pytest.approx(0.0)
        assert run.metrics["n_fills"] == 1

    def test_funding_charge_then_receive(self) -> None:
        account = _aaa_account()
        steps = [
            ScenarioStep(at=T0, orders=[_order()]),
            ScenarioStep(
                at=datetime(2026, 1, 1, 0, 0, 10, tzinfo=UTC),
                shocks=[FundingShock(venue=Venue.MOOMOO, symbol="AAA", rate=0.01)],
            ),
            ScenarioStep(
                at=datetime(2026, 1, 1, 0, 0, 20, tzinfo=UTC),
                shocks=[FundingShock(venue=Venue.MOOMOO, symbol="AAA", rate=-0.005)],
            ),
        ]
        run = run_scenario(
            account,
            _scenario(*steps),
            quotes={"moomoo:AAA": _quote()},
            holdings=[_holding()],
        )
        # 840,000 x 0.01 charged, then 840,000 x 0.005 received.
        assert run.windows[1].cash == pytest.approx(150_760.0)
        assert run.windows[1].total_funding == pytest.approx(8_400.0)
        assert run.windows[2].cash == pytest.approx(154_960.0)
        assert run.windows[2].total_funding == pytest.approx(4_200.0)
        assert run.metrics["final_equity"] == pytest.approx(894_960.0)
        assert run.metrics["n_fills"] == 1

    def test_short_funding_marks_at_bid_and_receives(self) -> None:
        account = PaperAccount(
            cash=1000.0,
            positions={
                "moomoo:AAA": Position(
                    instrument=_instrument(), quantity=-100.0, average_cost=100.0
                )
            },
        )
        run = run_scenario(
            account,
            _scenario(
                ScenarioStep(
                    at=T0, shocks=[FundingShock(venue=Venue.MOOMOO, symbol="AAA", rate=0.01)]
                )
            ),
            quotes={"moomoo:AAA": _quote()},
            holdings=[_holding()],
        )
        # Marked at the bid (95): -100 x 95 x 0.01 = -95, the short receives.
        assert run.windows[0].cash == pytest.approx(1_095.0)
        assert run.windows[0].total_funding == pytest.approx(-95.0)

    def test_unknown_position_refused(self) -> None:
        account = _aaa_account()
        with pytest.raises(ValueError, match="funding shock targets 'moomoo:ZZZ'"):
            run_scenario(
                account,
                _scenario(
                    ScenarioStep(
                        at=T0,
                        shocks=[FundingShock(venue=Venue.MOOMOO, symbol="ZZZ", rate=0.01)],
                    )
                ),
                quotes={"moomoo:AAA": _quote(), "moomoo:ZZZ": _quote("ZZZ")},
                holdings=[_holding()],
            )

    def test_charge_beyond_cash_fails_closed(self) -> None:
        """Funding is charged before the step's orders submit, so the
        over-cash case needs the buy in its own step: cash 159,160 is
        insufficient for the 831,600 charge at rate 0.99."""
        account = _aaa_account()
        with pytest.raises(ValueError, match="exceed cash"):
            run_scenario(
                account,
                _scenario(
                    ScenarioStep(at=T0, orders=[_order()]),
                    ScenarioStep(
                        at=datetime(2026, 1, 1, 0, 0, 10, tzinfo=UTC),
                        shocks=[FundingShock(venue=Venue.MOOMOO, symbol="AAA", rate=0.99)],
                    ),
                ),
                quotes={"moomoo:AAA": _quote()},
                holdings=[_holding()],
            )

    def test_funding_shock_without_quote_refused(self) -> None:
        with pytest.raises(ValueError, match="which has no base quote"):
            run_scenario(
                _aaa_account(),
                _scenario(
                    ScenarioStep(
                        at=T0,
                        shocks=[FundingShock(venue=Venue.MOOMOO, symbol="ZZZ", rate=0.01)],
                    )
                ),
                quotes={},
                holdings=[],
            )

    def test_rate_bounds(self) -> None:
        with pytest.raises(ValidationError):
            FundingShock(venue=Venue.MOOMOO, symbol="AAA", rate=-1.0)
        with pytest.raises(ValidationError):
            FundingShock(venue=Venue.MOOMOO, symbol="AAA", rate=1.0)


class TestLiquidationShock:
    def _drill(self, floor: float) -> object:
        account = _aaa_account()
        step1 = ScenarioStep(at=T0, orders=[_order()])
        step2 = ScenarioStep(
            at=datetime(2026, 1, 1, 0, 0, 10, tzinfo=UTC),
            shocks=[
                GapShock(venue=Venue.MOOMOO, symbol="AAA", direction="down", gap_fraction=0.20),
                LiquidationShock(equity_floor=floor),
            ],
        )
        scenario = _scenario(step1, step2)
        return run_scenario(
            account, scenario, quotes={"moomoo:AAA": _quote()}, holdings=[_holding()]
        )

    def test_satisfiable_floor_flushes_in_one_sweep(self) -> None:
        run = self._drill(0.76)
        # Post-buy cash 159,160; gap-down marks equity at 751,160 (below
        # the 760,000 floor), so the sweep sells 8000 at the 76 bid:
        # 159,160 + 608,000 - 608 = 766,552, which holds the floor.
        assert run.windows[0].cash == pytest.approx(159_160.0)
        assert run.windows[0].equity == pytest.approx(899_160.0)
        assert run.windows[1].cash == pytest.approx(766_552.0)
        assert run.windows[1].equity == pytest.approx(766_552.0)
        assert run.windows[1].positions == {}
        assert run.windows[1].total_fees == pytest.approx(1_448.0)
        assert run.metrics["n_liquidation_rounds"] == 1.0
        assert run.metrics["n_fills"] == 1
        assert run.metrics["n_rejections"] == 0
        assert run.metrics["final_equity"] == pytest.approx(766_552.0)
        assert run.metrics["max_drawdown"] == pytest.approx(0.233448)

    def test_unreachable_floor_fails_closed(self) -> None:
        """Closing converts mark to cash (minus fees), so the flush
        cannot restore equity above what the 76 bid affords: a 0.8
        floor is a refusal, never a silent cascade."""
        with pytest.raises(ValueError, match="cannot satisfy the 0.8 equity floor"):
            self._drill(0.8)

    def test_floor_below_equity_does_not_trigger(self) -> None:
        run = self._drill(0.7)
        assert run.windows[1].equity == pytest.approx(751_160.0)
        assert run.windows[1].positions == {"moomoo:AAA": 8000.0}
        assert run.metrics["n_liquidation_rounds"] == 0.0

    def test_liquidation_needs_a_bid(self) -> None:
        account = _aaa_account()
        scenario = _scenario(
            ScenarioStep(at=T0, orders=[_order()]),
            ScenarioStep(
                at=datetime(2026, 1, 1, 0, 0, 10, tzinfo=UTC),
                shocks=[
                    GapShock(venue=Venue.MOOMOO, symbol="AAA", direction="down", gap_fraction=0.20),
                    LiquidationShock(equity_floor=0.76),
                ],
            ),
        )
        with pytest.raises(ValueError, match="liquidation needs a bid"):
            run_scenario(
                account,
                scenario,
                quotes={"moomoo:AAA": _quote(bid=None)},
                holdings=[_holding()],
            )

    def test_floor_bounds(self) -> None:
        with pytest.raises(ValidationError):
            LiquidationShock(equity_floor=-0.1)
        with pytest.raises(ValidationError):
            LiquidationShock(equity_floor=1.1)


class TestEventMisresolutionShock:
    def test_held_side_zeroes_the_event_sleeve(self) -> None:
        account = PaperAccount(cash=100_000.0)
        run = run_scenario(
            account,
            _scenario(
                ScenarioStep(
                    at=T0, shocks=[EventMisresolutionShock(event_key="FED-SEP")]
                )
            ),
            quotes={"moomoo:AAA": _quote()},
            holdings=[
                _holding(
                    symbol="tok-1",
                    venue=Venue.POLYMARKET,
                    asset_class="event",
                    event_key="FED-SEP",
                    held_probability=0.25,
                    weight=0.2,
                ),
                _holding("AAA", weight=0.8),
            ],
        )
        # The sleeve is marked-only: 0.2 x 0.25 = 0.05 of event value,
        # zeroed on misresolution; the kernel never sees the event.
        assert run.windows[0].event_value == pytest.approx(0.0)
        assert run.windows[0].equity == pytest.approx(100_000.0)
        assert run.metrics["final_equity"] == pytest.approx(100_000.0)

    def test_all_markets_on_the_event_key_zero(self) -> None:
        account = PaperAccount(cash=100_000.0)
        run = run_scenario(
            account,
            _scenario(
                ScenarioStep(
                    at=T0, shocks=[EventMisresolutionShock(event_key="FED-SEP")]
                )
            ),
            quotes={},
            holdings=[
                _holding(
                    symbol="tok-1",
                    venue=Venue.POLYMARKET,
                    asset_class="event",
                    event_key="FED-SEP",
                    held_probability=0.25,
                    weight=0.2,
                ),
                _holding(
                    symbol="KXFED",
                    venue=Venue.KALSHI,
                    asset_class="event",
                    event_key="FED-SEP",
                    held_probability=0.5,
                    weight=0.1,
                ),
            ],
        )
        assert run.windows[0].event_value == pytest.approx(0.0)

    def test_unknown_event_refused(self) -> None:
        with pytest.raises(ValueError, match="misresolution shock targets unknown event"):
            run_scenario(
                PaperAccount(cash=100_000.0),
                _scenario(
                    ScenarioStep(
                        at=T0, shocks=[EventMisresolutionShock(event_key="FED-DEC")]
                    )
                ),
                quotes={},
                holdings=[
                    _holding(
                        symbol="tok-1",
                        venue=Venue.POLYMARKET,
                        asset_class="event",
                        event_key="FED-SEP",
                        held_probability=0.25,
                        weight=0.2,
                    )
                ],
            )


class TestRunScenarioRefusals:
    def test_market_holding_without_quote(self) -> None:
        with pytest.raises(ValueError, match="has no base quote"):
            run_scenario(
                _aaa_account(),
                _scenario(ScenarioStep(at=T0)),
                quotes={},
                holdings=[_holding()],
            )

    def test_step_order_without_quote(self) -> None:
        with pytest.raises(ValueError, match="no base quote to match against"):
            run_scenario(
                _aaa_account(),
                _scenario(ScenarioStep(at=T0, orders=[_order("BBB")])),
                quotes={"moomoo:AAA": _quote()},
                holdings=[_holding()],
            )

    def test_gap_shock_without_quote(self) -> None:
        with pytest.raises(ValueError, match="which has no base quote"):
            run_scenario(
                _aaa_account(),
                _scenario(
                    ScenarioStep(
                        at=T0,
                        shocks=[
                            GapShock(
                                venue=Venue.MOOMOO,
                                symbol="BBB",
                                direction="up",
                                gap_fraction=0.1,
                            )
                        ],
                    )
                ),
                quotes={"moomoo:AAA": _quote()},
                holdings=[_holding()],
            )

    def test_position_without_mark_fails_closed(self) -> None:
        account = PaperAccount(
            cash=1000.0,
            positions={
                "moomoo:BBB": Position(
                    instrument=_instrument("BBB"), quantity=100.0, average_cost=10.0
                )
            },
        )
        with pytest.raises(ValueError, match="no mark for position 'moomoo:BBB'"):
            run_scenario(
                account,
                _scenario(ScenarioStep(at=T0)),
                quotes={"moomoo:AAA": _quote()},
                holdings=[_holding()],
            )

    def test_quote_without_mark_fails_closed(self) -> None:
        with pytest.raises(ValueError, match="no mark available"):
            run_scenario(
                _aaa_account(),
                _scenario(ScenarioStep(at=T0)),
                quotes={"moomoo:AAA": _quote(bid=None, last=None)},
                holdings=[_holding()],
            )

    def test_kill_switch_rejects_step_orders(self) -> None:
        run = run_scenario(
            PaperAccount(cash=1_000_000.0, kill_switch=True),
            _scenario(ScenarioStep(at=T0, orders=[_order()])),
            quotes={"moomoo:AAA": _quote()},
            holdings=[_holding()],
        )
        assert run.windows[0].rejections == ["kill switch enabled"]
        assert run.metrics["n_rejections"] == 1
        assert run.metrics["n_fills"] == 0


class TestScenarioIdentity:
    def test_step_order_is_setup(self) -> None:
        """The timeline order is setup: reordering the steps changes
        the id even when the steps themselves are unchanged."""
        first = ScenarioStep(
            at=T0,
            shocks=[
                GapShock(venue=Venue.MOOMOO, symbol="AAA", direction="up", gap_fraction=0.1)
            ],
        )
        second = ScenarioStep(
            at=datetime(2026, 1, 1, 0, 0, 10, tzinfo=UTC),
            shocks=[FundingShock(venue=Venue.MOOMOO, symbol="AAA", rate=0.01)],
        )
        assert scenario_id(steps=[first, second]) != scenario_id(steps=[second, first])

    def test_shock_order_within_step_is_not_setup(self) -> None:
        gap = GapShock(venue=Venue.MOOMOO, symbol="AAA", direction="up", gap_fraction=0.1)
        funding = FundingShock(venue=Venue.MOOMOO, symbol="AAA", rate=0.01)
        assert scenario_id(
            steps=[ScenarioStep(at=T0, shocks=[gap, funding])]
        ) == scenario_id(steps=[ScenarioStep(at=T0, shocks=[funding, gap])])

    def test_order_order_within_step_is_not_setup(self) -> None:
        buy = _order("AAA", Side.BUY, 10.0, 100.0)
        sell = _order("AAA", Side.SELL, 5.0, 95.0)
        assert scenario_id(
            steps=[ScenarioStep(at=T0, orders=[buy, sell])]
        ) == scenario_id(steps=[ScenarioStep(at=T0, orders=[sell, buy])])

    def test_shock_parameters_are_setup(self) -> None:
        small = GapShock(venue=Venue.MOOMOO, symbol="AAA", direction="up", gap_fraction=0.1)
        large = GapShock(venue=Venue.MOOMOO, symbol="AAA", direction="up", gap_fraction=0.2)
        assert scenario_id(steps=[ScenarioStep(at=T0, shocks=[small])]) != scenario_id(
            steps=[ScenarioStep(at=T0, shocks=[large])]
        )

    def test_deterministic(self) -> None:
        step = ScenarioStep(
            at=T0,
            shocks=[
                GapShock(venue=Venue.MOOMOO, symbol="AAA", direction="up", gap_fraction=0.1)
            ],
        )
        assert scenario_id(steps=[step]) == scenario_id(steps=[step])

    def test_steps_must_advance(self) -> None:
        with pytest.raises(ValueError, match="steps must advance"):
            _scenario(ScenarioStep(at=T0), ScenarioStep(at=T0))

    def test_step_timestamp_must_be_aware(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            ScenarioStep(at=datetime(2026, 1, 1))

    def test_scenario_id_must_match_timeline(self) -> None:
        step = ScenarioStep(at=T0)
        with pytest.raises(ValueError, match="does not match its timeline"):
            Scenario(steps=[step], id="0" * 16)
