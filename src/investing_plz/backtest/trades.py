from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from investing_plz.backtest.models import Fill
from investing_plz.domain import OrderSide
from investing_plz.domain.decimal import require_decimal
from investing_plz.domain.time import require_utc


@dataclass(frozen=True, slots=True)
class ClosedTrade:
    """One completed flat-to-position-to-flat lifecycle."""

    opened_at: datetime
    closed_at: datetime
    entry_cost: Decimal
    exit_proceeds: Decimal
    realized_pnl: Decimal

    def __post_init__(self) -> None:
        require_utc(self.opened_at)
        require_utc(self.closed_at)
        require_decimal(self.entry_cost, name="entry_cost")
        require_decimal(self.exit_proceeds, name="exit_proceeds")
        require_decimal(self.realized_pnl, name="realized_pnl")
        if self.closed_at < self.opened_at:
            raise ValueError("closed_at must not be earlier than opened_at")
        if self.entry_cost <= 0:
            raise ValueError("entry_cost must be greater than zero")
        if self.exit_proceeds < 0:
            raise ValueError("exit_proceeds must not be negative")
        if self.realized_pnl != self.exit_proceeds - self.entry_cost:
            raise ValueError("realized_pnl must equal exit_proceeds - entry_cost")


def build_closed_trades(fills: Sequence[Fill]) -> tuple[ClosedTrade, ...]:
    """Build completed position lifecycles without closing a remaining position."""

    closed_trades: list[ClosedTrade] = []
    position_quantity = Decimal("0")
    opened_at: datetime | None = None
    entry_cost = Decimal("0")
    exit_proceeds = Decimal("0")
    instrument = None
    previous_timestamp: datetime | None = None

    for fill in fills:
        if previous_timestamp is not None and fill.timestamp < previous_timestamp:
            raise ValueError("fills must be in ascending timestamp order")
        previous_timestamp = fill.timestamp
        if instrument is None:
            instrument = fill.instrument
        elif fill.instrument != instrument:
            raise ValueError("all fills must belong to the same instrument")

        if fill.side is OrderSide.BUY:
            if position_quantity == 0:
                opened_at = fill.timestamp
                entry_cost = Decimal("0")
                exit_proceeds = Decimal("0")
            position_quantity += fill.quantity
            entry_cost += fill.quantity * fill.fill_price + fill.fee_amount
            continue

        if position_quantity == 0 or fill.quantity > position_quantity:
            raise ValueError("SELL fill quantity exceeds the open position")
        position_quantity -= fill.quantity
        exit_proceeds += fill.quantity * fill.fill_price - fill.fee_amount
        if position_quantity == 0:
            assert opened_at is not None
            closed_trades.append(
                ClosedTrade(
                    opened_at=opened_at,
                    closed_at=fill.timestamp,
                    entry_cost=entry_cost,
                    exit_proceeds=exit_proceeds,
                    realized_pnl=exit_proceeds - entry_cost,
                )
            )
            opened_at = None
            entry_cost = Decimal("0")
            exit_proceeds = Decimal("0")

    return tuple(closed_trades)
