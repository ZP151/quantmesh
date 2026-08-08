"""Pre-submission risk surface for the testnet execution path (issue #31, Phase C).

Every order passes through ``evaluate_order`` before the wire when the
adapter is constructed with ``risk_limits``: the check surface is pure
and deterministic, so the guard is fixture-testable without the SDK or
the network, and it fails closed — a check whose inputs are incomplete
is a refusal, never a guess (the M4 discipline). The four checks:

- **Leverage bound** — the resulting position (venue position + the new
  order, signed) must not exceed ``max_leverage`` against the account
  equity. A missing equity is a refusal: leverage cannot be verified.
- **Liquidation-distance floor** — the resulting position's estimated
  distance to its liquidation price must stay above
  ``min_liquidation_distance_bps``. The estimate uses the venue's own
  reported ``liquidationPx`` scaled proportionally to the size-weighted
  entry of the resulting position (the venue's number already embeds its
  funding ledger), corrected for cumulative funding; the l2Book mid is
  the mark. A check that cannot be computed (no position, no entry, no
  liquidation price, no mark, no funding) is a typed refusal, except a
  fully-reducing order which strictly decreases risk and skips the
  estimate.
- **Reduce-only posture** — with ``reduce_only`` limits configured, only
  reduce-only orders pass.
- **Stale-data window** — the latest book timestamp must be within
  ``stale_data_window_s`` of the context clock; a missing or future
  timestamp is a refusal. No order trades on stale data.

Funding is accounted as a fee-like journal entry through
``FundingLedger``: the venue reports cumulative funding on each asset
position, and the ledger records the signed delta (positive = the
position paid) as an append-only JSONL row with the same atomic-write
and fail-closed-read discipline as ``OrderJournal``.
"""

import math
import os
import tempfile
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field, ValidationError

from quantmesh.domain.models import OrderRequest, Side, Venue
from quantmesh.hyperliquid.exchange import BrokerPosition
from quantmesh.settings import settings

__all__ = [
    "FUNDING_LEDGER_FILE",
    "FundingEntry",
    "FundingLedger",
    "RiskContext",
    "RiskContextProvider",
    "RiskDecision",
    "RiskKind",
    "RiskLimits",
    "RiskRefusal",
    "evaluate_order",
]

FUNDING_LEDGER_FILE = "funding.jsonl"


class RiskKind(StrEnum):
    LEVERAGE = "leverage"
    LIQUIDATION_DISTANCE = "liquidation_distance"
    REDUCE_ONLY = "reduce_only"
    STALE_DATA = "stale_data"
    MISSING_DATA = "missing_data"


class RiskLimits(BaseModel):
    """Operator-declared pre-submission limits; every default is explicit."""

    max_leverage: float = Field(default=3.0, gt=0)
    min_liquidation_distance_bps: float = Field(default=500, ge=0)
    reduce_only: bool = False
    stale_data_window_s: int = Field(default=30, ge=0)


class RiskRefusal(BaseModel):
    """One typed refusal from the pre-submission gate."""

    kind: RiskKind
    message: str
    observed: str | None = None
    expected: str | None = None


class RiskDecision(BaseModel):
    """The gate's verdict: allowed only with zero refusals."""

    allowed: bool
    refusals: list[RiskRefusal] = Field(default_factory=list)
    checks: list[str] = Field(default_factory=list)


class RiskContext(BaseModel):
    """The market/account state one order evaluation runs against."""

    position: BrokerPosition | None = None
    book_mid: float | None = Field(default=None, ge=0)
    book_timestamp: datetime | None = None
    # Cumulative funding on the position (venue userState, signed quote
    # currency; positive = the position paid). Used both by the distance
    # estimate and the funding ledger.
    funding: float | None = None
    # Account equity (venue marginSummary.accountValue): the leverage
    # check's denominator; missing equity fails the check closed.
    equity: float | None = Field(default=None, ge=0)
    now: datetime


class RiskContextProvider(Protocol):
    """Supplies the risk context at order time; never default-constructed."""

    def risk_context(self) -> RiskContext:
        """Assemble the current position, book, funding, and clock."""


def evaluate_order(
    request: OrderRequest,
    *,
    reduce_only: bool,
    context: RiskContext,
    limits: RiskLimits,
) -> RiskDecision:
    """Run every check against the context; refusals are typed and complete.

    A missing input is a MISSING_DATA refusal, never a silent pass — the
    gate cannot verify what it cannot see. Orders that strictly decrease
    risk (reductions, full closes) skip the distance estimate but still
    face the reduce-only and stale-data checks.
    """
    if request.instrument.venue is not Venue.HYPERLIQUID:
        raise ValueError(
            f"instrument {request.instrument.symbol!r} is not a Hyperliquid "
            "instrument"
        )
    checks: list[str] = []
    refusals: list[RiskRefusal] = []

    def refuse(kind: RiskKind, message: str, **observed_expected: str) -> None:
        refusals.append(
            RiskRefusal(
                kind=kind,
                message=message,
                observed=observed_expected.get("observed"),
                expected=observed_expected.get("expected"),
            )
        )

    # -- stale-data window --------------------------------------------------
    checks.append("stale_data")
    if context.book_timestamp is None:
        refuse(
            RiskKind.STALE_DATA,
            "no book timestamp: cannot verify the data is fresh enough to trade",
        )
    else:
        age_s = (context.now - context.book_timestamp).total_seconds()
        if age_s < 0:
            refuse(
                RiskKind.STALE_DATA,
                f"book timestamp {context.book_timestamp.isoformat()} is in "
                "the future; the clock or the feed is untrustworthy",
                observed=f"{age_s:g}s",
            )
        elif age_s > limits.stale_data_window_s:
            refuse(
                RiskKind.STALE_DATA,
                f"book data is {age_s:g}s old; the stale-data window is "
                f"{limits.stale_data_window_s}s",
                observed=f"{age_s:g}s",
                expected=f"<= {limits.stale_data_window_s}s",
            )

    # -- reduce-only posture -------------------------------------------------
    checks.append("reduce_only")
    if limits.reduce_only and not reduce_only:
        refuse(
            RiskKind.REDUCE_ONLY,
            "the account is in reduce-only posture; only reduce-only orders pass",
            observed="reduce_only=False",
            expected="reduce_only=True",
        )

    # -- leverage bound ------------------------------------------------------
    checks.append("leverage")
    signed_quantity = request.quantity * (1.0 if request.side is Side.BUY else -1.0)
    position_size = context.position.size if context.position is not None else 0.0
    resulting_size = position_size + signed_quantity
    entry_estimate = _entry_estimate(request, context)
    if math.isclose(resulting_size, 0.0, abs_tol=1e-12):
        pass  # a full close: no position left to lever
    elif context.equity is None:
        refuse(
            RiskKind.MISSING_DATA,
            "no account equity: leverage cannot be verified",
        )
    elif entry_estimate is None:
        refuse(
            RiskKind.MISSING_DATA,
            "no entry price (no limit price and no book mid): leverage cannot "
            "be computed",
        )
    else:
        leverage = abs(resulting_size) * entry_estimate / context.equity
        if leverage > limits.max_leverage:
            refuse(
                RiskKind.LEVERAGE,
                f"resulting position {resulting_size:g} at {entry_estimate:g} "
                f"levers the account {leverage:g}x against a {limits.max_leverage:g}x "
                "bound",
                observed=f"{leverage:g}x",
                expected=f"<= {limits.max_leverage:g}x",
            )

    # -- liquidation-distance floor -------------------------------------------
    checks.append("liquidation_distance")
    _check_liquidation_distance(
        request, reduce_only, context, limits, resulting_size, entry_estimate, refuse
    )

    return RiskDecision(allowed=not refusals, refusals=refusals, checks=checks)


def _entry_estimate(request: OrderRequest, context: RiskContext) -> float | None:
    """The price the new size enters at: the limit price, else the mark."""
    if request.limit_price is not None:
        return request.limit_price
    return context.book_mid


def _check_liquidation_distance(
    request: OrderRequest,
    reduce_only: bool,
    context: RiskContext,
    limits: RiskLimits,
    resulting_size: float,
    entry_estimate: float | None,
    refuse,
) -> None:
    position = context.position
    if position is None or math.isclose(position.size, 0.0, abs_tol=1e-12):
        return  # no position at risk
    if _reduces_risk(position.size, resulting_size):
        return  # a reduction or full close strictly decreases risk
    if entry_estimate is None:
        refuse(
            RiskKind.MISSING_DATA,
            "no entry price (no limit price and no book mid): the resulting "
            "position's liquidation distance cannot be estimated",
        )
        return
    if position.entry_price is None:
        refuse(
            RiskKind.MISSING_DATA,
            "the venue position has no entry price: liquidation distance "
            "cannot be estimated",
        )
        return
    if position.liquidation_price is None:
        refuse(
            RiskKind.MISSING_DATA,
            "the venue position has no liquidation price: the distance floor "
            "cannot be verified",
        )
        return
    if context.book_mid is None:
        refuse(
            RiskKind.MISSING_DATA,
            "no book mid: the liquidation distance needs a mark to measure "
            "against",
        )
        return
    if context.funding is None:
        refuse(
            RiskKind.MISSING_DATA,
            "no cumulative funding: the resulting position's cost basis "
            "cannot be estimated",
        )
        return

    signed_quantity = request.quantity * (1.0 if request.side is Side.BUY else -1.0)
    if _flips_direction(position.size, resulting_size):
        resulting_entry = entry_estimate
    else:
        resulting_entry = (
            position.size * position.entry_price
            + signed_quantity * entry_estimate
        ) / resulting_size
    # Paid funding (positive) raises a long's cost basis and lowers a
    # short's: the effective entry moves toward the mark, shrinking the
    # estimated distance — a conservative correction.
    effective_entry = resulting_entry + math.copysign(1.0, resulting_size) * (
        context.funding / abs(resulting_size)
    )
    liquidation_estimate = position.liquidation_price * (
        effective_entry / position.entry_price
    )
    mark = context.book_mid
    long = resulting_size > 0.0
    if (long and mark <= liquidation_estimate) or (
        not long and mark >= liquidation_estimate
    ):
        refuse(
            RiskKind.LIQUIDATION_DISTANCE,
            f"the resulting position is already at or beyond its estimated "
            f"liquidation price {liquidation_estimate:g} at the mark {mark:g}",
            observed=f"{mark:g}",
            expected=f"{'above' if long else 'below'} {liquidation_estimate:g}",
        )
        return
    distance = abs(mark - liquidation_estimate) / mark
    floor = limits.min_liquidation_distance_bps / 10_000.0
    if distance < floor:
        refuse(
            RiskKind.LIQUIDATION_DISTANCE,
            f"the resulting position's estimated distance to liquidation is "
            f"{distance * 10_000:g} bps at the mark {mark:g}; the floor is "
            f"{limits.min_liquidation_distance_bps:g} bps",
            observed=f"{distance * 10_000:g} bps",
            expected=f">= {limits.min_liquidation_distance_bps:g} bps",
        )


def _reduces_risk(position_size: float, resulting_size: float) -> bool:
    if position_size > 0:
        return resulting_size <= position_size and resulting_size >= 0
    if position_size < 0:
        return resulting_size >= position_size and resulting_size <= 0
    return True


def _flips_direction(position_size: float, resulting_size: float) -> bool:
    return resulting_size != 0.0 and position_size * resulting_size < 0.0


# --- funding ledger -----------------------------------------------------------


class FundingEntry(BaseModel):
    """One recorded funding delta — a fee-like journal row (Phase C)."""

    timestamp: datetime
    coin: str
    size: float
    amount: float  # signed: positive = the position paid funding


class FundingLedger:
    """Append-only delta ledger for venue cumulative funding.

    The venue reports *cumulative* funding per position; the ledger
    records the signed delta against the last recorded value, so an
    hourly funding charge is one row. The first record anchors the
    series (its delta is the cumulative itself). Writes are atomic
    (temp-file + replace) and reads fail closed with line attribution,
    mirroring ``OrderJournal``.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = root if root is not None else settings.orders_dir

    def record(
        self,
        position: BrokerPosition,
        cumulative_funding: float | None,
        *,
        at: datetime,
    ) -> FundingEntry | None:
        """Record the delta since the last entry for the coin (None when 0)."""
        if cumulative_funding is None:
            raise ValueError(
                f"position {position.coin} has no cumulative funding to record"
            )
        entries = self.read()
        # Every row is a true delta, so the running cumulative per coin is
        # the sum of its prior deltas — never the last row's delta, which
        # would compound the series.
        last_cumulative = sum(
            entry.amount for entry in entries if entry.coin == position.coin
        )
        delta = cumulative_funding - last_cumulative
        if math.isclose(delta, 0.0, abs_tol=1e-12):
            return None
        entry = FundingEntry(
            timestamp=at,
            coin=position.coin,
            size=position.size,
            amount=delta,
        )
        self._write(entries + [entry])
        return entry

    def read(self) -> list[FundingEntry]:
        path = self.root / FUNDING_LEDGER_FILE
        if not path.exists():
            return []
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise ValueError(f"funding ledger {path} is unreadable") from error
        entries = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                entries.append(FundingEntry.model_validate_json(line))
            except ValidationError as error:
                raise ValueError(
                    f"funding ledger {path} line {line_number} is invalid"
                ) from error
        return entries

    def _write(self, entries: list[FundingEntry]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / FUNDING_LEDGER_FILE
        descriptor, temp_name = tempfile.mkstemp(
            dir=self.root, prefix=f".{FUNDING_LEDGER_FILE}.", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                for entry in entries:
                    handle.write(entry.model_dump_json())
                    handle.write("\n")
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
