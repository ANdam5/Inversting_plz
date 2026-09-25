from datetime import datetime
from decimal import Decimal

from investing_plz.domain import Instrument, OrderIntent, OrderSide
from investing_plz.domain.decimal import require_decimal, round_down_to_step
from investing_plz.domain.time import require_utc


def create_target_weight_order_intent(
    *,
    instrument: Instrument,
    timestamp: datetime,
    strategy_id: str,
    target_weight: Decimal,
    portfolio_value: Decimal,
    current_price: Decimal,
    current_quantity: Decimal,
    quantity_step: Decimal,
) -> OrderIntent | None:
    """Create the quantity adjustment needed to reach a long-only target weight."""

    if not isinstance(instrument, Instrument):
        raise TypeError("instrument must be an Instrument")
    require_utc(timestamp)
    if not strategy_id.strip():
        raise ValueError("strategy_id must not be empty")

    target_weight = require_decimal(target_weight, name="target_weight")
    portfolio_value = require_decimal(portfolio_value, name="portfolio_value")
    current_price = require_decimal(current_price, name="current_price")
    current_quantity = require_decimal(current_quantity, name="current_quantity")
    quantity_step = require_decimal(quantity_step, name="quantity_step")

    if not Decimal("0") <= target_weight <= Decimal("1"):
        raise ValueError("target_weight must be between 0 and 1")
    if portfolio_value < 0:
        raise ValueError("portfolio_value must not be negative")
    if current_price <= 0:
        raise ValueError("current_price must be greater than zero")
    if current_quantity < 0:
        raise ValueError("current_quantity must not be negative")
    if quantity_step <= 0:
        raise ValueError("quantity_step must be greater than zero")

    target_value = portfolio_value * target_weight
    target_quantity = target_value / current_price
    difference = target_quantity - current_quantity
    quantity = round_down_to_step(abs(difference), quantity_step)
    if quantity == 0:
        return None

    side = OrderSide.BUY if difference > 0 else OrderSide.SELL
    return OrderIntent(
        instrument=instrument,
        timestamp=timestamp,
        strategy_id=strategy_id,
        side=side,
        quantity=quantity,
    )
