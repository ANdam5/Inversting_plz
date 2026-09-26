from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from investing_plz.broker.memory import InMemoryBroker
from investing_plz.broker.models import ExecutionFill
from investing_plz.domain import Order, OrderStatus


class PaperBroker(InMemoryBroker):
    """Explicit in-memory Order/Fill lifecycle without account execution."""

    def __init__(
        self,
        *,
        order_id_factory: Callable[[], str],
        submitted_at_factory: Callable[[], datetime],
    ) -> None:
        super().__init__(
            order_id_factory=order_id_factory,
            submitted_at_factory=submitted_at_factory,
        )
        self._fills: dict[str, ExecutionFill] = {}

    def fill_order(
        self,
        order_id: str,
        *,
        fill_id: str,
        quantity: Decimal,
        fill_price: Decimal,
        fee_amount: Decimal,
        filled_at: datetime,
    ) -> ExecutionFill:
        order = self.get_order(order_id)
        if order is None:
            raise KeyError(f"order not found: {order_id}")
        if fill_id in self._fills:
            raise ValueError(f"duplicate fill_id: {fill_id}")

        fill = ExecutionFill(
            fill_id=fill_id,
            order_id=order.order_id,
            instrument=order.instrument,
            side=order.side,
            quantity=quantity,
            fill_price=fill_price,
            fee_amount=fee_amount,
            filled_at=filled_at,
            strategy_id=order.strategy_id,
        )
        if fill.quantity != order.quantity:
            raise ValueError("fill quantity must equal order quantity")
        filled_order = order.transition_to(OrderStatus.FILLED)
        self._replace_order(filled_order)
        self._fills[fill.fill_id] = fill
        return fill

    def list_fills(self) -> tuple[ExecutionFill, ...]:
        return tuple(self._fills.values())

    def reject_order(self, order_id: str) -> Order:
        order = self.get_order(order_id)
        if order is None:
            raise KeyError(f"order not found: {order_id}")
        rejected = order.transition_to(OrderStatus.REJECTED)
        self._replace_order(rejected)
        return rejected
