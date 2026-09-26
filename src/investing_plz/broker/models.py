from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from investing_plz.domain import Instrument, OrderSide
from investing_plz.domain.decimal import require_decimal
from investing_plz.domain.time import require_utc


@dataclass(frozen=True, slots=True)
class ExecutionFill:
    """Provider-neutral execution result linked to a submitted order."""

    fill_id: str
    order_id: str
    instrument: Instrument
    side: OrderSide
    quantity: Decimal
    fill_price: Decimal
    fee_amount: Decimal
    filled_at: datetime
    strategy_id: str

    def __post_init__(self) -> None:
        for name in ("fill_id", "order_id", "strategy_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be empty")
        if not isinstance(self.instrument, Instrument):
            raise TypeError("instrument must be an Instrument")
        if not isinstance(self.side, OrderSide):
            raise TypeError("side must be an OrderSide")
        quantity = require_decimal(self.quantity, name="quantity")
        fill_price = require_decimal(self.fill_price, name="fill_price")
        fee_amount = require_decimal(self.fee_amount, name="fee_amount")
        if quantity <= 0:
            raise ValueError("quantity must be greater than zero")
        if fill_price <= 0:
            raise ValueError("fill_price must be greater than zero")
        if fee_amount < 0:
            raise ValueError("fee_amount must not be negative")
        require_utc(self.filled_at)
