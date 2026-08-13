"""Explicit adjustment policies for trusted-data publications."""

from __future__ import annotations

import math
import re
from datetime import UTC, date, datetime, time, timedelta
from hashlib import sha256
from typing import Self
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

from quantmesh.data.instruments import CanonicalInstrumentId
from quantmesh.domain.market_data import Bar

_RATE = re.compile(r"^(\d+(?:\.\d+)?)\s*->\s*(\d+(?:\.\d+)?)$")
_NEW_YORK = ZoneInfo("America/New_York")


class AdjustmentUnavailableError(ValueError):
    """Corporate-action evidence cannot support the requested adjusted series."""


def _is_utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == timedelta(0)


class EquitySplitAction(BaseModel):
    """One provider-evidenced split, including when it became knowable."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    action_id: str = Field(min_length=1)
    canonical_instrument: CanonicalInstrumentId
    announced_at: datetime
    effective_at: datetime
    ratio: float = Field(gt=0)

    @model_validator(mode="after")
    def timestamps_and_ratio_are_unambiguous(self) -> Self:
        if not _is_utc(self.announced_at) or not _is_utc(self.effective_at):
            raise ValueError("split announcement and effective timestamps must be UTC")
        if self.announced_at > self.effective_at:
            raise ValueError("split announcement cannot be after effective timestamp")
        if not math.isfinite(self.ratio) or self.ratio == 1.0:
            raise ValueError("split ratio must be finite and different from one")
        return self


class EquityAdjustmentPolicy(BaseModel):
    """A knowledge-bounded split policy pinned to factor and action evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    policy_id: str = "split-adjusted-v1"
    canonical_instrument: CanonicalInstrumentId
    factor_manifest_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    action_manifest_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    known_at: datetime
    applies_corporate_actions: bool = True
    qualifies: bool = True

    @model_validator(mode="after")
    def policy_is_supported_and_knowledge_is_utc(self) -> Self:
        if self.policy_id != "split-adjusted-v1":
            raise ValueError(f"unsupported equity adjustment policy {self.policy_id!r}")
        if not self.applies_corporate_actions or not self.qualifies:
            raise ValueError("split-adjusted-v1 must declare qualifying corporate actions")
        if not _is_utc(self.known_at):
            raise ValueError("equity adjustment knowledge time must be UTC")
        if self.factor_manifest_id == self.action_manifest_id:
            raise ValueError("factor and action manifests must be independently identified")
        return self

    def apply(self, bars: list[Bar], actions: list[EquitySplitAction]) -> list[Bar]:
        """Apply only splits evidenced no later than this policy's knowledge time."""
        return build_adjusted_series(bars=bars, actions=actions, policy=self)


def adjust_split(bar: Bar, *, factor: float) -> Bar:
    """Backward-adjust one bar for a split ratio without mutating the input."""
    if (
        isinstance(factor, bool)
        or not isinstance(factor, (int, float))
        or not math.isfinite(factor)
        or factor <= 0
    ):
        raise AdjustmentUnavailableError("split factor must be a finite positive number")
    return bar.model_copy(
        update={
            "open": bar.open / factor,
            "high": bar.high / factor,
            "low": bar.low / factor,
            "close": bar.close / factor,
            "volume": bar.volume * factor,
        }
    )


def build_adjusted_series(
    *,
    bars: list[Bar],
    actions: list[EquitySplitAction],
    policy: EquityAdjustmentPolicy,
) -> list[Bar]:
    """Build a backward split-adjusted series under an explicit knowledge cutoff."""
    expected = policy.canonical_instrument.value
    expected_symbol = expected.split(":")[2]
    if any(
        bar.instrument.symbol != expected_symbol or bar.instrument.venue.value != "moomoo"
        for bar in bars
    ):
        raise AdjustmentUnavailableError("bar instrument disagrees with adjustment policy")
    if any(action.canonical_instrument != policy.canonical_instrument for action in actions):
        raise AdjustmentUnavailableError("action instrument disagrees with adjustment policy")
    if any(action.announced_at > policy.known_at for action in actions):
        raise AdjustmentUnavailableError(
            "corporate action was unavailable at the requested knowledge time"
        )

    action_ids = [action.action_id for action in actions]
    if len(action_ids) != len(set(action_ids)):
        raise AdjustmentUnavailableError("ambiguous duplicate corporate-action identity")
    effective_ratios: dict[datetime, float] = {}
    for action in actions:
        observed = effective_ratios.setdefault(action.effective_at, action.ratio)
        if observed != action.ratio:
            raise AdjustmentUnavailableError("ambiguous split ratios for one effective timestamp")

    effective_actions = [
        action for action in actions if action.effective_at <= policy.known_at
    ]
    adjusted: list[Bar] = []
    for bar in bars:
        bar_session_date = bar.timestamp.astimezone(_NEW_YORK).date()
        factor = math.prod(
            action.ratio
            for action in effective_actions
            if bar_session_date < action.effective_at.astimezone(_NEW_YORK).date()
        )
        adjusted.append(adjust_split(bar, factor=factor))
    return adjusted


def normalize_moomoo_split_actions(
    *,
    canonical_instrument: CanonicalInstrumentId,
    factor_rows: list[dict],
    split_rows: list[dict],
) -> list[EquitySplitAction]:
    """Cross-check Moomoo rehab factors against separately sourced split actions.

    Moomoo's official action ``rate`` is old shares -> new shares. ``get_rehab``
    reports old/new as ``split_ratio`` for both splits and joins, so its inverse
    is the new/old adjustment factor. Only a unique chronological pairing becomes
    an adjustment action; dividend-only rehab rows are ignored.
    """
    candidates = [_parse_action_candidate(row, index) for index, row in enumerate(split_rows)]
    used: set[int] = set()
    normalized: list[EquitySplitAction] = []
    factors = [
        parsed
        for factor_index, row in enumerate(factor_rows)
        if (parsed := _parse_factor_candidate(row, factor_index)) is not None
    ]
    for kind, effective_date, ratio in sorted(factors, key=lambda item: item[1]):
        matches = [
            (index, candidate)
            for index, candidate in enumerate(candidates)
            if index not in used
            and candidate[0] == kind
            and math.isclose(candidate[2], ratio, rel_tol=0.0, abs_tol=1e-12)
            and candidate[1].date() <= effective_date
        ]
        if not matches:
            raise AdjustmentUnavailableError(
                "factor/action evidence is ambiguous or incomplete for split adjustment"
            )
        latest_announcement = max(candidate[1] for _, candidate in matches)
        matches = [
            (index, candidate)
            for index, candidate in matches
            if candidate[1] == latest_announcement
        ]
        if len(matches) != 1:
            raise AdjustmentUnavailableError(
                "factor/action evidence is ambiguous or incomplete for split adjustment"
            )
        action_index, (_, announced_at, _, rate) = matches[0]
        used.add(action_index)
        effective_at = datetime.combine(effective_date, time.min, tzinfo=_NEW_YORK).astimezone(UTC)
        identity = "|".join(
            (
                canonical_instrument.value,
                announced_at.isoformat(),
                effective_at.isoformat(),
                rate,
            )
        )
        normalized.append(
            EquitySplitAction(
                action_id=f"moomoo-split:{sha256(identity.encode('utf-8')).hexdigest()}",
                canonical_instrument=canonical_instrument,
                announced_at=announced_at,
                effective_at=effective_at,
                ratio=ratio,
            )
        )
    unmatched = [index for index in range(len(candidates)) if index not in used]
    if unmatched:
        raise AdjustmentUnavailableError(
            "split action has no unique matching adjustment-factor evidence"
        )
    return sorted(normalized, key=lambda item: (item.effective_at, item.action_id))


def _parse_action_candidate(row: dict, index: int) -> tuple[str, datetime, float, str]:
    if not isinstance(row, dict):
        raise AdjustmentUnavailableError(f"split action row {index} is not a mapping")
    reform = row.get("reform_type")
    kind = _reform_kind(reform)
    rate = row.get("rate")
    if not isinstance(rate, str):
        raise AdjustmentUnavailableError(f"split action row {index} has no supported rate")
    match = _RATE.fullmatch(rate.strip())
    if match is None:
        raise AdjustmentUnavailableError(f"split action row {index} has no supported rate")
    old_shares, new_shares = (float(value) for value in match.groups())
    if not all(math.isfinite(value) and value > 0 for value in (old_shares, new_shares)):
        raise AdjustmentUnavailableError(f"split action row {index} has an invalid rate")
    timestamp = row.get("dir_deci_pub_date")
    date_text = row.get("dir_deci_pub_date_str")
    if isinstance(timestamp, bool) or not isinstance(timestamp, int) or timestamp <= 0:
        raise AdjustmentUnavailableError(f"split action row {index} has no announcement time")
    try:
        announced_at = datetime.fromtimestamp(timestamp, UTC)
        announced_date = date.fromisoformat(date_text)
    except (OSError, OverflowError, TypeError, ValueError) as error:
        raise AdjustmentUnavailableError(
            f"split action row {index} has an invalid announcement date"
        ) from error
    if abs((announced_at.date() - announced_date).days) > 1:
        raise AdjustmentUnavailableError(
            f"split action row {index} announcement timestamp and date disagree"
        )
    return kind, announced_at, new_shares / old_shares, rate.strip()


def _reform_kind(value: object) -> str:
    if not isinstance(value, str):
        raise AdjustmentUnavailableError("split action has no reorganization type")
    normalized = value.strip().casefold()
    if normalized in {"split", "stock split", "拆股"}:
        return "split"
    if normalized in {"merge", "join", "reverse split", "stock merge", "合股"}:
        return "join"
    raise AdjustmentUnavailableError(f"unsupported split reorganization type {value!r}")


def _positive_number(value: object, *, field: str, row: int) -> float | None:
    if value is None or value == 0:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AdjustmentUnavailableError(f"factor row {row} field {field} must be numeric")
    converted = float(value)
    if not math.isfinite(converted) or converted <= 0:
        raise AdjustmentUnavailableError(f"factor row {row} field {field} must be positive")
    return converted


def _parse_factor_candidate(row: dict, index: int) -> tuple[str, date, float] | None:
    if not isinstance(row, dict):
        raise AdjustmentUnavailableError(f"factor row {index} is not a mapping")
    split_base = _positive_number(row.get("split_base"), field="split_base", row=index)
    split_ert = _positive_number(row.get("split_ert"), field="split_ert", row=index)
    join_base = _positive_number(row.get("join_base"), field="join_base", row=index)
    join_ert = _positive_number(row.get("join_ert"), field="join_ert", row=index)
    has_split = split_base is not None or split_ert is not None
    has_join = join_base is not None or join_ert is not None
    if not has_split and not has_join:
        return None
    if has_split == has_join or (has_split and (split_base is None or split_ert is None)) or (
        has_join and (join_base is None or join_ert is None)
    ):
        raise AdjustmentUnavailableError(f"factor row {index} has ambiguous split fields")
    try:
        effective_date = date.fromisoformat(row["ex_div_date"])
    except (KeyError, TypeError, ValueError) as error:
        raise AdjustmentUnavailableError(
            f"factor row {index} has no valid effective date"
        ) from error
    if has_split:
        assert split_base is not None and split_ert is not None
        kind, provider_ratio = "split", split_base / split_ert
    else:
        assert join_base is not None and join_ert is not None
        kind, provider_ratio = "join", join_base / join_ert
    observed = _positive_number(row.get("split_ratio"), field="split_ratio", row=index)
    if observed is None or not math.isclose(
        observed, provider_ratio, rel_tol=0.0, abs_tol=1e-12
    ):
        raise AdjustmentUnavailableError(
            f"factor row {index} split_ratio disagrees with numerator/denominator"
        )
    return kind, effective_date, 1.0 / provider_ratio


class AdjustmentPolicy(BaseModel):
    """A named, immutable price-adjustment contract."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    policy_id: str = Field(min_length=1)
    applies_corporate_actions: bool
    qualifies: bool

    @model_validator(mode="after")
    def identity_policy_is_truthful(self) -> Self:
        if self.policy_id == "unadjusted-identity-v1" and (
            self.applies_corporate_actions or self.qualifies
        ):
            raise ValueError("the unadjusted identity policy cannot claim adjusted evidence")
        return self

    def apply(self, bars: list[Bar]) -> list[Bar]:
        """Apply this policy without mutating caller-owned rows."""
        if self.policy_id != "unadjusted-identity-v1":
            raise ValueError(f"unsupported adjustment policy {self.policy_id!r}")
        return list(bars)


UNADJUSTED_IDENTITY = AdjustmentPolicy(
    policy_id="unadjusted-identity-v1",
    applies_corporate_actions=False,
    qualifies=False,
)
