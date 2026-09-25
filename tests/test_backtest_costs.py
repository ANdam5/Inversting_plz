from datetime import datetime, timezone
from decimal import Decimal

import pytest

from investing_plz.backtest import (
    BacktestConfig,
    Fill,
    apply_slippage,
    calculate_fee,
)
from investing_plz.domain import Instrument, OrderSide
from investing_plz.risk import RiskLimits


def config(**overrides: object) -> BacktestConfig:
    values: dict[str, object] = {
        "initial_cash": Decimal("10000000"),
        "target_weight": Decimal("0.10"),
        "quantity_step": Decimal("0.00000001"),
        "risk_limits": RiskLimits(
            max_order_amount=Decimal("500000"),
            max_instrument_weight=Decimal("0.20"),
            min_cash_reserve=Decimal("1000000"),
        ),
    }
    values.update(overrides)
    return BacktestConfig(**values)


def test_cost_config_defaults_are_zero() -> None:
    backtest_config = config()

    assert backtest_config.fee_rate == Decimal("0")
    assert backtest_config.slippage_bps == Decimal("0")


def test_decimal_cost_config_is_allowed() -> None:
    backtest_config = config(
        fee_rate=Decimal("0.0005"),
        slippage_bps=Decimal("5"),
    )

    assert backtest_config.fee_rate == Decimal("0.0005")
    assert backtest_config.slippage_bps == Decimal("5")


@pytest.mark.parametrize("value", [0.0005, -0.1, 1.0])
def test_float_fee_rate_is_rejected(value: float) -> None:
    with pytest.raises(TypeError, match="Decimal"):
        config(fee_rate=value)


@pytest.mark.parametrize("value", [Decimal("-0.0001"), Decimal("1")])
def test_fee_rate_outside_range_is_rejected(value: Decimal) -> None:
    with pytest.raises(ValueError, match="fee_rate"):
        config(fee_rate=value)


@pytest.mark.parametrize("value", [5.0, -1.0, 10000.0])
def test_float_slippage_bps_is_rejected(value: float) -> None:
    with pytest.raises(TypeError, match="Decimal"):
        config(slippage_bps=value)


@pytest.mark.parametrize("value", [Decimal("-0.01"), Decimal("10000")])
def test_slippage_bps_outside_range_is_rejected(value: Decimal) -> None:
    with pytest.raises(ValueError, match="slippage_bps"):
        config(slippage_bps=value)


def test_zero_slippage_preserves_reference_price() -> None:
    price = Decimal("100000000")

    assert apply_slippage(price, OrderSide.BUY, Decimal("0")) == price
    assert apply_slippage(price, OrderSide.SELL, Decimal("0")) == price


def test_slippage_moves_buy_and_sell_prices_in_unfavorable_directions() -> None:
    price = Decimal("100000000")

    buy_price = apply_slippage(price, OrderSide.BUY, Decimal("5"))
    sell_price = apply_slippage(price, OrderSide.SELL, Decimal("5"))

    assert buy_price == Decimal("100050000.0000")
    assert sell_price == Decimal("99950000.0000")
    assert buy_price > price
    assert sell_price < price


def test_fee_is_notional_times_fee_rate() -> None:
    assert calculate_fee(
        Decimal("0.01"),
        Decimal("100000000"),
        Decimal("0.0005"),
    ) == Decimal("500.000000")


def test_fill_preserves_decimal_fee_amount() -> None:
    fill = Fill(
        instrument=Instrument("upbit", "KRW-BTC"),
        timestamp=datetime(2026, 9, 25, tzinfo=timezone.utc),
        side=OrderSide.BUY,
        quantity=Decimal("0.01"),
        fill_price=Decimal("100050000"),
        strategy_id="moving_average_crossover",
        fee_amount=Decimal("500.25"),
    )

    assert isinstance(fill.fee_amount, Decimal)
    assert fill.fee_amount == Decimal("500.25")


def test_fill_fee_defaults_to_zero_and_rejects_float() -> None:
    values = {
        "instrument": Instrument("upbit", "KRW-BTC"),
        "timestamp": datetime(2026, 9, 25, tzinfo=timezone.utc),
        "side": OrderSide.BUY,
        "quantity": Decimal("0.01"),
        "fill_price": Decimal("100000000"),
        "strategy_id": "moving_average_crossover",
    }
    assert Fill(**values).fee_amount == Decimal("0")

    with pytest.raises(TypeError, match="Decimal"):
        Fill(**values, fee_amount=500.0)
