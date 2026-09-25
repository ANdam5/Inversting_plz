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


def test_zero_position_has_zero_unrealized_pnl() -> None:
    portfolio = BacktestPortfolio(cash=Decimal("1000"))

    assert portfolio.unrealized_pnl_at(Decimal("120")) == Decimal("0")


@pytest.mark.parametrize(
    ("current_price", "expected"),
    [
        (Decimal("120"), Decimal("40")),
        (Decimal("80"), Decimal("-40")),
        (Decimal("100"), Decimal("0")),
    ],
)
def test_unrealized_pnl_uses_current_price_and_average_cost(
    current_price: Decimal,
    expected: Decimal,
) -> None:
    portfolio = BacktestPortfolio(
        cash=Decimal("0"),
        position_quantity=Decimal("2"),
        average_cost=Decimal("100"),
    )

    assert portfolio.unrealized_pnl_at(current_price) == expected


def test_buy_fee_is_not_deducted_again_from_unrealized_pnl() -> None:
    portfolio = BacktestPortfolio(cash=Decimal("1000"))
    portfolio = portfolio.apply(fill(OrderSide.BUY, "2", "100", fee="10"))

    assert portfolio.average_cost == Decimal("105")
    assert portfolio.unrealized_pnl_at(Decimal("110")) == Decimal("10")


def test_partial_sell_uses_remaining_quantity_without_changing_accounting() -> None:
    portfolio = BacktestPortfolio(cash=Decimal("1000"))
    portfolio = portfolio.apply(fill(OrderSide.BUY, "2", "100"))
    portfolio = portfolio.apply(fill(OrderSide.SELL, "0.5", "120"))
    state_before_evaluation = portfolio

    assert portfolio.unrealized_pnl_at(Decimal("110")) == Decimal("15.0")
    assert portfolio == state_before_evaluation
    assert portfolio.realized_pnl == Decimal("10.0")


def test_full_sell_has_zero_unrealized_pnl() -> None:
    portfolio = BacktestPortfolio(cash=Decimal("1000"))
    portfolio = portfolio.apply(fill(OrderSide.BUY, "1", "100"))
    portfolio = portfolio.apply(fill(OrderSide.SELL, "1", "120"))

    assert portfolio.unrealized_pnl_at(Decimal("150")) == Decimal("0")
    assert portfolio.realized_pnl == Decimal("20")


def test_unrealized_pnl_requires_decimal_price() -> None:
    portfolio = BacktestPortfolio(cash=Decimal("1000"))

    with pytest.raises(TypeError, match="Decimal"):
        portfolio.unrealized_pnl_at(120.0)  # type: ignore[arg-type]


def test_realized_plus_unrealized_reconciles_to_portfolio_gain() -> None:
    initial_cash = Decimal("1000")
    current_price = Decimal("110")
    portfolio = BacktestPortfolio(cash=initial_cash)
    portfolio = portfolio.apply(fill(OrderSide.BUY, "2", "100", fee="10"))
    portfolio = portfolio.apply(fill(OrderSide.SELL, "0.5", "120", fee="1"))

    total_pnl = portfolio.realized_pnl + portfolio.unrealized_pnl_at(current_price)

    assert initial_cash + total_pnl == portfolio.value_at(current_price)
