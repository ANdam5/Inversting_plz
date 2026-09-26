from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from investing_plz.domain.decimal import require_decimal
from investing_plz.domain.instrument import Instrument
from investing_plz.domain.order_intent import OrderIntent, OrderSide
from investing_plz.domain.time import require_utc


class OrderStatus(StrEnum):
    PENDING = "pending"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"

    @property
    def is_open(self) -> bool:
        return self is OrderStatus.PENDING

    @property
    def is_terminal(self) -> bool:
        return not self.is_open


@dataclass(frozen=True, slots=True)
class Order:
    """A submitted order with a provider-neutral lifecycle status."""

    order_id: str
    instrument: Instrument
    side: OrderSide
    quantity: Decimal
    strategy_id: str
    submitted_at: datetime
    status: OrderStatus = OrderStatus.PENDING

    def __post_init__(self) -> None:
        if not isinstance(self.order_id, str) or not self.order_id.strip():
            raise ValueError("order_id must not be empty")
        if not isinstance(self.instrument, Instrument):
            raise TypeError("instrument must be an Instrument")
        if not isinstance(self.side, OrderSide):
            raise TypeError("side must be an OrderSide")
        quantity = require_decimal(self.quantity, name="quantity")
        if quantity <= 0:
            raise ValueError("quantity must be greater than zero")
        if not isinstance(self.strategy_id, str) or not self.strategy_id.strip():
            raise ValueError("strategy_id must not be empty")
        require_utc(self.submitted_at)
        if not isinstance(self.status, OrderStatus):
            raise TypeError("status must be an OrderStatus")

    @property
    def is_open(self) -> bool:
        return self.status.is_open

    @property
    def is_terminal(self) -> bool:
        return self.status.is_terminal

    def transition_to(self, status: OrderStatus) -> "Order":
        if not isinstance(status, OrderStatus):
            raise TypeError("status must be an OrderStatus")
        if self.status is not OrderStatus.PENDING or status is OrderStatus.PENDING:
            raise ValueError(
                f"invalid order status transition: {self.status.value} -> {status.value}"
            )
        return replace(self, status=status)

    @classmethod
    def from_intent(
        cls,
        intent: OrderIntent,
        *,
        order_id: str,
        submitted_at: datetime,
    ) -> "Order":
        if not isinstance(intent, OrderIntent):
            raise TypeError("intent must be an OrderIntent")
        return cls(
            order_id=order_id,
            instrument=intent.instrument,
            side=intent.side,
            quantity=intent.quantity,
            strategy_id=intent.strategy_id,
            submitted_at=submitted_at,
            status=OrderStatus.PENDING,
        )
