import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from investing_plz.adapters.upbit_order import (
    UpbitOrderConversionError,
    UpbitOrderValidationError,
    upbit_order_response_to_snapshot,
    upbit_order_snapshot_to_order,
)
from investing_plz.domain import OrderSide, OrderStatus


FIXTURE = Path(__file__).parent / "fixtures" / "upbit_orders.json"
STRATEGY_ID = "moving_average_crossover"


def payload(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "uuid": "order-1",
        "side": "bid",
        "ord_type": "limit",
        "price": "100.0",
        "state": "wait",
        "market": "KRW-BTC",
        "created_at": "2026-09-27T09:30:00+09:00",
        "volume": "1.0",
        "remaining_volume": "1.0",
        "reserved_fee": "0.05",
        "remaining_fee": "0.05",
        "paid_fee": "0.0",
        "locked": "100.05",
        "executed_volume": "0.0",
        "trades_count": 0,
    }
    values.update(overrides)
    return values


def to_order(raw: dict[str, object]):
    return upbit_order_snapshot_to_order(
        upbit_order_response_to_snapshot(raw),
        strategy_id=STRATEGY_ID,
    )


def test_limit_buy_wait_maps_to_pending_buy_with_utc_time() -> None:
    order = to_order(payload())

    assert order.order_id == "order-1"
    assert order.instrument.symbol == "KRW-BTC"
    assert order.side is OrderSide.BUY
    assert order.status is OrderStatus.PENDING
    assert order.quantity == Decimal("1.0")
    assert order.submitted_at == datetime(2026, 9, 27, 0, 30, tzinfo=timezone.utc)


def test_limit_sell_done_maps_to_filled_sell() -> None:
    order = to_order(payload(side="ask", state="done", volume="0.5"))

    assert order.side is OrderSide.SELL
    assert order.status is OrderStatus.FILLED
    assert order.quantity == Decimal("0.5")


@pytest.mark.parametrize(
    ("state", "expected"),
    [("cancel", OrderStatus.CANCELED), ("watch", OrderStatus.PENDING)],
)
def test_cancel_and_watch_states_map_explicitly(
    state: str, expected: OrderStatus
) -> None:
    assert to_order(payload(state=state)).status is expected


def test_partial_fill_details_remain_in_snapshot_while_order_is_pending() -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))[2]

    snapshot = upbit_order_response_to_snapshot(raw)
    order = upbit_order_snapshot_to_order(snapshot, strategy_id=STRATEGY_ID)

    assert snapshot.volume == Decimal("1.0")
    assert snapshot.remaining_volume == Decimal("0.4")
    assert snapshot.executed_volume == Decimal("0.6")
    assert snapshot.trades_count == 2
    assert order.status is OrderStatus.PENDING
    assert order.quantity == Decimal("1.0")


def test_decimal_precision_is_preserved() -> None:
    snapshot = upbit_order_response_to_snapshot(
        payload(
            price="100.1234567890123456789",
            volume="0.1234567890123456789",
            remaining_volume="0.1234567890123456789",
        )
    )

    assert snapshot.price == Decimal("100.1234567890123456789")
    assert snapshot.volume == Decimal("0.1234567890123456789")


@pytest.mark.parametrize(
    "field",
    [
        "price",
        "volume",
        "remaining_volume",
        "reserved_fee",
        "remaining_fee",
        "paid_fee",
        "locked",
        "executed_volume",
    ],
)
def test_float_financial_values_are_rejected(field: str) -> None:
    with pytest.raises(UpbitOrderValidationError):
        upbit_order_response_to_snapshot(payload(**{field: 0.1}))


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_financial_values_are_rejected(value: str) -> None:
    with pytest.raises(UpbitOrderValidationError):
        upbit_order_response_to_snapshot(payload(locked=value))


@pytest.mark.parametrize(
    "field",
    [
        "price",
        "volume",
        "remaining_volume",
        "reserved_fee",
        "remaining_fee",
        "paid_fee",
        "locked",
        "executed_volume",
    ],
)
def test_negative_financial_values_are_rejected(field: str) -> None:
    with pytest.raises(UpbitOrderValidationError):
        upbit_order_response_to_snapshot(payload(**{field: "-0.1"}))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("side", "buy"),
        ("state", "rejected"),
        ("ord_type", "stop"),
        ("created_at", "not-a-time"),
        ("trades_count", -1),
        ("trades_count", True),
    ],
)
def test_malformed_enum_time_and_count_fields_are_rejected(
    field: str, value: object
) -> None:
    with pytest.raises(UpbitOrderValidationError):
        upbit_order_response_to_snapshot(payload(**{field: value}))


def test_missing_required_field_is_rejected() -> None:
    raw = payload()
    del raw["uuid"]

    with pytest.raises(UpbitOrderValidationError):
        upbit_order_response_to_snapshot(raw)


def test_optional_strings_allow_absence_or_null_but_reject_empty_values() -> None:
    snapshot = upbit_order_response_to_snapshot(
        payload(identifier=None, time_in_force=None)
    )

    assert snapshot.identifier is None
    assert snapshot.time_in_force is None
    with pytest.raises(UpbitOrderValidationError):
        upbit_order_response_to_snapshot(payload(identifier=""))


def test_market_buy_snapshot_parses_but_cannot_be_misrepresented_as_order() -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))[3]

    snapshot = upbit_order_response_to_snapshot(raw)

    assert snapshot.order_type == "price"
    assert snapshot.price == Decimal("100000.0")
    assert snapshot.volume is None
    with pytest.raises(UpbitOrderConversionError, match="market buy"):
        upbit_order_snapshot_to_order(snapshot, strategy_id=STRATEGY_ID)


def test_market_sell_volume_can_map_to_order_quantity() -> None:
    order = to_order(
        payload(side="ask", ord_type="market", price=None, volume="0.25")
    )

    assert order.side is OrderSide.SELL
    assert order.quantity == Decimal("0.25")
