from datetime import datetime, timezone
from decimal import Decimal

import pytest

from investing_plz.domain import (
    Instrument,
    Order,
    OrderIntent,
    OrderSide,
    OrderStatus,
)


SUBMITTED_AT = datetime(2026, 9, 26, tzinfo=timezone.utc)


def make_order(**overrides: object) -> Order:
    values: dict[str, object] = {
        "order_id": "paper-order-1",
        "instrument": Instrument("upbit", "KRW-BTC"),
        "side": OrderSide.BUY,
        "quantity": Decimal("0.01"),
        "strategy_id": "moving_average_crossover",
        "submitted_at": SUBMITTED_AT,
        "status": OrderStatus.PENDING,
    }
    values.update(overrides)
    return Order(**values)


@pytest.mark.parametrize("side", [OrderSide.BUY, OrderSide.SELL])
def test_creates_pending_buy_and_sell_orders(side: OrderSide) -> None:
    order = make_order(side=side)

    assert order.side is side
    assert order.quantity == Decimal("0.01")
    assert order.status is OrderStatus.PENDING


def test_rejects_float_quantity() -> None:
    with pytest.raises(TypeError, match="quantity must be a Decimal"):
        make_order(quantity=0.01)


@pytest.mark.parametrize("quantity", [Decimal("0"), Decimal("-0.01")])
def test_rejects_non_positive_quantity(quantity: Decimal) -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        make_order(quantity=quantity)


def test_requires_utc_submitted_at() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        make_order(submitted_at=datetime(2026, 9, 26))


def test_accepts_utc_submitted_at() -> None:
    assert make_order().submitted_at == SUBMITTED_AT


@pytest.mark.parametrize("field", ["order_id", "strategy_id"])
def test_rejects_empty_identifiers(field: str) -> None:
    with pytest.raises(ValueError, match=field):
        make_order(**{field: "   "})


def test_pending_is_open_and_non_terminal() -> None:
    order = make_order()

    assert order.is_open is True
    assert order.is_terminal is False
    assert OrderStatus.PENDING.is_open is True
    assert OrderStatus.PENDING.is_terminal is False


@pytest.mark.parametrize(
    "status",
    [OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED],
)
def test_terminal_statuses_are_closed(status: OrderStatus) -> None:
    order = make_order(status=status)

    assert order.is_open is False
    assert order.is_terminal is True
    assert status.is_open is False
    assert status.is_terminal is True


@pytest.mark.parametrize(
    "status",
    [OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED],
)
def test_pending_can_transition_to_each_terminal_status(status: OrderStatus) -> None:
    original = make_order()

    transitioned = original.transition_to(status)

    assert transitioned.status is status
    assert transitioned.order_id == original.order_id
    assert original.status is OrderStatus.PENDING


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (OrderStatus.FILLED, OrderStatus.PENDING),
        (OrderStatus.FILLED, OrderStatus.CANCELED),
        (OrderStatus.FILLED, OrderStatus.REJECTED),
        (OrderStatus.CANCELED, OrderStatus.PENDING),
        (OrderStatus.CANCELED, OrderStatus.FILLED),
        (OrderStatus.CANCELED, OrderStatus.REJECTED),
        (OrderStatus.REJECTED, OrderStatus.PENDING),
        (OrderStatus.REJECTED, OrderStatus.FILLED),
        (OrderStatus.REJECTED, OrderStatus.CANCELED),
    ],
)
def test_terminal_orders_cannot_transition(
    current: OrderStatus,
    target: OrderStatus,
) -> None:
    with pytest.raises(ValueError, match="invalid order status transition"):
        make_order(status=current).transition_to(target)


@pytest.mark.parametrize("status", list(OrderStatus))
def test_self_transitions_are_rejected(status: OrderStatus) -> None:
    with pytest.raises(ValueError, match="invalid order status transition"):
        make_order(status=status).transition_to(status)


def test_order_from_intent_preserves_approved_order_fields() -> None:
    intent = OrderIntent(
        instrument=Instrument("upbit", "KRW-ETH"),
        timestamp=datetime(2026, 9, 25, tzinfo=timezone.utc),
        strategy_id="moving_average_crossover",
        side=OrderSide.SELL,
        quantity=Decimal("1.2500"),
    )

    order = Order.from_intent(
        intent,
        order_id="paper-order-2",
        submitted_at=SUBMITTED_AT,
    )

    assert order.instrument == intent.instrument
    assert order.side is intent.side
    assert order.quantity == intent.quantity
    assert order.strategy_id == intent.strategy_id
    assert order.order_id == "paper-order-2"
    assert order.submitted_at == SUBMITTED_AT
    assert order.status is OrderStatus.PENDING
