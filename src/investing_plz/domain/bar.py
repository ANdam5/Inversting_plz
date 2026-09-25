from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from investing_plz.domain.instrument import Instrument
from investing_plz.domain.time import require_utc


@dataclass(frozen=True, slots=True)
class Bar:
    """A completed OHLCV bar normalized to UTC."""

    instrument: Instrument
    interval: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    def __post_init__(self) -> None:
        if not self.interval.strip():
            raise ValueError("interval must not be empty")
        require_utc(self.timestamp)

        if min(self.open, self.high, self.low, self.close) < 0:
            raise ValueError("OHLC prices must not be negative")
        if self.volume < 0:
            raise ValueError("volume must not be negative")
        if self.high < max(self.open, self.close):
            raise ValueError("high must be at least open and close")
        if self.low > min(self.open, self.close):
            raise ValueError("low must be at most open and close")
        if self.high < self.low:
            raise ValueError("high must be at least low")

