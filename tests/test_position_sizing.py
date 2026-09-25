from datetime import datetime, timezone
from decimal import Decimal

import pytest

from investing_plz.application import create_target_weight_order_intent
from investing_plz.domain import Instrument, OrderSide
from investing_plz.strategy import (
    MovingAverageCrossoverParameters,
    MovingAverageCrossoverStrategy,
    StrategyProfile,
    create_strategy_from_profile,
)


NOW = datetime(2026, 9, 25, tzinfo=timezone.utc)
BTC = Instrument("upbit", "KRW-BTC")


def size_btc(**overrides: object):
    values: dict[str, object] = {
        "instrument": BTC,
        "timestamp": NOW,
        "strategy_id": "moving_average_crossover",
        "target_weight": Decimal("0.10"),
        "portfolio_value": Decimal("10000000"),
        "current_price": Decimal("100000000"),
        "current_quantity": Decimal("0"),
        "quantity_step": Decimal("0.00000001"),
    }
    values.update(overrides)
    return create_target_weight_order_intent(**values)


def test_zero_position_creates_buy_for_full_target_quantity() -> None:
    intent = size_btc()

    assert intent is not None
    assert intent.side is OrderSide.BUY
    assert intent.quantity == Decimal("0.01000000")


def test_existing_position_buys_only_missing_quantity() -> None:
    intent = size_btc(current_quantity=Decimal("0.004"))

    assert intent is not None
    assert intent.side is OrderSide.BUY
    assert intent.quantity == Decimal("0.00600000")


def test_position_above_target_creates_positive_sell_quantity() -> None:
    intent = size_btc(current_quantity=Decimal("0.02"))

    assert intent is not None
    assert intent.side is OrderSide.SELL
    assert intent.quantity == Decimal("0.01000000")


def test_zero_target_sells_existing_long_position() -> None:
    intent = size_btc(
        target_weight=Decimal("0"),
        current_quantity=Decimal("0.02"),
    )

    assert intent is not None
    assert intent.side is OrderSide.SELL
    assert intent.quantity == Decimal("0.02000000")


def test_equal_target_and_current_position_creates_no_intent() -> None:
    assert size_btc(current_quantity=Decimal("0.01")) is None


def test_difference_below_quantity_step_creates_no_intent() -> None:
    assert size_btc(
        portfolio_value=Decimal("1"),
        current_price=Decimal("100"),
        target_weight=Decimal("0.10"),
        quantity_step=Decimal("0.01"),
    ) is None


def test_quantity_is_rounded_down_to_step() -> None:
    intent = size_btc(
        portfolio_value=Decimal("1000000.9"),
        target_weight=Decimal("1"),
        current_price=Decimal("100000000"),
    )

    assert intent is not None
    assert intent.quantity == Decimal("0.01000000")


@pytest.mark.parametrize("target_weight", [Decimal("-0.01"), Decimal("1.01")])
def test_rejects_target_weight_outside_long_only_range(
    target_weight: Decimal,
) -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        size_btc(target_weight=target_weight)


def test_rejects_float_target_weight() -> None:
    with pytest.raises(TypeError, match="target_weight must be a Decimal"):
        size_btc(target_weight=0.10)


@pytest.mark.parametrize("price", [Decimal("0"), Decimal("-1")])
def test_rejects_non_positive_price(price: Decimal) -> None:
    with pytest.raises(ValueError, match="current_price"):
        size_btc(current_price=price)


def test_rejects_negative_portfolio_value() -> None:
    with pytest.raises(ValueError, match="portfolio_value"):
        size_btc(portfolio_value=Decimal("-1"))


def test_rejects_negative_current_quantity() -> None:
    with pytest.raises(ValueError, match="current_quantity"):
        size_btc(current_quantity=Decimal("-0.01"))


def test_same_strategy_and_sizing_code_support_btc_and_etf() -> None:
    spy = Instrument("stock", "SPY")
    btc_profile = StrategyProfile(
        BTC,
        "moving_average_crossover",
        MovingAverageCrossoverParameters(20, 60),
    )
    spy_profile = StrategyProfile(
        spy,
        "moving_average_crossover",
        MovingAverageCrossoverParameters(50, 200),
    )

    btc_strategy = create_strategy_from_profile(btc_profile)
    spy_strategy = create_strategy_from_profile(spy_profile)
    btc_intent = size_btc()
    spy_intent = create_target_weight_order_intent(
        instrument=spy,
        timestamp=NOW,
        strategy_id=spy_strategy.strategy_id,
        target_weight=Decimal("0.30"),
        portfolio_value=Decimal("10000000"),
        current_price=Decimal("500000"),
        current_quantity=Decimal("0"),
        quantity_step=Decimal("1"),
    )

    assert type(btc_strategy) is MovingAverageCrossoverStrategy
    assert type(spy_strategy) is MovingAverageCrossoverStrategy
    assert btc_intent is not None and btc_intent.quantity == Decimal("0.01000000")
    assert spy_intent is not None and spy_intent.quantity == Decimal("6")

