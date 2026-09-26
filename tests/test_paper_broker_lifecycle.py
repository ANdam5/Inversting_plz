from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from investing_plz.broker import Broker, ExecutionFill, PaperBroker
from investing_plz.domain import Instrument, OrderIntent, OrderSide, OrderStatus


SUBMITTED_AT = datetime(2026, 9, 26, tzinfo=timezone.utc)
FILLED_AT = datetime(2026, 9, 26, 0, 1, tzinfo=timezone.utc)


def make_intent(*, side: OrderSide = OrderSide.BUY) -> OrderIntent:
    return OrderIntent(
        instrument=Instrument("upbit", "KRW-BTC"),
        timestamp=datetime(2026, 9, 25, tzinfo=timezone.utc),
        strategy_id="moving_average_crossover",
        side=side,
        quantity=Decimal("0.01"),
    )


def make_broker() -> PaperBroker:
    identifiers = iter(("order-1", "order-2", "order-3"))
    return PaperBroker(
        order_id_factory=lambda: next(identifiers),
        submitted_at_factory=lambda: SUBMITTED_AT,
    )


def fill_order(
    broker: PaperBroker,
    order_id: str,
    **overrides: object,
) -> ExecutionFill:
    values: dict[str, object] = {
        "fill_id": "fill-1",
        "quantity": Decimal("0.01"),
        "fill_price": Decimal("100000000"),
        "fee_amount": Decimal("500"),
        "filled_at": FILLED_AT,
    }
    values.update(overrides)
    return broker.fill_order(order_id, **values)


def test_paper_broker_satisfies_existing_order_contract() -> None:
    broker: Broker = make_broker()
    order = broker.submit(make_intent())

    assert order.status is OrderStatus.PENDING
    assert broker.get_order(order.order_id) == order
    assert broker.list_open_orders() == (order,)

    canceled = broker.cancel_order(order.order_id)
    assert canceled.status is OrderStatus.CANCELED
    assert broker.list_open_orders() == ()


@pytest.mark.parametrize("side", [OrderSide.BUY, OrderSide.SELL])
def test_pending_order_fills_and_preserves_order_identity(side: OrderSide) -> None:
    broker = make_broker()
    original = broker.submit(make_intent(side=side))

    fill = fill_order(broker, original.order_id)

    stored = broker.get_order(original.order_id)
    assert original.status is OrderStatus.PENDING
    assert stored is not None
    assert stored.status is OrderStatus.FILLED
    assert fill.order_id == original.order_id
    assert fill.instrument == original.instrument
    assert fill.side is original.side
    assert fill.quantity == original.quantity
    assert fill.strategy_id == original.strategy_id
    assert broker.list_open_orders() == ()
    assert broker.list_fills() == (fill,)


def test_canceled_order_cannot_fill() -> None:
    broker = make_broker()
    order = broker.submit(make_intent())
    broker.cancel_order(order.order_id)

    with pytest.raises(ValueError, match="invalid order status transition"):
        fill_order(broker, order.order_id)

    assert broker.list_fills() == ()


def test_filled_order_cannot_fill_again() -> None:
    broker = make_broker()
    order = broker.submit(make_intent())
    fill_order(broker, order.order_id)

    with pytest.raises(ValueError, match="invalid order status transition"):
        fill_order(broker, order.order_id, fill_id="fill-2")

    assert len(broker.list_fills()) == 1


def test_rejected_order_cannot_fill() -> None:
    broker = make_broker()
    order = broker.submit(make_intent())

    rejected = broker.reject_order(order.order_id)

    assert rejected.status is OrderStatus.REJECTED
    assert broker.list_open_orders() == ()
    with pytest.raises(ValueError, match="invalid order status transition"):
        fill_order(broker, order.order_id)


def test_missing_order_cannot_fill_or_be_rejected() -> None:
    broker = make_broker()

    with pytest.raises(KeyError, match="order not found"):
        fill_order(broker, "missing-order")
    with pytest.raises(KeyError, match="order not found"):
        broker.reject_order("missing-order")


def test_duplicate_fill_id_is_rejected_without_changing_second_order() -> None:
    broker = make_broker()
    first = broker.submit(make_intent())
    second = broker.submit(make_intent(side=OrderSide.SELL))
    fill_order(broker, first.order_id)

    with pytest.raises(ValueError, match="duplicate fill_id"):
        fill_order(broker, second.order_id)

    assert broker.get_order(second.order_id) == second
    assert broker.list_open_orders() == (second,)


def test_fill_quantity_must_equal_order_quantity() -> None:
    broker = make_broker()
    order = broker.submit(make_intent())

    with pytest.raises(ValueError, match="must equal order quantity"):
        fill_order(broker, order.order_id, quantity=Decimal("0.005"))

    assert broker.get_order(order.order_id) == order
    assert broker.list_fills() == ()


@pytest.mark.parametrize(
    ("field", "value", "error", "message"),
    [
        ("quantity", 0.01, TypeError, "quantity must be a Decimal"),
        ("quantity", Decimal("0"), ValueError, "quantity must be greater"),
        ("quantity", Decimal("-0.01"), ValueError, "quantity must be greater"),
        ("fill_price", 100.0, TypeError, "fill_price must be a Decimal"),
        ("fee_amount", 0.0, TypeError, "fee_amount must be a Decimal"),
        ("fill_price", Decimal("0"), ValueError, "fill_price must be greater"),
        ("fee_amount", Decimal("-1"), ValueError, "fee_amount must not be negative"),
        ("filled_at", datetime(2026, 9, 26), ValueError, "timezone-aware"),
    ],
)
def test_invalid_fill_values_are_rejected_without_changing_order(
    field: str,
    value: object,
    error: type[Exception],
    message: str,
) -> None:
    broker = make_broker()
    order = broker.submit(make_intent())

    with pytest.raises(error, match=message):
        fill_order(broker, order.order_id, **{field: value})

    assert broker.get_order(order.order_id) == order
    assert broker.list_fills() == ()


@pytest.mark.parametrize("field", ["fill_id", "order_id", "strategy_id"])
def test_execution_fill_rejects_empty_identifiers(field: str) -> None:
    values: dict[str, object] = {
        "fill_id": "fill-1",
        "order_id": "order-1",
        "instrument": Instrument("upbit", "KRW-BTC"),
        "side": OrderSide.BUY,
        "quantity": Decimal("0.01"),
        "fill_price": Decimal("100000000"),
        "fee_amount": Decimal("500"),
        "filled_at": FILLED_AT,
        "strategy_id": "moving_average_crossover",
    }
    values[field] = "   "

    with pytest.raises(ValueError, match=field):
        ExecutionFill(**values)


def test_identical_inputs_produce_identical_order_and_fill_results() -> None:
    first = make_broker()
    second = make_broker()

    first_order = first.submit(make_intent())
    second_order = second.submit(make_intent())
    first_fill = fill_order(first, first_order.order_id)
    second_fill = fill_order(second, second_order.order_id)

    assert first_order == second_order
    assert first_fill == second_fill
    assert first.get_order(first_order.order_id) == second.get_order(
        second_order.order_id
    )
    assert first.list_fills() == second.list_fills()


def test_execution_fill_is_immutable() -> None:
    broker = make_broker()
    order = broker.submit(make_intent())
    fill = fill_order(broker, order.order_id)

    with pytest.raises(FrozenInstanceError):
        fill.quantity = Decimal("1")  # type: ignore[misc]
