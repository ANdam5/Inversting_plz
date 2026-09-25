import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from investing_plz.domain import Instrument, OrderIntent, OrderSide


def make_intent(**overrides: object) -> OrderIntent:
    values: dict[str, object] = {
        "instrument": Instrument("upbit", "KRW-BTC"),
        "timestamp": datetime(2026, 9, 25, tzinfo=timezone.utc),
        "strategy_id": "moving_average_crossover",
        "side": OrderSide.BUY,
        "quantity": Decimal("0.01"),
    }
    values.update(overrides)
    return OrderIntent(**values)


@pytest.mark.parametrize("side", [OrderSide.BUY, OrderSide.SELL])
def test_creates_buy_and_sell_intents_with_decimal_quantity(side: OrderSide) -> None:
    intent = make_intent(side=side)

    assert intent.side is side
    assert intent.quantity == Decimal("0.01")


def test_rejects_float_quantity() -> None:
    with pytest.raises(TypeError, match="quantity must be a Decimal"):
        make_intent(quantity=0.01)


@pytest.mark.parametrize("quantity", [Decimal("0"), Decimal("-0.01")])
def test_rejects_non_positive_quantity(quantity: Decimal) -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        make_intent(quantity=quantity)


def test_rejects_missing_instrument() -> None:
    with pytest.raises(TypeError, match="Instrument"):
        make_intent(instrument=None)


def test_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        make_intent(timestamp=datetime(2026, 9, 25))


def test_rejects_empty_strategy_id() -> None:
    with pytest.raises(ValueError, match="strategy_id"):
        make_intent(strategy_id="   ")


def test_json_serialization_round_trip_preserves_order_intent() -> None:
    original = make_intent(side=OrderSide.SELL, quantity=Decimal("1.2500"))

    serialized = json.loads(json.dumps(original.to_dict()))
    restored = OrderIntent.from_dict(serialized)

    assert restored == original
    assert serialized["quantity"] == "1.2500"


def test_serialized_float_quantity_is_rejected() -> None:
    payload = make_intent().to_dict()
    payload["quantity"] = 0.01

    with pytest.raises(TypeError, match="serialized quantity must be a string"):
        OrderIntent.from_dict(payload)

