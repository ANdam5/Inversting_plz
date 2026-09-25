from decimal import Decimal

from investing_plz.domain import OrderSide
from investing_plz.domain.decimal import require_decimal


def apply_slippage(
    reference_price: Decimal,
    side: OrderSide,
    slippage_bps: Decimal,
) -> Decimal:
    """Return a deterministic fill price moved against the trading side."""

    reference_price = require_decimal(reference_price, name="reference_price")
    slippage_bps = require_decimal(slippage_bps, name="slippage_bps")
    if reference_price <= 0:
        raise ValueError("reference_price must be greater than zero")
    if not isinstance(side, OrderSide):
        raise TypeError("side must be an OrderSide")
    if not Decimal("0") <= slippage_bps < Decimal("10000"):
        raise ValueError("slippage_bps must be at least 0 and less than 10000")

    slippage_rate = slippage_bps / Decimal("10000")
    if side is OrderSide.BUY:
        return reference_price * (Decimal("1") + slippage_rate)
    return reference_price * (Decimal("1") - slippage_rate)


def calculate_fee(
    quantity: Decimal,
    fill_price: Decimal,
    fee_rate: Decimal,
) -> Decimal:
    """Calculate a fee from executed quantity, fill price, and fee rate."""

    quantity = require_decimal(quantity, name="quantity")
    fill_price = require_decimal(fill_price, name="fill_price")
    fee_rate = require_decimal(fee_rate, name="fee_rate")
    if quantity < 0:
        raise ValueError("quantity must not be negative")
    if fill_price <= 0:
        raise ValueError("fill_price must be greater than zero")
    if not Decimal("0") <= fee_rate < Decimal("1"):
        raise ValueError("fee_rate must be at least 0 and less than 1")
    return quantity * fill_price * fee_rate
