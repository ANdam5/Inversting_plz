from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from investing_plz.domain.decimal import require_decimal
from investing_plz.domain.instrument import Instrument
from investing_plz.domain.time import require_utc


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True, slots=True)
class OrderIntent:
    """A strategy's internal order candidate, not an order sent to a broker."""

    instrument: Instrument
    timestamp: datetime
    strategy_id: str
    side: OrderSide
    quantity: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, Instrument):
            raise TypeError("instrument must be an Instrument")
        require_utc(self.timestamp)
        if not self.strategy_id.strip():
            raise ValueError("strategy_id must not be empty")
        if not isinstance(self.side, OrderSide):
            raise TypeError("side must be an OrderSide")
        quantity = require_decimal(self.quantity, name="quantity")
        if quantity <= 0:
            raise ValueError("quantity must be greater than zero")

    def to_dict(self) -> dict[str, object]:
        return {
            "instrument": {
                "venue": self.instrument.venue,
                "symbol": self.instrument.symbol,
            },
            "timestamp": self.timestamp.isoformat(),
            "strategy_id": self.strategy_id,
            "side": self.side.value,
            "quantity": str(self.quantity),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "OrderIntent":
        instrument = payload.get("instrument")
        if not isinstance(instrument, dict):
            raise ValueError("instrument must be an object")
        quantity = payload.get("quantity")
        if not isinstance(quantity, str):
            raise TypeError("serialized quantity must be a string")
        return cls(
            instrument=Instrument(
                venue=str(instrument["venue"]),
                symbol=str(instrument["symbol"]),
            ),
            timestamp=datetime.fromisoformat(str(payload["timestamp"])),
            strategy_id=str(payload["strategy_id"]),
            side=OrderSide(str(payload["side"])),
            quantity=Decimal(quantity),
        )

