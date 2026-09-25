from datetime import datetime, timezone
from decimal import Decimal

import pytest

from investing_plz.backtest import (
    ClosedTrade,
    calculate_trade_metrics,
    calculate_trade_return,
)


TIMESTAMP = datetime(2024, 1, 1, tzinfo=timezone.utc)


def trade(pnl: str, *, entry_cost: str = "100") -> ClosedTrade:
    entry = Decimal(entry_cost)
    realized = Decimal(pnl)
    return ClosedTrade(
        opened_at=TIMESTAMP,
        closed_at=TIMESTAMP,
        entry_cost=entry,
        exit_proceeds=entry + realized,
        realized_pnl=realized,
    )


def test_aggregate_trade_metrics_use_closed_trades() -> None:
    metrics = calculate_trade_metrics(
        (trade("100"), trade("-40"), trade("20"), trade("-10"), trade("0"))
    )

    assert metrics.closed_trade_count == 5
    assert metrics.winning_trade_count == 2
    assert metrics.losing_trade_count == 2
    assert metrics.breakeven_trade_count == 1
    assert metrics.win_rate == Decimal("0.4")
    assert metrics.gross_profit == Decimal("120")
    assert metrics.gross_loss == Decimal("50")
    assert metrics.profit_factor == Decimal("2.4")
    assert metrics.average_trade_pnl == Decimal("14")


def test_all_winning_trades_have_no_profit_factor_denominator() -> None:
    metrics = calculate_trade_metrics((trade("10"), trade("20")))

    assert metrics.win_rate == Decimal("1")
    assert metrics.gross_profit == Decimal("30")
    assert metrics.gross_loss == Decimal("0")
    assert metrics.profit_factor is None


def test_all_losing_trades_have_zero_profit_factor() -> None:
    metrics = calculate_trade_metrics((trade("-10"), trade("-20")))

    assert metrics.win_rate == Decimal("0")
    assert metrics.gross_profit == Decimal("0")
    assert metrics.gross_loss == Decimal("30")
    assert metrics.profit_factor == Decimal("0")
    assert metrics.average_trade_pnl == Decimal("-15")


def test_breakeven_only_has_no_profit_factor_denominator() -> None:
    metrics = calculate_trade_metrics((trade("0"), trade("0")))

    assert metrics.breakeven_trade_count == 2
    assert metrics.win_rate == Decimal("0")
    assert metrics.profit_factor is None


def test_empty_closed_trade_ledger_is_rejected() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        calculate_trade_metrics(())


def test_trade_return_is_realized_pnl_divided_by_entry_cost() -> None:
    assert calculate_trade_return(trade("25", entry_cost="200")) == Decimal("0.125")


def test_average_trade_return_is_simple_arithmetic_mean() -> None:
    metrics = calculate_trade_metrics(
        (
            trade("10", entry_cost="100"),
            trade("200", entry_cost="1000"),
        )
    )

    assert metrics.average_trade_return == Decimal("0.15")


def test_same_ledger_produces_identical_decimal_metrics() -> None:
    ledger = (trade("10"), trade("-5"), trade("0"))

    first = calculate_trade_metrics(ledger)
    second = calculate_trade_metrics(ledger)

    assert first == second
    assert isinstance(first.win_rate, Decimal)
    assert isinstance(first.average_trade_pnl, Decimal)
    assert isinstance(first.average_trade_return, Decimal)
