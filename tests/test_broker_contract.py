from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from investing_plz.broker import Broker, InMemoryBroker
from investing_plz.domain import Instrument, OrderIntent, OrderSide, OrderStatus


def make_intent(
    *,
    side: OrderSide = OrderSide.BUY,
    instrument: Instrument | None = None,
    quantity: Decimal = Decimal("0.01"),
) -> OrderIntent:
    return OrderIntent(
        instrument=instrument or Instrument("upbit", "KRW-BTC"),
        timestamp=datetime(2026, 9, 25, tzinfo=timezone.utc),
        strategy_id="moving_average_crossover",
        side=side,
        quantity=quantity,
    )


@pytest.fixture
def broker() -> Broker:
    identifiers = iter(("order-1", "order-2", "order-3"))
    timestamps = iter(
        (
            datetime(2026, 9, 26, tzinfo=timezone.utc),
            datetime(2026, 9, 26, 0, 1, tzinfo=timezone.utc),
            datetime(2026, 9, 26, 0, 2, tzinfo=timezone.utc),
        )
    )
    return InMemoryBroker(
        order_id_factory=lambda: next(identifiers),
        submitted_at_factory=lambda: next(timestamps),
    )


@pytest.mark.parametrize("side", [OrderSide.BUY, OrderSide.SELL])
def test_submit_returns_pending_order_and_preserves_intent(
    broker: Broker,
    side: OrderSide,
) -> None:
    intent = make_intent(side=side, quantity=Decimal("1.2500"))

    order = broker.submit(intent)

    assert order.status is OrderStatus.PENDING
    assert order.instrument == intent.instrument
    assert order.side is intent.side
    assert order.quantity == intent.quantity
    assert order.strategy_id == intent.strategy_id


def test_submissions_receive_different_deterministic_ids_and_times(
    broker: Broker,
) -> None:
    first = broker.submit(make_intent())
    second = broker.submit(make_intent(side=OrderSide.SELL))

    assert first.order_id == "order-1"
    assert second.order_id == "order-2"
    assert first.submitted_at == datetime(2026, 9, 26, tzinfo=timezone.utc)
    assert second.submitted_at == first.submitted_at + timedelta(minutes=1)


def test_get_order_returns_submitted_order_and_none_when_missing(
    broker: Broker,
) -> None:
    submitted = broker.submit(make_intent())

    assert broker.get_order(submitted.order_id) == submitted
    assert broker.get_order("missing-order") is None


def test_pending_orders_are_listed_as_open(broker: Broker) -> None:
    first = broker.submit(make_intent())
    second = broker.submit(make_intent(side=OrderSide.SELL))

    assert broker.list_open_orders() == (first, second)


def test_cancel_transitions_pending_order_and_removes_it_from_open_orders(
    broker: Broker,
) -> None:
    submitted = broker.submit(make_intent())

    canceled = broker.cancel_order(submitted.order_id)

    assert canceled.status is OrderStatus.CANCELED
    assert broker.get_order(submitted.order_id) == canceled
    assert broker.list_open_orders() == ()


def test_canceling_terminal_order_is_rejected(broker: Broker) -> None:
    submitted = broker.submit(make_intent())
    broker.cancel_order(submitted.order_id)

    with pytest.raises(ValueError, match="invalid order status transition"):
        broker.cancel_order(submitted.order_id)


def test_canceling_missing_order_is_rejected(broker: Broker) -> None:
    with pytest.raises(KeyError, match="order not found"):
        broker.cancel_order("missing-order")


def test_orders_for_multiple_instruments_remain_distinct(broker: Broker) -> None:
    btc = broker.submit(make_intent())
    eth = broker.submit(
        make_intent(instrument=Instrument("upbit", "KRW-ETH"))
    )

    assert broker.get_order(btc.order_id) == btc
    assert broker.get_order(eth.order_id) == eth
    assert tuple(order.instrument for order in broker.list_open_orders()) == (
        Instrument("upbit", "KRW-BTC"),
        Instrument("upbit", "KRW-ETH"),
    )


def test_duplicate_generated_order_id_is_rejected() -> None:
    broker = InMemoryBroker(
        order_id_factory=lambda: "same-order-id",
        submitted_at_factory=lambda: datetime(
            2026, 9, 26, tzinfo=timezone.utc
        ),
    )
    broker.submit(make_intent())

    with pytest.raises(ValueError, match="duplicate order_id"):
        broker.submit(make_intent(side=OrderSide.SELL))
