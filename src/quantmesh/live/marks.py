"""Fail-closed live marks for paper-account valuation.

Marks are derived from the same venue/instrument-exact, real, fresh and
continuity-proven quote fence used by paper confirmation. A stale or unproven
live quote removes any injected fallback for that held instrument so equity
cannot silently use an unrelated or obsolete value.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from quantmesh.execution.accounting import PaperAccount, position_key
from quantmesh.live.contract import UpdateKind
from quantmesh.live.feed import LiveFeed
from quantmesh.live.fence import QuoteFence


@dataclass(frozen=True)
class LiveMarkSnapshot:
    marks: dict[str, float]
    statuses: dict[str, dict[str, object]]


@dataclass(frozen=True)
class AccountValuationSnapshot:
    """One immutable account revision and marks derived for that revision."""

    account: PaperAccount
    marks: dict[str, float]
    statuses: dict[str, dict[str, object]]
    missing_marks: tuple[str, ...]
    complete: bool
    reason: str | None


def account_valuation_snapshot(
    account: PaperAccount,
    mark_snapshot: LiveMarkSnapshot,
) -> AccountValuationSnapshot:
    missing = tuple(sorted(key for key in account.positions if key not in mark_snapshot.marks))
    return AccountValuationSnapshot(
        account=account,
        marks=dict(mark_snapshot.marks),
        statuses={key: dict(value) for key, value in mark_snapshot.statuses.items()},
        missing_marks=missing,
        complete=not missing,
        reason=(
            None
            if not missing
            else f"missing valid marks for held positions: {', '.join(missing)}"
        ),
    )


def live_mark_snapshot(
    account: PaperAccount,
    *,
    base_marks: dict[str, float],
    feed: LiveFeed,
    as_of: datetime,
    fence: QuoteFence | None = None,
) -> LiveMarkSnapshot:
    """Resolve held-position marks from exact live quote authority."""
    quote_fence = fence if fence is not None else QuoteFence()
    marks = dict(base_marks)
    statuses: dict[str, dict[str, object]] = {}
    for position in account.positions.values():
        instrument = position.instrument
        key = position_key(instrument)
        snapshot = feed.snapshot_exact(
            instrument.venue,
            instrument.symbol,
            UpdateKind.QUOTE,
            as_of=as_of,
        )
        decision = quote_fence.resolve(snapshot, instrument=instrument, now=as_of)
        quote = decision.quote
        if not decision.allowed or quote is None or quote.last is None:
            marks.pop(key, None)
            reason = decision.reason or "live quote did not provide a mark"
            statuses[key] = {
                "status": "stale" if "old" in reason else "unavailable",
                "provenance": (
                    snapshot.provenance.value if snapshot is not None else "unavailable"
                ),
                "received_at": (
                    snapshot.received_at.isoformat() if snapshot is not None else None
                ),
                "reason": reason,
            }
            continue
        marks[key] = quote.last
        statuses[key] = {
            "status": "available",
            "provenance": snapshot.provenance.value if snapshot is not None else "real",
            "received_at": quote.timestamp.isoformat(),
            "reason": None,
        }
    return LiveMarkSnapshot(marks=marks, statuses=statuses)
