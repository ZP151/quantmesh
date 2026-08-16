"""Wallet isolation and secret-handling suite (issue #33, Phase E).

Phase E contract: private-key material is accepted only through an
injected in-memory signer or an env var; it is never persisted, logged,
or reported. The signer's repr is redacted, env-parse errors never echo
the value, construction without a key fails closed, and a full scripted
drill through the wired adapter leaves no key material on any durable
surface — journal JSONL, the drill script, captured logs, or the whole
scratch tree — and none in refusal messages.
"""

import ast
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from quantmesh.domain.models import (
    Instrument,
    InstrumentType,
    OrderRequest,
    Side,
    Venue,
)
from quantmesh.domain.orders import OrderStatus
from quantmesh.execution.journal import OrderJournal
from quantmesh.hyperliquid.errors import HyperliquidRiskRefusalError
from quantmesh.hyperliquid.exchange import (
    HyperliquidExecutionAdapter,
    InMemorySigner,
    ScriptedExchangeTransport,
    SdkExchangeTransport,
    signer_from_env,
)
from quantmesh.hyperliquid.market_data import FIXTURE_DIR
from quantmesh.hyperliquid.public_info import PublicInfoTransport
from quantmesh.hyperliquid.reconciliation import (
    apply_reconciliation,
    run_reconciliation,
)
from quantmesh.hyperliquid.risk import (
    RiskContext,
    RiskContextProvider,
    RiskLimits,
)

# A real 32-byte testnet key with a deterministic hex form: the suite
# scans every durable surface for these literals.
KEY = bytes(range(32))
KEY_HEX = KEY.hex()
KEY_REPR = repr(KEY)

P1 = datetime.fromtimestamp(1754600400, tz=UTC)  # the drill's phase-1 clock
SCRIPT = FIXTURE_DIR / "wire_exchange_script.jsonl"
CID_1001 = "5e8f2c4d7a1b9e3f6c0d4a2b8e5f7c1d"

BTC = Instrument(
    symbol="BTC",
    venue=Venue.HYPERLIQUID,
    instrument_type=InstrumentType.PERPETUAL,
)


def test_public_info_surface_cannot_reach_execution_or_wallet_modules() -> None:
    """The mainnet public reader remains structurally data-only."""
    public_methods = {
        name
        for name, value in PublicInfoTransport.__dict__.items()
        if not name.startswith("_") and callable(value)
    }
    assert public_methods == {"candles", "l2_book"}

    public_sources = (
        Path("src/quantmesh/hyperliquid/public_info.py"),
        Path("src/quantmesh/data/hyperliquid_collection.py"),
    )
    forbidden = {
        "quantmesh.hyperliquid.exchange",
        "quantmesh.hyperliquid.reconciliation",
        "quantmesh.hyperliquid.risk",
    }
    for source in public_sources:
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        imports = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        imports.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        assert imports.isdisjoint(forbidden)


def drill(tmp_path: Path) -> tuple[HyperliquidExecutionAdapter, OrderJournal]:
    """Drive the Phase B drill (lost ack → cloid recovery → cancel →
    fills + positions → clean) and return the wired adapter and journal."""
    transport = ScriptedExchangeTransport(SCRIPT)
    journal = OrderJournal(tmp_path / "orders")
    adapter = HyperliquidExecutionAdapter(transport, journal)

    transport.advance_to(P1)
    with pytest.raises(Exception, match="acknowledgement never arrived"):
        adapter.place(
            OrderRequest(
                instrument=BTC, side=Side.SELL, quantity=1.0, limit_price=107.2
            ),
            order_id="ord-1001",
            created_at=P1,
            client_order_id=CID_1001,
        )

    transport.advance_to(P1 + timedelta(minutes=1))
    apply_reconciliation(
        run_reconciliation(transport.snapshot(), journal), journal, transport.snapshot()
    )
    assert journal.get("ord-1001").status is OrderStatus.ACCEPTED

    transport.advance_to(P1 + timedelta(minutes=2))
    run_reconciliation(transport.snapshot(), journal)
    adapter.cancel(journal.get("ord-1001"), at=P1 + timedelta(minutes=2))

    transport.advance_to(P1 + timedelta(minutes=3))
    report = run_reconciliation(transport.snapshot(), journal)
    assert report.findings == []
    return adapter, journal


# --- the signer never leaks through repr, errors, or construction ---------------


def test_in_memory_signer_repr_redacts_key_material() -> None:
    signer = InMemorySigner(KEY)
    for rendering in (repr(signer), str(signer)):
        assert KEY_HEX not in rendering
        assert KEY_REPR not in rendering
        assert "redacted" in rendering


def test_signer_from_env_errors_never_echo_the_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Malformed values are near-keys; the error must not contain them.
    for bad in ("not-hex-at-all", "0x" + "zz" * 32, "ab" * 8):
        monkeypatch.setenv("QUANTMESH_HYPERLIQUID_PRIVATE_KEY", bad)
        with pytest.raises(Exception) as exc:
            signer_from_env()
        message = str(exc.value)
        assert bad not in message
        assert KEY_HEX not in message


def test_exchange_transport_construction_without_a_key_fails_closed() -> None:
    with pytest.raises(TypeError, match="signer"):
        SdkExchangeTransport()  # noqa: E501 - missing required positional
    with pytest.raises(TypeError, match="no default-key path"):
        SdkExchangeTransport(None)


# --- the full drill leaves nothing on any durable surface ------------------------


def test_full_drill_leaves_no_key_material_on_durable_surfaces(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    _, journal = drill(tmp_path)
    assert journal.all()  # the drill really traded

    # Every durable surface in the scratch tree, plus the drill script
    # (itself a fixture QuantMesh ships) and the captured logs.
    files = sorted(p for p in tmp_path.rglob("*") if p.is_file())
    assert files, "expected the drill to have written journal files"
    surfaces = [p.read_text(encoding="utf-8", errors="ignore") for p in files]
    surfaces.append(SCRIPT.read_text(encoding="utf-8"))
    surfaces.append(caplog.text)

    for index, surface in enumerate(surfaces):
        assert KEY_HEX not in surface, f"key hex leaked into surface {index}"
        assert KEY_REPR not in surface, f"key bytes repr leaked into surface {index}"
        assert "redacted" not in surface or "InMemorySigner" not in surface, (
            f"signer repr leaked into surface {index}"
        )


def test_refusal_messages_carry_no_key_material(tmp_path: Path) -> None:
    class FixedContext(RiskContextProvider):
        def risk_context(self) -> RiskContext:
            return RiskContext(
                position=None,
                book_mid=100.0,
                book_timestamp=P1,
                funding=0.0,
                equity=1000.0,
                now=P1,
            )

    transport = ScriptedExchangeTransport(SCRIPT)
    transport.advance_to(P1)
    journal = OrderJournal(tmp_path / "orders")
    adapter = HyperliquidExecutionAdapter(
        transport,
        journal,
        risk_limits=RiskLimits(max_leverage=0.05),
        risk_context=FixedContext(),
    )

    with pytest.raises(HyperliquidRiskRefusalError) as exc:
        adapter.place(
            OrderRequest(
                instrument=BTC, side=Side.BUY, quantity=1.0, limit_price=100.0
            ),
            order_id="ord-refused",
            created_at=P1,
            client_order_id=CID_1001,
        )
    message = str(exc.value)
    assert KEY_HEX not in message
    assert KEY_REPR not in message
    assert "redacted" not in message or "InMemorySigner" not in message
    assert journal.all() == []  # the refusal consumed nothing
