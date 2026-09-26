from typing import Protocol

from investing_plz.domain import Order, OrderIntent


class Broker(Protocol):
    """Provider-neutral contract for submitted order lifecycles."""

    def submit(self, intent: OrderIntent) -> Order: ...

    def get_order(self, order_id: str) -> Order | None: ...

    def list_open_orders(self) -> tuple[Order, ...]: ...

    def cancel_order(self, order_id: str) -> Order: ...
