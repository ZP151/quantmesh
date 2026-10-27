"""Fixed synthetic research policy; no market access, matcher, ledger or order authority.

DoubleMA is a transparent public rule reference, not imported native vn.py execution.
Cash/account/fill values are supplied observations. This module only proposes quantities
and tracks a campaign following those supplied fills; it never updates a cash account.
"""

from dataclasses import dataclass, replace
from decimal import Context, Decimal, localcontext
from functools import wraps
from statistics import median

_STAGES = (
    ("add15", Decimal("0.85"), Decimal("0.10")),
    ("add25", Decimal("0.75"), Decimal("0.25")),
    ("sell25", Decimal("1.25"), Decimal("0.10")),
    ("sell35", Decimal("1.35"), Decimal("0.20")),
    ("sell45", Decimal("1.45"), Decimal("0.30")),
    ("sell60", Decimal("1.60"), Decimal("0.40")),
)
_STAGE_IDS = {stage[0] for stage in _STAGES}
_EXIT_CAUSES = {"trend_exit", "profit100", "terminal"}


def _integer(value, name, *, minimum=0):
    if type(value) is not int or not minimum <= value <= 1_000_000_000:
        raise ValueError(name)
    return value


def _decimal(value, name, *, positive=False):
    # Reject binary floats, bools, unbounded exponents and pathological fixture sizes.
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(name)
    if not 0 <= value <= Decimal("1e12") or (positive and not value):
        raise ValueError(name)
    if len(value.as_tuple().digits) > 20 or not -8 <= value.as_tuple().exponent <= 12:
        raise ValueError(name)
    return value


def _fixed_decimal(function):
    @wraps(function)
    def fixed(*args, **kwargs):
        with localcontext(Context(prec=40)):
            return function(*args, **kwargs)

    return fixed


@dataclass(frozen=True)
class Account:
    cash: Decimal
    shares: int
    receivable: Decimal = Decimal(0)

    def __post_init__(self):
        _decimal(self.cash, "cash")
        _integer(self.shares, "shares")
        _decimal(self.receivable, "receivable")


@dataclass(frozen=True)
class Close:
    """Synthetic session ordinal; terminal schedules the next (final) open exit."""

    session: int
    closes: tuple[Decimal, ...]
    available: bool = True
    terminal: bool = False
    unsupported_action: bool = False

    def __post_init__(self):
        _integer(self.session, "session")
        _closes(self.closes)
        for flag in (self.available, self.terminal, self.unsupported_action):
            if type(flag) is not bool:
                raise ValueError("close_flags")


@dataclass(frozen=True)
class Open:
    session: int
    price: Decimal
    prior_volumes: tuple[Decimal, ...]
    cost_bps: Decimal = Decimal(5)

    def __post_init__(self):
        _integer(self.session, "session")
        _decimal(self.price, "open_price", positive=True)
        if type(self.prior_volumes) is not tuple or len(self.prior_volumes) != 20:
            raise ValueError("prior20_volume_required")
        for volume in self.prior_volumes:
            _decimal(volume, "volume")
        _decimal(self.cost_bps, "cost_bps")
        if self.cost_bps not in (Decimal(5), Decimal(10)):
            raise ValueError("fixed_cost_scenarios_only")


@dataclass(frozen=True)
class Fill:
    """An explicit fixture event, never produced by this policy."""

    session: int
    quantity: int  # unsigned filled shares; side comes from the bound action
    price: Decimal

    def __post_init__(self):
        _integer(self.session, "fill_session")
        _integer(self.quantity, "fill_quantity")
        _decimal(self.price, "fill_price", positive=True)


@dataclass(frozen=True)
class Action:
    session: int
    kind: str
    signal: str
    reason: str
    requested: int | None = 0  # entry is a budget request, sized only at next open
    stages: tuple[str, ...] = ()
    averages: tuple[Decimal, ...] = ()  # fast, slow, prior fast, prior slow


@dataclass(frozen=True)
class SizedAction:
    action: Action
    session: int
    price: Decimal
    requested: int
    allowed: int
    participation_cap: int
    cost_bps: Decimal
    fee_at_allowed: Decimal
    constraints: tuple[str, ...]


@dataclass(frozen=True)
class Campaign:
    shares: int = 0
    initial_price: Decimal | None = None
    initial_quantity: int = 0
    consumed: tuple[str, ...] = ()
    pending_full_exit: str | None = None
    last_close: int = -1
    last_fill: int = -1
    pending: Action | None = None
    execution: SizedAction | None = None

    def __post_init__(self):
        _integer(self.shares, "campaign_shares")
        _integer(self.initial_quantity, "initial_quantity")
        _integer(self.last_close, "last_close", minimum=-1)
        _integer(self.last_fill, "last_fill", minimum=-1)
        if self.shares:
            _decimal(self.initial_price, "initial_price", positive=True)
            if not self.initial_quantity:
                raise ValueError("initial_quantity")
        elif self.initial_price is not None or self.initial_quantity or self.consumed:
            raise ValueError("flat_campaign_anchor")
        if type(self.consumed) is not tuple or len(set(self.consumed)) != len(self.consumed):
            raise ValueError("consumed_stages")
        if set(self.consumed) - _STAGE_IDS:
            raise ValueError("consumed_stages")
        if self.pending_full_exit is not None:
            if not self.shares or self.pending_full_exit not in _EXIT_CAUSES:
                raise ValueError("pending_full_exit")
        if self.execution is not None and self.execution.action != self.pending:
            raise ValueError("pending_execution")


def _closes(values):
    if type(values) is not tuple or not 1 <= len(values) <= 4096:
        raise ValueError("close_history")
    for value in values:
        _decimal(value, "close_price", positive=True)


@_fixed_decimal
def doublema_signal(closes: tuple[Decimal, ...]) -> str:
    """100 prior completed warmup bars; a strict crossing, never a level filter."""
    _closes(closes)
    if len(closes) <= 100:
        return "warmup"
    fast, slow, prior_fast, prior_slow = _averages(closes)
    if fast > slow and prior_fast < prior_slow:
        return "enter_long"
    if fast < slow and prior_fast > prior_slow:
        return "exit_long"
    return "hold"


def _averages(closes):
    return (
        sum(closes[-10:]) / 10,
        sum(closes[-20:]) / 20,
        sum(closes[-11:-1]) / 10,
        sum(closes[-21:-1]) / 20,
    )


def _account_matches(state, account):
    if not isinstance(account, Account) or account.shares != state.shares:
        raise ValueError("account_shares")


@_fixed_decimal
def on_close(
    state: Campaign, close: Close, account: Account, *, overlay: bool = True
) -> tuple[Campaign, Action]:
    """Propose research action only; account cash cannot affect the trend signal."""
    _account_matches(state, account)
    if state.pending is not None or state.execution is not None:
        raise ValueError("pending_action")
    if type(overlay) is not bool:
        raise ValueError("overlay")
    if close.session <= state.last_close or close.session < state.last_fill:
        raise ValueError("close_session")
    if close.unsupported_action:
        raise ValueError("unsupported_action")
    signal = doublema_signal(close.closes)
    kind, reason, quantity, stages = "hold", signal, 0, ()
    exit_cause = state.pending_full_exit
    if not close.available:
        reason = "unavailable"
    elif close.terminal and state.shares:
        kind, reason, quantity = "full_exit", "terminal", state.shares
        exit_cause = "terminal"
    elif signal == "warmup":
        pass
    elif state.shares and (exit_cause or signal == "exit_long"):
        exit_cause = exit_cause or "trend_exit"
        kind, reason, quantity = "full_exit", exit_cause, state.shares
    elif state.shares and overlay:
        price = close.closes[-1]
        if price >= state.initial_price * 2:
            kind, reason, quantity = "full_exit", "profit100", state.shares
            exit_cause = "profit100"
        else:
            selected = []
            for name, threshold, fraction in _STAGES:
                reached = (
                    price <= state.initial_price * threshold
                    if name.startswith("add")
                    else price >= state.initial_price * threshold
                )
                if name not in state.consumed and reached:
                    selected.append((name, int(state.initial_quantity * fraction)))
            if selected:
                stages = tuple(name for name, _ in selected)
                quantity = sum(amount for _, amount in selected)
                kind = "add" if stages[0].startswith("add") else "reduce"
                reason = "threshold"
    elif not state.shares and signal == "enter_long":
        kind, reason, quantity = "entry", "trend_entry", None
    averages = _averages(close.closes) if len(close.closes) > 100 else ()
    action = Action(close.session, kind, signal, reason, quantity, stages, averages)
    state = replace(
        state,
        last_close=close.session,
        pending=action if kind != "hold" else None,
        pending_full_exit=exit_cause,
    )
    return state, action


@_fixed_decimal
def size_at_open(
    state: Campaign, action: Action, opening: Open, account: Account
) -> tuple[Campaign, SizedAction]:
    """Clamp proposed shares using supplied open/account; never create a fill."""
    _account_matches(state, account)
    if state.pending != action or action.kind == "hold":
        raise ValueError("pending_action")
    if state.execution is not None:
        raise ValueError("pending_execution")
    if opening.session != action.session + 1:
        raise ValueError("execution_session")
    price, rate = opening.price, opening.cost_bps / 10000
    equity = account.cash + account.shares * price + account.receivable
    constraints = []
    cap = int(median(opening.prior_volumes) * Decimal("0.01"))
    if action.kind == "entry":
        requested = int(Decimal("0.50") * equity / (price * (1 + rate)))
        constraints.append("initial_budget_includes_fee")
    else:
        requested = action.requested
    if requested is None or type(requested) is not int or requested < 0:
        raise ValueError("requested_quantity")
    allowed = requested
    if action.kind in ("entry", "add"):
        cash_cap = int(account.cash / (price * (1 + rate)))
        headroom = Decimal("0.75") * equity - account.shares * price
        concentration_cap = max(0, int(headroom / (price * (1 + Decimal("0.75") * rate))))
        for name, bound in (("cash", cash_cap), ("concentration", concentration_cap)):
            if requested > bound:
                constraints.append(name)
            allowed = min(allowed, bound)
    else:
        if requested > account.shares:
            constraints.append("ownership")
        allowed = min(allowed, account.shares)
    if requested > cap:
        constraints.append("prior20_volume")
    allowed = min(allowed, cap)
    if not requested:
        constraints.append("zero_rounding")
    sized = SizedAction(
        action,
        opening.session,
        price,
        requested,
        allowed,
        cap,
        opening.cost_bps,
        allowed * price * rate,
        tuple(constraints),
    )
    return replace(state, execution=sized), sized


@_fixed_decimal
def on_fill(state: Campaign, sized: SizedAction, fill: Fill) -> Campaign:
    """Consume one supplied fixture fill and cancel the unfilled stage remainder."""
    if state.execution != sized or state.pending != sized.action:
        raise ValueError("pending_execution")
    if fill.session != sized.session or fill.price != sized.price or fill.quantity > sized.allowed:
        raise ValueError("fill_binding")
    action = sized.action
    buying = action.kind in ("entry", "add")
    shares = state.shares + (fill.quantity if buying else -fill.quantity)
    if action.reason == "terminal" and shares:
        raise ValueError("terminal_liquidation_incomplete")
    if not shares:
        return Campaign(last_close=state.last_close, last_fill=fill.session)
    initial_price, initial_quantity = state.initial_price, state.initial_quantity
    if action.kind == "entry":
        initial_price, initial_quantity = fill.price, fill.quantity
    consumed = tuple(sorted(set(state.consumed) | set(action.stages)))
    return replace(
        state,
        shares=shares,
        initial_price=initial_price,
        initial_quantity=initial_quantity,
        consumed=consumed,
        last_fill=fill.session,
        pending=None,
        execution=None,
    )
