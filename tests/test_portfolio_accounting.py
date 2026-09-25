from datetime import datetime, timezone
from decimal import Decimal

import pytest

from investing_plz.backtest import BacktestPortfolio, Fill
from investing_plz.domain import Instrument, OrderSide


INSTRUMENT = Instrument("upbit", "KRW-BTC")
TIMESTAMP = datetime(2024, 1, 1, tzinfo=timezone.utc)


def fill(
    side: OrderSide,
    quantity: str,
    price: str,
    *,
    fee: str = "0",
) -> Fill:
    return Fill(
        instrument=INSTRUMENT,
        timestamp=TIMESTAMP,
        side=side,
        quantity=Decimal(quantity),
        fill_price=Decimal(price),
        strategy_id="test",
        fee_amount=Decimal(fee),
    )


def test_initial_accounting_state_is_zero() -> None:
    portfolio = BacktestPortfolio(cash=Decimal("1000"))

    assert portfolio.position_quantity == Decimal("0")
    assert portfolio.average_cost == Decimal("0")
    assert portfolio.realized_pnl == Decimal("0")


def test_buys_calculate_fee_inclusive_weighted_average_cost() -> None:
    portfolio = BacktestPortfolio(cash=Decimal("1000"))
    portfolio = portfolio.apply(fill(OrderSide.BUY, "1", "100", fee="10"))

    assert portfolio.average_cost == Decimal("110")

    portfolio = portfolio.apply(fill(OrderSide.BUY, "1", "200"))

    assert portfolio.position_quantity == Decimal("2")
    assert portfolio.average_cost == Decimal("155")
    assert portfolio.cash == Decimal("690")


def test_partial_sell_realizes_profit_and_keeps_average_cost() -> None:
    portfolio = BacktestPortfolio(cash=Decimal("1000"))
    portfolio = portfolio.apply(fill(OrderSide.BUY, "1", "100"))
    portfolio = portfolio.apply(fill(OrderSide.BUY, "1", "200"))

    portfolio = portfolio.apply(fill(OrderSide.SELL, "0.5", "180"))

    assert portfolio.position_quantity == Decimal("1.5")
    assert portfolio.average_cost == Decimal("150")
    assert portfolio.realized_pnl == Decimal("15.0")
    assert portfolio.cash == Decimal("790.0")


def test_sell_fee_reduces_realized_pnl_and_losses_are_negative() -> None:
    portfolio = BacktestPortfolio(
        cash=Decimal("0"),
        position_quantity=Decimal("2"),
        average_cost=Decimal("100"),
    )

    portfolio = portfolio.apply(fill(OrderSide.SELL, "1", "90", fee="2"))

    assert portfolio.realized_pnl == Decimal("-12")
    assert portfolio.cash == Decimal("88")


def test_multiple_sells_accumulate_realized_pnl() -> None:
    portfolio = BacktestPortfolio(
        cash=Decimal("0"),
        position_quantity=Decimal("2"),
        average_cost=Decimal("100"),
    )
    portfolio = portfolio.apply(fill(OrderSide.SELL, "0.5", "120"))
    portfolio = portfolio.apply(fill(OrderSide.SELL, "0.5", "80", fee="1"))

    assert portfolio.position_quantity == Decimal("1.0")
    assert portfolio.average_cost == Decimal("100")
    assert portfolio.realized_pnl == Decimal("-1.0")


def test_full_sell_resets_average_cost_but_keeps_realized_pnl() -> None:
    portfolio = BacktestPortfolio(cash=Decimal("1000"))
    portfolio = portfolio.apply(fill(OrderSide.BUY, "1", "100"))
    portfolio = portfolio.apply(fill(OrderSide.SELL, "1", "120"))

    assert portfolio.position_quantity == Decimal("0")
    assert portfolio.average_cost == Decimal("0")
    assert portfolio.realized_pnl == Decimal("20")

    portfolio = portfolio.apply(fill(OrderSide.BUY, "2", "50", fee="2"))

    assert portfolio.average_cost == Decimal("51")
    assert portfolio.realized_pnl == Decimal("20")


def test_accounting_keeps_existing_oversell_protection() -> None:
    portfolio = BacktestPortfolio(
        cash=Decimal("0"),
        position_quantity=Decimal("1"),
        average_cost=Decimal("100"),
    )

    with pytest.raises(ValueError, match="exceeds the current position"):
        portfolio.apply(fill(OrderSide.SELL, "2", "100"))
