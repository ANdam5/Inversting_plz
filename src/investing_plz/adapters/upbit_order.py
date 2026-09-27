from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from investing_plz.domain import Instrument, Order, OrderSide, OrderStatus


_SIDES = frozenset(("bid", "ask"))
_ORDER_TYPES = frozenset(("limit", "price", "market", "best"))
_STATES = frozenset(("wait", "watch", "done", "cancel"))


class UpbitOrderValidationError(ValueError):
    """An Upbit order payload violates the expected response contract."""


class UpbitOrderConversionError(ValueError):
    """A valid Upbit order cannot be represented by the current domain Order."""


@dataclass(frozen=True, slots=True)
class UpbitOrderSnapshot:
    uuid: str
    market: str
    side: str
    order_type: str
    state: str
    created_at: datetime
    price: Decimal | None
    volume: Decimal | None
    remaining_volume: Decimal
    executed_volume: Decimal
    reserved_fee: Decimal
    remaining_fee: Decimal
    paid_fee: Decimal
    locked: Decimal
    trades_count: int
    identifier: str | None = None
    time_in_force: str | None = None

    def __post_init__(self) -> None:
        _nonempty_string(self.uuid, "uuid")
        _nonempty_string(self.market, "market")
        if self.side not in _SIDES:
            raise ValueError("side must be bid or ask")
        if self.order_type not in _ORDER_TYPES:
            raise ValueError("ord_type is not supported")
        if self.state not in _STATES:
            raise ValueError("state is not supported")
        if not isinstance(self.created_at, datetime) or self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        if self.created_at.utcoffset() is None:
            raise ValueError("created_at must have a UTC offset")

        for name in ("price", "volume"):
            value = getattr(self, name)
            if value is not None:
                _nonnegative_decimal(value, name)
                if value == 0:
                    raise ValueError(f"{name} must be greater than zero")
        for name in (
            "remaining_volume",
            "executed_volume",
            "reserved_fee",
            "remaining_fee",
            "paid_fee",
            "locked",
        ):
            _nonnegative_decimal(getattr(self, name), name)

        if type(self.trades_count) is not int or self.trades_count < 0:
            raise ValueError("trades_count must be a non-negative int")
        for name in ("identifier", "time_in_force"):
            value = getattr(self, name)
            if value is not None:
                _nonempty_string(value, name)

        if self.order_type == "limit" and (
            self.price is None or self.volume is None
        ):
            raise ValueError("limit order requires price and volume")
        if self.order_type == "price" and (
            self.side != "bid" or self.price is None or self.volume is not None
        ):
            raise ValueError("price order requires bid side, price, and null volume")
        if self.order_type == "market" and (
            self.side != "ask" or self.price is not None or self.volume is None
        ):
            raise ValueError("market order requires ask side, null price, and volume")
        if self.order_type == "best":
            valid_best_buy = (
                self.side == "bid" and self.price is not None and self.volume is None
            )
            valid_best_sell = (
                self.side == "ask" and self.price is None and self.volume is not None
            )
            if not valid_best_buy and not valid_best_sell:
                raise ValueError("best order price/volume does not match its side")


def upbit_order_response_to_snapshot(
    payload: Mapping[str, object],
) -> UpbitOrderSnapshot:
    """Parse one Upbit order response without inventing domain semantics."""

    if not isinstance(payload, Mapping):
        raise UpbitOrderValidationError("Upbit order response must be an object")
    try:
        created_at = datetime.fromisoformat(
            _nonempty_string(payload["created_at"], "created_at")
        )
        return UpbitOrderSnapshot(
            uuid=_nonempty_string(payload["uuid"], "uuid"),
            market=_nonempty_string(payload["market"], "market"),
            side=_nonempty_string(payload["side"], "side"),
            order_type=_nonempty_string(payload["ord_type"], "ord_type"),
            state=_nonempty_string(payload["state"], "state"),
            created_at=created_at,
            price=_optional_decimal_string(payload["price"], "price"),
            volume=_optional_decimal_string(payload["volume"], "volume"),
            remaining_volume=_decimal_string(
                payload["remaining_volume"], "remaining_volume"
            ),
            executed_volume=_decimal_string(
                payload["executed_volume"], "executed_volume"
            ),
            reserved_fee=_decimal_string(payload["reserved_fee"], "reserved_fee"),
            remaining_fee=_decimal_string(
                payload["remaining_fee"], "remaining_fee"
            ),
            paid_fee=_decimal_string(payload["paid_fee"], "paid_fee"),
            locked=_decimal_string(payload["locked"], "locked"),
            trades_count=_trades_count(payload["trades_count"]),
            identifier=_optional_string(payload.get("identifier"), "identifier"),
            time_in_force=_optional_string(
                payload.get("time_in_force"), "time_in_force"
            ),
        )
    except (KeyError, TypeError, ValueError, InvalidOperation) as error:
        raise UpbitOrderValidationError(f"invalid Upbit order: {error}") from error


def upbit_order_snapshot_to_order(
    snapshot: UpbitOrderSnapshot,
    *,
    strategy_id: str,
) -> Order:
    """Convert only snapshots with an exact original base-asset quantity."""

    if not isinstance(snapshot, UpbitOrderSnapshot):
        raise TypeError("snapshot must be an UpbitOrderSnapshot")
    if not isinstance(strategy_id, str) or not strategy_id.strip():
        raise UpbitOrderConversionError("strategy_id must not be empty")
    if snapshot.order_type == "price":
        raise UpbitOrderConversionError(
            "market buy has no exact original base-asset order quantity"
        )
    if snapshot.order_type == "best" and snapshot.side == "bid":
        raise UpbitOrderConversionError(
            "best buy has no exact original base-asset order quantity"
        )
    if snapshot.volume is None:
        raise UpbitOrderConversionError("order has no original base-asset volume")

    return Order(
        order_id=snapshot.uuid,
        instrument=Instrument("upbit", snapshot.market),
        side=OrderSide.BUY if snapshot.side == "bid" else OrderSide.SELL,
        quantity=snapshot.volume,
        strategy_id=strategy_id,
        submitted_at=snapshot.created_at.astimezone(timezone.utc),
        status={
            "wait": OrderStatus.PENDING,
            "watch": OrderStatus.PENDING,
            "done": OrderStatus.FILLED,
            "cancel": OrderStatus.CANCELED,
        }[snapshot.state],
    )


def _decimal_string(value: object, field: str) -> Decimal:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    if not value or value != value.strip():
        raise ValueError(f"{field} must be a non-empty unpadded string")
    result = Decimal(value)
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def _optional_decimal_string(value: object, field: str) -> Decimal | None:
    return None if value is None else _decimal_string(value, field)


def _nonempty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field} must be a non-empty unpadded string")
    return value


def _optional_string(value: object, field: str) -> str | None:
    return None if value is None else _nonempty_string(value, field)


def _trades_count(value: object) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("trades_count must be a non-negative int")
    return value


def _nonnegative_decimal(value: object, field: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field} must be a Decimal")
    if not value.is_finite():
        raise ValueError(f"{field} must be finite")
    if value < 0:
        raise ValueError(f"{field} must not be negative")
    return value
