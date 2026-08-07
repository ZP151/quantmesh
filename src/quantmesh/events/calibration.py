"""Pure probability transforms and calibration metrics (issue #36, Phase C).

Everything here is a pure function of a ``MarketQuote``, a price
series, or paired predictions/outcomes — no I/O, no randomness, so the
same inputs always yield the same ``ImpliedProbability`` and the same
calibration curves (ADR-0005 discipline applied to event markets).

Formulas (all documented, all fail closed):

- **Fee-aware mid.** The price surface is the mid ``(bid + ask) / 2``
  when both sides are present, else the venue's last trade price, else
  an error — a quote with neither is no price. The linear-fee venue
  (Polymarket: ``taker_fee_bps`` on notional) widens the no-arbitrage
  interval: buying YES at ``a`` breaks even at ``a(1 + f)`` and
  selling at ``b`` at ``b(1 - f)``, whose center is
  ``mid + f * (a - b) / 2 = mid + fee_rate * half_spread``. That shift
  is ``spread_adjustment``. Kalshi quotes carry ``taker_fee_bps = 0``
  (the venue's fee is quadratic on profit and is not linearizable into
  the quote surface — the adapter says so), so its adjustment is zero
  and the quadratic fee is absorbed by the confidence band.
- **Liquidity confidence.** A product of a depth score (total contract
  depth saturating at ``_DEPTH_SCALE``) and a spread score (tight when
  the spread is at most ``_TIGHT_SPREAD_TICKS`` ticks, decaying to the
  ``_WIDE_SPREAD_TICKS`` floor). A one-sided book halves the score:
  the other side's level is simply unobserved.
- **History fallback.** A thin book (confidence below
  ``_FALLBACK_THRESHOLD``) blends the quote toward the mean of the
  venue's recent price series; the series' volatility is surfaced for
  consumers (the band that would carry it). A book at or above the
  threshold is not diluted.
- **Brier and reliability.** ``brier`` per pair, ``brier_score`` over
  paired series, ``brier_by_bin`` per probability bin (the reliability
  curve data), and ``liquidity_weighted_brier`` weighting each pair's
  error by its observation's liquidity confidence. Unresolved or empty
  bins are ``None``, never fabricated.
"""

import math

from pydantic import BaseModel, Field

from quantmesh.events.models import ImpliedProbability, MarketQuote

__all__ = [
    "CalibrationBin",
    "brier",
    "brier_by_bin",
    "brier_score",
    "fee_adjusted_mid",
    "history_signal",
    "implied_probability",
    "liquidity_confidence",
    "liquidity_weighted_brier",
    "with_history_fallback",
]

# Total contract depth (both sides) at which the depth score saturates.
_DEPTH_SCALE = 2000.0
# Spread at or below this many ticks is "tight" (score 1.0).
_TIGHT_SPREAD_TICKS = 2.0
# Spread at or beyond this many ticks floors the spread score.
_WIDE_SPREAD_TICKS = 10.0
# Floor of the spread score on a wide-spread book.
_SPREAD_FLOOR = 0.2
# A one-sided (or side-less) book halves the confidence: the other
# side's level is unobserved, not absent.
_ONE_SIDED_FACTOR = 0.5
# Below this confidence the history fallback dilutes the quote.
_FALLBACK_THRESHOLD = 0.5


def _raw_mid(quote: MarketQuote) -> float:
    """The quote's price surface: mid, else last trade, else fail closed."""
    if quote.best_bid is not None and quote.best_ask is not None:
        return (quote.best_bid + quote.best_ask) / 2.0
    if quote.last_trade_price is not None:
        return quote.last_trade_price
    raise ValueError(
        f"quote {quote.symbol!r} has no price surface (no bid, no ask, no last trade)"
    )


def _half_spread(quote: MarketQuote) -> float:
    if quote.best_bid is not None and quote.best_ask is not None:
        return (quote.best_ask - quote.best_bid) / 2.0
    return 0.0


def fee_adjusted_mid(quote: MarketQuote) -> float:
    """Fee-aware consensus price: ``mid + fee_rate * half_spread``.

    The adjustment is zero when either the venue reports no bps fee
    (Kalshi) or only one side of the book exists (no spread to shift).
    """
    fee = quote.taker_fee_bps / 10_000.0
    return _raw_mid(quote) + fee * _half_spread(quote)


def liquidity_confidence(quote: MarketQuote) -> float:
    """Thin books → wide confidence bands, tight books → narrow."""
    depth_score = min(1.0, (quote.bid_depth + quote.ask_depth) / _DEPTH_SCALE)
    if quote.best_bid is not None and quote.best_ask is not None:
        ticks = (quote.best_ask - quote.best_bid) / quote.tick_size
        if ticks <= _TIGHT_SPREAD_TICKS:
            spread_score = 1.0
        else:
            spread_score = max(_SPREAD_FLOOR, 1.0 - (ticks - _TIGHT_SPREAD_TICKS) / 8.0)
    else:
        spread_score = _ONE_SIDED_FACTOR
    return round(depth_score * spread_score, 4)


def implied_probability(quote: MarketQuote) -> ImpliedProbability:
    """One quote → one fee/spread/liquidity-aware probability estimate.

    ``basis`` names the price surface that produced the estimate:
    ``"mid"`` (both sides present) or ``"last"`` (single-sided).
    """
    both_sides = quote.best_bid is not None and quote.best_ask is not None
    return ImpliedProbability(
        probability=fee_adjusted_mid(quote),
        spread_adjustment=(quote.taker_fee_bps / 10_000.0) * _half_spread(quote),
        liquidity_confidence=liquidity_confidence(quote),
        basis="mid" if both_sides else "last",
        timestamp=quote.timestamp,
    )


def history_signal(prices: list[float]) -> tuple[float, float]:
    """Mean and population volatility of a price series; fails closed."""
    if not prices:
        raise ValueError("history needs at least one price")
    values = []
    for price in prices:
        if not math.isfinite(price) or not 0.0 <= price <= 1.0:
            raise ValueError(f"history price {price!r} is not a probability in [0, 1]")
        values.append(price)
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return round(mean, 6), round(math.sqrt(variance), 6)


def with_history_fallback(
    quote: MarketQuote, prices: list[float]
) -> ImpliedProbability:
    """Thin-book estimates lean on the recent price series.

    Below ``_FALLBACK_THRESHOLD`` the estimate blends
    ``confidence * quote`` with ``(1 - confidence) * history_mean`` and
    the basis names the fallback; at or above the threshold the quote
    stands alone (history would only dilute a book the venue prices
    actively). The history volatility is surfaced alongside.
    """
    base = implied_probability(quote)
    confidence = base.liquidity_confidence
    if confidence >= _FALLBACK_THRESHOLD:
        return base
    history_mean, history_vol = history_signal(prices)
    return ImpliedProbability(
        probability=round(
            confidence * base.probability + (1.0 - confidence) * history_mean, 6
        ),
        spread_adjustment=base.spread_adjustment,
        liquidity_confidence=confidence,
        basis=f"{base.basis}+history(vol={history_vol:.4f})",
        timestamp=base.timestamp,
    )


def _require_outcomes(predictions: list[float], outcomes: list[float]) -> None:
    if len(predictions) != len(outcomes):
        raise ValueError(
            f"{len(predictions)} predictions vs {len(outcomes)} outcomes"
        )
    for value in predictions:
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError(f"prediction {value!r} is not a probability in [0, 1]")
    for value in outcomes:
        if value not in (0.0, 1.0):
            raise ValueError(f"outcome {value!r} is not 0 or 1")
    if not predictions:
        raise ValueError("need at least one (prediction, outcome) pair")


def brier(prediction: float, outcome: float) -> float:
    """The Brier error of one (probability, outcome) pair."""
    _require_outcomes([prediction], [outcome])
    return (prediction - outcome) ** 2


def brier_score(predictions: list[float], outcomes: list[float]) -> float:
    """Mean Brier error over paired series."""
    _require_outcomes(predictions, outcomes)
    return sum((p - o) ** 2 for p, o in zip(predictions, outcomes)) / len(predictions)


class CalibrationBin(BaseModel):
    """One reliability-curve bin: predicted vs observed frequency."""

    bin: int = Field(ge=0)
    lo: float = Field(ge=0, le=1)
    hi: float = Field(ge=0, le=1)
    count: int = Field(default=0, ge=0)
    mean_prediction: float | None = Field(default=None, ge=0, le=1)
    observed_frequency: float | None = Field(default=None, ge=0, le=1)
    brier: float | None = Field(default=None, ge=0)


def brier_by_bin(
    predictions: list[float], outcomes: list[float], n_bins: int = 10
) -> list[CalibrationBin]:
    """Reliability-curve data: per-bin mean prediction vs frequency.

    A prediction ``p`` falls in bin ``k`` when ``k/n <= p < (k + 1)/n``
    for ``k < n - 1``; ``p == 1.0`` goes in the last bin. Empty bins
    stay ``None`` — a bin with no observations asserts nothing.
    """
    if n_bins < 1:
        raise ValueError(f"n_bins must be positive, got {n_bins}")
    _require_outcomes(predictions, outcomes)
    bins = [CalibrationBin(bin=k, lo=k / n_bins, hi=(k + 1) / n_bins) for k in range(n_bins)]
    for prediction, outcome in zip(predictions, outcomes):
        index = min(int(prediction * n_bins), n_bins - 1)
        bins[index].count += 1
    for bin_row in bins:
        if bin_row.count == 0:
            continue
        members = [
            (p, o)
            for p, o in zip(predictions, outcomes)
            if min(int(p * n_bins), n_bins - 1) == bin_row.bin
        ]
        mean_prediction = sum(p for p, _ in members) / len(members)
        observed = sum(o for _, o in members) / len(members)
        bin_row.mean_prediction = round(mean_prediction, 6)
        bin_row.observed_frequency = round(observed, 6)
        bin_row.brier = round(
            sum((p - o) ** 2 for p, o in members) / len(members), 6
        )
    return bins


def liquidity_weighted_brier(
    predictions: list[float], outcomes: list[float], confidences: list[float]
) -> float:
    """Brier error weighted by each observation's liquidity confidence."""
    if len(confidences) != len(predictions):
        raise ValueError(
            f"{len(confidences)} confidences vs {len(predictions)} predictions"
        )
    _require_outcomes(predictions, outcomes)
    for value in confidences:
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError(f"confidence {value!r} is not in [0, 1]")
    total = sum(confidences)
    if total <= 0:
        raise ValueError("liquidity weights sum to zero; nothing to weight")
    return round(
        sum(w * (p - o) ** 2 for w, p, o in zip(confidences, predictions, outcomes))
        / total,
        6,
    )
