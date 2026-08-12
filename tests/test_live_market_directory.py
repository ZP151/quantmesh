import sys
import types

from quantmesh.api import workstation
from quantmesh.domain.models import Venue
from quantmesh.instruments.contracts import DatasetBinding
from quantmesh.live.directory import build_live_market_directory
from quantmesh.live.prediction import PredictionBoard, PredictionPair
from quantmesh.settings import settings


def test_live_market_directory_combines_configured_and_discovered_instruments() -> None:
    prediction = PredictionBoard(
        [
            PredictionPair(
                event_key="fed-cut",
                title="Fed cuts rates",
                expiry=None,
                symbols={
                    Venue.POLYMARKET: "pm-fed-cut",
                    Venue.KALSHI: "FEDCUT-26",
                },
            )
        ]
    )
    bindings = [
        DatasetBinding(
            dataset_id="hl_btc_1m",
            interval="1m",
            venue=Venue.HYPERLIQUID,
            symbol="BTC",
            calendar="24/7",
        ),
        DatasetBinding(
            dataset_id="moomoo_tsla_1m",
            interval="1m",
            venue=Venue.MOOMOO,
            symbol="US.TSLA",
            calendar="XNYS",
        ),
    ]

    directory = build_live_market_directory(
        hyperliquid_symbols=["BTC", "ETH", "BTC"],
        moomoo_symbols=["US.NVDA"],
        prediction=prediction,
        bindings=bindings,
    )

    assert directory == {
        "hyperliquid": {"BTC": None, "ETH": None},
        "kalshi": {"FEDCUT-26": None},
        "moomoo": {"US.NVDA": None, "US.TSLA": None},
        "polymarket": {"pm-fed-cut": None},
    }


def test_live_market_directory_never_invents_a_mark() -> None:
    directory = build_live_market_directory(hyperliquid_symbols=["SOL"])

    assert directory == {"hyperliquid": {"SOL": None}}
    assert all(mark is None for instruments in directory.values() for mark in instruments.values())


def test_live_main_injects_configured_symbols_into_the_market_directory(
    tmp_path, monkeypatch
) -> None:
    calls: dict = {}

    def fake_run(app, *args, **kwargs) -> None:  # noqa: ANN001
        calls["app"] = app

    monkeypatch.setitem(sys.modules, "uvicorn", types.SimpleNamespace(run=fake_run))
    monkeypatch.setattr(settings, "workstation_host", "127.0.0.1")
    monkeypatch.setattr(settings, "live_watchlist", "BTC,ETH")
    monkeypatch.setattr(settings, "prediction_watchlist", "")
    monkeypatch.setattr(settings, "moomoo_watchlist", "")
    monkeypatch.setattr(settings, "lake_root", tmp_path / "lake")
    monkeypatch.setattr(settings, "orders_dir", tmp_path / "orders")

    workstation.main(["--live"])

    app = calls["app"]
    assert app.state.page_context.markets == {"hyperliquid": {"BTC": None, "ETH": None}}
    app.state.live.replay_buffer.close()
