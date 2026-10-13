"""Additive estimate authority, serialized by the owning store transaction."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from fractions import Fraction


def valid_amount(value):
    return isinstance(value, Decimal) and value.is_finite() and value >= 0


def canonical(value):
    """Normalize exact Decimal digits without rounding through a context."""
    if not valid_amount(value):
        raise ValueError("invalid accounting amount")
    if value == 0:
        return "0"
    sign, digits, exponent = value.as_tuple()
    digits = list(digits)
    while digits[-1] == 0:
        digits.pop()
        exponent += 1
    return str(Decimal((sign, tuple(digits), exponent)))


@dataclass(frozen=True)
class PortfolioBudgetPolicy:
    policy_id: str
    operating_monthly_usd: Decimal
    development_total_usd: Decimal

    def __post_init__(self):
        if (
            not isinstance(self.policy_id, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", self.policy_id)
            or not valid_amount(self.operating_monthly_usd)
            or not valid_amount(self.development_total_usd)
            or self.operating_monthly_usd > Decimal("50")
            or self.development_total_usd > Decimal("200")
        ):
            raise ValueError("invalid portfolio policy")

    def binding(self):
        return (
            self.policy_id,
            canonical(self.operating_monthly_usd),
            canonical(self.development_total_usd),
        )


def utc_stamp(now):
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("invalid accounting clock")
    return now.astimezone(UTC).isoformat(timespec="microseconds")


def exact_total(values):
    # Decimal's ambient precision can round a tiny overage away at a cap.
    # Exact ratios of validated Decimals avoid both rounding and floating point.
    return sum((Fraction(value) for value in values), Fraction(0))


def validate(con, policy):
    versions = con.execute("SELECT version FROM qm_portfolio_schema").fetchall()
    if [tuple(row) for row in versions] != [(1,)]:
        raise ValueError("unsupported portfolio accounting version")
    rows = con.execute(
        "SELECT slot,policy_id,operating_monthly_usd,development_total_usd,high_water "
        "FROM qm_portfolio_policy"
    ).fetchall()
    if len(rows) != 1 or rows[0][0] != 1 or tuple(rows[0][1:4]) != policy.binding():
        raise ValueError("portfolio policy mismatch")
    stamp = rows[0][4]
    if utc_stamp(datetime.fromisoformat(stamp)) != stamp:
        raise ValueError("invalid accounting clock")
    # Never attribute pre-policy history or tolerate incomplete restore/import.
    if con.execute(
        "SELECT 1 FROM model_effects e LEFT JOIN qm_portfolio_reservations r "
        "ON e.job_id=r.job_id AND e.digest=r.digest WHERE r.job_id IS NULL"
    ).fetchone():
        raise ValueError("unattributed model effects")
    return stamp


def initialize(con, policy, now):
    con.execute("CREATE TABLE IF NOT EXISTS qm_portfolio_schema(version INTEGER NOT NULL)")
    versions = con.execute("SELECT version FROM qm_portfolio_schema").fetchall()
    if versions and [tuple(row) for row in versions] != [(1,)]:
        raise ValueError("unsupported portfolio accounting version")
    con.execute(
        "CREATE TABLE IF NOT EXISTS qm_portfolio_policy ("
        "slot INTEGER PRIMARY KEY CHECK(slot=1), policy_id TEXT NOT NULL, "
        "operating_monthly_usd TEXT NOT NULL, development_total_usd TEXT NOT NULL, "
        "high_water TEXT NOT NULL)"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS qm_portfolio_reservations ("
        "job_id TEXT NOT NULL, digest TEXT NOT NULL, "
        "category TEXT NOT NULL CHECK(category IN ('operating','development')), "
        "period TEXT NOT NULL, price TEXT NOT NULL, reserved_at TEXT NOT NULL, "
        "PRIMARY KEY(job_id,digest), "
        "FOREIGN KEY(job_id,digest) REFERENCES model_effects(job_id,digest))"
    )
    if not versions:
        if (
            con.execute("SELECT 1 FROM qm_portfolio_policy").fetchone()
            or con.execute("SELECT 1 FROM qm_portfolio_reservations").fetchone()
        ):
            raise ValueError("missing portfolio accounting version")
        con.execute("INSERT INTO qm_portfolio_schema VALUES (1)")
    if policy is None:
        return
    if not con.execute("SELECT 1 FROM qm_portfolio_policy").fetchone():
        if con.execute("SELECT 1 FROM model_effects").fetchone():
            raise ValueError("unattributed model effects")
        con.execute(
            "INSERT INTO qm_portfolio_policy VALUES (1,?,?,?,?)",
            (*policy.binding(), utc_stamp(now)),
        )
    validate(con, policy)


def admit(con, policy, category, now, amount):
    """Validate and consume clock authority; caller inserts both rows atomically."""
    if policy is None:
        return None
    try:
        high_water = validate(con, policy)
        stamp = utc_stamp(now)
        if stamp < high_water:
            return None
        period = stamp[:7]
        rows = con.execute(
            "SELECT r.category,r.period,r.price,r.reserved_at,e.price,e.status,e.response "
            "FROM qm_portfolio_reservations r JOIN model_effects e "
            "ON r.job_id=e.job_id AND r.digest=e.digest"
        ).fetchall()
        charged = []
        for row_category, row_period, price, reserved_at, effect_price, status, response in rows:
            value = Decimal(price)
            if (
                row_category not in {"operating", "development"}
                or canonical(value) != price
                or canonical(Decimal(effect_price)) != price
                or utc_stamp(datetime.fromisoformat(reserved_at)) != reserved_at
                or reserved_at[:7] != row_period
                or reserved_at > high_water
                or status not in {"reserved", "completed"}
                or (status == "completed" and not response)
            ):
                return None
            if row_category == category and (
                category == "development" or row_period == period or status == "reserved"
            ):
                charged.append(value)
        con.execute("UPDATE qm_portfolio_policy SET high_water=? WHERE slot=1", (stamp,))
        cap = (
            policy.operating_monthly_usd
            if category == "operating"
            else policy.development_total_usd
        )
        if exact_total([*charged, amount]) > Fraction(cap):
            return None
        return period, stamp
    except (ValueError, ArithmeticError, TypeError):
        return None
