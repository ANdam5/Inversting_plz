from datetime import datetime, timezone
from decimal import Decimal

import pytest

from investing_plz.broker import PaperBroker
from investing_plz.domain import Instrument, OrderIntent, OrderSide, OrderStatus


NOW = datetime(2026, 9, 26, tzinfo=timezone.utc)
BTC = Instrument("upbit", "KRW-BTC")
ETH = Instrument("upbit", "KRW-ETH")


def make_broker(
    *,
    initial_cash: object = Decimal("10000000"),
    fee_rate: object = Decimal("0.0005"),
    slippage_bps: object = Decimal("5"),
) -> PaperBroker:
    identifiers = iter(("order-1", "order-2", "order-3", "order-4"))
    return PaperBroker(
        initial_cash=initial_cash,
        fee_rate=fee_rate,
        slippage_bps=slippage_bps,
        order_id_factory=lambda: next(identifiers),
        submitted_at_factory=lambda: NOW,
    )


def submit(
    broker: PaperBroker,
    *,
    instrument: Instrument = BTC,
    side: OrderSide = OrderSide.BUY,
    quantity: Decimal = Decimal("0.01"),
):
    return broker.submit(
        OrderIntent(
            instrument=instrument,
            timestamp=NOW,
            strategy_id="moving_average_crossover",
            side=side,
            quantity=quantity,
        )
    )


def execute(
    broker: PaperBroker,
    order_id: str,
    *,
    fill_id: str = "fill-1",
    reference_price: object = Decimal("100000000"),
    filled_at: object = NOW,
):
    return broker.execute_order(
        order_id,
        reference_price=reference_price,
        fill_id=fill_id,
        filled_at=filled_at,
    )


def test_initial_cash_and_zero_positions() -> None:
    broker = make_broker()

    assert broker.cash == Decimal("10000000")
    assert broker.position_quantity(BTC) == Decimal("0")
    assert broker.position_quantity(ETH) == Decimal("0")


@pytest.mark.parametrize("value", [10000000.0, -1.0])
def test_initial_cash_rejects_float(value: float) -> None:
    with pytest.raises(TypeError, match="initial_cash must be a Decimal"):
        make_broker(initial_cash=value)


def test_negative_initial_cash_is_rejected() -> None:
    with pytest.raises(ValueError, match="initial_cash must not be negative"):
        make_broker(initial_cash=Decimal("-1"))


def test_buy_applies_slippage_fee_cash_and_position_atomically() -> None:
    broker = make_broker()
    order = submit(broker)

    fill = execute(broker, order.order_id)

    assert fill is not None
    assert fill.fill_price == Decimal("100050000.0000")
    assert fill.fee_amount == Decimal("500.250000000")
    assert broker.cash == Decimal("8998999.750000000")
    assert broker.position_quantity(BTC) == Decimal("0.01")
    assert broker.get_order(order.order_id).status is OrderStatus.FILLED
    assert broker.list_fills() == (fill,)


def test_sell_applies_slippage_fee_cash_and_position_atomically() -> None:
    broker = make_broker()
    buy = submit(broker)
    assert execute(broker, buy.order_id) is not None
    sell = submit(broker, side=OrderSide.SELL)

    fill = execute(
        broker,
        sell.order_id,
        fill_id="fill-2",
        reference_price=Decimal("110000000"),
    )

    assert fill is not None
    assert fill.fill_price == Decimal("109945000.0000")
    assert fill.fee_amount == Decimal("549.725000000")
    assert broker.cash == Decimal("10097900.025000000")
    assert broker.position_quantity(BTC) == Decimal("0.00")
    assert broker.get_order(sell.order_id).status is OrderStatus.FILLED


def test_zero_cost_execution_uses_reference_price() -> None:
    broker = make_broker(fee_rate=Decimal("0"), slippage_bps=Decimal("0"))
    order = submit(broker)

    fill = execute(broker, order.order_id)

    assert fill is not None
    assert fill.fill_price == Decimal("100000000")
    assert fill.fee_amount == Decimal("0")
    assert broker.cash == Decimal("9000000.00")


def test_insufficient_cash_rejects_order_without_fill_or_account_mutation() -> None:
    broker = make_broker(initial_cash=Decimal("100"))
    order = submit(broker)

    result = execute(broker, order.order_id)

    assert result is None
    assert broker.get_order(order.order_id).status is OrderStatus.REJECTED
    assert broker.list_fills() == ()
    assert broker.cash == Decimal("100")
    assert broker.position_quantity(BTC) == Decimal("0")


def test_oversell_rejects_order_without_fill_or_account_mutation() -> None:
    broker = make_broker()
    order = submit(broker, side=OrderSide.SELL)

    result = execute(broker, order.order_id)

    assert result is None
    assert broker.get_order(order.order_id).status is OrderStatus.REJECTED
    assert broker.list_fills() == ()
    assert broker.cash == Decimal("10000000")
    assert broker.position_quantity(BTC) == Decimal("0")


def test_positions_are_independent_across_instruments() -> None:
    broker = make_broker()
    btc = submit(broker, instrument=BTC, quantity=Decimal("0.01"))
    eth = submit(broker, instrument=ETH, quantity=Decimal("0.1"))

    assert execute(broker, btc.order_id) is not None
    assert execute(
        broker,
        eth.order_id,
        fill_id="fill-2",
        reference_price=Decimal("5000000"),
    ) is not None

    assert broker.position_quantity(BTC) == Decimal("0.01")
    assert broker.position_quantity(ETH) == Decimal("0.1")


def test_duplicate_or_terminal_execution_does_not_mutate_account() -> None:
    broker = make_broker()
    order = submit(broker)
    assert execute(broker, order.order_id) is not None
    cash = broker.cash
    position = broker.position_quantity(BTC)

    with pytest.raises(ValueError, match="duplicate fill_id"):
        execute(broker, order.order_id)
    with pytest.raises(ValueError, match="invalid order status transition"):
        execute(broker, order.order_id, fill_id="fill-2")

    assert broker.cash == cash
    assert broker.position_quantity(BTC) == position
    assert len(broker.list_fills()) == 1


def test_canceled_and_explicitly_rejected_orders_cannot_execute() -> None:
    broker = make_broker()
    canceled = submit(broker)
    rejected = submit(broker)
    broker.cancel_order(canceled.order_id)
    broker.reject_order(rejected.order_id)

    for sequence, order in enumerate((canceled, rejected), start=1):
        with pytest.raises(ValueError, match="invalid order status transition"):
            execute(broker, order.order_id, fill_id=f"fill-{sequence}")

    assert broker.cash == Decimal("10000000")
    assert broker.list_fills() == ()


@pytest.mark.parametrize(
    ("field", "value", "error", "message"),
    [
        ("reference_price", 100.0, TypeError, "reference_price must be a Decimal"),
        ("reference_price", Decimal("0"), ValueError, "reference_price must be greater"),
        ("filled_at", datetime(2026, 9, 26), ValueError, "timezone-aware"),
    ],
)
def test_invalid_execution_input_leaves_all_state_unchanged(
    field: str,
    value: object,
    error: type[Exception],
    message: str,
) -> None:
    broker = make_broker()
    order = submit(broker)

    with pytest.raises(error, match=message):
        execute(broker, order.order_id, **{field: value})

    assert broker.get_order(order.order_id) == order
    assert broker.cash == Decimal("10000000")
    assert broker.position_quantity(BTC) == Decimal("0")
    assert broker.list_fills() == ()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("fee_rate", 0.0005, "fee_rate must be a Decimal"),
        ("fee_rate", Decimal("-0.1"), "fee_rate"),
        ("fee_rate", Decimal("1"), "fee_rate"),
        ("slippage_bps", 5.0, "slippage_bps must be a Decimal"),
        ("slippage_bps", Decimal("-1"), "slippage_bps"),
        ("slippage_bps", Decimal("10000"), "slippage_bps"),
    ],
)
def test_invalid_cost_configuration_is_rejected(
    field: str,
    value: object,
    message: str,
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        make_broker(**{field: value})
