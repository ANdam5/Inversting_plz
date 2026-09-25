from datetime import datetime, timezone
from decimal import Decimal

import pytest

from investing_plz.backtest import (
    BacktestPortfolio,
    ClosedTrade,
    Fill,
    build_closed_trades,
)
from investing_plz.domain import Instrument, OrderSide


INSTRUMENT = Instrument("upbit", "KRW-BTC")


def fill(
    day: int,
    side: OrderSide,
    quantity: str,
    price: str,
    *,
    fee: str = "0",
) -> Fill:
    return Fill(
        instrument=INSTRUMENT,
        timestamp=datetime(2024, 1, day, tzinfo=timezone.utc),
        side=side,
        quantity=Decimal(quantity),
        fill_price=Decimal(price),
        strategy_id="test",
        fee_amount=Decimal(fee),
    )


def test_buy_then_sell_creates_one_closed_trade() -> None:
    fills = (
        fill(1, OrderSide.BUY, "1", "100"),
        fill(2, OrderSide.SELL, "1", "120"),
    )

    assert build_closed_trades(fills) == (
        ClosedTrade(
            opened_at=fills[0].timestamp,
            closed_at=fills[1].timestamp,
            entry_cost=Decimal("100"),
            exit_proceeds=Decimal("120"),
            realized_pnl=Decimal("20"),
        ),
    )


def test_multiple_buys_are_one_trade_and_include_buy_fees() -> None:
    fills = (
        fill(1, OrderSide.BUY, "1", "100", fee="1"),
        fill(2, OrderSide.BUY, "2", "150", fee="2"),
        fill(3, OrderSide.SELL, "3", "160"),
    )

    trade = build_closed_trades(fills)[0]

    assert trade.opened_at == fills[0].timestamp
    assert trade.closed_at == fills[-1].timestamp
    assert trade.entry_cost == Decimal("403")
    assert trade.exit_proceeds == Decimal("480")
    assert trade.realized_pnl == Decimal("77")


def test_partial_sells_accumulate_net_proceeds_until_final_sell() -> None:
    fills = (
        fill(1, OrderSide.BUY, "2", "100"),
        fill(2, OrderSide.SELL, "0.5", "120", fee="1"),
    )

    assert build_closed_trades(fills) == ()

    trades = build_closed_trades(
        fills + (fill(3, OrderSide.SELL, "1.5", "110", fee="2"),)
    )

    assert len(trades) == 1
    assert trades[0].exit_proceeds == Decimal("222.0")
    assert trades[0].realized_pnl == Decimal("22.0")


def test_loss_trade_has_negative_realized_pnl() -> None:
    trade = build_closed_trades(
        (
            fill(1, OrderSide.BUY, "1", "100", fee="1"),
            fill(2, OrderSide.SELL, "1", "90", fee="1"),
        )
    )[0]

    assert trade.entry_cost == Decimal("101")
    assert trade.exit_proceeds == Decimal("89")
    assert trade.realized_pnl == Decimal("-12")


def test_two_position_cycles_create_two_closed_trades() -> None:
    fills = (
        fill(1, OrderSide.BUY, "1", "100"),
        fill(2, OrderSide.SELL, "1", "120"),
        fill(3, OrderSide.BUY, "2", "80"),
        fill(4, OrderSide.SELL, "2", "70"),
    )

    trades = build_closed_trades(fills)

    assert len(trades) == 2
    assert [trade.realized_pnl for trade in trades] == [
        Decimal("20"),
        Decimal("-20"),
    ]


def test_last_open_position_is_not_added_to_closed_trades() -> None:
    fills = (
        fill(1, OrderSide.BUY, "1", "100"),
        fill(2, OrderSide.SELL, "1", "120"),
        fill(3, OrderSide.BUY, "1", "90"),
    )

    trades = build_closed_trades(fills)

    assert len(trades) == 1
    assert trades[0].closed_at == fills[1].timestamp


def test_closed_trade_pnl_sum_matches_portfolio_realized_pnl() -> None:
    fills = (
        fill(1, OrderSide.BUY, "1", "100", fee="1"),
        fill(2, OrderSide.BUY, "1", "150", fee="1"),
        fill(3, OrderSide.SELL, "0.5", "180", fee="1"),
        fill(4, OrderSide.SELL, "1.5", "160", fee="1"),
        fill(5, OrderSide.BUY, "1", "200"),
        fill(6, OrderSide.SELL, "1", "190", fee="1"),
    )
    portfolio = BacktestPortfolio(cash=Decimal("1000"))
    for item in fills:
        portfolio = portfolio.apply(item)

    closed_pnl = sum(
        (trade.realized_pnl for trade in build_closed_trades(fills)),
        start=Decimal("0"),
    )

    assert closed_pnl == portfolio.realized_pnl


def test_invalid_sell_and_fill_order_are_rejected() -> None:
    with pytest.raises(ValueError, match="exceeds the open position"):
        build_closed_trades((fill(1, OrderSide.SELL, "1", "100"),))

    with pytest.raises(ValueError, match="ascending timestamp"):
        build_closed_trades(
            (
                fill(2, OrderSide.BUY, "1", "100"),
                fill(1, OrderSide.SELL, "1", "100"),
            )
        )
