from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from investing_plz.broker.models import ExecutionFill
from investing_plz.domain import Instrument, Order, OrderSide, OrderStatus
from investing_plz.domain.decimal import require_decimal


@dataclass(frozen=True, slots=True)
class PaperAccountProjection:
    cash: Decimal
    positions: tuple[tuple[Instrument, Decimal], ...]

    def position_quantity(self, instrument: Instrument) -> Decimal:
        return dict(self.positions).get(instrument, Decimal("0"))


def project_paper_account(
    initial_cash: Decimal,
    orders: Sequence[Order],
    fills: Sequence[ExecutionFill],
) -> PaperAccountProjection:
    """Validate durable execution records and derive cash/positions."""

    cash = require_decimal(initial_cash, name="initial_cash")
    if cash < 0:
        raise ValueError("initial_cash must not be negative")

    order_by_id: dict[str, Order] = {}
    for order in orders:
        if not isinstance(order, Order):
            raise TypeError("orders must contain only Order values")
        if order.order_id in order_by_id:
            raise ValueError(f"duplicate persisted order_id: {order.order_id}")
        order_by_id[order.order_id] = order

    fill_ids: set[str] = set()
    filled_order_ids: set[str] = set()
    positions: dict[Instrument, Decimal] = {}
    for fill in fills:
        if not isinstance(fill, ExecutionFill):
            raise TypeError("fills must contain only ExecutionFill values")
        if fill.fill_id in fill_ids:
            raise ValueError(f"duplicate persisted fill_id: {fill.fill_id}")
        fill_ids.add(fill.fill_id)
        order = order_by_id.get(fill.order_id)
        if order is None:
            raise ValueError(
                f"persisted fill references missing order: {fill.order_id}"
            )
        _validate_fill(fill, order)
        if order.order_id in filled_order_ids:
            raise ValueError(
                f"multiple fills found for non-partial order: {order.order_id}"
            )
        filled_order_ids.add(order.order_id)
        notional = fill.quantity * fill.fill_price
        quantity = positions.get(fill.instrument, Decimal("0"))
        if fill.side is OrderSide.BUY:
            cash -= notional + fill.fee_amount
            positions[fill.instrument] = quantity + fill.quantity
        else:
            cash += notional - fill.fee_amount
            positions[fill.instrument] = quantity - fill.quantity

    missing_fills = {
        order.order_id
        for order in orders
        if order.status is OrderStatus.FILLED
        and order.order_id not in filled_order_ids
    }
    if missing_fills:
        raise ValueError(
            "FILLED orders must have exactly one persisted fill: "
            + ", ".join(sorted(missing_fills))
        )
    if cash < 0:
        raise ValueError("persisted fills produce negative cash")
    negative_positions = [
        instrument for instrument, quantity in positions.items() if quantity < 0
    ]
    if negative_positions:
        names = ", ".join(
            f"{instrument.venue}:{instrument.symbol}"
            for instrument in negative_positions
        )
        raise ValueError(f"persisted fills produce negative position: {names}")

    return PaperAccountProjection(
        cash=cash,
        positions=tuple(
            sorted(
                (
                    (instrument, quantity)
                    for instrument, quantity in positions.items()
                    if quantity != 0
                ),
                key=lambda item: (item[0].venue, item[0].symbol),
            )
        ),
    )


def _validate_fill(fill: ExecutionFill, order: Order) -> None:
    if order.status is not OrderStatus.FILLED:
        raise ValueError("persisted fill requires a FILLED order")
    if (
        fill.instrument != order.instrument
        or fill.side is not order.side
        or fill.quantity != order.quantity
        or fill.strategy_id != order.strategy_id
    ):
        raise ValueError("persisted fill does not match its order")
