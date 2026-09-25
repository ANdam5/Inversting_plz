from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from investing_plz.backtest.trades import ClosedTrade


@dataclass(frozen=True, slots=True)
class TradeMetrics:
    closed_trade_count: int
    winning_trade_count: int
    losing_trade_count: int
    breakeven_trade_count: int
    win_rate: Decimal
    gross_profit: Decimal
    gross_loss: Decimal
    profit_factor: Decimal | None
    average_trade_pnl: Decimal
    average_trade_return: Decimal


def calculate_trade_return(trade: ClosedTrade) -> Decimal:
    """Return one closed trade's result relative to its entry cost."""

    return trade.realized_pnl / trade.entry_cost


def calculate_trade_metrics(trades: Sequence[ClosedTrade]) -> TradeMetrics:
    """Aggregate performance from completed position lifecycles only."""

    if not trades:
        raise ValueError("closed trade ledger must not be empty")

    count = len(trades)
    winning_count = sum(trade.realized_pnl > 0 for trade in trades)
    losing_count = sum(trade.realized_pnl < 0 for trade in trades)
    breakeven_count = count - winning_count - losing_count
    gross_profit = sum(
        (trade.realized_pnl for trade in trades if trade.realized_pnl > 0),
        start=Decimal("0"),
    )
    gross_loss = sum(
        (-trade.realized_pnl for trade in trades if trade.realized_pnl < 0),
        start=Decimal("0"),
    )
    total_pnl = sum(
        (trade.realized_pnl for trade in trades),
        start=Decimal("0"),
    )
    total_return = sum(
        (calculate_trade_return(trade) for trade in trades),
        start=Decimal("0"),
    )
    decimal_count = Decimal(count)

    return TradeMetrics(
        closed_trade_count=count,
        winning_trade_count=winning_count,
        losing_trade_count=losing_count,
        breakeven_trade_count=breakeven_count,
        win_rate=Decimal(winning_count) / decimal_count,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        profit_factor=(
            None if gross_loss == 0 else gross_profit / gross_loss
        ),
        average_trade_pnl=total_pnl / decimal_count,
        average_trade_return=total_return / decimal_count,
    )
