from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from investing_plz.broker.memory import InMemoryBroker
from investing_plz.broker.models import ExecutionFill
from investing_plz.domain import Instrument, Order, OrderSide, OrderStatus
from investing_plz.domain.decimal import require_decimal
from investing_plz.execution import (
    apply_slippage,
    calculate_fee,
    validate_fee_rate,
    validate_slippage_bps,
)


class PaperBroker(InMemoryBroker):
    """Deterministic in-memory execution account for paper orders."""

    def __init__(
        self,
        *,
        initial_cash: Decimal,
        fee_rate: Decimal = Decimal("0"),
        slippage_bps: Decimal = Decimal("0"),
        order_id_factory: Callable[[], str],
        submitted_at_factory: Callable[[], datetime],
    ) -> None:
        super().__init__(
            order_id_factory=order_id_factory,
            submitted_at_factory=submitted_at_factory,
        )
        initial_cash = require_decimal(initial_cash, name="initial_cash")
        if initial_cash < 0:
            raise ValueError("initial_cash must not be negative")
        self._cash = initial_cash
        self._fee_rate = validate_fee_rate(fee_rate)
        self._slippage_bps = validate_slippage_bps(slippage_bps)
        self._positions: dict[Instrument, Decimal] = {}
        self._fills: dict[str, ExecutionFill] = {}

    @property
    def cash(self) -> Decimal:
        return self._cash

    def position_quantity(self, instrument: Instrument) -> Decimal:
        if not isinstance(instrument, Instrument):
            raise TypeError("instrument must be an Instrument")
        return self._positions.get(instrument, Decimal("0"))

    def execute_order(
        self,
        order_id: str,
        *,
        reference_price: Decimal,
        fill_id: str,
        filled_at: datetime,
    ) -> ExecutionFill | None:
        order = self.get_order(order_id)
        if order is None:
            raise KeyError(f"order not found: {order_id}")
        if fill_id in self._fills:
            raise ValueError(f"duplicate fill_id: {fill_id}")

        fill_price = apply_slippage(
            reference_price,
            order.side,
            self._slippage_bps,
        )
        fee_amount = calculate_fee(order.quantity, fill_price, self._fee_rate)
        fill = ExecutionFill(
            fill_id=fill_id,
            order_id=order.order_id,
            instrument=order.instrument,
            side=order.side,
            quantity=order.quantity,
            fill_price=fill_price,
            fee_amount=fee_amount,
            filled_at=filled_at,
            strategy_id=order.strategy_id,
        )
        filled_order = order.transition_to(OrderStatus.FILLED)

        notional = fill.quantity * fill.fill_price
        current_position = self.position_quantity(order.instrument)
        if order.side is OrderSide.BUY:
            new_cash = self._cash - notional - fill.fee_amount
            if new_cash < 0:
                self._replace_order(order.transition_to(OrderStatus.REJECTED))
                return None
            new_position = current_position + fill.quantity
        else:
            if fill.quantity > current_position:
                self._replace_order(order.transition_to(OrderStatus.REJECTED))
                return None
            new_cash = self._cash + notional - fill.fee_amount
            new_position = current_position - fill.quantity

        self._replace_order(filled_order)
        self._fills[fill.fill_id] = fill
        self._cash = new_cash
        self._positions[order.instrument] = new_position
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
