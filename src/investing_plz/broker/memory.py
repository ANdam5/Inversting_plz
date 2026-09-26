from collections.abc import Callable
from datetime import datetime
import logging

from investing_plz.domain import Order, OrderIntent, OrderStatus
from investing_plz.structured_logging import log_event


_LOGGER = logging.getLogger(__name__)


class InMemoryBroker:
    """Minimal deterministic Broker fake without execution or balance logic."""

    def __init__(
        self,
        *,
        order_id_factory: Callable[[], str],
        submitted_at_factory: Callable[[], datetime],
    ) -> None:
        self._order_id_factory = order_id_factory
        self._submitted_at_factory = submitted_at_factory
        self._orders: dict[str, Order] = {}

    def submit(self, intent: OrderIntent) -> Order:
        if not isinstance(intent, OrderIntent):
            raise TypeError("intent must be an OrderIntent")
        order = Order.from_intent(
            intent,
            order_id=self._order_id_factory(),
            submitted_at=self._submitted_at_factory(),
        )
        if order.order_id in self._orders:
            raise ValueError(f"duplicate order_id: {order.order_id}")
        self._orders[order.order_id] = order
        log_event(
            _LOGGER,
            "paper.order_submitted",
            instrument=str(order.instrument),
            strategy_id=order.strategy_id,
            order_id=order.order_id,
            order_status=order.status.value,
        )
        return order

    def get_order(self, order_id: str) -> Order | None:
        return self._orders.get(order_id)

    def list_open_orders(self) -> tuple[Order, ...]:
        return tuple(order for order in self._orders.values() if order.is_open)

    def list_orders(self) -> tuple[Order, ...]:
        return tuple(self._orders.values())

    def cancel_order(self, order_id: str) -> Order:
        order = self.get_order(order_id)
        if order is None:
            raise KeyError(f"order not found: {order_id}")
        canceled = order.transition_to(OrderStatus.CANCELED)
        self._replace_order(canceled)
        log_event(
            _LOGGER,
            "paper.order_canceled",
            order_id=canceled.order_id,
            order_status=canceled.status.value,
        )
        return canceled

    def _replace_order(self, order: Order) -> None:
        if order.order_id not in self._orders:
            raise KeyError(f"order not found: {order.order_id}")
        self._orders[order.order_id] = order
