"""Deterministic quote fence (iteration 0015 Phase D, ADR-0014).

The operator's architecture prescribes that orders may only read
*locally validated latest quotes* — source + age + sequence
continuity — and that any disconnected or expired source shows
stale/degraded and blocks paper orders on its instruments. The fence
is the pure gate at that boundary: given the feed's latest QUOTE view
for an instrument and an explicit clock, it either blesses the quote
(a domain ``Quote`` the matcher can consume) or rejects it with one
explicit reason.

``evaluate`` is a pure function of (view, now) — wall-clock-free, so
drills script the clock exactly like the rest of the live surface.
``resolve`` binds it to a ``latest_state``-shaped snapshot (the same
JSON the browser's watchlist renders) for a caller that owns the
clock. Demo orders never pass through the fence: the demo runtime
submits scenario-anchored quotes straight to ``PaperAccount.submit``
without a fence, so demo mode is unchanged by construction.

Rejection reasons are explicit and ordered (the first defect wins):

- ``no-quote`` — no QUOTE view exists for the instrument;
- ``not-real`` — provenance is not real (delayed/synthetic/…);
- ``gap`` — the quote's sequence is discontinuous (the venue dropped
  updates, e.g. backpressure or a reconnect gap);
- ``stale`` — the quote is older than the fence horizon;
- ``no-depth`` — the payload carries no usable bid/ask/sizes.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta

from quantmesh.domain.models import Instrument, Quote
from quantmesh.live.contract import Provenance, UpdateKind
from quantmesh.live.feed import ExactUpdateSnapshot

FENCE_DEFAULT_MAX_AGE = timedelta(seconds=30)  # same horizon family as the matcher


def _finite(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if math.isfinite(number):
            return number
    return None


@dataclass(frozen=True)
class FenceDecision:
    """One fence verdict: the blessed quote, or the explicit rejection."""

    allowed: bool
    reason: str | None = None
    quote: Quote | None = None


class QuoteFence:
    """Provenance + age + sequence-continuity gate over quote consumption.

    ``max_age`` is the freshness horizon: a quote older than it (age
    measured from the local ``received_at`` anchor, the same anchor the
    feed's label and the matcher's ``max_quote_age`` use) is stale.
    """

    def __init__(self, *, max_age: timedelta = FENCE_DEFAULT_MAX_AGE) -> None:
        if max_age <= timedelta(0):
            raise ValueError("max_age must be positive")
        self.max_age = max_age

    def evaluate(
        self, view: Mapping[str, object] | None, *, instrument: Instrument, now: datetime
    ) -> FenceDecision:
        """One latest QUOTE view -> allow (with a blessed Quote) or reject.

        The view is exactly the feed's per-kind view (provenance,
        received_at, sequence, sequence_gap, payload). ``now`` is the
        submission instant; the age is computed from it so the fence
        never depends on when the snapshot was rendered.
        """
        if view is None:
            return FenceDecision(False, f"no locally validated quote for {instrument.symbol}")
        if view.get("kind") != UpdateKind.QUOTE.value:
            return FenceDecision(False, f"no locally validated quote for {instrument.symbol}")
        provenance = view.get("provenance")
        if provenance != Provenance.REAL.value:
            return FenceDecision(
                False,
                f"quote provenance is {provenance}; only locally validated real quotes "
                "may feed paper orders",
            )
        if view.get("sequence_gap") is True:
            return FenceDecision(
                False, "quote sequence is discontinuous — the venue dropped updates"
            )
        if view.get("sequence_gap") is not False or view.get("continuity_proven") is not True:
            return FenceDecision(
                False,
                "quote continuity is unproven — two clean ordered venue updates are required",
            )
        received_at = view.get("received_at")
        if not isinstance(received_at, str):
            return FenceDecision(
                False, "quote has no local receipt time — it cannot be age-validated"
            )
        try:
            anchored = datetime.fromisoformat(received_at)
        except ValueError:
            return FenceDecision(
                False, "quote has no local receipt time — it cannot be age-validated"
            )
        age = now - anchored
        if age < timedelta(0):
            return FenceDecision(False, "quote receipt time is in the future")
        if age > self.max_age:
            seconds = round(age.total_seconds())
            return FenceDecision(
                False,
                f"quote is {seconds} s old; the fence horizon is "
                f"{self.max_age.total_seconds():g} s",
            )
        quote = self._blessed_quote(view, instrument, anchored)
        if quote is None:
            return FenceDecision(
                False, "quote has no usable depth (bid/ask/sizes) for a paper order"
            )
        return FenceDecision(True, quote=quote)

    def resolve(
        self,
        snapshot: ExactUpdateSnapshot | None,
        *,
        instrument: Instrument,
        now: datetime,
    ) -> FenceDecision:
        """Evaluate one venue/symbol/kind-exact feed snapshot.

        Presentation-oriented ``latest_state`` is intentionally not accepted:
        its symbol-only merge can combine venues and is not order authority.
        """
        if not isinstance(snapshot, ExactUpdateSnapshot):
            return FenceDecision(False, f"no locally validated quote for {instrument.symbol}")
        if (
            snapshot.venue is not instrument.venue
            or snapshot.instrument != instrument.symbol
            or snapshot.kind is not UpdateKind.QUOTE
            or snapshot.source != instrument.venue.value
        ):
            return FenceDecision(
                False,
                f"exact quote snapshot does not match "
                f"{instrument.venue.value}:{instrument.symbol}",
            )
        return self.evaluate(
            {
                "kind": snapshot.kind.value,
                "provenance": snapshot.provenance.value,
                "received_at": snapshot.received_at.isoformat(),
                "sequence_gap": snapshot.sequence_gap,
                "continuity_proven": snapshot.continuity_proven,
                "payload": snapshot.payload,
            },
            instrument=instrument,
            now=now,
        )

    @staticmethod
    def _blessed_quote(
        view: Mapping[str, object], instrument: Instrument, received_at: datetime
    ) -> Quote | None:
        """The domain Quote the matcher can consume, or None (no depth).

        Volume is the touch-side depth the BBO carries (bid+ask size),
        the same convention the demo route uses for its seeded book.
        """
        payload = view.get("payload")
        if not isinstance(payload, Mapping):
            return None
        bid = _finite(payload.get("bid"))
        ask = _finite(payload.get("ask"))
        bid_size = _finite(payload.get("bid_size"))
        ask_size = _finite(payload.get("ask_size"))
        if bid is None or ask is None or bid > ask:
            return None
        volume = None if bid_size is None or ask_size is None else bid_size + ask_size
        if volume is None or volume <= 0:
            return None
        mid = (bid + ask) / 2 if bid is not None and ask is not None else bid
        return Quote(
            instrument=instrument,
            timestamp=received_at,
            bid=bid,
            ask=ask,
            last=mid,
            volume=volume,
        )
